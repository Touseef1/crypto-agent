"""Align Phase 1 (5m) and Step 2 (1m) trade labels; chronological diagnostics.

Read-only offline analysis. No model training, orders, or parameter selection.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

COSTS = {"primary": 0.003, "lower": 0.0014}
KEYS = ["decision_candle_open_utc", "side"]
BASE_COLUMNS = KEYS + ["outcome", "exit_candle_open_utc", "entry", "take_profit", "stop_loss"]
NEW_COLUMNS = BASE_COLUMNS + ["exit_price", "gross_return"]
LABEL = {-1: "SL", 0: "TIMEOUT", 1: "TP"}


def load(path, cols, suffix):
    df = pd.read_csv(path, usecols=cols)
    if df[KEYS].isna().any().any() or df.duplicated(KEYS).any():
        raise ValueError(f"{suffix}: null or duplicate trade keys")
    if not df["side"].isin([-1, 1]).all() or not df["outcome"].isin([-1, 0, 1]).all():
        raise ValueError(f"{suffix}: invalid side or outcome")
    for col in ("decision_candle_open_utc", "exit_candle_open_utc"):
        df[col] = pd.to_datetime(df[col], utc=True, errors="raise")
    if (df["exit_candle_open_utc"] <= df["decision_candle_open_utc"]).any():
        raise ValueError(f"{suffix}: exit not after decision")
    if not df["decision_candle_open_utc"].is_monotonic_increasing:
        raise ValueError(f"{suffix}: decisions not sorted")
    for col in ("entry", "take_profit", "stop_loss"):
        if not np.isfinite(df[col].to_numpy(dtype=float)).all():
            raise ValueError(f"{suffix}: nonfinite {col}")
    return df


def stats(df):
    if df.empty:
        return {"n": 0}
    returns = df["gross_return"].to_numpy(float)
    if not np.isfinite(returns).all():
        raise ValueError("Nonfinite gross returns")
    counts = {LABEL[outcome]: int((df["outcome_1m"] == outcome).sum()) for outcome in (-1, 0, 1)}
    return {
        "n": len(df), "outcomes": counts,
        "mean_gross_pct": round(float(returns.mean() * 100), 6),
        "mean_net_pct": {name: round(float((returns - cost).mean() * 100), 6)
                         for name, cost in COSTS.items()},
    }


def compare(old, new):
    if old.duplicated(KEYS).any() or new.duplicated(KEYS).any():
        raise ValueError("Duplicate trade keys")
    merged = old.merge(new, on=KEYS, how="outer", suffixes=("_5m", "_1m"), indicator=True,
                       validate="one_to_one", sort=False)
    counts = merged["_merge"].value_counts()
    unmatched = {"only_5m": int(counts.get("left_only", 0)),
                 "only_1m": int(counts.get("right_only", 0))}
    both = merged.loc[merged["_merge"] == "both"].copy()
    for field in ("entry", "take_profit", "stop_loss"):
        a = both[field + "_5m"].to_numpy(float)
        b = both[field + "_1m"].to_numpy(float)
        if not np.allclose(a, b, rtol=1e-8, atol=1e-8):
            raise ValueError(f"Aligned {field} differs across datasets")
    if not both.empty:
        bad_exit = both["exit_candle_open_utc_1m"] < both["decision_candle_open_utc"]
        if bad_exit.any():
            raise ValueError("Exit before decision")
    changes = pd.crosstab(both["outcome_5m"], both["outcome_1m"])
    transitions = {
        LABEL[a] + "_to_" + LABEL[b]: int(changes.loc[a, b]) if a in changes.index and b in changes.columns else 0
        for a in (-1, 0, 1) for b in (-1, 0, 1)
    }
    # Chronological thirds based on unique decision times (not row indices).
    times = both["decision_candle_open_utc"].drop_duplicates().sort_values().reset_index(drop=True)
    if len(times) < 3:
        raise ValueError("Need at least three distinct decision times")
    b1, b2 = times.iloc[len(times) // 3], times.iloc[2 * len(times) // 3]
    periods = {
        "early": both["decision_candle_open_utc"] < b1,
        "middle": (both["decision_candle_open_utc"] >= b1) & (both["decision_candle_open_utc"] < b2),
        "late": both["decision_candle_open_utc"] >= b2,
    }
    by_period = {}
    for name, mask in periods.items():
        by_period[name] = {}
        for side, side_name in ((1, "long"), (-1, "short")):
            subset = both.loc[mask & (both["side"] == side)]
            by_period[name][side_name] = stats(subset)
    return {
        "original_rows": int(len(old)),
        "new_rows": int(len(new)),
        "matched_rows": int(len(both)),
        "unmatched": unmatched,
        "changed_labels": int((both["outcome_5m"] != both["outcome_1m"]).sum()),
        "transitions": transitions,
        "period_boundaries_utc": [b1.isoformat(), b2.isoformat()],
        "by_period": by_period,
        "overall": {
            name: stats(both.loc[both["side"] == side])
            for side, name in ((1, "long"), (-1, "short"))
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", choices=["BTCUSDT", "ETHUSDT"], required=True)
    parser.add_argument("--data-dir", default="ml/data")
    parser.add_argument("--output-dir", default="ml/artifacts/step2")
    args = parser.parse_args()
    name = args.symbol.lower()
    old_path = Path(args.data_dir) / f"{name}_5m_phase1.csv"
    new_path = Path(args.data_dir) / "step2" / f"{name}_1m_first_hit_h24_tp2_sl1.5.csv"
    old = load(old_path, BASE_COLUMNS, "5m")
    new = load(new_path, NEW_COLUMNS, "1m")
    if not np.isfinite(new[["exit_price", "gross_return"]].to_numpy(dtype=float)).all():
        raise ValueError("Nonfinite exit price or return")
    report = {"symbol": args.symbol, "costs_pct": {k: v * 100 for k, v in COSTS.items()},
              "notes": [
                  "Only exact (decision timestamp, side) matches are compared.",
                  "Gross/net returns are calculated from 1m labels, not executable signals.",
                  "Every eligible long and short is included; overlapping events are dependent.",
                  "Chronological thirds are descriptive, not independent out-of-sample tests.",
                  "Constant percentage round-trip costs exclude funding and market impact.",
              ], **compare(old, new)}
    target = Path(args.output_dir) / f"{name}_alignment_validation.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{args.symbol}: matched {report['matched_rows']:,}; "
          f"only 5m {report['unmatched']['only_5m']:,}; "
          f"only 1m {report['unmatched']['only_1m']:,}")
    print(f"Changed outcomes: {report['changed_labels']:,}")
    for k, v in report["transitions"].items():
        if k.split("_to_")[0] != k.split("_to_")[1] and v:
            print(f"  {k}: {v:,}")
    for period, sides in report["by_period"].items():
        for side, values in sides.items():
            if values["n"]:
                print(f"  {period:6} {side:5}: n={values['n']:,}, "
                      f"gross={values['mean_gross_pct']:+.4f}%, "
                      f"net primary={values['mean_net_pct']['primary']:+.4f}%, "
                      f"net lower={values['mean_net_pct']['lower']:+.4f}%")
    print("Saved:", target)


if __name__ == "__main__":
    main()
