'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import CandlestickChart from './candlestick-chart';

type Candle = { openTime:number; closeTime:number; open:number; high:number; low:number; close:number; volume:number };
type MarketResponse = { symbol:string; interval:string; candles:Candle[]; ticker:{bidPrice:string;askPrice:string}; fetchedAt:number };
type SymbolName = 'BTCUSDT' | 'ETHUSDT';
const symbols: SymbolName[] = ['BTCUSDT','ETHUSDT'];
type ChartInterval = '5m' | '10m' | '15m' | '1h';
const intervals: ChartInterval[] = ['5m','10m','15m','1h'];

export default function MarketTerminal() {
  const [symbol,setSymbol] = useState<SymbolName>('BTCUSDT');
  const [interval,setIntervalValue] = useState<ChartInterval>('5m');
  const [data,setData] = useState<MarketResponse|null>(null);
  const [price,setPrice] = useState<number|null>(null);
  const [connection,setConnection] = useState('Connecting');
  const [error,setError] = useState('');
  const [syncing,setSyncing] = useState(false);
  const [syncMessage,setSyncMessage] = useState('');
  const [importInterval,setImportInterval] = useState('5m');
  const [importYears,setImportYears] = useState('1');
  const [importMode,setImportMode] = useState<'year'|'duration'>('year');
  const [calendarYear,setCalendarYear] = useState(String(new Date().getUTCFullYear()-1));
  const stopImport=useRef(false);
  const load = useCallback(async () => {
    try {
      const response = await fetch('/api/market?symbol=' + symbol + '&interval=' + interval, {cache:'no-store'});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Market request failed');
      setData(result);setError('');setPrice(Number(result.candles.at(-1)?.close ?? 0));
    } catch(e) {setError(e instanceof Error ? e.message : 'Unable to fetch market data');}
  },[symbol,interval]);

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

  async function sync() {
    stopImport.current=false;setSyncing(true);setSyncMessage('');
    const now=Date.now();
    const earliest=Date.UTC(2017,0,1);
    const year=Number(calendarYear);
    if(importMode==='year' && (!Number.isInteger(year)||year<2017||year>new Date().getUTCFullYear())) {
      setSyncMessage('Choose a valid calendar year from 2017 to the current year.');setSyncing(false);return;
    }
    const requestedStart=importMode==='year'?Date.UTC(year,0,1):Math.max(earliest,now-Number(importYears)*365.25*86400000);
    const requestedEnd=importMode==='year'?Math.min(Date.UTC(year+1,0,1),now):now;
    const key='cryptobot-import-v2-'+symbol+'-'+importInterval+'-'+importMode+'-'+(importMode==='year'?calendarYear:importYears);
    const saved=Number(localStorage.getItem(key));
    let cursor=Number.isSafeInteger(saved)&&saved>=requestedStart&&saved<requestedEnd?saved:requestedStart;
    let batches=0,inserted=0,emptyWindows=0,retries=0;
    const sleep=(ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms));
    try {
      while(!stopImport.current && cursor<requestedEnd) {
        const params=new URLSearchParams({symbol,interval:importInterval,startTime:String(Math.floor(cursor)),endTime:String(requestedEnd)});
        let result: {startTime:number;nextStartTime:number;inserted:number;hasMore:boolean;closed:number;warning?:string}|null=null;
        for(let attempt=0;attempt<5 && !stopImport.current;attempt++) {
          try {
            const response=await fetch('/api/market/sync?'+params,{method:'POST'});
            const body=await response.json();
            if(!response.ok)throw new Error(body.error||'Import failed (HTTP '+response.status+')');
            result=body;
            break;
          } catch(e) {
            if(attempt===4)throw new Error('Import stopped at '+new Date(cursor).toISOString()+': '+(e instanceof Error?e.message:'Request failed')+'. Resume later; this window was not skipped.');
            retries++;
            setSyncMessage('Temporary error at '+new Date(cursor).toISOString().slice(0,10)+'. Retry '+(attempt+1)+'/4…');
            await sleep(Math.min(15000,1000*Math.pow(2,attempt)));
          }
        }
        if(stopImport.current)break;
        if(!result)throw new Error('No import response; progress preserved.');
        if(!Number.isSafeInteger(result.nextStartTime)||result.nextStartTime<=cursor||result.nextStartTime>requestedEnd)
          throw new Error('Invalid import cursor; progress preserved.');
        batches++;inserted+=result.inserted;
        if(result.closed===0)emptyWindows++;
        cursor=result.nextStartTime;
        localStorage.setItem(key,String(cursor));
        setSyncMessage('Saved '+inserted+' new candles in '+batches+' batches. Through '+new Date(cursor).toISOString().slice(0,16)+' UTC. Empty windows: '+emptyWindows+'. Retries: '+retries+'. '+(result.warning??''));
        if(!result.hasMore)break;
        await sleep(300);
      }
      if(stopImport.current) {
        setSyncMessage('Paused. Progress saved; choose the same symbol, interval and year to resume.');
      } else if(cursor>=requestedEnd) {
        localStorage.removeItem(key);
        setSyncMessage('Year/range import completed. '+inserted+' new candles; '+batches+' batches; '+emptyWindows+' empty windows; '+retries+' retries. Empty windows may indicate unavailable exchange history. Run the data-quality audit.');
      }
    } catch(e) {
      setSyncMessage((e instanceof Error?e.message:'Import failed')+' Progress saved; click Save to retry.');
    } finally {setSyncing(false);}
  }

  return <main className="min-h-screen bg-[#0b101a] text-slate-100 p-5 md:p-10">
    <div className="mx-auto max-w-6xl">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div><Link href="/dashboard" className="text-cyan-400 text-sm">← Dashboard</Link><h1 className="text-3xl font-bold mt-3">Live Markets</h1><p className="text-slate-400 text-sm mt-1">Binance public data · paper trading only · OHLC candlesticks</p></div>
        <span className="rounded-full border border-slate-700 px-4 py-2 text-sm">{connection}</span>
      </div>
      <div className="flex flex-wrap items-center gap-3 mt-8">
        {symbols.map(s => <button key={s} onClick={()=>{setSymbol(s);setData(null);setPrice(null);setSyncMessage('');}} className={`rounded-lg px-5 py-3 text-sm ${symbol===s?'bg-cyan-600 text-white':'bg-slate-800 text-slate-300'}`}>{s.replace('USDT','/USDT')}</button>)}
        <div className="flex flex-wrap gap-2" aria-label="Chart timeframe">{intervals.map(value => <button key={value} onClick={()=>{setIntervalValue(value);setData(null);}} aria-pressed={interval===value} className={`rounded-lg px-4 py-3 text-sm ${interval===value?'bg-cyan-600 text-white':'bg-slate-800 text-slate-300'}`}>{value}</button>)}</div>
        <button onClick={()=>void load()} className="rounded-lg bg-slate-800 px-4 py-3 text-sm">Refresh</button>
        <label className="text-sm text-slate-300">Import timeframe <select value={importInterval} onChange={e=>setImportInterval(e.target.value)} disabled={syncing} className="ml-2 bg-slate-800 rounded-lg p-3">{['1m','5m','15m','1h','4h','1d'].map(v=><option key={v}>{v}</option>)}</select></label>
        <label className="text-sm text-slate-300">Import range <select value={importMode} onChange={e=>setImportMode(e.target.value as 'year'|'duration')} disabled={syncing} className="ml-2 bg-slate-800 rounded-lg p-3"><option value="year">Specific calendar year</option><option value="duration">Last N years</option></select></label>
        {importMode==='year'
          ? <label className="text-sm text-slate-300">Year <select value={calendarYear} onChange={e=>setCalendarYear(e.target.value)} disabled={syncing} className="ml-2 bg-slate-800 rounded-lg p-3">{Array.from({length:new Date().getUTCFullYear()-2017+1},(_,i)=>String(new Date().getUTCFullYear()-i)).map(y=><option key={y} value={y}>{y}</option>)}</select></label>
          : <label className="text-sm text-slate-300">History <select value={importYears} onChange={e=>setImportYears(e.target.value)} disabled={syncing} className="ml-2 bg-slate-800 rounded-lg p-3">{['1','2','5','10','15'].map(v=><option key={v} value={v}>{v} years</option>)}</select></label>}
        <button onClick={()=>void sync()} disabled={syncing} className="rounded-lg bg-cyan-700 px-4 py-3 text-sm disabled:opacity-50">{syncing?'Importing…':'Save historical data / resume'}</button>
        {syncing&&<button onClick={()=>{stopImport.current=true;}} className="rounded-lg bg-slate-800 px-4 py-3 text-sm">Pause after batch</button>}
      </div>
      {error && <p role="alert" className="text-rose-400 mt-5">{error}</p>}
      <p className="text-xs text-slate-400 mt-3">Imports run while this page stays open. Closing the page pauses work; reopen it and use the same symbol, timeframe and history range to resume. A calendar year imports only January 1 through December 31 UTC (or through today for the current year). Temporary failures retry automatically; persistent failures pause without skipping data. Empty exchange windows are counted and may indicate unavailable history. Re-run the SQL audit to find gaps.</p>
      {syncMessage && <p role="status" className="text-cyan-300 mt-5">{syncMessage}</p>}
      <div className="grid md:grid-cols-3 gap-4 mt-7">
        <div className="md:col-span-2 rounded-2xl border border-slate-800 bg-[#111c2b] p-6"><p className="text-sm text-slate-400">Last traded price</p><p className="text-4xl font-bold mt-3">{price!==null&&Number.isFinite(price)?'$'+price.toLocaleString('en-US',{maximumFractionDigits:2}):'Loading…'}</p></div>
        <div className="rounded-2xl border border-slate-800 bg-[#111c2b] p-6"><p className="text-sm text-slate-400">Best bid / ask (REST snapshot)</p><p className="text-xl mt-3">{data ? `${Number(data.ticker.bidPrice).toFixed(2)} / ${Number(data.ticker.askPrice).toFixed(2)}` : 'Loading…'}</p><p className="text-xs text-slate-500 mt-3">Updates on refresh</p></div>
      </div>
      <section className="rounded-2xl border border-slate-800 bg-[#111c2b] p-6 mt-5">
        <h2 className="font-semibold">Candlestick price chart</h2><p className="text-xs text-slate-400 mt-2">5m, 15m and 1h are Binance candles. 10m combines complete pairs of 5m candles. Chart refreshes every minute.</p>
        <div className="mt-6"><CandlestickChart key={symbol+'-'+interval} candles={data?.candles ?? []} symbol={symbol} interval={interval}/></div>
        <p className="text-xs text-slate-500 mt-4">The latest Binance candle may still be forming. No orders are placed.</p>
      </section>
    </div>
  </main>;
}
