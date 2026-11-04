'use client';
import Link from 'next/link';
import {useState} from 'react';

type Fill={symbol:string;side:string;time:number;quantity:number;price:number;fee:number};
type Result={initialBalance:number;finalBalance:number;returnPct:number;maxDrawdownPct:number;
 winRatePct:number;wins:number;losses:number;candlesUsed:number;buyHoldPct:Record<string,number>;
 trades:Fill[];equityCurve:{time:number;equity:number}[];methodology:string};
export default function PortfolioTerminal(){
 const [balance,setBalance]=useState(1000);
 const [allocation,setAllocation]=useState(0.2);
 const [fee,setFee]=useState(0.1);
 const [slippage,setSlippage]=useState(0.05);
 const [result,setResult]=useState<Result|null>(null);
 const [loading,setLoading]=useState(false);
 const [error,setError]=useState('');
 async function run(){
  setLoading(true);setError('');setResult(null);
  try{
   const response=await fetch('/api/portfolio-backtest',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({initialBalance:balance,allocation,feeRate:fee/100,slippageRate:slippage/100})
   });
   const body=await response.json();
   if(!response.ok)throw new Error(body.error||'Simulation failed');
   setResult(body);
  }catch(e){setError(e instanceof Error?e.message:'Simulation failed');}
  finally{setLoading(false);}
 }
 const curve=result?.equityCurve??[];
 const min=curve.length?Math.min(...curve.map(p=>p.equity)):0;
 const max=curve.length?Math.max(...curve.map(p=>p.equity)):1;
 const points=curve.map((p,i)=>`${i/Math.max(1,curve.length-1)*900},${230-(p.equity-min)/Math.max(max-min,0.000001)*210}`).join(' ');
 return <main className="min-h-screen bg-[#0b101a] text-slate-100 p-5 md:p-10">
  <div className="max-w-6xl mx-auto">
   <Link href="/backtesting" className="text-cyan-400 text-sm">← Backtesting Lab</Link>
   <h1 className="text-3xl font-bold mt-4">Phase 5 · Portfolio Backtesting</h1>
   <p className="text-slate-300 mt-3">Simulate BTC/USDT and ETH/USDT together with shared virtual cash and a maximum 20% allocation per entry.</p>
   <div className="mt-4 rounded-xl border border-amber-700 bg-amber-950/30 p-4 text-sm text-amber-200">
    <strong>Research-only baseline.</strong> This version uses the website's existing RSI/EMA/MACD rules, not the Python ML models.
    Spot long-only: no shorts, leverage, futures funding or real orders. The simulation uses up to 1,000 recent 5-minute candles per market.
   </div>
   <section className="mt-6 rounded-xl border border-slate-700 bg-[#111c2b] p-5">
    <div className="grid gap-4 md:grid-cols-4">
     <label className="text-sm">Virtual balance (USDT)<input type="number" min={100} max={1000000} value={balance} onChange={e=>setBalance(Number(e.target.value))} className="block mt-2 w-full rounded bg-slate-900 border border-slate-700 p-3"/></label>
     <label className="text-sm">Allocation per entry<select value={allocation} onChange={e=>setAllocation(Number(e.target.value))} className="block mt-2 w-full rounded bg-slate-900 border border-slate-700 p-3"><option value={0.05}>5%</option><option value={0.1}>10%</option><option value={0.2}>20%</option></select></label>
     <label className="text-sm">Fee per side (%)<input type="number" min={0} max={1} step={0.01} value={fee} onChange={e=>setFee(Number(e.target.value))} className="block mt-2 w-full rounded bg-slate-900 border border-slate-700 p-3"/></label>
     <label className="text-sm">Slippage per side (%)<input type="number" min={0} max={1} step={0.01} value={slippage} onChange={e=>setSlippage(Number(e.target.value))} className="block mt-2 w-full rounded bg-slate-900 border border-slate-700 p-3"/></label>
    </div>
    <p className="text-xs text-slate-400 mt-4">Estimated round-trip cost ≈ {(2*(fee+slippage)).toFixed(2)}%. Signals use closed candles; orders execute at the next candle open. Shared cash prevents overspending.</p>
    <button onClick={()=>void run()} disabled={loading} className="mt-5 rounded bg-cyan-600 px-5 py-3 disabled:opacity-50">{loading?'Running simulation…':'Run portfolio backtest'}</button>
    {error&&<p role="alert" className="mt-3 text-rose-400">{error}</p>}
   </section>
   {result&&<>
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-6">
     {([['Final equity',result.finalBalance.toFixed(2)+' USDT'],['Total return',result.returnPct.toFixed(2)+'%'],['Max drawdown',result.maxDrawdownPct.toFixed(2)+'%'],['Win rate',result.winRatePct.toFixed(1)+'%']] as const).map(([label,value])=><div key={label} className="rounded-xl border border-slate-700 bg-[#111c2b] p-4"><p className="text-sm text-slate-400">{label}</p><p className="text-xl font-bold mt-2">{value}</p></div>)}
    </div>
    <section className="rounded-xl border border-slate-700 bg-[#111c2b] p-5 mt-5">
     <h2 className="text-lg font-semibold">Virtual account equity</h2>
     <svg viewBox="0 0 900 240" role="img" aria-label="Simulated portfolio equity" className="w-full mt-4"><polyline points={points} fill="none" stroke="#22d3ee" strokeWidth={2}/></svg>
     <p className="text-sm text-slate-400 mt-3">BTC buy-and-hold: {result.buyHoldPct.BTCUSDT.toFixed(2)}% · ETH buy-and-hold: {result.buyHoldPct.ETHUSDT.toFixed(2)}% · No-trade: 0% · {result.candlesUsed} candles · {result.trades.length} fills</p>
    </section>
    <section className="rounded-xl border border-slate-700 bg-[#111c2b] p-5 mt-5">
     <h2 className="text-lg font-semibold mb-3">Simulated fills</h2>
     <div className="overflow-x-auto"><table className="w-full text-sm text-left"><thead><tr>{['Time','Market','Side','Quantity','Price','Fee'].map(h=><th key={h} className="p-2">{h}</th>)}</tr></thead><tbody>{result.trades.map((t,i)=><tr key={i} className="border-t border-slate-800"><td className="p-2">{new Date(t.time).toLocaleString()}</td><td className="p-2">{t.symbol}</td><td className="p-2">{t.side}</td><td className="p-2">{t.quantity.toFixed(6)}</td><td className="p-2">{t.price.toFixed(2)}</td><td className="p-2">{t.fee.toFixed(4)}</td></tr>)}</tbody></table></div>
     {!result.trades.length&&<p className="text-slate-400 text-sm">No signals met the entry rules during this period.</p>}
    </section>
   </>}
   <p className="mt-6 text-xs text-amber-300">This page does not use the final ML holdout or imply ML profitability. Historical results do not predict future performance.</p>
  </div>
 </main>;
}
