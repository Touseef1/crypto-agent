import { NextRequest, NextResponse } from 'next/server';
import { getAdmin, sameOrigin } from '@/lib/auth';
import { binanceJson, parseCandles, SYMBOLS } from '@/lib/market';
import { prisma } from '@/lib/db';
export const dynamic = 'force-dynamic';
const durations: Record<string,number> = {'1m':60000,'5m':300000,'15m':900000,'1h':3600000,'4h':14400000,'1d':86400000};
const earliest = Date.UTC(2017,0,1); // Never claim exchange data exists from this date.
export async function POST(request:NextRequest) {
 if(!await getAdmin())return NextResponse.json({error:'Unauthorized'},{status:401});
 if(!sameOrigin(request))return NextResponse.json({error:'Invalid origin'},{status:403});
 const symbol=request.nextUrl.searchParams.get('symbol')??'BTCUSDT';
 const interval=request.nextUrl.searchParams.get('interval')??'5m';
 if(!SYMBOLS.includes(symbol as typeof SYMBOLS[number])||!durations[interval])return NextResponse.json({error:'Unsupported symbol or interval'},{status:400});
 const ms=durations[interval], now=Date.now();
 const fromRaw=request.nextUrl.searchParams.get('startTime');
 const start=fromRaw===null?Math.max(earliest,now-1000*ms):Number(fromRaw);
 if(!Number.isSafeInteger(start)||start<earliest||start>now)return NextResponse.json({error:'Invalid startTime'},{status:400});
 const endRaw=request.nextUrl.searchParams.get('endTime');
 const requestedEnd=endRaw===null?now:Number(endRaw);
 if(!Number.isSafeInteger(requestedEnd)||requestedEnd<=start||requestedEnd>now+86400000)return NextResponse.json({error:'Invalid endTime'},{status:400});
 const effectiveEnd=Math.min(now,requestedEnd);
 const end=Math.min(effectiveEnd-1,start+1000*ms-1);
 try {
  const q=new URLSearchParams({symbol,interval,limit:'1000',startTime:String(start),endTime:String(end)});
  const candles=parseCandles(await binanceJson('/api/v3/klines?'+q));
  const closed=candles.filter(c=>c.closeTime<now&&c.openTime>=start&&c.openTime<=end);
  const inserted=closed.length?await prisma.marketCandle.createMany({data:closed.map(c=>({symbol,interval,openTime:new Date(c.openTime),closeTime:new Date(c.closeTime),open:c.open.toString(),high:c.high.toString(),low:c.low.toString(),close:c.close.toString(),volume:c.volume.toString()})),skipDuplicates:true}):{count:0};
  return NextResponse.json({symbol,interval,startTime:start,nextStartTime:Math.min(start+1000*ms,effectiveEnd),received:candles.length,closed:closed.length,inserted:inserted.count,rangeEnd:end,hasMore:start+1000*ms<effectiveEnd,warning:closed.length===0?'No exchange candles returned in this window; historical availability may not extend this far.':undefined});
 }catch(e){return NextResponse.json({error:e instanceof Error?e.message:'Import failed'},{status:502});}
}
