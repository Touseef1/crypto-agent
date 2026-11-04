"""Step 1 only: label-shuffle negative control, class balance, and ATR/cost checks.

Research-only. Reads Phase 1 CSVs; does not modify DB, trading, or UI.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import roc_auc_score
from ml.phase1 import FEATURE_COLUMNS
from ml.phase2 import load_dataset, partitions

def cost_roundtrip(fee,slippage):
    if min(fee,slippage)<0:raise ValueError("Costs must be nonnegative")
    return 2*(fee+slippage)

def atr_cost_stats(df,fee,slippage,tp_atr=2.0):
    cost=cost_roundtrip(fee,slippage)
    atr=df["atr14_pct"].to_numpy(float)
    tp=tp_atr*atr
    return {"round_trip_cost_pct":100*cost,"median_atr_pct":100*float(np.median(atr)),
            "median_tp_distance_pct":100*float(np.median(tp)),
            "median_tp_to_cost":float(np.median(tp)/cost) if cost else None,
            "tp_less_than_3x_cost_fraction":float(np.mean(tp<3*cost)) if cost else 0.0,
            "median_tp_less_than_3x_cost":bool(np.median(tp)<3*cost) if cost else False}

def shuffled_control(train,test,seed):
    """Shuffle TRAIN targets only; test remains genuine future labels."""
    rng=np.random.default_rng(seed)
    y_train=(train["outcome"].to_numpy()==1).astype(int)
    shuffled=rng.permutation(y_train)
    y_test=(test["outcome"].to_numpy()==1).astype(int)
    if len(np.unique(shuffled))<2 or len(np.unique(y_test))<2:
        raise ValueError("AUC requires both classes")
    model=LGBMClassifier(n_estimators=250,learning_rate=.04,num_leaves=15,max_depth=6,
                         min_child_samples=100,colsample_bytree=.8,subsample=.8,
                         subsample_freq=1,reg_lambda=2,random_state=seed,n_jobs=4,verbosity=-1)
    model.fit(train[FEATURE_COLUMNS],shuffled)
    prob=model.predict_proba(test[FEATURE_COLUMNS])[:,1]
    return float(roc_auc_score(y_test,prob))

def evaluate(df,seed,repeats):
    output={"rows":len(df),"unique_decisions":int(df["decision"].nunique()),"sides":{}}
    for side,name in ((1,"long"),(-1,"short")):
        subset=df.loc[df["side"]==side].copy()
        counts=subset["outcome"].value_counts().reindex([-1,0,1],fill_value=0)
        folds=[]
        for fold,frac in enumerate((.50,.60,.70),1):
            train,cal,test=partitions(subset,frac,.10,.10,embargo_bars=24)
            # We use the exact same chronology as Phase 2. The calibration
            # window is left unused by this negative control.
            aucs=[shuffled_control(train,test,seed+100*fold+k) for k in range(repeats)]
            folds.append({"fold":fold,"train_rows":len(train),"test_rows":len(test),
                          "test_start":test["decision"].min().isoformat(),
                          "test_end":test["decision"].max().isoformat(),
                          "shuffled_label_auc":aucs,"mean_auc":float(np.mean(aucs))})
        output["sides"][name]={"class_counts":{"sl":int(counts[-1]),"timeout":int(counts[0]),"tp":int(counts[1])},
                               "class_percent":{"sl":float(counts[-1]/len(subset)*100),
                                                "timeout":float(counts[0]/len(subset)*100),
                                                "tp":float(counts[1]/len(subset)*100)},
                               "folds":folds}
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--symbol",choices=["BTCUSDT","ETHUSDT"],required=True)
    p.add_argument("--data-dir",default="ml/data")
    p.add_argument("--output-dir",default="ml/artifacts/phase2/sanity")
    p.add_argument("--fee",type=float,default=.001,help="fee per side, decimal fraction")
    p.add_argument("--slippage",type=float,default=.0005,help="slippage per side, decimal fraction")
    p.add_argument("--lower-fee",type=float,default=.0005)
    p.add_argument("--lower-slippage",type=float,default=.0002)
    p.add_argument("--repeats",type=int,default=3)
    p.add_argument("--seed",type=int,default=42)
    args=p.parse_args()
    if args.repeats<1:raise ValueError("repeats must be positive")
    path=Path(args.data_dir)/(args.symbol.lower()+"_5m_phase1.csv")
    df=load_dataset(path)
    report={"symbol":args.symbol,"step":1,"dataset":str(path),
            "note":"Negative control only. Shuffled TRAIN labels, real chronological TEST labels. AUC near 0.5 expected but not guaranteed in finite samples. No profitability claim.",
            "cost_scenarios":{"primary":atr_cost_stats(df,args.fee,args.slippage),
                              "lower":atr_cost_stats(df,args.lower_fee,args.lower_slippage)},
            "control":evaluate(df,args.seed,args.repeats)}
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    dest=out/(args.symbol.lower()+"_step1.json")
    dest.write_text(json.dumps(report,indent=2)+"\n")
    print("Symbol:",args.symbol,"Rows:",len(df))
    for name,scenario in report["cost_scenarios"].items():
        print(name,"round-trip cost %:",round(scenario["round_trip_cost_pct"],4),
              "median ATR %:",round(scenario["median_atr_pct"],4),
              "median TP/cost:",round(scenario["median_tp_to_cost"],3) if scenario["median_tp_to_cost"] is not None else "N/A",
              "median TP < 3x cost:",scenario["median_tp_less_than_3x_cost"])
    for name,side in report["control"]["sides"].items():
        print(name,"class balance:",side["class_counts"])
        for fold in side["folds"]:
            print("  Fold",fold["fold"],"shuffled-label AUCs:",[round(v,4) for v in fold["shuffled_label_auc"]])
    print("Saved:",dest)
if __name__=="__main__":main()
