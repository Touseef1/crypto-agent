"""Step 3B: isolated volatility feature ablation, offline research only.

Uses the same 1m labels, splits, LightGBM settings and cost assumptions
as Step 3A; compares baseline and baseline + volatility on identical rows.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ml.phase1 import FEATURE_COLUMNS, STEP, continuous_segments, load_mysql, validate
from ml.phase2 import partitions
from ml.step3_trend import COSTS, evaluate

VOL_COLUMNS = [
    "atr_pct_percentile_288", "bb_width20", "realized_vol_ratio_12_48",
    "volatility_change_12", "range_percentile_288",
]


def _past_percentile(values, window, min_periods):
    """Percentile rank of current observation among current and earlier bars."""
    return values.rolling(window, min_periods=min_periods).apply(
        lambda a: float(np.mean(a <= a[-1])), raw=True
    )


def volatility_features(frame):
    """All calculations use candles known at the current 5m close."""
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    prev = close.shift()
    ret = close.pct_change()
    tr = pd.concat([high-low, (high-prev).abs(), (low-prev).abs()], axis=1).max(axis=1)
    atr_pct = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean() / close
    middle = close.rolling(20, min_periods=20).mean()
    sd20 = close.rolling(20, min_periods=20).std()
    v12 = ret.rolling(12, min_periods=12).std()
    v48 = ret.rolling(48, min_periods=48).std()
    candle_range = (high-low) / close
    return pd.DataFrame({
        "atr_pct_percentile_288": _past_percentile(atr_pct, 288, 288),
        "bb_width20": 4*sd20/middle.replace(0, np.nan),
        "realized_vol_ratio_12_48": v12/v48.replace(0, np.nan),
        "volatility_change_12": v12/v12.shift(12).replace(0, np.nan)-1,
        "range_percentile_288": _past_percentile(candle_range, 288, 288),
    }, index=frame.index)


def build_volatility(frame):
    validate(frame)
    result = pd.concat([volatility_features(s) for s in continuous_segments(frame)])
    if result.index.has_duplicates:
        raise ValueError("Duplicate 5m timestamps")
    return result.replace([np.inf, -np.inf], np.nan)


def prepare(labels, features):
    required = ["decision_candle_open_utc", "exit_candle_open_utc", "side", "outcome", "gross_return"] + FEATURE_COLUMNS
    absent = set(required)-set(labels.columns)
    if absent:
        raise ValueError("Missing columns: "+str(sorted(absent)))
    if labels.duplicated(["decision_candle_open_utc", "side"]).any():
        raise ValueError("Duplicate trade keys")
    if not labels["decision_candle_open_utc"].is_monotonic_increasing:
        raise ValueError("Decisions must be chronological")
    df = labels.copy()
    df["decision"] = pd.to_datetime(df["decision_candle_open_utc"], utc=True, errors="raise")
    df["exit"] = pd.to_datetime(df["exit_candle_open_utc"], utc=True, errors="raise")
    if df[["decision", "exit"]].isna().any().any() or (df["exit"] <= df["decision"]).any():
        raise ValueError("Invalid event timestamps")
    if not df["side"].isin([-1, 1]).all() or not df["outcome"].isin([-1, 0, 1]).all():
        raise ValueError("Invalid side or outcome")
    joined = df.join(features, on="decision", how="left", validate="many_to_one")
    joined = joined.replace([np.inf, -np.inf], np.nan)
    missing = int(joined[VOL_COLUMNS].isna().any(axis=1).sum())
    joined = joined.dropna(subset=FEATURE_COLUMNS+VOL_COLUMNS+["gross_return"])
    if joined.empty:
        raise ValueError("No complete rows after volatility warm-up")
    return joined, missing


def run(df, seed=42):
    results = []
    for fold, frac in enumerate((.45, .55, .65), 1):
        record = {"fold": fold, "train_fraction": frac, "sides": {}}
        for side, name in ((1, "long"), (-1, "short")):
            subset = df.loc[df["side"] == side]
            train, cal, test = partitions(subset, frac, .08, .08, embargo_bars=24)
            if test["decision"].max() >= subset["decision"].iloc[int(len(subset)*.82)]:
                raise ValueError("Evaluation enters reserved holdout")
            baseline = evaluate(train, test, FEATURE_COLUMNS, seed)
            enhanced = evaluate(train, test, FEATURE_COLUMNS+VOL_COLUMNS, seed)
            record["sides"][name] = {
                "train_n": int(len(train)), "unused_cal_n": int(len(cal)),
                "test_start": test["decision"].min().isoformat(),
                "test_end": test["decision"].max().isoformat(),
                "baseline": baseline, "with_volatility": enhanced,
                "delta_auc": round(enhanced["auc"]-baseline["auc"], 6),
                "delta_top_decile_net_primary_pct": round(
                    enhanced["top_decile_mean_net_pct"]["primary"]
                    - baseline["top_decile_mean_net_pct"]["primary"], 6),
            }
        results.append(record)
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", choices=["BTCUSDT", "ETHUSDT"], required=True)
    p.add_argument("--data-dir", default="ml/data/step2")
    p.add_argument("--output-dir", default="ml/artifacts/step3")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    source = Path(args.data_dir)/f"{args.symbol.lower()}_1m_first_hit_h24_tp2_sl1.5.csv"
    columns = ["decision_candle_open_utc", "exit_candle_open_utc", "side", "outcome", "gross_return"]+FEATURE_COLUMNS
    labels = pd.read_csv(source, usecols=columns)
    candles = load_mysql(args.symbol)
    candles = candles.loc[candles.index+STEP <= pd.Timestamp.now(tz="UTC")]
    df, missing = prepare(labels, build_volatility(candles))
    folds = run(df, args.seed)
    report = {
        "symbol": args.symbol, "experiment": "baseline vs volatility features",
        "baseline_features": FEATURE_COLUMNS, "added_features": VOL_COLUMNS,
        "source_rows": int(len(labels)), "eligible_rows": int(len(df)),
        "missing_volatility_rows": missing,
        "costs_pct": {k: v*100 for k, v in COSTS.items()},
        "notes": [
            "Only closed 5m candles used; all indicators are backward-looking.",
            "288-bar rolling percentiles use the current and preceding 287 candles.",
            "Features restart at historical data gaps.",
            "Both models use the same eligible examples, splits, hyperparameters and seed.",
            "Final approximately 19% of decisions is reserved, not evaluated.",
            "Top 10% is ranked within each test fold: diagnostic, not a live trading threshold.",
            "Returns are per overlapping hypothetical opportunity, not portfolio performance.",
            "Constant round-trip cost ignores funding, market impact and fill uncertainty.",
            "No live orders, model deployment, or database writes.",
        ], "folds": folds,
    }
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    target = output/f"{args.symbol.lower()}_volatility.json"
    target.write_text(json.dumps(report, indent=2)+"\n")
    for fold in folds:
        for name, item in fold["sides"].items():
            b, v = item["baseline"], item["with_volatility"]
            print(f"Fold {fold['fold']} {name}: AUC baseline={b['auc']:.4f}, volatility={v['auc']:.4f}, "
                  f"delta={item['delta_auc']:+.4f}; "
                  f"top-10% net baseline={b['top_decile_mean_net_pct']['primary']:+.4f}%, "
                  f"volatility={v['top_decile_mean_net_pct']['primary']:+.4f}%, "
                  f"delta={item['delta_top_decile_net_primary_pct']:+.4f} pp", flush=True)
    print("Saved:", target)


if __name__ == "__main__":
    main()
