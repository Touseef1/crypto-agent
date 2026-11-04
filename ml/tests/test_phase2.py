import unittest
import numpy as np
import pandas as pd
from ml.phase1 import FEATURE_COLUMNS
from ml.phase2 import partitions,metrics,load_dataset

class Phase2Tests(unittest.TestCase):
    def fixture(self,n=500):
        ts=pd.date_range("2025-01-01",periods=n,freq="5min",tz="UTC")
        data={col:np.ones(n) for col in FEATURE_COLUMNS}
        data.update({"decision_candle_open_utc":ts.astype(str),
                     "exit_candle_open_utc":(ts+pd.Timedelta(minutes=120)).astype(str),
                     "side":np.ones(n,dtype=int),"outcome":np.tile([1,-1],n//2)})
        df=pd.DataFrame(data)
        df["decision"]=pd.to_datetime(df["decision_candle_open_utc"],utc=True)
        df["exit"]=pd.to_datetime(df["exit_candle_open_utc"],utc=True)
        return df
    def test_purge_prevents_label_overlap(self):
        df=self.fixture()
        train,cal,test=partitions(df,.5,.1,.1)
        self.assertLess(train["exit"].max(),cal["decision"].min())
        self.assertLess(cal["exit"].max(),test["decision"].min())
    def test_metrics(self):
        x=metrics([0,1,0,1],[.1,.9,.2,.8])
        self.assertLess(x["brier"],.1)
        self.assertEqual(x["auc"],1.)
    def test_duplicate_detection(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            df=self.fixture()
            df=pd.concat([df,df.iloc[[0]]],ignore_index=True)
            path=d+"/dataset.csv"
            df.drop(columns=["decision","exit"]).to_csv(path,index=False)
            with self.assertRaisesRegex(ValueError,"Duplicate"):load_dataset(path)
if __name__=="__main__":unittest.main()
