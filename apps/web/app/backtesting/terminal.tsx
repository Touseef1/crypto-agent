'use client';
import Link from 'next/link';
import {useEffect,useState} from 'react';
type Result={runId:string;finalBalance:number;returnPct:number;buyHoldPct:number;maxDrawdownPct:number;winRatePct:number;wins:number;losses:number;openQuantity:number;candlesUsed:number;trades:{side:string;quantity:number;price:number;fee:number;executedAt:number}[];equityCurve:{time:number;equity:number}[]};
type History={id:string;symbol:string;createdAt:string;initialBalance:string;finalBalance:string|null;trades:number};
export default function BacktestTerminal(){
 const [symbol,setSymbol]=useState<'BTCUSDT'|'ETHUSDT'>('BTCUSDT');
 const [balance,setBalance]=useState(1000);
 const [allocation,setAllocation]=useState(0.2);
 const [loading,setLoading]=useState(false);
 const [error,setError]=useState('');
 const [result,setResult]=useState<Result|null>(null);
 const [history,setHistory]=useState<History[]>([]);
 async function refresh(){try{const r=await fetch('/api/backtests',{cache:'no-store'});if(r.ok)setHistory((await r.json()).runs);}catch{}}
 useEffect(()=>{void refresh();},[]);
 async function run(){setLoading(true);setError('');setResult(null);
  try{const r=await fetch('/api/backtests',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol,initialBalance:balance,allocation})});const data=await r.json();if(!r.ok)throw new Error(data.error||'Backtest failed');setResult(data);await refresh();}
  catch(e){setError(e instanceof Error?e.message:'Backtest failed');}finally{setLoading(false);}
 }
 const curve=result?.equityCurve??[];
 const lo=curve.length?Math.min(...curve.map(p=>p.equity)):0,hi=curve.length?Math.max(...curve.map(p=>p.equity)):1;
 const pts=curve.map((p,i)=>`${i/Math.max(1,curve.length-1)*900},${240-(p.equity-lo)/Math.max(hi-lo,0.00001)*220}`).join(' ');
 return <main className="min-h-screen bg-[#0b101a] text-slate-100 p-5 md:p-10"><div className="max-w-6xl mx-auto">
 <Link href="/dashboard" className="text-cyan-400 text-sm">← Dashboard</Link>
 <h1 className="text-3xl font-bold mt-4">Strategy Backtesting</h1><p className="text-slate-400 text-sm mt-2">RSI · EMA · MACD · closed 5-minute candles · historical simulation only</p>
 <section className="rounded-2xl border border-slate-800 bg-[#111c2b] p-6 mt-7">
  <div className="grid md:grid-cols-3 gap-4">
   <label className="text-sm">Trading pair<select className="block mt-2 w-full bg-slate-900 border border-slate-700 rounded-lg p-3" value={symbol} onChange={e=>setSymbol(e.target.value as 'BTCUSDT'|'ETHUSDT')}><option value="BTCUSDT">BTC/USDT</option><option value="ETHUSDT">ETH/USDT</option></select></label>
   <label className="text-sm">Starting virtual USDT<input type="number" min="100" max="1000000" value={balance} onChange={e=>setBalance(Number(e.target.value))} className="block mt-2 w-full bg-slate-900 border border-slate-700 rounded-lg p-3"/></label>
   <label className="text-sm">Allocation per entry<select className="block mt-2 w-full bg-slate-900 border border-slate-700 rounded-lg p-3" value={allocation} onChange={e=>setAllocation(Number(e.target.value))}><option value={0.05}>5%</option><option value={0.1}>10%</option><option value={0.2}>20%</option></select></label>
  </div>
  <p className="text-xs text-slate-400 mt-4">Next-candle open execution, 0.10% fee, 0.05% adverse slippage, long-only, no leverage. Results use saved continuous MySQL candles; no look-ahead trading at the signal candle's close.</p>
  <button disabled={loading} onClick={()=>void run()} className="bg-cyan-600 rounded-lg px-6 py-3 mt-5 disabled:opacity-50">{loading?'Running…':'Run backtest'}</button>
  {error&&<p role="alert" className="text-rose-400 mt-4">{error}</p>}
 </section>
 {result&&<><div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-6">{[['Final equity',result.finalBalance.toFixed(2)+' USDT'],['Return',result.returnPct.toFixed(2)+'%'],['Max drawdown',result.maxDrawdownPct.toFixed(2)+'%'],['Win rate',result.winRatePct.toFixed(1)+'%']].map(([label,value])=><div key={label} className="rounded-xl border border-slate-800 bg-[#111c2b] p-5"><p className="text-sm text-slate-400">{label}</p><p className="text-2xl font-bold mt-2">{value}</p></div>)}</div>
 <section className="rounded-xl border border-slate-800 bg-[#111c2b] p-6 mt-5"><h2 className="font-semibold">Equity curve</h2><svg viewBox="0 0 900 250" role="img" aria-label="Backtest equity curve" className="w-full mt-5"><polyline points={pts} stroke="#22d3ee" strokeWidth="2" fill="none"/></svg><p className="text-sm text-slate-400 mt-3">{result.candlesUsed} candles · {result.trades.length} fills · {result.wins} winning exits · {result.losses} losing exits · Buy-and-hold {result.buyHoldPct.toFixed(2)}% · Open quantity {result.openQuantity.toFixed(8)}</p></section>
 <section className="rounded-xl border border-slate-800 bg-[#111c2b] p-6 mt-5"><h2 className="font-semibold mb-4">Simulated fills</h2><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{['Time','Side','Quantity','Price','Fee'].map(h=><th key={h} className="p-2">{h}</th>)}</tr></thead><tbody>{result.trades.map((t,i)=><tr key={i} className="border-t border-slate-800"><td className="p-2">{new Date(t.executedAt).toLocaleString()}</td><td className="p-2">{t.side}</td><td className="p-2">{t.quantity.toFixed(8)}</td><td className="p-2">{t.price.toFixed(2)}</td><td className="p-2">{t.fee.toFixed(4)}</td></tr>)}</tbody></table></div></section></>}
 <section className="rounded-xl border border-slate-800 bg-[#111c2b] p-6 mt-6"><h2 className="font-semibold mb-4">Saved backtest runs</h2>{history.length?history.map(h=><p key={h.id} className="text-sm border-t border-slate-800 py-3">{new Date(h.createdAt).toLocaleString()} · {h.symbol} · {h.initialBalance} → {h.finalBalance??'—'} USDT · {h.trades} fills</p>):<p className="text-sm text-slate-400">No backtests saved yet.</p>}</section>
 <p className="text-xs text-amber-300 mt-6">Historical results do not predict future performance. The simulator excludes spread variability, latency, liquidity constraints and market regime changes.</p>
 </div></main>;
}
