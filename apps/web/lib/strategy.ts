import type { Candle } from '@/lib/market';

export function ema(values:number[], period:number):number[] {
  if(values.length<period)return [];
  const multiplier=2/(period+1);
  let current=values.slice(0,period).reduce((a,b)=>a+b,0)/period;
  const result=Array(period-1).fill(NaN) as number[];
  result.push(current);
  for(let i=period;i<values.length;i++){current=(values[i]-current)*multiplier+current;result.push(current);}
  return result;
}
export function rsi(values:number[], period=14):number|null {
  if(values.length<=period)return null;
  let gain=0,loss=0;
  for(let i=1;i<=period;i++){const diff=values[i]-values[i-1];gain+=Math.max(diff,0);loss+=Math.max(-diff,0);}
  gain/=period;loss/=period;
  for(let i=period+1;i<values.length;i++){const diff=values[i]-values[i-1];gain=(gain*(period-1)+Math.max(diff,0))/period;loss=(loss*(period-1)+Math.max(-diff,0))/period;}
  return loss===0?100:100-100/(1+gain/loss);
}
export function signalFromCandles(candles:Candle[]) {
  const values=candles.map(c=>c.close);
  if(values.length<60)throw new Error('At least 60 closed candles are required');
  const fast=ema(values,12),slow=ema(values,26);
  const macd=fast.map((v,i)=>v-slow[i]);
  const macdValid=macd.filter(Number.isFinite);
  const signalLine=ema(macdValid,9).at(-1);
  const macdValue=macd.at(-1);
  const rsiValue=rsi(values);
  const ema20=ema(values,20).at(-1);
  const ema50=ema(values,50).at(-1);
  const latest=values.at(-1)!;
  if([signalLine,macdValue,rsiValue,ema20,ema50].some(x=>x===undefined||!Number.isFinite(x)))throw new Error('Indicators unavailable');
  // Conservative trend/momentum filter; no guaranteed profitability.
  const buy=latest>ema20! && ema20!>ema50! && rsiValue!>=50 && rsiValue!<=65 && macdValue!>signalLine!;
  const sell=latest<ema20! && rsiValue!<45 && macdValue!<signalLine!;
  return {action:buy?'BUY':sell?'SELL':'HOLD',price:latest,ema20,ema50,rsi:rsiValue,macd:macdValue,macdSignal:signalLine,candleCloseTime:candles.at(-1)!.closeTime};
}
