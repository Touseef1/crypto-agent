"""Synthetic tests for Step 4C cost sensitivity."""
import unittest
import numpy as np
import pandas as pd
from ml.step4_cost_sensitivity import selected_stats, evaluate_cost, calibration_diagnostics


class CostSensitivityTests(unittest.TestCase):
    @staticmethod
    def frame(n=120, gross=.005):
        times = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
        return pd.DataFrame({"decision": times,
                             "exit": times+pd.Timedelta(minutes=5),
                             "gross_return": np.full(n, gross)})

    def test_stress_cost_reduces_net_without_changing_trades(self):
        f = self.frame()
        idx = np.array([0, 1, 2, 3])
        base = selected_stats(f, idx, .0014)
        stressed = selected_stats(f, idx, .0024)
        self.assertEqual(base["trades"], stressed["trades"])
        self.assertAlmostEqual(base["mean_net_pct"]-stressed["mean_net_pct"], .10)

    def test_abstains_when_calibration_unprofitable(self):
        cal, test = self.frame(gross=-.002), self.frame()
        entry = evaluate_cost(cal, test, np.full(120, .004), np.full(120, .004), .003)
        self.assertIsNone(entry["threshold_pct"])
        self.assertEqual(entry["test"]["trades"], 0)

    def test_threshold_fixed_when_test_outcomes_change(self):
        cal = self.frame(gross=.005)
        test_a = self.frame(gross=.005)
        test_b = self.frame(gross=-.005)
        scores = np.full(120, .004)
        a = evaluate_cost(cal, test_a, scores, scores, .003)
        b = evaluate_cost(cal, test_b, scores, scores, .003)
        self.assertEqual(a["threshold_pct"], b["threshold_pct"])
        self.assertEqual(a["test"]["trades"], b["test"]["trades"])
        self.assertGreater(a["test"]["mean_net_pct"], b["test"]["mean_net_pct"])

    def test_calibration_prediction_bias(self):
        f = self.frame(100, gross=.002)
        result = calibration_diagnostics(f, np.full(100, .003))
        self.assertAlmostEqual(result["mean_prediction_bias_pct"], .1)


if __name__ == "__main__":
    unittest.main()
