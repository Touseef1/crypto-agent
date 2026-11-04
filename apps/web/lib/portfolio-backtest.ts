import type {Candle} from '@/lib/market';
import {signalFromCandles} from '@/lib/strategy';

export type PortfolioCandle=Candle & {symbol:'BTCUSDT'|'ETHUSDT'};
export type PortfolioFill={symbol:string;side:'BUY'|'SELL';time:number;quantity:number;price:number;fee:number;cashAfter:number};
export type PortfolioOptions={initialBalance:number;allocation:number;feeRate:number;slippageRate:number};
const INTERVAL=300000;

/** Research-only shared-cash spot simulator. Existing RSI/EMA/MACD signals;
 * this is NOT an integration of Python ML predictions or a futures simulator. */
export function runPortfolioBacktest(data:Record<'BTCUSDT'|'ETHUSDT',Candle[]>,o:PortfolioOptions){
 if(!Number.isFinite(o.initialBalance)||o.initialBalance<100||o.initialBalance>1000000||
 !Number.isFinite(o.allocation)||o.allocation<=0||o.allocation>0.2||
 !Number.isFinite(o.feeRate)||o.feeRate<0||o.feeRate>0.01||
 !Number.isFinite(o.slippageRate)||o.slippageRate<0||o.slippageRate>0.01)throw new Error('Invalid portfolio settings');
 const symbols=['BTCUSDT','ETHUSDT'] as const;
 const btc=data.BTCUSDT,eth=data.ETHUSDT;
 if(btc.length<65||eth.length<65)throw new Error('At least 65 candles per market are required');
 const lookup=new Map(eth.map(c=>[c.openTime,c]));
 const joined=btc.filter(c=>lookup.has(c.openTime));
 if(joined.length<65)throw new Error('Insufficient shared historical period');
 for(let i=1;i<joined.length;i++)if(joined[i].openTime-joined[i-1].openTime!==INTERVAL)throw new Error('Shared candles contain gaps');
 const aligned:{BTCUSDT:Candle[];ETHUSDT:Candle[]}={BTCUSDT:joined,ETHUSDT:joined.map(c=>lookup.get(c.openTime)!)};
 let cash=o.initialBalance,peak=cash,drawdown=0,wins=0,losses=0;
 const holdings:{[K in typeof symbols[number]]:{quantity:number;entryCost:number}}={
 BTCUSDT:{quantity:0,entryCost:0},ETHUSDT:{quantity:0,entryCost:0}};
 const fills:PortfolioFill[]=[];
 const equityCurve:{time:number;equity:number}[]=[];
 for(let i=60;i<joined.length;i++){
  // Exit before entry, but only signals known at the previous close.
  const signals=symbols.map(symbol=>({symbol,action:signalFromCandles(aligned[symbol].slice(0,i)).action}));
  for(const {symbol,action} of signals){
   if(action!=='SELL'||holdings[symbol].quantity<=0)continue;
   const p=aligned[symbol][i].open*(1-o.slippageRate);
   const h=holdings[symbol],fee=h.quantity*p*o.feeRate,proceeds=h.quantity*p-fee;
   if(proceeds>h.entryCost)wins++;else losses++;
   cash+=proceeds;fills.push({symbol,side:'SELL',time:joined[i].openTime,quantity:h.quantity,price:p,fee,cashAfter:cash});
   holdings[symbol]={quantity:0,entryCost:0};
  }
  const equityAtOpen=cash+symbols.reduce((sum,s)=>sum+holdings[s].quantity*aligned[s][i].open,0);
  for(const {symbol,action} of signals){
   if(action!=='BUY'||holdings[symbol].quantity>0)continue;
   const p=aligned[symbol][i].open*(1+o.slippageRate);
   const budget=Math.min(cash,equityAtOpen*o.allocation);
   const quantity=budget/(p*(1+o.feeRate)),fee=quantity*p*o.feeRate;
   if(quantity*p<10||!Number.isFinite(quantity))continue;
   const total=quantity*p+fee;
   cash-=total;holdings[symbol]={quantity,entryCost:total};
   fills.push({symbol,side:'BUY',time:joined[i].openTime,quantity,price:p,fee,cashAfter:cash});
  }
  const equity=cash+symbols.reduce((sum,s)=>sum+holdings[s].quantity*aligned[s][i].close,0);
  peak=Math.max(peak,equity);drawdown=Math.max(drawdown,(peak-equity)/peak);
  equityCurve.push({time:joined[i].closeTime,equity});
 }
 const finalBalance=equityCurve.at(-1)!.equity;
 const buyHoldPct=Object.fromEntries(symbols.map(s=>[s,(aligned[s].at(-1)!.close/aligned[s][60].open-1)*100]));
 return {initialBalance:o.initialBalance,finalBalance,returnPct:(finalBalance/o.initialBalance-1)*100,
 maxDrawdownPct:drawdown*100,winRatePct:wins+losses?wins/(wins+losses)*100:0,wins,losses,
 trades:fills,equityCurve,buyHoldPct,openPositions:holdings,candlesUsed:joined.length,
 startTime:joined[0].openTime,endTime:joined.at(-1)!.closeTime,
 methodology:'RSI_EMA_MACD_SPOT_BASELINE_NOT_ML'};
}
