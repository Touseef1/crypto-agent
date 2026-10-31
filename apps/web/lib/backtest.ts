import type { Candle } from '@/lib/market';
import { signalFromCandles } from '@/lib/strategy';

export type SimTrade={side:'BUY'|'SELL';quantity:number;price:number;fee:number;executedAt:number};
export type EquityPoint={time:number;equity:number};
export type BacktestOptions={initialBalance:number;feeRate:number;slippageRate:number;allocation:number};
export function runBacktest(candles:Candle[],options:BacktestOptions){
  if(candles.length<65)throw new Error('At least 65 closed candles required');
  const {initialBalance,feeRate,slippageRate,allocation}=options;
  if(!Number.isFinite(initialBalance)||initialBalance<=0||feeRate<0||slippageRate<0||allocation<=0||allocation>1)throw new Error('Invalid simulation settings');
  let cash=initialBalance,coin=0,entryCost=0,peak=initialBalance,maxDrawdown=0,wins=0,losses=0;
  const trades:SimTrade[]=[],equityCurve:EquityPoint[]=[];
  // A signal is computed from candles ending at i-1; orders execute at candle i OPEN.
  // This prevents using the same candle's closing price to trade in its past.
  for(let i=60;i<candles.length;i++){
    const prior=candles.slice(0,i);
    const current=candles[i];
    const decision=signalFromCandles(prior).action;
    if(decision==='BUY'&&coin===0){
      const price=current.open*(1+slippageRate);
      const budget=cash*allocation;
      const quantity=budget/(price*(1+feeRate));
      const fee=quantity*price*feeRate;
      if(quantity*price>=10&&quantity>0){
        cash-=quantity*price+fee;coin=quantity;entryCost=quantity*price+fee;
        trades.push({side:'BUY',quantity,price,fee,executedAt:current.openTime});
      }
    }else if(decision==='SELL'&&coin>0){
      const price=current.open*(1-slippageRate);
      const fee=coin*price*feeRate;
      const proceeds=coin*price-fee;
      if(proceeds>entryCost)wins++;else losses++;
      cash+=proceeds;trades.push({side:'SELL',quantity:coin,price,fee,executedAt:current.openTime});
      coin=0;entryCost=0;
    }
    const equity=cash+coin*current.close;
    peak=Math.max(peak,equity);
    maxDrawdown=Math.max(maxDrawdown,(peak-equity)/peak);
    equityCurve.push({time:current.closeTime,equity});
  }
  const finalBalance=cash+coin*candles.at(-1)!.close;
  const startPrice=candles[60].open,endPrice=candles.at(-1)!.close;
  return {trades,equityCurve,finalBalance,returnPct:(finalBalance/initialBalance-1)*100,
    buyHoldPct:(endPrice/startPrice-1)*100,maxDrawdownPct:maxDrawdown*100,
    wins,losses,winRatePct:wins+losses?wins/(wins+losses)*100:0,
    openQuantity:coin,candlesUsed:candles.length,
    startTime:candles[0].openTime,endTime:candles.at(-1)!.closeTime};
}
