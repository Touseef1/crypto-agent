"""Synthetic causality and sample-alignment checks for trend-strength experiment."""
import unittest
import numpy as np
import pandas as pd

from ml.step3_trend import TREND_COLUMNS, build_trend, prepare
from ml.phase1 import FEATURE_COLUMNS


class TrendTests(unittest.TestCase):
    def candles(self, n=270):
        t = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC", name="openTime")
        c = 100 + np.arange(n)*.02 + np.sin(np.arange(n)/5)*.2
        return pd.DataFrame({"open": c, "high": c+.2, "low": c-.2,
                             "close": c, "volume": np.full(n, 10.)}, index=t)

    def test_causal_no_future_dependency(self):
        a = self.candles()
        original = build_trend(a)
        changed = a.copy()
        changed.iloc[-1, changed.columns.get_loc("close")] += .1
        changed.iloc[-1, changed.columns.get_loc("high")] += .1
        after = build_trend(changed)
        pd.testing.assert_frame_equal(original.iloc[:-1], after.iloc[:-1])
        self.assertTrue(np.isfinite(original[TREND_COLUMNS].iloc[-1]).all())

    def test_gap_resets_ema_warmup(self):
        a = self.candles(500)
        a = pd.concat([a.iloc[:250], a.iloc[260:]])
        result = build_trend(a)
        self.assertTrue(pd.isna(result.loc[a.index[260], "ema200_gap"]))
        self.assertTrue(np.isfinite(result.loc[a.index[-1], "ema200_gap"]))

    def test_exact_alignment_and_warmup(self):
        a = self.candles()
        trend = build_trend(a)
        t = a.index
        rows = pd.DataFrame({
            "decision_candle_open_utc": t.astype(str),
            "exit_candle_open_utc": (t+pd.Timedelta(minutes=5)).astype(str),
            "side": [1]*len(t), "outcome": [1]*len(t),
            "gross_return": [0.01]*len(t),
        })
        for name in FEATURE_COLUMNS:
            rows[name] = 1.
        aligned, missing = prepare(rows, trend)
        self.assertGreater(missing, 0)
        self.assertEqual(len(aligned)+missing, len(rows))
        self.assertEqual(len(aligned), len(aligned["decision"].unique()))


if __name__ == "__main__":
    unittest.main()
