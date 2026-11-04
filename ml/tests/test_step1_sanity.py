import unittest
import numpy as np
import pandas as pd
from ml.step1_sanity import atr_cost_stats,cost_roundtrip

class Step1SanityTests(unittest.TestCase):
    def test_round_trip_cost(self):
        self.assertAlmostEqual(cost_roundtrip(.001,.0005),.003)
    def test_atr_vs_cost(self):
        df=pd.DataFrame({"atr14_pct":[.001,.002,.003]})
        stats=atr_cost_stats(df,.001,.0005)
        self.assertAlmostEqual(stats["median_atr_pct"],.2)
        self.assertAlmostEqual(stats["median_tp_distance_pct"],.4)
        self.assertTrue(stats["median_tp_less_than_3x_cost"])
    def test_lower_cost(self):
        df=pd.DataFrame({"atr14_pct":[.005,.005,.005]})
        stats=atr_cost_stats(df,.0005,.0002)
        self.assertFalse(stats["median_tp_less_than_3x_cost"])
    def test_negative_cost_rejected(self):
        with self.assertRaises(ValueError):cost_roundtrip(-.001,.0005)
if __name__=="__main__":unittest.main()
