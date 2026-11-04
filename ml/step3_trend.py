"""Step 3A: isolated trend-strength feature-group experiment (offline only).

Compares the existing 21-feature baseline with baseline + trend-strength group
on the SAME 1m first-hit labels. Final 20% of time is untouched. No orders.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import roc_auc_score, brier_score_loss

from ml.phase1 import FEATURE_COLUMNS, STEP, continuous_segments, load_mysql, validate
from ml.phase2 import partitions

TREND_COLUMNS = ["adx14", "ema20_slope_6", "ema50_slope_12", "ema200_gap", "ema20_50_spread_atr"]
COSTS = {"primary": 0.003, "lower": 0.0014}


def trend_features(frame):
    """Causal Wilder-style ADX and EMA features; each segment starts cold."""
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    prev_close = close.shift()
    up = high.diff()
    down = -low.diff()
    plus = up.where((up > down) & (up > 0), 0.0)
    minus = down.where((down > up) & (down > 0), 0.0)
    tr = pd.concat([high-low, (high-prev_close).abs(), (low-prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    plus_di = 100 * plus.ewm(alpha=1/14, adjust=False, min_periods=14).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus.ewm(alpha=1/14, adjust=False, min_periods=14).mean() / atr.replace(0, np.nan)
    dx = 100 * (plus_di-minus_di).abs() / (plus_di+minus_di).replace(0, np.nan)
    e20 = close.ewm(span=20, adjust=False, min_periods=20).mean()
    e50 = close.ewm(span=50, adjust=False, min_periods=50).mean()
    e200 = close.ewm(span=200, adjust=False, min_periods=200).mean()
    return pd.DataFrame({
        "adx14": dx.ewm(alpha=1/14, adjust=False, min_periods=14).mean(),
        "ema20_slope_6": e20 / e20.shift(6) - 1,
        "ema50_slope_12": e50 / e50.shift(12) - 1,
        "ema200_gap": close / e200 - 1,
        "ema20_50_spread_atr": (e20-e50) / atr.replace(0, np.nan),
    }, index=frame.index)


def build_trend(frame):
    validate(frame)
    pieces = [trend_features(s) for s in continuous_segments(frame)]
    result = pd.concat(pieces).replace([np.inf, -np.inf], np.nan)
    if result.index.has_duplicates:
        raise ValueError("Duplicate trend timestamps")
    return result


def prepare(labels, trend):
    if labels.duplicated(["decision_candle_open_utc", "side"]).any():
        raise ValueError("Duplicate label keys")
    if not labels["decision_candle_open_utc"].is_monotonic_increasing:
        raise ValueError("Labels must be chronological")
    labels = labels.copy()
    labels["decision"] = pd.to_datetime(labels["decision_candle_open_utc"], utc=True)
    labels["exit"] = pd.to_datetime(labels["exit_candle_open_utc"], utc=True)
    if labels["decision"].isna().any() or labels["exit"].isna().any():
        raise ValueError("Invalid label times")
    if (labels["exit"] <= labels["decision"]).any():
        raise ValueError("Invalid event times")
    if not labels["side"].isin([-1, 1]).all() or not labels["outcome"].isin([-1, 0, 1]).all():
        raise ValueError("Invalid label values")
    if not np.isfinite(labels["gross_return"].to_numpy(dtype=float)).all():
        raise ValueError("Nonfinite returns")
    # Exact 5m open-time match; no asof that could silently cross a gap.
    merged = labels.join(trend, on="decision", how="left", validate="many_to_one")
    missing = int(merged[TREND_COLUMNS].isna().any(axis=1).sum())
    merged = merged.replace([np.inf, -np.inf], np.nan).dropna(subset=FEATURE_COLUMNS+TREND_COLUMNS)
    if merged.empty:
        raise ValueError("No complete rows after trend warm-up")
    return merged, missing


def model(seed):
    return LGBMClassifier(
        n_estimators=250, learning_rate=.04, num_leaves=15, max_depth=6,
        min_child_samples=100, colsample_bytree=.8, subsample=.8,
        subsample_freq=1, reg_lambda=2, random_state=seed, n_jobs=4,
        verbosity=-1,
    )


def evaluate(train, test, columns, seed):
    y_train = (train["outcome"] == 1).astype(int)
    y_test = (test["outcome"] == 1).astype(int)
    if y_train.nunique() != 2 or y_test.nunique() != 2:
        raise ValueError("Both classes required in train/test")
    clf = model(seed)
    clf.fit(train[columns], y_train)
    prob = clf.predict_proba(test[columns])[:, 1]
    gross = test["gross_return"].to_numpy(dtype=float)
    # Ranking diagnostic: top decile is chosen using test predictions; no
    # deployable probability threshold, portfolio simulation or calibrated EV.
    k = max(1, int(np.ceil(len(prob)*.1)))
    selected = np.argsort(-prob, kind="stable")[:k]
    return {
        "auc": round(float(roc_auc_score(y_test, prob)), 6),
        "brier_uncalibrated": round(float(brier_score_loss(y_test, prob)), 6),
        "test_examples": int(len(test)),
        "top_decile_n": int(k),
        "top_decile_tp_rate": round(float(y_test.iloc[selected].mean()), 6),
        "top_decile_mean_gross_pct": round(float(gross[selected].mean()*100), 6),
        "top_decile_mean_net_pct": {
            name: round(float((gross[selected]-cost).mean()*100), 6)
            for name, cost in COSTS.items()
        },
    }


def run(df, seed=42):
    result = []
    for fold, frac in enumerate((.45, .55, .65), 1):
        record = {"fold": fold, "train_fraction": frac, "sides": {}}
        for side, name in ((1, "long"), (-1, "short")):
            subset = df.loc[df["side"] == side]
            # Calibration partition is intentionally unused by both models;
            # retained as a temporal gap to ensure identical comparisons.
            train, cal, test = partitions(subset, frac, .08, .08, embargo_bars=24)
            # Last 20% is reserved; fold 3 test ends at 81% with rounding.
            if test["decision"].max() >= subset["decision"].iloc[int(len(subset)*.82)]:
                raise ValueError("Evaluation extends into reserved holdout")
            baseline = evaluate(train, test, FEATURE_COLUMNS, seed)
            extended = evaluate(train, test, FEATURE_COLUMNS+TREND_COLUMNS, seed)
            record["sides"][name] = {
                "train_n": len(train), "unused_cal_n": len(cal),
                "test_start": test["decision"].min().isoformat(),
                "test_end": test["decision"].max().isoformat(),
                "baseline": baseline, "with_trend": extended,
                "delta_auc": round(extended["auc"]-baseline["auc"], 6),
                "delta_top_decile_net_primary_pct": round(
                    extended["top_decile_mean_net_pct"]["primary"]
                    - baseline["top_decile_mean_net_pct"]["primary"], 6),
            }
        result.append(record)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", choices=["BTCUSDT", "ETHUSDT"], required=True)
    p.add_argument("--data-dir", default="ml/data/step2")
    p.add_argument("--output-dir", default="ml/artifacts/step3")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    path = Path(args.data_dir) / f"{args.symbol.lower()}_1m_first_hit_h24_tp2_sl1.5.csv"
    needed = ["decision_candle_open_utc", "exit_candle_open_utc", "side", "outcome", "gross_return"] + FEATURE_COLUMNS
    labels = pd.read_csv(path, usecols=needed)
    frame = load_mysql(args.symbol)
    frame = frame.loc[frame.index+STEP <= pd.Timestamp.now(tz="UTC")]
    trend = build_trend(frame)
    data, missing = prepare(labels, trend)
    folds = run(data, args.seed)
    report = {
        "symbol": args.symbol, "experiment": "baseline vs trend-strength features",
        "base_features": FEATURE_COLUMNS, "new_features": TREND_COLUMNS,
        "source_rows": len(labels), "eligible_rows": len(data), "missing_trend_rows": missing,
        "costs_pct": {k: v*100 for k, v in COSTS.items()},
        "notes": [
            "No labels, targets, or features use future market data.",
            "Trend indicators reset at every 5m data gap; 200-bar EMA warm-up excluded.",
            "Both models use identical samples, splits, seeds and hyperparameters.",
            "Last approximately 19% of decisions are never evaluated in these folds.",
            "Uncalibrated AUC/Brier and top-10%-ranked hypothetical returns are exploratory.",
            "Top-decile selection uses test-set rank and is not an executable threshold.",
            "Overlapping events, fees, slippage, funding, and position constraints need further evaluation.",
            "No live trading, database writes or model deployment.",
        ], "folds": folds,
    }
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{args.symbol.lower()}_trend_strength.json"
    target.write_text(json.dumps(report, indent=2)+"\n")
    for fold in folds:
        for name, item in fold["sides"].items():
            print(f"Fold {fold['fold']} {name}: baseline AUC={item['baseline']['auc']:.4f}; "
                  f"trend AUC={item['with_trend']['auc']:.4f}; "
                  f"delta={item['delta_auc']:+.4f}; "
                  f"trend top-10% net={item['with_trend']['top_decile_mean_net_pct']['primary']:+.4f}%")
    print("Saved:", target)


if __name__ == "__main__":
    main()
