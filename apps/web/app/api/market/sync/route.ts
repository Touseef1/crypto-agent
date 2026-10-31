import { NextRequest, NextResponse } from 'next/server';
import { getAdmin, sameOrigin } from '@/lib/auth';
import { fetchCandles, persistClosedCandles, validSymbol, SYMBOLS } from '@/lib/market';
export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  if (!await getAdmin()) return NextResponse.json({error:'Unauthorized'}, {status:401});
  if (!sameOrigin(request)) return NextResponse.json({error:'Invalid origin'}, {status:403});
  const symbolParam = request.nextUrl.searchParams.get('symbol');
  if (symbolParam && !SYMBOLS.includes(symbolParam as typeof SYMBOLS[number]))
    return NextResponse.json({error:'Unsupported symbol'}, {status:400});
  const symbol = validSymbol(symbolParam);
  try {
    // Backfill up to 1000 recent candles; unique MySQL key prevents duplicates.
    const candles = await fetchCandles(symbol, 1000);
    const closed = await persistClosedCandles(symbol, candles);
    return NextResponse.json({symbol, received:candles.length, closed, note:'Duplicate candles skipped'});
  } catch (error) {
    return NextResponse.json({error:error instanceof Error ? error.message : 'Sync failed'}, {status:502});
  }
}
