import {describe,it,expect} from 'vitest';
import {atr,levels,sizeLong,projection,decide,type Bar} from '../packages/core/src/setup';
const bars:Bar[]=Array.from({length:70},(_,i)=>({openTime:i*300000,closeTime:(i+1)*300000-1,open:100+i,high:102+i,low:99+i,close:101+i,volume:10}));
describe('trade setup math',()=>{
 it('computes ATR from closed bars',()=>{expect(atr(bars,14)).toBeCloseTo(3)});
 it('calculates stop and R targets',()=>{const p=levels(100,2,'BUY',2,1.5,3);expect(p.stopLoss).toBe(96);expect(p.tp1).toBe(106);expect(p.tp2).toBe(112)});
 it('limits long sizing by 1% risk and 20% notional',()=>{const p=levels(100,2,'BUY');const s=sizeLong(1000,1000,p);expect(s.amountAtRisk).toBeLessThanOrEqual(10.00001);expect(s.notional).toBeLessThanOrEqual(200.00001);expect(s.tp1Profit).toBeGreaterThan(0)});
 it('includes fees and slippage in net P&L',()=>{const p=levels(100,2,'BUY');const s=sizeLong(1000,1000,p);expect(s.tp1Profit).toBeLessThan(s.quantity*(p.tp1-p.entry))});
 it('does not allow a sell to open a short',()=>{expect(decide({action:'SELL',price:100},'DOWN',false,[]).direction).toBe('NO TRADE')});
 it('blocks trades when risk checks fail',()=>{const result=decide({action:'BUY',price:100},'UP',false,['Stale candle']);expect(result.direction).toBe('NO TRADE');expect(result.reasons).toContain('Stale candle')});
 it('uses only supplied closed bars for ATR',()=>{const before=atr(bars);const extra={...bars.at(-1)!,openTime:70*300000,closeTime:71*300000-1,high:10000};expect(atr(bars)).toBe(before);expect(atr([...bars,extra])).not.toBe(before)});
 it('returns a bounded ATR scenario',()=>{const p=projection(100,2,4,'BUY');expect(p.low).toBeLessThan(p.midpoint);expect(p.high).toBeGreaterThan(p.midpoint)});
});
