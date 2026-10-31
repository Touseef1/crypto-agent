'use client';
import Link from 'next/link';
import { useCallback,useEffect,useState } from 'react';
type Balance={asset:string;available:string};
type Order={id:string;symbol:string;side:string;quantity:string;price?:string;fee?:string;createdAt:string};
type Signal={action:string;price:number;ema20:number;ema50:number;rsi:number;macd:number;macdSignal:number};
export default function TradingTerminal(){
 const [symbol,setSymbol]=useState<'BTCUSDT'|'ETHUSDT'>('BTCUSDT');
 const [side,setSide]=useState<'BUY'|'SELL'>('BUY');
 const [quantity,setQuantity]=useState('0.0001');
 const [balances,setBalances]=useState<Balance[]>([]);
 const [orders,setOrders]=useState<Order[]>([]);
 const [signal,setSignal]=useState<Signal|null>(null);
 const [message,setMessage]=useState('');
 const [loading,setLoading]=useState(false);
 const load=useCallback(async()=>{
   try{
     const [a,b]=await Promise.all([fetch('/api/paper',{cache:'no-store'}),fetch('/api/paper/signal?symbol='+symbol,{cache:'no-store'})]);
     const account=await a.json(),indicators=await b.json();
     if(!a.ok)throw new Error(account.error||'Account unavailable');
     setBalances(account.balances);setOrders(account.orders);
     setSignal(b.ok?indicators.signal:null);
     if(!b.ok)setMessage(indicators.error||'Signals unavailable');
   }catch(e){setMessage(e instanceof Error?e.message:'Unable to load');}
 },[symbol]);
 useEffect(()=>{void load();},[load]);
 async function submit(){
   if(!window.confirm('Confirm '+side+' '+quantity+' '+symbol+' with virtual funds?'))return;
   setLoading(true);setMessage('');
   try{
     const key=crypto.randomUUID();
     const response=await fetch('/api/paper',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol,side,quantity,key})});
     const result=await response.json();
     if(!response.ok)throw new Error(result.error||'Order rejected');
     setMessage('Paper order filled at '+result.fillPrice+' USDT. No real order was sent.');
     await load();
   }catch(e){setMessage(e instanceof Error?e.message:'Order failed');}
   finally{setLoading(false);}
 }
 return <main className="min-h-screen bg-[#0b101a] text-slate-100 p-5 md:p-10"><div className="max-w-6xl mx-auto">
   <Link href="/dashboard" className="text-cyan-400 text-sm">← Dashboard</Link>
   <div className="flex flex-wrap justify-between items-center gap-4 mt-4"><div><h1 className="text-3xl font-bold">Paper Trading</h1><p className="text-sm text-slate-400 mt-2">Virtual funds only · no Binance order permissions · spot trading without shorts</p></div><span className="border border-emerald-700 text-emerald-400 rounded-full px-4 py-2 text-xs">PAPER MODE</span></div>
   <div className="grid md:grid-cols-3 gap-4 mt-8">{balances.map(b=><div key={b.asset} className="rounded-xl bg-[#111c2b] border border-slate-800 p-6"><p className="text-slate-400 text-sm">{b.asset} available</p><p className="text-2xl font-semibold mt-2">{Number(b.available).toLocaleString('en-US',{maximumFractionDigits:8})}</p></div>)}</div>
   <div className="grid lg:grid-cols-2 gap-5 mt-6">
     <section className="rounded-xl bg-[#111c2b] border border-slate-800 p-6"><h2 className="font-semibold text-lg">Manual paper order</h2>
       <label className="block text-sm mt-5 text-slate-300">Pair<select className="block w-full bg-slate-900 border border-slate-700 rounded-lg p-3 mt-2" value={symbol} onChange={e=>setSymbol(e.target.value as 'BTCUSDT'|'ETHUSDT')}><option value="BTCUSDT">BTC/USDT</option><option value="ETHUSDT">ETH/USDT</option></select></label>
       <label className="block text-sm mt-4 text-slate-300">Side<select className="block w-full bg-slate-900 border border-slate-700 rounded-lg p-3 mt-2" value={side} onChange={e=>setSide(e.target.value as 'BUY'|'SELL')}><option>BUY</option><option>SELL</option></select></label>
       <label className="block text-sm mt-4 text-slate-300">Quantity (BTC or ETH)<input type="number" min="0.00000001" step="0.00000001" value={quantity} onChange={e=>setQuantity(e.target.value)} className="block w-full bg-slate-900 border border-slate-700 rounded-lg p-3 mt-2"/></label>
       <p className="text-xs text-slate-400 mt-4">Simulated fee 0.10%, slippage 0.05%, maximum BUY size 20% of available USDT, minimum notional 10 USDT. Market quote is fetched at submission.</p>
       <button disabled={loading} onClick={()=>void submit()} className="bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 rounded-lg px-5 py-3 mt-5">{loading?'Submitting…':'Place paper '+side}</button>
       {message&&<p role="status" className="text-sm text-cyan-300 mt-4">{message}</p>}
     </section>
     <section className="rounded-xl bg-[#111c2b] border border-slate-800 p-6"><h2 className="font-semibold text-lg">RSI · EMA · MACD strategy monitor</h2>
       {signal?<div className="mt-5 space-y-3 text-sm"><p>Current rule-based signal: <strong className="text-cyan-300">{signal.action}</strong></p><p>RSI (14): {signal.rsi?.toFixed(2)}</p><p>EMA (20): {signal.ema20?.toFixed(2)}</p><p>EMA (50): {signal.ema50?.toFixed(2)}</p><p>MACD: {signal.macd?.toFixed(4)}</p><p>Signal line: {signal.macdSignal?.toFixed(4)}</p></div>:<p className="mt-5 text-slate-400">Indicators loading or unavailable.</p>}
       <p className="text-xs text-amber-300 mt-6">Signals are informational only. Automatic order execution is not enabled.</p>
       <button onClick={()=>void load()} className="mt-5 rounded-lg bg-slate-800 px-4 py-2 text-sm">Refresh account and signal</button>
     </section>
   </div>
   <section className="rounded-xl bg-[#111c2b] border border-slate-800 p-6 mt-6"><h2 className="font-semibold text-lg mb-5">Recent paper orders</h2><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-slate-400"><tr><th className="p-2">Time</th><th className="p-2">Pair</th><th className="p-2">Side</th><th className="p-2">Quantity</th><th className="p-2">Price</th><th className="p-2">Fee USDT</th></tr></thead><tbody>{orders.map(o=><tr key={o.id} className="border-t border-slate-800"><td className="p-2">{new Date(o.createdAt).toLocaleString()}</td><td className="p-2">{o.symbol}</td><td className="p-2">{o.side}</td><td className="p-2">{o.quantity}</td><td className="p-2">{o.price??'—'}</td><td className="p-2">{o.fee??'—'}</td></tr>)}</tbody></table></div>{!orders.length&&<p className="text-slate-400 text-sm mt-4">No paper orders yet.</p>}</section>
 </div></main>;
}
