import { NextRequest, NextResponse } from 'next/server';
import { getAdmin } from '@/lib/auth';
import { binanceJson, fetchCandles, validSymbol } from '@/lib/market';
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  if (!await getAdmin()) return NextResponse.json({error:'Unauthorized'}, {status:401});
  const symbol = validSymbol(request.nextUrl.searchParams.get('symbol'));
  try {
    const [candles, ticker] = await Promise.all([
      fetchCandles(symbol),
      binanceJson('/api/v3/ticker/bookTicker?symbol=' + symbol)
    ]);
    return NextResponse.json({symbol, interval:'5m', candles, ticker, fetchedAt:Date.now()},
      {headers:{'Cache-Control':'no-store'}});
  } catch (error) {
    return NextResponse.json({error:error instanceof Error ? error.message : 'Market data unavailable'}, {status:502});
  }
}
