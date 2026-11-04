"""Step 4C: execution-cost robustness of Step 4B regression filters.

For each cost, select threshold on calibration only; freeze before test.
Also stress-test the *same* selected trades at higher realized costs.
One-side-at-a-time research; not a portfolio backtest or live strategy.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ml.phase1 import FEATURE_COLUMNS, STEP, load_mysql
from ml.phase2 import partitions
from ml.step3_volume import VOLUME_COLUMNS, build_volume, prepare
from ml.step4_cost_filter import performance, select_threshold, sequential_trades, train_predict

COST_GRID = (0.0010, 0.0014, 0.0018, 0.0022, 0.0030, 0.0040)
STRESS_ADD = (0.0005, 0.0010)
MIN_TEST_TRADES = 30


def selected_stats(frame, indices, cost):
    """Evaluate an unchanged selection at a different realized cost."""
    gross = frame["gross_return"].to_numpy(dtype=float)[indices]
    net = gross-cost
    if not len(indices):
        return {"trades": 0, "mean_net_pct": None,
                "total_net_pct_fixed_notional": 0.0,
                "max_drawdown_pct_fixed_notional": 0.0, "win_rate": None}
    curve = np.r_[0.0, np.cumsum(net)]
    dd = np.maximum.accumulate(curve)-curve
    return {"trades": int(len(indices)),
            "mean_net_pct": round(float(net.mean()*100), 6),
            "total_net_pct_fixed_notional": round(float(net.sum()*100), 6),
            "max_drawdown_pct_fixed_notional": round(float(dd.max()*100), 6),
            "win_rate": round(float(np.mean(net>0)), 6)}


def calibration_diagnostics(cal, predictions):
    actual = cal["gross_return"].to_numpy(dtype=float)
    if not len(actual):
        raise ValueError("Empty calibration set")
    errors = predictions-actual
    return {"cal_n": int(len(actual)),
            "mean_predicted_gross_pct": round(float(predictions.mean()*100), 6),
            "mean_realized_gross_pct": round(float(actual.mean()*100), 6),
            "mean_prediction_bias_pct": round(float(errors.mean()*100), 6),
            "mae_pct": round(float(np.abs(errors).mean()*100), 6)}


def evaluate_cost(cal, test, cal_scores, test_scores, cost):
    threshold, candidates = select_threshold(cal, cal_scores, cost)
    if threshold is None:
        return {"threshold_pct": None, "calibration_candidates": candidates,
                "test": selected_stats(test, np.array([], dtype=int), cost),
                "stress": {}, "passes_30_test_trades": False,
                "note": "No calibration threshold passed; abstain"}
    indices = sequential_trades(test, test_scores, threshold)
    test_stats = selected_stats(test, indices, cost)
    stress = {f"plus_{int(round(extra*10000))}bp":
              selected_stats(test, indices, cost+extra)
              for extra in STRESS_ADD}
    return {"threshold_pct": round(threshold*100, 6),
            "calibration_candidates": candidates,
            "test": test_stats, "stress": stress,
            "passes_30_test_trades": bool(len(indices)>=MIN_TEST_TRADES),
            "note": "Small test sample: not robust" if len(indices)<MIN_TEST_TRADES else None}


def run(df, seed=42):
    folds = []
    for fold, frac in enumerate((.45, .55, .65), 1):
        record = {"fold": fold, "train_fraction": frac, "sides": {}}
        for side, side_name in ((1, "long"), (-1, "short")):
            subset = df.loc[df["side"]==side]
            train, cal, test = partitions(subset, frac, .08, .08, embargo_bars=24)
            if test["decision"].max() >= subset["decision"].iloc[int(len(subset)*.82)]:
                raise ValueError("Reserved holdout would be evaluated")
            item = {"train_n": int(len(train)), "cal_n": int(len(cal)),
                    "test_n": int(len(test)),
                    "test_start": test["decision"].min().isoformat(),
                    "test_end": test["decision"].max().isoformat(),
                    "features": {}}
            for group, columns in (("baseline21", FEATURE_COLUMNS),
                                   ("plus_volume", FEATURE_COLUMNS+VOLUME_COLUMNS)):
                cal_scores, test_scores = train_predict(train, cal, test, columns, seed)
                item["features"][group] = {
                    "calibration_prediction_diagnostics": calibration_diagnostics(cal, cal_scores),
                    "costs": {f"{cost*100:.2f}pct": evaluate_cost(
                        cal, test, cal_scores, test_scores, cost) for cost in COST_GRID}
                }
            record["sides"][side_name] = item
        folds.append(record)
    return folds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", choices=["BTCUSDT", "ETHUSDT"], required=True)
    parser.add_argument("--data-dir", default="ml/data/step2")
    parser.add_argument("--output-dir", default="ml/artifacts/step4")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    source = Path(args.data_dir)/f"{args.symbol.lower()}_1m_first_hit_h24_tp2_sl1.5.csv"
    needed = ["decision_candle_open_utc", "exit_candle_open_utc",
              "side", "outcome", "gross_return"]+FEATURE_COLUMNS
    labels = pd.read_csv(source, usecols=needed)
    candles = load_mysql(args.symbol)
    candles = candles.loc[candles.index+STEP <= pd.Timestamp.now(tz="UTC")]
    data, missing = prepare(labels, build_volume(candles))
    folds = run(data, args.seed)
    report = {
        "symbol": args.symbol, "experiment": "Step 4C execution cost sensitivity",
        "source_rows": int(len(labels)), "eligible_rows": int(len(data)),
        "missing_volume_rows": missing,
        "cost_grid_pct": [v*100 for v in COST_GRID],
        "stress_additional_pct": [v*100 for v in STRESS_ADD],
        "minimum_test_trades_for_flag": MIN_TEST_TRADES,
        "notes": [
            "Cost grid is hypothetical, NOT verified Binance fees.",
            "Each cost has its own threshold selected using calibration data only.",
            "Stress adds cost to unchanged test selections; it does not retune thresholds.",
            "Tests do not use the reserved final ~19% holdout.",
            "Long and short are separate; results cannot be combined as a portfolio.",
            "Fixed-notional additive P/L, not $1000 equity drawdown.",
            "No model deployment, exchange orders or database writes.",
        ], "folds": folds}
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out/f"{args.symbol.lower()}_cost_sensitivity.json"
    target.write_text(json.dumps(report, indent=2)+"\n")
    for fold in folds:
        for side, item in fold["sides"].items():
            for group, values in item["features"].items():
                for cost, entry in values["costs"].items():
                    stats = entry["test"]
                    net = stats["mean_net_pct"]
                    print(f"Fold {fold['fold']} {side} {group} cost={cost}: "
                          f"threshold={entry['threshold_pct']}%, trades={stats['trades']}, "
                          f"net={'N/A' if net is None else f'{net:+.4f}%'}; "
                          f"30+ trades={entry['passes_30_test_trades']}", flush=True)
    print("Saved:", target)


if __name__ == "__main__":
    main()
