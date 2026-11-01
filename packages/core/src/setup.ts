/** Pure trade setup calculations. No network, DB or exchange calls. */
export type Bar={openTime:number;closeTime:number;open:number;high:number;low:number;close:number;volume:number};
export type Bias='BUY'|'SELL'|'NO TRADE';
export type Signal={action:'BUY'|'SELL'|'HOLD';price:number;ema20?:number|null;ema50?:number|null};
export type Levels={entry:number;stopLoss:number;tp1:number;tp2:number;riskPerUnit:number;atr:number};
export type Sizing={quantity:number;notional:number;amountAtRisk:number;maxRisk:number;estimatedFees:number;estimatedSlippage:number;tp1Profit:number;tp2Profit:number;tp1Pct:number;tp2Pct:number};
export function atr(bars:Bar[],period=14):number|null{
 if(!Number.isInteger(period)||period<1||bars.length<period+1)return null;
 const ranges:number[]=[];
 for(let i=1;i<bars.length;i++){const b=bars[i],prev=bars[i-1];ranges.push(Math.max(b.high-b.low,Math.abs(b.high-prev.close),Math.abs(b.low-prev.close)));}
 let value=ranges.slice(0,period).reduce((a,b)=>a+b,0)/period;
 for(let i=period;i<ranges.length;i++)value=(value*(period-1)+ranges[i])/period;
 return Number.isFinite(value)&&value>0?value:null;
}
export function levels(entry:number,volatility:number,side:'BUY'|'SELL',multiple=2,rr1=1.5,rr2=3):Levels{
 if(![entry,volatility,multiple,rr1,rr2].every(Number.isFinite)||entry<=0||volatility<=0||multiple<=0||rr1<=0||rr2<=rr1)throw new Error('Invalid setup parameters');
 const riskPerUnit=volatility*multiple;
 const direction=side==='BUY'?1:-1;
 const stopLoss=entry-direction*riskPerUnit;
 if(stopLoss<=0)throw new Error('Stop loss would be nonpositive');
 return {entry,stopLoss,tp1:entry+direction*riskPerUnit*rr1,tp2:entry+direction*riskPerUnit*rr2,riskPerUnit,atr:volatility};
}
export function sizeLong(equity:number,availableUsdt:number,plan:Levels,feeRate=.001,slippageRate=.0005):Sizing{
 if(![equity,availableUsdt,feeRate,slippageRate].every(Number.isFinite)||equity<=0||availableUsdt<0||feeRate<0||slippageRate<0)throw new Error('Invalid risk inputs');
 const maxRisk=equity*.01;
 const buyPrice=plan.entry*(1+slippageRate);
 const unitRisk=Math.max(0,buyPrice-plan.stopLoss)+buyPrice*feeRate+plan.stopLoss*(feeRate+slippageRate);
 const quantity=Math.max(0,Math.min(maxRisk/unitRisk,equity*.2/buyPrice,availableUsdt/(buyPrice*(1+feeRate))));
 const notional=quantity*buyPrice;
 const estimatedFees=quantity*(buyPrice+plan.tp1)*feeRate;
 const estimatedSlippage=quantity*(plan.entry+plan.tp1)*slippageRate;
 const tpProfit=(target:number)=>quantity*(target*(1-slippageRate)*(1-feeRate)-buyPrice*(1+feeRate));
 const tp1Profit=tpProfit(plan.tp1),tp2Profit=tpProfit(plan.tp2);
 return {quantity,notional,amountAtRisk:quantity*unitRisk,maxRisk,estimatedFees,estimatedSlippage,tp1Profit,tp2Profit,tp1Pct:notional?tp1Profit/notional*100:0,tp2Pct:notional?tp2Profit/notional*100:0};
}
export function projection(lastClose:number,volatility:number,horizonBars:number,bias:'BUY'|'SELL'){
 if(!Number.isFinite(lastClose)||!Number.isFinite(volatility)||lastClose<=0||volatility<=0||!Number.isInteger(horizonBars)||horizonBars<1)throw new Error('Invalid projection');
 const spread=volatility*Math.sqrt(horizonBars);
 const midpoint=lastClose+(bias==='BUY'?1:-1)*spread*.5;
 return {midpoint,low:Math.max(0,midpoint-spread),high:midpoint+spread,horizonBars,label:'Projection, not a guarantee'};
}
export function decide(signal:Signal,trend:'UP'|'DOWN'|'UNKNOWN',hasPosition:boolean,reasons:string[]):{direction:Bias;reasons:string[]}{
 const issues=[...reasons];
 if(signal.action==='HOLD')issues.push('Strategy returned HOLD');
 if(signal.action==='BUY'&&trend!=='UP')issues.push('Higher-timeframe uptrend not confirmed');
 if(signal.action==='BUY'&&hasPosition)issues.push('Existing spot position: no additional entry');
 if(signal.action==='SELL'&&!hasPosition)issues.push('SELL cannot open a short position');
 if(issues.length)return {direction:'NO TRADE',reasons:issues};
 return {direction:signal.action,reasons:[]};
}
