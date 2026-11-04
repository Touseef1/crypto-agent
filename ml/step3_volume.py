"""Step 3C: isolated volume-proxy feature ablation, offline research only.

Uses the same 1m labels, splits, LightGBM settings and cost assumptions
as Step 3A; compares baseline and baseline + volume proxies on identical rows.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ml.phase1 import FEATURE_COLUMNS, STEP, continuous_segments, load_mysql, validate
from ml.phase2 import partitions
from ml.step3_trend import COSTS, evaluate

VOLUME_COLUMNS = [
    "relative_volume_48", "volume_zscore_48", "signed_volume_imbalance_12",
    "money_flow_ratio_20", "volume_price_corr_48",
]


def volume_features(frame):
    """OHLCV-only proxies; NOT exchange aggressor-side or order-book flow.

    All windows include current fully closed 5m candle and past candles only.
    """
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    volume = frame["volume"].astype(float)
    vmean = volume.rolling(48, min_periods=48).mean()
    vstd = volume.rolling(48, min_periods=48).std()
    price_change = close.diff()
    signed = np.sign(price_change).fillna(0.0)*volume
    v12 = volume.rolling(12, min_periods=12).sum()
    spread = (high-low).replace(0, np.nan)
    close_location = ((2*close-high-low)/spread).clip(-1, 1).fillna(0.0)
    money_flow = close_location*volume
    v20 = volume.rolling(20, min_periods=20).sum()
    returns = close.pct_change()
    return pd.DataFrame({
        "relative_volume_48": volume/vmean.replace(0, np.nan),
        "volume_zscore_48": (volume-vmean)/vstd.replace(0, np.nan),
        "signed_volume_imbalance_12": signed.rolling(12, min_periods=12).sum()/v12.replace(0, np.nan),
        "money_flow_ratio_20": money_flow.rolling(20, min_periods=20).sum()/v20.replace(0, np.nan),
        "volume_price_corr_48": volume.rolling(48, min_periods=48).corr(returns),
    }, index=frame.index)


def build_volume(frame):
    validate(frame)
    result = pd.concat([volume_features(s) for s in continuous_segments(frame)])
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
    missing = int(joined[VOLUME_COLUMNS].isna().any(axis=1).sum())
    joined = joined.dropna(subset=FEATURE_COLUMNS+VOLUME_COLUMNS+["gross_return"])
    if joined.empty:
        raise ValueError("No complete rows after volume warm-up")
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
            enhanced = evaluate(train, test, FEATURE_COLUMNS+VOLUME_COLUMNS, seed)
            record["sides"][name] = {
                "train_n": int(len(train)), "unused_cal_n": int(len(cal)),
                "test_start": test["decision"].min().isoformat(),
                "test_end": test["decision"].max().isoformat(),
                "baseline": baseline, "with_volume": enhanced,
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
    df, missing = prepare(labels, build_volume(candles))
    folds = run(df, args.seed)
    report = {
        "symbol": args.symbol, "experiment": "baseline vs volume proxy features",
        "baseline_features": FEATURE_COLUMNS, "added_features": VOLUME_COLUMNS,
        "source_rows": int(len(labels)), "eligible_rows": int(len(df)),
        "missing_volume_rows": missing,
        "costs_pct": {k: v*100 for k, v in COSTS.items()},
        "notes": [
            "Only closed 5m candles used; all indicators are backward-looking.",
            "Volume proxies use only OHLCV; no true order-flow or taker-side data.",
            "Features restart at historical data gaps; zero-volume/constant-volume windows may be excluded.",
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
    target = output/f"{args.symbol.lower()}_volume.json"
    target.write_text(json.dumps(report, indent=2)+"\n")
    for fold in folds:
        for name, item in fold["sides"].items():
            b, v = item["baseline"], item["with_volume"]
            print(f"Fold {fold['fold']} {name}: AUC baseline={b['auc']:.4f}, volume={v['auc']:.4f}, "
                  f"delta={item['delta_auc']:+.4f}; "
                  f"top-10% net baseline={b['top_decile_mean_net_pct']['primary']:+.4f}%, "
                  f"volume={v['top_decile_mean_net_pct']['primary']:+.4f}%, "
                  f"delta={item['delta_top_decile_net_primary_pct']:+.4f} pp", flush=True)
    print("Saved:", target)


if __name__ == "__main__":
    main()
