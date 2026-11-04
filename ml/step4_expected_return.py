"""Step 4A: offline return-regression vs TP-classifier ranking experiment.

Same 1m first-hit labels, purged chronological folds and identical eligible
samples for baseline (21) and baseline+volume. No trading or database writes.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

from ml.phase1 import FEATURE_COLUMNS, STEP, load_mysql
from ml.phase2 import partitions
from ml.step3_trend import COSTS, model as classifier_model
from ml.step3_volume import VOLUME_COLUMNS, build_volume, prepare


def regression_model(seed):
    return LGBMRegressor(
        n_estimators=250, learning_rate=.04, num_leaves=15, max_depth=6,
        min_child_samples=100, colsample_bytree=.8, subsample=.8,
        subsample_freq=1, reg_lambda=2, random_state=seed, n_jobs=4,
        verbosity=-1,
    )


def ranking_metrics(gross, scores):
    """Evaluate the best-scored 10% of TEST examples, never rank on outcomes."""
    gross = np.asarray(gross, dtype=float)
    scores = np.asarray(scores, dtype=float)
    if not len(gross) or len(gross) != len(scores) or not np.isfinite(scores).all():
        raise ValueError("Invalid scores/returns")
    k = max(1, int(np.ceil(len(scores)*.1)))
    idx = np.argsort(-scores, kind="stable")[:k]
    return {
        "n": int(k),
        "mean_gross_pct": round(float(gross[idx].mean()*100), 6),
        "mean_net_pct": {
            key: round(float((gross[idx]-cost).mean()*100), 6)
            for key, cost in COSTS.items()
        },
        "positive_net_fraction_primary": round(float(np.mean(gross[idx] > COSTS["primary"])), 6),
    }


def evaluate_models(train, test, columns, seed):
    x_train, x_test = train[columns], test[columns]
    y_tp = (train["outcome"] == 1).astype(int)
    if y_tp.nunique() != 2:
        raise ValueError("TP classifier requires two training classes")
    y_gross = train["gross_return"].to_numpy(dtype=float)
    actual = test["gross_return"].to_numpy(dtype=float)
    if not np.isfinite(y_gross).all() or not np.isfinite(actual).all():
        raise ValueError("Nonfinite return labels")
    clf = classifier_model(seed)
    clf.fit(x_train, y_tp)
    prob = clf.predict_proba(x_test)[:, 1]
    reg = regression_model(seed)
    # Target is gross return in percentage points for numerical stability.
    reg.fit(x_train, y_gross*100)
    predicted_gross = reg.predict(x_test)/100
    return {
        "classifier_tp_probability": ranking_metrics(actual, prob),
        "regression_expected_return": {
            **ranking_metrics(actual, predicted_gross),
            "mae_pct": round(float(mean_absolute_error(actual, predicted_gross)*100), 6),
            "rmse_pct": round(float(np.sqrt(mean_squared_error(actual, predicted_gross))*100), 6),
            "predicted_mean_gross_pct": round(float(np.mean(predicted_gross)*100), 6),
            "predicted_positive_net_fraction_primary": round(
                float(np.mean(predicted_gross > COSTS["primary"])), 6),
        },
        "test_n": int(len(test)),
    }


def run(df, seed=42):
    records = []
    for fold, frac in enumerate((.45, .55, .65), 1):
        record = {"fold": fold, "train_fraction": frac, "sides": {}}
        for side, name in ((1, "long"), (-1, "short")):
            subset = df.loc[df["side"] == side]
            train, cal, test = partitions(subset, frac, .08, .08, embargo_bars=24)
            if test["decision"].max() >= subset["decision"].iloc[int(len(subset)*.82)]:
                raise ValueError("Evaluation enters reserved holdout")
            basic = evaluate_models(train, test, FEATURE_COLUMNS, seed)
            volume = evaluate_models(train, test, FEATURE_COLUMNS+VOLUME_COLUMNS, seed)
            record["sides"][name] = {
                "train_n": int(len(train)), "unused_cal_n": int(len(cal)),
                "test_start": test["decision"].min().isoformat(),
                "test_end": test["decision"].max().isoformat(),
                "baseline_features": basic, "with_volume_features": volume,
            }
        records.append(record)
    return records


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True, choices=["BTCUSDT", "ETHUSDT"])
    p.add_argument("--data-dir", default="ml/data/step2")
    p.add_argument("--output-dir", default="ml/artifacts/step4")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    source = Path(args.data_dir)/f"{args.symbol.lower()}_1m_first_hit_h24_tp2_sl1.5.csv"
    needed = ["decision_candle_open_utc", "exit_candle_open_utc", "side",
              "outcome", "gross_return"]+FEATURE_COLUMNS
    labels = pd.read_csv(source, usecols=needed)
    candles = load_mysql(args.symbol)
    candles = candles.loc[candles.index+STEP <= pd.Timestamp.now(tz="UTC")]
    data, missing = prepare(labels, build_volume(candles))
    folds = run(data, args.seed)
    report = {
        "symbol": args.symbol, "experiment": "Step 4A TP classifier vs gross-return regressor",
        "source_rows": int(len(labels)), "eligible_rows": int(len(data)),
        "missing_volume_rows": missing, "baseline_features": FEATURE_COLUMNS,
        "added_volume_features": VOLUME_COLUMNS,
        "costs_pct": {k: v*100 for k, v in COSTS.items()},
        "notes": [
            "Regressor target is realized gross return, not a future input feature.",
            "Regressor predicts gross return; net ranking is identical for a constant cost.",
            "Both objectives use identical purged splits and eligible rows.",
            "Calibration interval is unused; last ~19% reserved untouched.",
            "Top-decile test-set ranking is exploratory, not an executable threshold.",
            "Overlapping opportunities are not a portfolio or realistic order schedule.",
            "No funding, dynamic slippage, market impact, live orders or DB writes.",
        ], "folds": folds,
    }
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out/f"{args.symbol.lower()}_expected_return.json"
    target.write_text(json.dumps(report, indent=2)+"\n")
    for fold in folds:
        for side, item in fold["sides"].items():
            for group, label in (("baseline_features", "base21"), ("with_volume_features", "plus_volume")):
                comparison = item[group]
                clf = comparison["classifier_tp_probability"]["mean_net_pct"]["primary"]
                reg = comparison["regression_expected_return"]["mean_net_pct"]["primary"]
                print(f"Fold {fold['fold']} {side} {label}: "
                      f"TP-rank net={clf:+.4f}%, return-rank net={reg:+.4f}%, "
                      f"delta={reg-clf:+.4f} pp", flush=True)
    print("Saved:", target)


if __name__ == "__main__":
    main()
