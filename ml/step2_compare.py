"""Step 2 parameter comparison: historical, read-only, no orders.

This is an exploratory diagnostic, NOT a backtest of an executable strategy:
every 5m decision produces both hypothetical long and short outcomes.
Do not select a configuration using these data and report its performance as OOS.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ml.phase1 import STEP, add_higher_timeframes, continuous_segments, load_mysql, validate
from ml.step2_labels import MINUTE, label_segment, load_minutes

CONFIGS = [
    ("baseline", 2.0, 1.5, 24),
    ("A", 3.0, 1.5, 24),
    ("B", 2.0, 1.5, 12),
    ("C", 3.0, 1.5, 48),
]
COSTS = {"primary": 0.003, "lower": 0.0014}


def summarize(labels, timestamps):
    """Summarize every eligible hypothetical opportunity, not selected trades."""
    if labels.empty:
        return {"examples": 0}
    result = {"examples": int(len(labels)), "directions": {}}
    decision = pd.DatetimeIndex(timestamps.take(labels["row"].to_numpy(dtype=int)))
    # Chronological thirds are descriptive only; no tuning or training here.
    time_min = decision.min()
    time_max = decision.max()
    boundaries = [time_min + (time_max - time_min) * k / 3 for k in (1, 2)]
    gross = labels["gross_return"].to_numpy(dtype=float)
    outcomes = labels["outcome"].to_numpy(dtype=int)
    sides = labels["side"].to_numpy(dtype=int)
    for side, name in ((1, "long"), (-1, "short")):
        selected = sides == side
        entries = {}
        for period, mask in [
            ("all", selected),
            ("early", selected & (decision < boundaries[0])),
            ("middle", selected & (decision >= boundaries[0]) & (decision < boundaries[1])),
            ("late", selected & (decision >= boundaries[1])),
        ]:
            values = gross[mask]
            if not len(values):
                entries[period] = {"n": 0}
                continue
            counts = {key: int(np.count_nonzero(outcomes[mask] == val))
                      for key, val in (("tp", 1), ("sl", -1), ("timeout", 0))}
            entries[period] = {
                "n": int(len(values)),
                **counts,
                "tp_rate": round(counts["tp"] / len(values), 6),
                "mean_gross_pct": round(float(values.mean() * 100), 6),
                "mean_net_pct": {key: round(float((values - cost).mean() * 100), 6)
                                 for key, cost in COSTS.items()},
                "positive_net_fraction": {key: round(float(np.mean(values > cost)), 6)
                                          for key, cost in COSTS.items()},
            }
        result["directions"][name] = entries
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", choices=["BTCUSDT", "ETHUSDT"], required=True)
    parser.add_argument("--output-dir", default="ml/artifacts/step2")
    args = parser.parse_args()

    five = load_mysql(args.symbol)
    now = pd.Timestamp.now(tz="UTC")
    five = five.loc[five.index + STEP <= now]
    validate(five)
    minute = load_minutes(args.symbol)
    minute = minute.loc[minute.index + MINUTE <= now]
    segments = continuous_segments(five)
    prepared = [(segment, add_higher_timeframes(segment)) for segment in segments]
    report = {
        "symbol": args.symbol,
        "source_5m": int(len(five)),
        "source_1m": int(len(minute)),
        "continuous_segments": len(segments),
        "round_trip_costs_pct": {k: v * 100 for k, v in COSTS.items()},
        "assumptions": [
            "Entry at next 5m open; 1m first-hit labels; same-minute ties are losses.",
            "Gross return uses barrier price on hits and last 1m close on timeout.",
            "Fixed round-trip cost deducted from every outcome, including timeouts.",
            "No funding, market impact, gap-through fill penalty, or position sizing.",
            "Long and short are separate hypothetical opportunities, not executable signals.",
            "Overlapping events are dependent; chronological thirds are descriptive only.",
            "Parameter comparison is exploratory and not out-of-sample validation.",
        ],
        "configurations": {},
    }
    for name, tp, sl, horizon in CONFIGS:
        aggregate = []
        skipped = 0
        for segment, features in prepared:
            labels, missing = label_segment(segment, minute, features, horizon, tp, sl)
            skipped += missing
            if not labels.empty:
                # Keep only compact outcome columns, not large feature matrices.
                labels["decision_time"] = segment.index.take(labels["row"].to_numpy(dtype=int))
                aggregate.append(labels[["side", "outcome", "gross_return", "decision_time"]])
        if not aggregate:
            raise ValueError("No complete 1m windows for configuration " + name)
        combined = pd.concat(aggregate, ignore_index=True)
        # Reuse summary's row-to-timestamp mapping with a compact, sorted index.
        combined = combined.sort_values("decision_time", kind="stable").reset_index(drop=True)
        timestamps = pd.DatetimeIndex(combined["decision_time"])
        combined["row"] = np.arange(len(combined))
        stats = summarize(combined, timestamps)
        report["configurations"][name] = {
            "tp_atr": tp, "sl_atr": sl, "horizon_5m_bars": horizon,
            "skipped_incomplete_1m_windows": int(skipped),
            **stats,
        }
        print(f"{name}: {len(combined):,} examples; incomplete windows skipped: {skipped}")
        for direction in ("long", "short"):
            overall = stats["directions"][direction]["all"]
            print(f"  {direction}: TP {overall['tp_rate']:.2%}, "
                  f"gross {overall['mean_gross_pct']:+.4f}%, "
                  f"net primary {overall['mean_net_pct']['primary']:+.4f}%, "
                  f"net lower {overall['mean_net_pct']['lower']:+.4f}%")
        del combined, aggregate
    target = Path(args.output_dir) / (args.symbol.lower() + "_parameter_comparison.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n")
    print("Saved:", target)


if __name__ == "__main__":
    main()
