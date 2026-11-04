"""Step 4B: offline cost-aware trade/no-trade filtering.

Calibrate predicted-net-return thresholds using TRAIN/CAL only; never select
thresholds using TEST outcomes. Sequential, non-overlapping trade diagnostic.
No DB writes, trading engine integration, or live orders.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ml.phase1 import FEATURE_COLUMNS, STEP, load_mysql
from ml.phase2 import partitions
from ml.step3_trend import COSTS
from ml.step3_volume import VOLUME_COLUMNS, build_volume, prepare
from ml.step4_expected_return import regression_model

# Candidate extra margin above round-trip cost, in decimal returns.
MARGINS = (0.0, 0.0005, 0.001, 0.002)
MIN_CAL_TRADES = 30


def sequential_trades(frame, scores, threshold):
    """Only take opportunities above threshold, never overlap an open event.

    Input frame must represent ONE trade direction, chronological by decision.
    An event's exit is known only for offline accounting and position lockout,
    not used for scoring or choosing thresholds.
    """
    if not frame["decision"].is_monotonic_increasing:
        raise ValueError("Decisions must be chronological")
    if len(frame) != len(scores):
        raise ValueError("Scores length mismatch")
    scores = np.asarray(scores, dtype=float)
    if not np.isfinite(scores).all():
        raise ValueError("Nonfinite scores")
    candidates = np.flatnonzero(scores > threshold)
    chosen = []
    next_available = pd.Timestamp.min.tz_localize("UTC")
    for idx in candidates:
        decision = frame["decision"].iloc[idx]
        if decision < next_available:
            continue
        chosen.append(int(idx))
        next_available = frame["exit"].iloc[idx]
    return np.asarray(chosen, dtype=int)


def performance(frame, scores, threshold, cost):
    selected = sequential_trades(frame, scores, threshold)
    gross = frame["gross_return"].to_numpy(dtype=float)[selected]
    net = gross-cost
    if not len(selected):
        return {
            "trades": 0, "candidate_count": int(np.sum(np.asarray(scores)>threshold)),
            "mean_net_pct": None, "total_net_pct_on_fixed_notional": 0.0,
            "win_rate": None, "max_drawdown_pct_on_fixed_notional": 0.0,
            "selected_fraction": 0.0,
        }
    # Fixed-notional, additive P/L diagnostic, not account-equity compounding.
    curve = np.r_[0.0, np.cumsum(net)]
    drawdown = curve-np.maximum.accumulate(curve)
    return {
        "trades": int(len(selected)),
        "candidate_count": int(np.sum(np.asarray(scores)>threshold)),
        "mean_net_pct": round(float(net.mean()*100), 6),
        "total_net_pct_on_fixed_notional": round(float(net.sum()*100), 6),
        "win_rate": round(float(np.mean(net>0)), 6),
        "max_drawdown_pct_on_fixed_notional": round(float(-drawdown.min()*100), 6),
        "selected_fraction": round(float(len(selected)/len(frame)), 6),
    }


def select_threshold(cal, scores, cost):
    """Choose among predetermined cost-plus-margin candidates on CAL only.

    A positive mean calibration return is required; otherwise choose no trade.
    The threshold is frozen before the test period is scored.
    """
    candidates = []
    for margin in MARGINS:
        threshold = cost+margin
        stats = performance(cal, scores, threshold, cost)
        candidates.append({"threshold_pct": round(threshold*100, 6),
                           "margin_pct": round(margin*100, 6), **stats})
    eligible = [c for c in candidates if c["trades"] >= MIN_CAL_TRADES
                and c["mean_net_pct"] is not None and c["mean_net_pct"] > 0]
    if not eligible:
        return None, candidates
    best = max(eligible, key=lambda c: (c["mean_net_pct"], c["trades"]))
    return best["threshold_pct"]/100, candidates


def train_predict(train, cal, test, columns, seed):
    model = regression_model(seed)
    model.fit(train[columns], train["gross_return"].to_numpy(dtype=float)*100)
    cal_predictions = model.predict(cal[columns])/100
    test_predictions = model.predict(test[columns])/100
    return cal_predictions, test_predictions


def run(df, seed=42):
    results = []
    for fold, frac in enumerate((.45, .55, .65), 1):
        record = {"fold": fold, "train_fraction": frac, "sides": {}}
        for side, name in ((1, "long"), (-1, "short")):
            subset = df.loc[df["side"] == side]
            train, cal, test = partitions(subset, frac, .08, .08, embargo_bars=24)
            if test["decision"].max() >= subset["decision"].iloc[int(len(subset)*.82)]:
                raise ValueError("Reserved holdout would be evaluated")
            item = {"train_n": int(len(train)), "cal_n": int(len(cal)),
                    "test_n": int(len(test)),
                    "test_start": test["decision"].min().isoformat(),
                    "test_end": test["decision"].max().isoformat(),
                    "feature_sets": {}}
            for group, columns in (
                ("baseline21", FEATURE_COLUMNS),
                ("plus_volume", FEATURE_COLUMNS+VOLUME_COLUMNS),
            ):
                cal_scores, test_scores = train_predict(train, cal, test, columns, seed)
                costs = {}
                for label, cost in COSTS.items():
                    threshold, candidates = select_threshold(cal, cal_scores, cost)
                    costs[label] = {
                        "selected_threshold_pct": None if threshold is None else round(threshold*100, 6),
                        "calibration_candidates": candidates,
                        "test": performance(test, test_scores, threshold, cost)
                        if threshold is not None else {
                            "trades": 0, "candidate_count": 0,
                            "mean_net_pct": None, "total_net_pct_on_fixed_notional": 0.0,
                            "win_rate": None, "max_drawdown_pct_on_fixed_notional": 0.0,
                            "selected_fraction": 0.0,
                        },
                        "no_trade_reason": "No calibration candidate passed minimum trades and positive mean net"
                        if threshold is None else None,
                    }
                item["feature_sets"][group] = costs
            record["sides"][name] = item
        results.append(record)
    return results


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
    df, missing = prepare(labels, build_volume(candles))
    folds = run(df, args.seed)
    report = {
        "symbol": args.symbol, "experiment": "Step 4B cost-aware no-trade filter",
        "source_rows": int(len(labels)), "eligible_rows": int(len(df)),
        "missing_volume_rows": missing, "costs_pct": {k: v*100 for k, v in COSTS.items()},
        "margins_pct": [v*100 for v in MARGINS], "min_cal_trades": MIN_CAL_TRADES,
        "notes": [
            "Thresholds selected using calibration labels only; test outcomes never tune them.",
            "Regressor trained on training window only; predictions made out of sample.",
            "Sequential trade lockout prevents overlapping positions within each direction.",
            "Long and short evaluated separately: simultaneous opposing positions are NOT resolved.",
            "Total return/drawdown use additive fixed-notional P/L, not account equity.",
            "Cost assumptions fixed; funding, variable slippage, leverage and impact omitted.",
            "Last approximately 19% remains untouched; no production trading.",
        ], "folds": folds,
    }
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out/f"{args.symbol.lower()}_cost_filter.json"
    target.write_text(json.dumps(report, indent=2)+"\n")
    for fold in folds:
        for side, item in fold["sides"].items():
            for group, costs in item["feature_sets"].items():
                for cost_name, detail in costs.items():
                    result = detail["test"]
                    mean = result["mean_net_pct"]
                    print(f"Fold {fold['fold']} {side} {group} {cost_name}: "
                          f"threshold={detail['selected_threshold_pct']}%, "
                          f"trades={result['trades']}, "
                          f"mean_net={'N/A' if mean is None else f'{mean:+.4f}%'}; "
                          f"max_DD={result['max_drawdown_pct_on_fixed_notional']:.4f}%",
                          flush=True)
    print("Saved:", target)


if __name__ == "__main__":
    main()
