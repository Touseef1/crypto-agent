import {prisma} from '@/lib/db';
import {binanceJson,parseCandles,type Candle,type SymbolName} from '@/lib/market';
import {ema,signalFromCandles} from '@/lib/strategy';
import {atr,levels,projection,sizeLong,decide} from '@cryptobot/core';
export type SetupInterval='5m'|'15m'|'1h'|'4h';
const MS:Record<SetupInterval,number>={'5m':300000,'15m':900000,'1h':3600000,'4h':14400000};
export async function closedBars(symbol:SymbolName,interval:SetupInterval,now=Date.now()):Promise<Candle[]>{
 const q=new URLSearchParams({symbol,interval,limit:'250'});
 const rows=parseCandles(await binanceJson('/api/v3/klines?'+q));
 return rows.filter(c=>c.closeTime<now);
}
export async function getSetup(userId:string,symbol:SymbolName,interval:SetupInterval){
 const now=Date.now();
 const candles=await closedBars(symbol,interval,now);
 const last=candles.at(-1);
 if(!last||candles.length<65)throw new Error('Not enough closed candles');
 const higher:SetupInterval=interval==='5m'||interval==='15m'?'1h':'4h';
 const trendCandles=await closedBars(symbol,higher,now);
 const trendValues=trendCandles.map(c=>c.close);
 const e20=ema(trendValues,20).at(-1),e50=ema(trendValues,50).at(-1);
 const trend=trendValues.length>=50&&e20!==undefined&&e50!==undefined?(e20>e50?'UP':'DOWN'):'UNKNOWN';
 const signal=signalFromCandles(candles);
 const account=await prisma.tradingAccount.findFirst({where:{userId,mode:'PAPER'},include:{balances:true,positions:{where:{status:'OPEN'}}}});
 if(!account)throw new Error('Paper account not initialized');
 const usdt=Number(account.balances.find(b=>b.asset==='USDT')?.available??0);
 const asset=symbol==='BTCUSDT'?'BTC':'ETH';
 const held=Number(account.balances.find(b=>b.asset===asset)?.available??0);
 const hasPosition=held>0;
 const reasons:string[]=[];
 if(now-last.closeTime>MS[interval]*2)reasons.push('Stale closed candle');
 if(account.positions.length>=2)reasons.push('Maximum open positions reached');
 // No reliable daily starting-equity snapshot yet: fail closed rather than assume zero loss.
 const dayStart=new Date();dayStart.setUTCHours(0,0,0,0);
 const snapshot=await prisma.equitySnapshot.findFirst({where:{accountId:account.id,capturedAt:{gte:dayStart}},orderBy:{capturedAt:'asc'}});
 if(!snapshot)reasons.push('Daily loss limit cannot be verified: missing equity snapshot');
 const decision=decide(signal,trend,hasPosition,reasons);
 const vol=atr(candles);
 const direction=decision.direction;
 const plan=vol&&signal.action!=='HOLD'?levels(last.close,vol,signal.action):null;
 const equity=usdt+Number(account.balances.find(b=>b.asset==='BTC')?.available??0)*(symbol==='BTCUSDT'?last.close:0)+Number(account.balances.find(b=>b.asset==='ETH')?.available??0)*(symbol==='ETHUSDT'?last.close:0);
 const sizing=plan&&signal.action==='BUY'?sizeLong(equity,usdt,plan):null;
 if(sizing&&sizing.notional<10){decision.direction='NO TRADE';decision.reasons.push('Order value below 10 USDT minimum');}
 const projected=vol&&signal.action!=='HOLD'?projection(last.close,vol,5,signal.action):null;
 return {symbol,interval,higherInterval:higher,lastClosedTime:last.closeTime,candles,signal,trend,direction:decision.direction,reasons:decision.reasons,levels:plan,projection:projected,sizing,position:hasPosition?{asset,quantity:held,unrealizedPnl:null,reason:'Cost basis unavailable: no verified open position record'}:null,
 historicalStats:null,statsWarning:'Exact-setup backtest sample statistics are unavailable; no accuracy estimate shown.',disclaimer:'Paper trading simulation. Projections are scenarios based on the strategy and past data, not guaranteed outcomes.'};
}
