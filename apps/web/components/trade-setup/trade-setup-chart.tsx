'use client';
import {useEffect,useRef} from 'react';
import {createChart,CandlestickSeries,LineSeries,LineStyle,type IChartApi,type ISeriesApi,type UTCTimestamp} from 'lightweight-charts';
type Candle={openTime:number;open:number;high:number;low:number;close:number};
type Level={entry:number;stopLoss:number;tp1:number;tp2:number};
type Projection={midpoint:number;low:number;high:number;label:string};
type Props={candles:Candle[];levels:Level|null;projection:Projection|null};
export default function TradeSetupChart({candles,levels,projection}:Props){
 const host=useRef<HTMLDivElement>(null),chart=useRef<IChartApi|null>(null),series=useRef<ISeriesApi<'Candlestick'>|null>(null);
 useEffect(()=>{if(!host.current)return;const node=host.current;
 const c=createChart(node,{height:450,autoSize:true,layout:{background:{color:'#0f172a'},textColor:'#cbd5e1'},grid:{vertLines:{color:'#1e293b'},horzLines:{color:'#1e293b'}},timeScale:{timeVisible:true}});
 const s=c.addSeries(CandlestickSeries,{upColor:'#22c55e',downColor:'#ef4444',borderVisible:false,wickUpColor:'#22c55e',wickDownColor:'#ef4444'});
 chart.current=c;series.current=s;return()=>{chart.current=null;series.current=null;c.remove()};},[]);
 useEffect(()=>{const c=chart.current,s=series.current;if(!c||!s||!candles.length)return;
 const data=candles.map(v=>({time:Math.floor(v.openTime/1000) as UTCTimestamp,open:v.open,high:v.high,low:v.low,close:v.close}));
 s.setData(data);c.timeScale().fitContent();
 const lines=[];
 if(levels){for(const [name,price,color] of [['Entry',levels.entry,'#e2e8f0'],['SL',levels.stopLoss,'#ef4444'],['TP1',levels.tp1,'#22c55e'],['TP2',levels.tp2,'#16a34a']] as const){lines.push(s.createPriceLine({price,color,lineWidth:2,lineStyle:LineStyle.Dashed,axisLabelVisible:true,title:name}));}}
 const overlays:ISeriesApi<'Line'>[]=[];
 if(projection){const last=candles.at(-1)!;const start=Math.floor(last.openTime/1000) as UTCTimestamp;const step=candles.length>1?Math.floor((last.openTime-candles.at(-2)!.openTime)/1000):300;
 const end=(Number(start)+step*5) as UTCTimestamp;
 for(const [value,color,style] of [[projection.midpoint,'#a78bfa',LineStyle.Dotted],[projection.low,'#ef4444',LineStyle.Dotted],[projection.high,'#22c55e',LineStyle.Dotted]] as const){const line=c.addSeries(LineSeries,{color,lineWidth:2,lineStyle:style,priceLineVisible:false,lastValueVisible:false});line.setData([{time:start,value:last.close},{time:end,value}]);overlays.push(line);}}
 return()=>{for(const l of lines)s.removePriceLine(l);for(const overlay of overlays)c.removeSeries(overlay)};
 },[candles,levels,projection]);
 return <div><div ref={host} aria-label="Trade setup candlestick chart" className="w-full min-h-[450px]"/><div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-500"><span>Entry: gray dashed</span><span>Stop loss: red dashed</span><span>Targets: green dashed</span><span>Projection: purple dotted, range: green/red</span></div><p className="mt-2 text-xs text-amber-600">Projection, not a guarantee. Lines are scenario levels, not executed orders.</p></div>;
}
