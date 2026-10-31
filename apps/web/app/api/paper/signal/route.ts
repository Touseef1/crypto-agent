import { NextRequest,NextResponse } from 'next/server';
import { getAdmin } from '@/lib/auth';
import { fetchCandles,SYMBOLS } from '@/lib/market';
import { signalFromCandles } from '@/lib/strategy';
export const dynamic='force-dynamic';
export async function GET(req:NextRequest){
  if(!await getAdmin())return NextResponse.json({error:'Unauthorized'},{status:401});
  const symbol=req.nextUrl.searchParams.get('symbol');
  if(!symbol||!SYMBOLS.includes(symbol as typeof SYMBOLS[number]))return NextResponse.json({error:'Invalid symbol'},{status:400});
  try{
    const candles=(await fetchCandles(symbol as typeof SYMBOLS[number],200)).filter(c=>c.closeTime<Date.now());
    return NextResponse.json({symbol,signal:signalFromCandles(candles),notice:'Educational signal only. Not an order or financial recommendation.'},{headers:{'Cache-Control':'no-store'}});
  }catch(e){return NextResponse.json({error:e instanceof Error?e.message:'Signal unavailable'},{status:502});}
}
