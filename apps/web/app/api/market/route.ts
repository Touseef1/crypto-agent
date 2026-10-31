import { NextRequest, NextResponse } from 'next/server';
import { getAdmin } from '@/lib/auth';
import { aggregateTenMinuteCandles, binanceJson, fetchCandles, validInterval, validSymbol } from '@/lib/market';
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  if (!await getAdmin()) return NextResponse.json({error:'Unauthorized'}, {status:401});
  const symbol = validSymbol(request.nextUrl.searchParams.get('symbol'));
  const interval = validInterval(request.nextUrl.searchParams.get('interval'));
  if (!interval) return NextResponse.json({error:'Unsupported interval'}, {status:400});
  try {
    const [rawCandles, ticker] = await Promise.all([
      fetchCandles(symbol, interval === '10m' ? 400 : 200, undefined, interval === '10m' ? '5m' : interval),
      binanceJson('/api/v3/ticker/bookTicker?symbol=' + symbol)
    ]);
    const candles = interval === '10m' ? aggregateTenMinuteCandles(rawCandles) : rawCandles;
    return NextResponse.json({symbol, interval, candles, ticker, fetchedAt:Date.now()},
      {headers:{'Cache-Control':'no-store'}});
  } catch (error) {
    return NextResponse.json({error:error instanceof Error ? error.message : 'Market data unavailable'}, {status:502});
  }
}
