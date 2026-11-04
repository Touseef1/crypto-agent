"""Step 4B tests: no trade, cost accounting, chronological lockout, calibration."""
import unittest

import numpy as np
import pandas as pd

from ml.step4_cost_filter import performance, select_threshold, sequential_trades


class CostFilterTests(unittest.TestCase):
    def frame(self, n=120, gross=.005, exit_minutes=15):
        times = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
        return pd.DataFrame({
            "decision": times, "exit": times+pd.Timedelta(minutes=exit_minutes),
            "gross_return": np.full(n, gross),
        })

    def test_no_trade(self):
        frame = self.frame()
        result = performance(frame, np.zeros(len(frame)), .003, .003)
        self.assertEqual(result["trades"], 0)
        self.assertIsNone(result["mean_net_pct"])

    def test_lockout_and_fee(self):
        frame = self.frame(12)
        indices = sequential_trades(frame, np.full(12, .01), .003)
        self.assertEqual(indices.tolist(), [0, 3, 6, 9])
        result = performance(frame, np.full(12, .01), .003, .003)
        self.assertEqual(result["trades"], 4)
        self.assertAlmostEqual(result["mean_net_pct"], .2)

    def test_threshold_selected_from_calibration(self):
        frame = self.frame(120, gross=.005, exit_minutes=5)
        threshold, _ = select_threshold(frame, np.full(120, .004), .003)
        self.assertAlmostEqual(threshold, .003)
        negative = self.frame(120, gross=-.002, exit_minutes=5)
        threshold, _ = select_threshold(negative, np.full(120, .004), .003)
        self.assertIsNone(threshold)

    def test_calibration_minimum_trades(self):
        frame = self.frame(20, gross=.01, exit_minutes=5)
        threshold, _ = select_threshold(frame, np.full(20, .01), .003)
        self.assertIsNone(threshold)

    def test_future_score_cannot_change_prior_selection(self):
        frame = self.frame(120)
        original = np.full(120, .005)
        changed = original.copy()
        changed[-1] = .1
        a = sequential_trades(frame, original, .003)
        b = sequential_trades(frame, changed, .003)
        np.testing.assert_array_equal(a[:-1], b[:-1])


if __name__ == "__main__":
    unittest.main()
