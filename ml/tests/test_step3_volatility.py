"""Synthetic checks: causal volatility features, gap resets, exact joins."""
import unittest
import numpy as np
import pandas as pd

from ml.phase1 import FEATURE_COLUMNS
from ml.step3_volatility import VOL_COLUMNS, build_volatility, prepare


class VolatilityTests(unittest.TestCase):
    @staticmethod
    def candles(n=620):
        t = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC", name="openTime")
        a = np.arange(n, dtype=float)
        close = 100 + .015*a + np.sin(a/7)*.3
        return pd.DataFrame({
            "open": close, "high": close+.4, "low": close-.4,
            "close": close, "volume": np.full(n, 10.0),
        }, index=t)

    def test_future_change_does_not_affect_past(self):
        a = self.candles()
        original = build_volatility(a)
        changed = a.copy()
        changed.iloc[-1, changed.columns.get_loc("close")] += .1
        changed.iloc[-1, changed.columns.get_loc("high")] += .1
        after = build_volatility(changed)
        pd.testing.assert_frame_equal(original.iloc[:-1], after.iloc[:-1])
        self.assertTrue(np.isfinite(original[VOL_COLUMNS].iloc[-1]).all())

    def test_gap_resets_percentile_window(self):
        a = self.candles(900)
        a = pd.concat([a.iloc[:400], a.iloc[420:]])
        features = build_volatility(a)
        self.assertTrue(pd.isna(features.loc[a.index[420], "range_percentile_288"]))
        self.assertTrue(np.isfinite(features.loc[a.index[-1], "range_percentile_288"]))

    def test_label_join_and_warmup(self):
        a = self.candles()
        t = a.index
        labels = pd.DataFrame({
            "decision_candle_open_utc": t.astype(str),
            "exit_candle_open_utc": (t+pd.Timedelta(minutes=5)).astype(str),
            "side": [1]*len(t), "outcome": [1]*len(t),
            "gross_return": [.01]*len(t),
        })
        for column in FEATURE_COLUMNS:
            labels[column] = 1.0
        merged, missing = prepare(labels, build_volatility(a))
        self.assertGreater(missing, 0)
        self.assertEqual(len(merged)+missing, len(labels))
        self.assertTrue(np.isfinite(merged[VOL_COLUMNS].to_numpy()).all())


if __name__ == "__main__":
    unittest.main()
