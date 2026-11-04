"""Phase 2: offline walk-forward LightGBM research. No exchange orders or DB writes."""
import argparse
import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from ml.phase1 import FEATURE_COLUMNS

def load_dataset(path):
    path=Path(path)
    df=pd.read_csv(path)
    required=set(FEATURE_COLUMNS)|{"decision_candle_open_utc","exit_candle_open_utc","side","outcome"}
    if not required.issubset(df.columns):raise ValueError("Missing columns: "+str(sorted(required-set(df.columns))))
    df["decision"]=pd.to_datetime(df["decision_candle_open_utc"],utc=True,errors="raise")
    df["exit"]=pd.to_datetime(df["exit_candle_open_utc"],utc=True,errors="raise")
    if df[["decision","exit"]].isna().any().any():raise ValueError("Invalid timestamps")
    if df.duplicated(["decision","side"]).any():raise ValueError("Duplicate decisions/sides")
    if not df["decision"].is_monotonic_increasing:raise ValueError("Dataset must be time ordered")
    if not df["side"].isin([-1,1]).all() or not df["outcome"].isin([-1,0,1]).all():raise ValueError("Invalid labels")
    if (df["exit"]<=df["decision"]).any():raise ValueError("Exit must follow decision")
    values=df[FEATURE_COLUMNS].to_numpy(dtype=float)
    if not np.isfinite(values).all():raise ValueError("Invalid feature values")
    return df

def partitions(df,train_fraction,cal_fraction,test_fraction,embargo_bars=24):
    """Split on unique decision timestamps; purge labels crossing boundaries.
    Embargo after train/calibration and calibration/test boundaries.
    """
    if not 0<train_fraction<1 or not 0<cal_fraction<1 or not 0<test_fraction<1:
        raise ValueError("Invalid split fractions")
    times=df["decision"].drop_duplicates().sort_values().reset_index(drop=True)
    n=len(times)
    a=int(n*train_fraction);b=int(n*(train_fraction+cal_fraction));c=int(n*(train_fraction+cal_fraction+test_fraction))
    if not 0<a<b<c<=n:raise ValueError("Empty or overlapping split")
    gap=pd.Timedelta(minutes=5*embargo_bars)
    t_cal=times.iloc[a];t_test=times.iloc[b]
    train=df[(df["decision"]<t_cal-gap)&(df["exit"]<t_cal-gap)]
    cal=df[(df["decision"]>=t_cal)&(df["decision"]<t_test-gap)&(df["exit"]<t_test-gap)]
    test=df[(df["decision"]>=t_test)&(df["decision"]<=times.iloc[c-1])]
    if min(len(train),len(cal),len(test))<100:raise ValueError("Insufficient samples after purge")
    if train["exit"].max()>=cal["decision"].min() or cal["exit"].max()>=test["decision"].min():
        raise ValueError("Temporal leakage across partitions")
    return train,cal,test

def metrics(y,prob):
    y=np.asarray(y,dtype=int);p=np.clip(np.asarray(prob,dtype=float),1e-6,1-1e-6)
    result={"n":int(len(y)),"tp_rate":float(y.mean()),"brier":float(brier_score_loss(y,p)),"log_loss":float(log_loss(y,p,labels=[0,1]))}
    result["auc"]=float(roc_auc_score(y,p)) if len(np.unique(y))==2 else None
    return result

def train_one(train,cal,test,seed):
    y_train=(train["outcome"]==1).astype(int)
    y_cal=(cal["outcome"]==1).astype(int)
    y_test=(test["outcome"]==1).astype(int)
    if y_train.nunique()<2 or y_cal.nunique()<2:raise ValueError("Training/calibration requires both classes")
    model=LGBMClassifier(n_estimators=250,learning_rate=.04,num_leaves=15,max_depth=6,min_child_samples=100,
                         colsample_bytree=.8,subsample=.8,subsample_freq=1,reg_lambda=2,
                         random_state=seed,n_jobs=4,verbosity=-1)
    model.fit(train[FEATURE_COLUMNS],y_train)
    cal_raw=model.predict_proba(cal[FEATURE_COLUMNS])[:,1]
    calibrator=IsotonicRegression(y_min=0,y_max=1,out_of_bounds="clip")
    calibrator.fit(cal_raw,y_cal)
    test_raw=model.predict_proba(test[FEATURE_COLUMNS])[:,1]
    calibrated=calibrator.predict(test_raw)
    baseline=np.full(len(test),y_train.mean())
    # A transparent heuristic baseline: oversold long / overbought short.
    rsi=test["rsi14"].to_numpy()
    side=int(test["side"].iloc[0])
    heuristic=np.where((rsi<30) if side==1 else (rsi>70),.6,.4)
    return model,calibrator,{
        "calibrated":metrics(y_test,calibrated),
        "uncalibrated":metrics(y_test,test_raw),
        "constant_baseline":metrics(y_test,baseline),
        "rsi_heuristic_baseline":metrics(y_test,heuristic),
        "probability_mean":float(calibrated.mean()),
        "calibration_count":len(cal),
        "training_count":len(train),
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--symbol",choices=["BTCUSDT","ETHUSDT"],required=True)
    parser.add_argument("--data-dir",default="ml/data")
    parser.add_argument("--output-dir",default="ml/artifacts/phase2")
    parser.add_argument("--seed",type=int,default=42)
    args=parser.parse_args()
    path=Path(args.data_dir)/(args.symbol.lower()+"_5m_phase1.csv")
    df=load_dataset(path)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    out=Path(args.output_dir)/args.symbol.lower()
    out.mkdir(parents=True,exist_ok=True)
    report={"symbol":args.symbol,"dataset_sha256":digest,"feature_columns":FEATURE_COLUMNS,
            "target":"outcome == 1 (take profit before stop or timeout)","folds":[],"seed":args.seed,
            "note":"Research classification only; metrics are not trading returns. No trading costs included."}
    # Expanding-window folds: train 50/60/70%, calibration next 10%, test following 10%.
    # All folds have independent future tests; fold test windows do not overlap.
    for fold,frac in enumerate((.50,.60,.70),1):
        record={"fold":fold,"train_fraction":frac,"sides":{}}
        for side,label in ((1,"long"),(-1,"short")):
            subset=df[df["side"]==side].copy()
            train,cal,test=partitions(subset,frac,.10,.10)
            model,calibrator,result=train_one(train,cal,test,args.seed)
            record["sides"][label]={"train_start":train["decision"].min().isoformat(),
                "train_end":train["decision"].max().isoformat(),
                "cal_start":cal["decision"].min().isoformat(),
                "cal_end":cal["decision"].max().isoformat(),
                "test_start":test["decision"].min().isoformat(),
                "test_end":test["decision"].max().isoformat(),**result}
            # Store the most recent fold for later research, NOT live inference.
            if fold==3:
                joblib.dump({"model":model,"calibrator":calibrator,"features":FEATURE_COLUMNS,
                             "side":side,"dataset_sha256":digest},out/(label+"_research.joblib"))
        report["folds"].append(record)
        print(f"Fold {fold}: "+", ".join(
            f"{side} Brier={record['sides'][side]['calibrated']['brier']:.4f} baseline={record['sides'][side]['constant_baseline']['brier']:.4f}"
            for side in ("long","short")),flush=True)
    (out/"evaluation.json").write_text(json.dumps(report,indent=2)+"\n")
    print("Evaluation saved to",out/"evaluation.json")
if __name__=="__main__":main()
