"""Phase 1: offline, read-only feature and triple-barrier dataset generation."""
import argparse
import json
import os
from pathlib import Path
import numpy as np
import pandas as pd

STEP = pd.Timedelta(minutes=5)
FEATURE_COLUMNS = ["ret_1","ret_3","ret_12","ema20_gap","ema50_gap","ema20_50_gap","rsi14","macd","macd_signal","macd_hist","atr14_pct","volatility_12","volatility_48","volume_ratio20","range_pct","hour_sin","hour_cos","h1_ret","h1_ema20_gap","h4_ret","h4_ema20_gap"]

def indicators(frame):
    x = frame.copy()
    close, high, low, vol = (x[k].astype(float) for k in ("close","high","low","volume"))
    x["ret_1"] = close.pct_change()
    x["ret_3"] = close.pct_change(3)
    x["ret_12"] = close.pct_change(12)
    e20 = close.ewm(span=20, adjust=False, min_periods=20).mean()
    e50 = close.ewm(span=50, adjust=False, min_periods=50).mean()
    x["ema20_gap"] = close / e20 - 1
    x["ema50_gap"] = close / e50 - 1
    x["ema20_50_gap"] = e20 / e50 - 1
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = gain / loss.replace(0,np.nan)
    x["rsi14"] = 100 - 100/(1+rs)
    x.loc[(loss==0)&(gain>0),"rsi14"] = 100
    x.loc[(loss==0)&(gain==0),"rsi14"] = 50
    fast = close.ewm(span=12, adjust=False, min_periods=12).mean()
    slow = close.ewm(span=26, adjust=False, min_periods=26).mean()
    x["macd"] = (fast-slow)/close
    x["macd_signal"] = (fast-slow).ewm(span=9, adjust=False, min_periods=9).mean()/close
    x["macd_hist"] = x["macd"]-x["macd_signal"]
    prev = close.shift()
    tr = pd.concat([high-low,(high-prev).abs(),(low-prev).abs()],axis=1).max(axis=1)
    x["atr14_pct"] = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()/close
    x["volatility_12"] = x["ret_1"].rolling(12).std()
    x["volatility_48"] = x["ret_1"].rolling(48).std()
    x["volume_ratio20"] = vol / vol.rolling(20).mean().replace(0,np.nan)
    x["range_pct"] = (high-low)/close
    hour = x.index.hour + x.index.minute/60
    x["hour_sin"] = np.sin(2*np.pi*hour/24)
    x["hour_cos"] = np.cos(2*np.pi*hour/24)
    return x

def validate(frame):
    if frame.empty: raise ValueError("No candles")
    if frame.index.tz is None: raise ValueError("UTC timezone-aware timestamps required")
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing: raise ValueError("Duplicate or unordered candles")
    if not (frame.index.to_series().diff().dropna()==STEP).all(): raise ValueError("Missing 5m candles: repair gaps before feature generation")
    if not ((frame.index.minute%5==0)&(frame.index.second==0)).all(): raise ValueError("Misaligned 5m timestamps")
    if not np.isfinite(frame[["open","high","low","close","volume"]].to_numpy(dtype=float)).all(): raise ValueError("Nonfinite OHLCV")
    if not ((frame["low"]<=frame[["open","close"]].min(axis=1))&(frame["high"]>=frame[["open","close"]].max(axis=1))&(frame["low"]<=frame["high"])&(frame["low"]>0)&(frame["volume"]>=0)).all(): raise ValueError("Invalid OHLCV")

def add_higher_timeframes(frame):
    x=indicators(frame)
    # Each 5m index is an OPEN time; resample at 5m candle CLOSE times.
    at_close=frame.copy()
    at_close.index=at_close.index+STEP
    for freq,prefix in (("1h","h1"),("4h","h4")):
        h=at_close.resample(freq,label="right",closed="right",origin="epoch").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"})
        counts=at_close["close"].resample(freq,label="right",closed="right",origin="epoch").count()
        h=h[counts==int(pd.Timedelta(freq)/STEP)]
        h["ret"]=h["close"].pct_change()
        h["ema20_gap"]=h["close"]/h["close"].ewm(span=20,adjust=False,min_periods=20).mean()-1
        # Merge against decision time (end of current 5m bar), backward only.
        lookup=pd.DataFrame({"decision_time":x.index+STEP})
        merged=pd.merge_asof(lookup.sort_values("decision_time"),h[["ret","ema20_gap"]].reset_index().rename(columns={"openTime":"bar_close","index":"bar_close"}).sort_values("bar_close"),left_on="decision_time",right_on="bar_close",direction="backward")
        x[prefix+"_ret"]=merged["ret"].to_numpy()
        x[prefix+"_ema20_gap"]=merged["ema20_gap"].to_numpy()
    return x

def triple_barrier(frame, features, horizon=24, tp_atr=2., sl_atr=1.5):
    """Decision at candle i close, entry at i+1 open; evaluate i+1..i+horizon.
    A candle touching TP and SL simultaneously is labeled loss (conservative).
    Outcomes: 1 TP, -1 SL, 0 timeout; last horizon rows omitted.
    """
    if horizon<1 or tp_atr<=0 or sl_atr<=0: raise ValueError("Invalid barrier parameters")
    rows=[]
    high=frame["high"].to_numpy(float);low=frame["low"].to_numpy(float);op=frame["open"].to_numpy(float)
    atr=features["atr14_pct"].to_numpy(float)*frame["close"].to_numpy(float)
    for i in range(len(frame)-horizon):
        if not np.isfinite(atr[i]) or atr[i]<=0: continue
        entry=op[i+1]
        for side in (1,-1):
            tp=entry+side*tp_atr*atr[i];sl=entry-side*sl_atr*atr[i]
            outcome=0;hit=i+horizon
            for j in range(i+1,i+horizon+1):
                take=(high[j]>=tp if side==1 else low[j]<=tp)
                stop=(low[j]<=sl if side==1 else high[j]>=sl)
                if stop or take:
                    outcome=-1 if stop else 1
                    hit=j
                    break
            rows.append((i,side,outcome,hit,entry,tp,sl))
    return pd.DataFrame(rows,columns=["row","side","outcome","exit_row","entry","take_profit","stop_loss"])

def load_mysql(symbol):
    import pymysql
    from urllib.parse import urlparse,unquote
    url=os.environ.get("DATABASE_URL")
    if not url: raise ValueError("DATABASE_URL is required (do not commit credentials)")
    u=urlparse(url)
    if u.scheme!="mysql":raise ValueError("DATABASE_URL must use mysql://")
    conn=pymysql.connect(host=u.hostname,port=u.port or 3306,user=unquote(u.username or ""),password=unquote(u.password or ""),database=u.path.lstrip("/"),cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute("SET time_zone = '+00:00'")
            cur.execute("SELECT openTime, `open`, high, low, `close`, volume FROM MarketCandle WHERE symbol=%s AND `interval`='5m' ORDER BY openTime",(symbol,))
            rows=cur.fetchall()
    finally:conn.close()
    if not rows:raise ValueError("No stored 5m candles for "+symbol)
    df=pd.DataFrame(rows)
    df["openTime"]=pd.to_datetime(df["openTime"],utc=True)
    return df.set_index("openTime").astype(float)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--symbol",choices=["BTCUSDT","ETHUSDT"],required=True)
    p.add_argument("--output-dir",default="ml/data")
    p.add_argument("--horizon",type=int,default=24)
    p.add_argument("--tp-atr",type=float,default=2.)
    p.add_argument("--sl-atr",type=float,default=1.5)
    args=p.parse_args()
    frame=load_mysql(args.symbol)\n    # Exclude a potentially still-forming last bar; all inputs must be closed.\n    now=pd.Timestamp.now(tz="UTC")\n    frame=frame.loc[frame.index+STEP<=now]\n    validate(frame)
    features=add_higher_timeframes(frame)
    labels=triple_barrier(frame,features,args.horizon,args.tp_atr,args.sl_atr)
    if labels.empty:raise ValueError("Not enough history to generate labels")
    rows=labels["row"].to_numpy()
    dataset=features.iloc[rows][FEATURE_COLUMNS].reset_index().rename(columns={"openTime":"decision_candle_open_utc"})
    dataset["side"]=labels["side"].to_numpy()
    dataset["outcome"]=labels["outcome"].to_numpy()
    dataset["exit_candle_open_utc"]=frame.index.take(labels["exit_row"].to_numpy())
    dataset["entry"]=labels["entry"].to_numpy()
    dataset["take_profit"]=labels["take_profit"].to_numpy()
    dataset["stop_loss"]=labels["stop_loss"].to_numpy()
    dataset=dataset.replace([np.inf,-np.inf],np.nan).dropna(subset=FEATURE_COLUMNS)
    if dataset.empty:raise ValueError("No complete feature rows; need more warm-up data")
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    name=args.symbol.lower()+"_5m_phase1"
    dataset.to_csv(out/(name+".csv"),index=False)
    meta={"symbol":args.symbol,"rows":len(dataset),"source_candles":len(frame),"first_candle_utc":frame.index[0].isoformat(),"last_candle_utc":frame.index[-1].isoformat(),"feature_columns":FEATURE_COLUMNS,"horizon_5m_bars":args.horizon,"tp_atr":args.tp_atr,"sl_atr":args.sl_atr,"entry":"next candle open","tie_policy":"stop loss first","outcomes":{"1":"TP","-1":"SL","0":"timeout"}}
    (out/(name+".json")).write_text(json.dumps(meta,indent=2)+"\n")
    print(json.dumps({"output":str(out/(name+".csv")),"rows":len(dataset),"source_candles":len(frame)},indent=2))
if __name__=="__main__":main()
