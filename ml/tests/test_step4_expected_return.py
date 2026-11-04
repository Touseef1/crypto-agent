"""Unit tests for Step 4A ranking and equal-sample model comparison."""
import unittest

import numpy as np
import pandas as pd

from ml.phase1 import FEATURE_COLUMNS
from ml.step4_expected_return import ranking_metrics, evaluate_models


class ExpectedReturnTests(unittest.TestCase):
    def test_ranking_uses_scores_not_future_returns(self):
        gross = np.array([.10, -.10, .03, -.02, .01, .02, .04, .05, .06, .07])
        scores = np.arange(10, dtype=float)
        result = ranking_metrics(gross, scores)
        self.assertEqual(result["n"], 1)
        self.assertAlmostEqual(result["mean_gross_pct"], 7.0)
        self.assertAlmostEqual(result["mean_net_pct"]["primary"], 6.7)

    def test_constant_cost_difference(self):
        gross = np.linspace(-.02, .02, 100)
        r = ranking_metrics(gross, np.arange(100))
        self.assertAlmostEqual(
            r["mean_gross_pct"]-r["mean_net_pct"]["primary"], .3, places=5
        )

    def test_models_share_test_rows(self):
        n = 300
        rng = np.random.default_rng(123)
        values = rng.normal(size=(n, len(FEATURE_COLUMNS)))
        df = pd.DataFrame(values, columns=FEATURE_COLUMNS)
        df["outcome"] = np.where(values[:, 0] > 0, 1, -1)
        df["gross_return"] = values[:, 0]*.002
        results = evaluate_models(df.iloc[:220], df.iloc[220:], FEATURE_COLUMNS, 42)
        self.assertEqual(results["test_n"], 80)
        self.assertEqual(results["classifier_tp_probability"]["n"], 8)
        self.assertEqual(results["regression_expected_return"]["n"], 8)


if __name__ == "__main__":
    unittest.main()
