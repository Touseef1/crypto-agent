"""Small synthetic tests for alignment, transitions, and net-cost summaries."""
import unittest

import pandas as pd

from ml.step2_validate import compare


class AlignmentTests(unittest.TestCase):
    def test_alignment_and_transitions(self):
        t = pd.date_range("2024-01-01", periods=6, freq="5min", tz="UTC")
        keys = [(time, side) for time in t for side in (1, -1)]
        old = pd.DataFrame(keys, columns=["decision_candle_open_utc", "side"])
        old["outcome"] = [-1] * len(old)
        old["exit_candle_open_utc"] = old["decision_candle_open_utc"] + pd.Timedelta(minutes=10)
        old["entry"] = 100.0
        old["take_profit"] = old["entry"] + old["side"] * 2
        old["stop_loss"] = old["entry"] - old["side"] * 1.5
        new = old.copy()
        new.loc[0, "outcome"] = 1
        new["exit_price"] = 99.0
        new["gross_return"] = 0.01
        report = compare(old, new)
        self.assertEqual(report["matched_rows"], 12)
        self.assertEqual(report["changed_labels"], 1)
        self.assertEqual(report["transitions"]["SL_to_TP"], 1)
        self.assertEqual(report["unmatched"]["only_1m"], 0)
        self.assertAlmostEqual(report["overall"]["long"]["mean_net_pct"]["primary"], 0.7)
        self.assertEqual(sum(report["by_period"][p]["long"]["n"]
                             for p in ("early", "middle", "late")), 6)

    def test_unmatched_is_reported(self):
        t = pd.date_range("2024-01-01", periods=4, freq="5min", tz="UTC")
        old = pd.DataFrame({"decision_candle_open_utc": t, "side": [1] * 4,
                            "outcome": [-1] * 4, "exit_candle_open_utc": t + pd.Timedelta(minutes=5),
                            "entry": [100.] * 4, "take_profit": [102.] * 4,
                            "stop_loss": [98.] * 4})
        new = old.iloc[:3].copy()
        new["exit_price"] = 98.
        new["gross_return"] = -0.02
        report = compare(old, new)
        self.assertEqual(report["unmatched"]["only_5m"], 1)


if __name__ == "__main__":
    unittest.main()
