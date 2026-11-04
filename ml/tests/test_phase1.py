import unittest
import numpy as np
import pandas as pd
from ml.phase1 import validate, add_higher_timeframes, triple_barrier

def sample(n=300):
    idx=pd.date_range("2025-01-01",periods=n,freq="5min",tz="UTC",name="openTime")
    close=np.full(n,100.)
    return pd.DataFrame({"open":close,"high":close+1,"low":close-1,"close":close,"volume":np.ones(n)},index=idx)

class Phase1Tests(unittest.TestCase):
    def test_gap_rejected(self):
        x=sample().drop(sample().index[10])
        with self.assertRaisesRegex(ValueError,"Missing"):validate(x)
    def test_features_do_not_look_ahead(self):
        x=sample(800)
        a=add_higher_timeframes(x.iloc[:500])
        y=x.copy();y.loc[y.index[500]:,"close"]=200.;y.loc[y.index[500]:,"high"]=201.
        b=add_higher_timeframes(y)
        for col in ("h1_ret","h4_ret","ema20_gap","rsi14"):
            pd.testing.assert_series_equal(a[col],b[col].iloc[:500],check_names=False)
    def test_barrier_tie_is_loss(self):
        x=sample()
        f=pd.DataFrame({"atr14_pct":np.full(len(x),0.01)},index=x.index)
        result=triple_barrier(x,f,horizon=2,tp_atr=.5,sl_atr=.5)
        self.assertEqual(result.iloc[0]["outcome"],-1)
    def test_rows_exclude_unseen_future(self):
        x=sample(100);f=pd.DataFrame({"atr14_pct":np.full(100,.01)},index=x.index)
        result=triple_barrier(x,f,horizon=10)
        self.assertEqual(result["row"].max(),89)
if __name__=="__main__":unittest.main()
