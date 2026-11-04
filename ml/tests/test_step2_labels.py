"""Small deterministic tests for first-hit labeling; no database required."""
import unittest

import numpy as np
import pandas as pd

from ml.step2_labels import label_segment


class FirstHitTests(unittest.TestCase):
    def setUp(self):
        self.times = pd.date_range("2024-01-01", periods=4, freq="5min", tz="UTC", name="openTime")
        self.five = pd.DataFrame({"open": [100.] * 4, "high": [101.] * 4,
                                  "low": [99.] * 4, "close": [100.] * 4,
                                  "volume": [1.] * 4}, index=self.times)
        self.minute_times = pd.date_range(self.times[0], periods=20, freq="1min", tz="UTC", name="openTime")
        self.minute = pd.DataFrame({"open": 100., "high": 100., "low": 100.,
                                    "close": 100., "volume": 1.}, index=self.minute_times)
        self.features = pd.DataFrame({"atr14_pct": [0.01] * 4}, index=self.times)

    def test_first_hit_and_timeout(self):
        # Decision at 00:00; entry at 00:05; TP at 102, SL at 98.
        self.minute.loc[self.minute_times[6], "high"] = 102.5
        self.minute.loc[self.minute_times[7], "low"] = 97.5
        labels, skipped = label_segment(self.five, self.minute, self.features, 2, 2., 2.)
        first = labels[labels["row"] == 0]
        self.assertEqual(int(first[first["side"] == 1]["outcome"].iloc[0]), 1)
        self.assertEqual(int(first[first["side"] == -1]["outcome"].iloc[0]), -1)
        self.assertEqual(skipped, 0)

    def test_same_minute_tie_is_loss(self):
        self.minute.loc[self.minute_times[6], ["high", "low"]] = [103., 97.]
        labels, _ = label_segment(self.five, self.minute, self.features, 2, 2., 2.)
        self.assertTrue((labels[labels["row"] == 0]["outcome"] == -1).all())

    def test_missing_minute_skips_window(self):
        self.minute = self.minute.drop(self.minute_times[8])
        labels, skipped = label_segment(self.five, self.minute, self.features, 2, 2., 2.)
        self.assertEqual(len(labels), 0)
        self.assertEqual(skipped, 2)


if __name__ == "__main__":
    unittest.main()
