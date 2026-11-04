"""Tests for parameter-comparison summaries; no MySQL access required."""
import unittest
import pandas as pd
from ml.step2_compare import summarize


class ComparisonTests(unittest.TestCase):
    def test_cost_deduction_and_timeout(self):
        times = pd.date_range("2024-01-01", periods=6, freq="5min", tz="UTC")
        labels = pd.DataFrame({
            "row": [0, 1, 2, 3, 4, 5],
            "side": [1, 1, 1, -1, -1, -1],
            "outcome": [1, -1, 0, 1, -1, 0],
            "gross_return": [0.02, -0.01, 0.0, 0.02, -0.01, 0.0],
        })
        result = summarize(labels, times)
        for side in ("long", "short"):
            all_rows = result["directions"][side]["all"]
            self.assertEqual(all_rows["n"], 3)
            self.assertEqual((all_rows["tp"], all_rows["sl"], all_rows["timeout"]), (1, 1, 1))
            self.assertAlmostEqual(all_rows["mean_gross_pct"], 1/3, places=5)
            self.assertAlmostEqual(all_rows["mean_net_pct"]["primary"], 1/3 - 0.3, places=5)
            self.assertAlmostEqual(all_rows["mean_net_pct"]["lower"], 1/3 - 0.14, places=5)
            self.assertEqual(sum(result["directions"][side][p]["n"] for p in ("early", "middle", "late")), 3)


if __name__ == "__main__":
    unittest.main()
