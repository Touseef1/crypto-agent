'use client';
import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';

type Candle = { openTime:number; closeTime:number; open:number; high:number; low:number; close:number; volume:number };
type MarketResponse = { symbol:string; interval:string; candles:Candle[]; ticker:{bidPrice:string;askPrice:string}; fetchedAt:number };
type SymbolName = 'BTCUSDT' | 'ETHUSDT';
const symbols: SymbolName[] = ['BTCUSDT','ETHUSDT'];

export default function MarketTerminal() {
  const [symbol,setSymbol] = useState<SymbolName>('BTCUSDT');
  const [data,setData] = useState<MarketResponse|null>(null);
  const [price,setPrice] = useState<number|null>(null);
  const [connection,setConnection] = useState('Connecting');
  const [error,setError] = useState('');
  const [syncing,setSyncing] = useState(false);
  const [syncMessage,setSyncMessage] = useState('');
  const load = useCallback(async () => {
    try {
      const response = await fetch('/api/market?symbol=' + symbol, {cache:'no-store'});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Market request failed');
      setData(result);setError('');setPrice(Number(result.candles.at(-1)?.close ?? 0));
    } catch(e) {setError(e instanceof Error ? e.message : 'Unable to fetch market data');}
  },[symbol]);

  useEffect(() => {
    void load();
    const refresh = setInterval(() => void load(), 60000);
    return () => clearInterval(refresh);
  },[load]);

  useEffect(() => {
    let ws: WebSocket|null = null;
    let retry: ReturnType<typeof setTimeout>|null = null;
    let stopped = false;
    const connect = () => {
      if (stopped) return;
      setConnection('Connecting');
      ws = new WebSocket('wss://stream.binance.com:9443/ws/' + symbol.toLowerCase() + '@trade');
      ws.onopen = () => setConnection('Live');
      ws.onmessage = (event) => {
        try {const msg = JSON.parse(event.data) as {p?:string};if(msg.p) setPrice(Number(msg.p));}catch{}
      };
      ws.onerror = () => setConnection('WebSocket unavailable');
      ws.onclose = () => {setConnection('Reconnecting');if(!stopped)retry=setTimeout(connect,5000);};
    };
    connect();
    return () => {stopped=true;if(retry)clearTimeout(retry);ws?.close();};
  },[symbol]);

  const points = useMemo(() => {
    const candles = data?.candles.slice(-100) ?? [];
    if (!candles.length) return '';
    const values = candles.map(c => c.close);
    const low = Math.min(...values),high = Math.max(...values);
    const spread = high-low || 1;
    return values.map((value,i) => `${(i/(values.length-1 || 1))*900},${260-((value-low)/spread)*240}`).join(' ');
  },[data]);

  async function sync() {
    setSyncing(true);setSyncMessage('');
    try {
      const response = await fetch('/api/market/sync?symbol='+symbol,{method:'POST'});
      const result = await response.json();
      if(!response.ok)throw new Error(result.error || 'Sync failed');
      setSyncMessage(`Processed ${result.closed} closed candles; duplicates skipped.`);
    } catch(e) {setSyncMessage(e instanceof Error?e.message:'Sync failed');}
    finally {setSyncing(false);}
  }

  return <main className="min-h-screen bg-[#0b101a] text-slate-100 p-5 md:p-10">
    <div className="mx-auto max-w-6xl">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div><Link href="/dashboard" className="text-cyan-400 text-sm">← Dashboard</Link><h1 className="text-3xl font-bold mt-3">Live Markets</h1><p className="text-slate-400 text-sm mt-1">Binance public data · paper trading only · 5-minute candles</p></div>
        <span className="rounded-full border border-slate-700 px-4 py-2 text-sm">{connection}</span>
      </div>
      <div className="flex flex-wrap items-center gap-3 mt-8">
        {symbols.map(s => <button key={s} onClick={()=>{setSymbol(s);setData(null);setPrice(null);setSyncMessage('');}} className={`rounded-lg px-5 py-3 text-sm ${symbol===s?'bg-cyan-600 text-white':'bg-slate-800 text-slate-300'}`}>{s.replace('USDT','/USDT')}</button>)}
        <button onClick={()=>void load()} className="rounded-lg bg-slate-800 px-4 py-3 text-sm">Refresh</button>
        <button onClick={()=>void sync()} disabled={syncing} className="rounded-lg bg-slate-800 px-4 py-3 text-sm disabled:opacity-50">{syncing?'Syncing…':'Save historical candles'}</button>
      </div>
      {error && <p role="alert" className="text-rose-400 mt-5">{error}</p>}
      {syncMessage && <p role="status" className="text-cyan-300 mt-5">{syncMessage}</p>}
      <div className="grid md:grid-cols-3 gap-4 mt-7">
        <div className="md:col-span-2 rounded-2xl border border-slate-800 bg-[#111c2b] p-6"><p className="text-sm text-slate-400">Last traded price</p><p className="text-4xl font-bold mt-3">{price!==null&&Number.isFinite(price)?'$'+price.toLocaleString('en-US',{maximumFractionDigits:2}):'Loading…'}</p></div>
        <div className="rounded-2xl border border-slate-800 bg-[#111c2b] p-6"><p className="text-sm text-slate-400">Best bid / ask (REST snapshot)</p><p className="text-xl mt-3">{data ? `${Number(data.ticker.bidPrice).toFixed(2)} / ${Number(data.ticker.askPrice).toFixed(2)}` : 'Loading…'}</p><p className="text-xs text-slate-500 mt-3">Updates on refresh</p></div>
      </div>
      <section className="rounded-2xl border border-slate-800 bg-[#111c2b] p-6 mt-5">
        <h2 className="font-semibold">Recent 5-minute closing prices</h2><p className="text-xs text-slate-400 mt-2">Last 100 candles · chart refreshes every minute</p>
        <svg viewBox="0 0 900 280" role="img" aria-label={symbol+' recent price line chart'} className="w-full mt-5">
          <polyline points={points} fill="none" stroke="#22d3ee" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round"/>
        </svg>
        <p className="text-xs text-slate-500">Historical prices are indicative. This page does not place orders.</p>
      </section>
    </div>
  </main>;
}
