'use client';
import { useMemo, useState } from 'react';

export type ChartCandle = {openTime:number;closeTime:number;open:number;high:number;low:number;close:number;volume:number};
type Props = {candles:ChartCandle[];symbol:string;interval:string};
const W=1000,H=440,LEFT=14,RIGHT=88,TOP=20,BOTTOM=48;
export default function CandlestickChart({candles,symbol,interval}:Props){
  const [hover,setHover]=useState<number|null>(null);
  const shown=useMemo(()=>candles.slice(-90),[candles]);
  const min=shown.length?Math.min(...shown.map(c=>c.low)):0;
  const max=shown.length?Math.max(...shown.map(c=>c.high)):1;
  const pad=(max-min)*0.08||max*0.002||1;
  const low=min-pad,high=max+pad;
  const plotW=W-LEFT-RIGHT,plotH=H-TOP-BOTTOM;
  const y=(price:number)=>TOP+(high-price)/(high-low)*plotH;
  const step=plotW/Math.max(shown.length,1);
  const candleWidth=Math.max(2,Math.min(step*.65,12));
  const selected=hover!==null?shown[hover]:shown.at(-1);
  const format=(n:number)=>n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
  return <div>
    <div className="flex flex-wrap justify-between gap-3 text-xs text-slate-400 mb-2">
      <span>{symbol.replace('USDT','/USDT')} · {interval} · {shown.length} candles</span>
      {selected&&<span>O {format(selected.open)} · H {format(selected.high)} · L {format(selected.low)} · C {format(selected.close)} · Vol {selected.volume.toFixed(3)}</span>}
    </div>
    {!shown.length?<p className="py-20 text-center text-slate-400">No candle data available.</p>:
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={symbol+' '+interval+' OHLC candlestick chart'} className="w-full min-w-[560px]">
        {Array.from({length:6},(_,i)=>{const value=low+(high-low)*i/5;const yy=y(value);return <g key={i}><line x1={LEFT} x2={W-RIGHT} y1={yy} y2={yy} stroke="#334155" strokeDasharray="3 6"/><text x={W-RIGHT+8} y={yy+4} fill="#94a3b8" fontSize="12">{format(value)}</text></g>;})}
        {shown.map((c,i)=>{const x=LEFT+(i+.5)*step;const up=c.close>=c.open;const color=up?'#22c55e':'#ef4444';const top=y(Math.max(c.open,c.close));const height=Math.max(1,Math.abs(y(c.open)-y(c.close)));return <g key={c.openTime} onMouseEnter={()=>setHover(i)} onMouseLeave={()=>setHover(null)}>
          <line x1={x} x2={x} y1={y(c.high)} y2={y(c.low)} stroke={color} strokeWidth="1.5"/>
          <rect x={x-candleWidth/2} y={top} width={candleWidth} height={height} fill={color}/>
          <rect x={x-step/2} y={TOP} width={step} height={plotH} fill="transparent"/>
        </g>;})}
        {Array.from({length:6},(_,i)=>{const idx=Math.min(shown.length-1,Math.floor(i*(shown.length-1)/5));const c=shown[idx];return <text key={i} x={LEFT+(idx+.5)*step} y={H-17} textAnchor="middle" fill="#94a3b8" fontSize="12">{new Date(c.openTime).toLocaleString('en-US',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'UTC',hour12:false})}</text>;})}
      </svg>
    </div>}
    <div className="flex flex-wrap items-center gap-5 text-xs text-slate-400 mt-2"><span><span className="text-green-400">■</span> Price increased</span><span><span className="text-red-400">■</span> Price decreased</span><span>Times shown in UTC · hover candles for OHLC</span></div>
  </div>;
}
