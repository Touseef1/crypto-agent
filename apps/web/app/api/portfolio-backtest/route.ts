import {NextRequest,NextResponse} from 'next/server';
import {z} from 'zod';
import {getAdmin,sameOrigin} from '@/lib/auth';
import {prisma} from '@/lib/db';
import {runPortfolioBacktest} from '@/lib/portfolio-backtest';

export const dynamic='force-dynamic';
const schema=z.object({
 initialBalance:z.number().min(100).max(1000000).default(1000),
 allocation:z.number().min(0.01).max(0.2).default(0.2),
 feeRate:z.number().min(0).max(0.01).default(0.001),
 slippageRate:z.number().min(0).max(0.01).default(0.0005)
}).strict();
export async function POST(req:NextRequest){
 if(!await getAdmin())return NextResponse.json({error:'Unauthorized'},{status:401});
 if(!sameOrigin(req))return NextResponse.json({error:'Invalid origin'},{status:403});
 const parsed=schema.safeParse(await req.json().catch(()=>null));
 if(!parsed.success)return NextResponse.json({error:'Invalid settings'},{status:400});
 try{
  const symbols=['BTCUSDT','ETHUSDT'] as const;
  const rows=await Promise.all(symbols.map(symbol=>prisma.marketCandle.findMany({
   where:{symbol,interval:'5m',closeTime:{lt:new Date()}},
   orderBy:{openTime:'desc'},take:1000
  })));
  const data=Object.fromEntries(rows.map((candles,i)=>[symbols[i],candles.reverse().map(c=>({
   openTime:c.openTime.getTime(),closeTime:c.closeTime.getTime(),
   open:Number(c.open),high:Number(c.high),low:Number(c.low),
   close:Number(c.close),volume:Number(c.volume)
  }))])) as Parameters<typeof runPortfolioBacktest>[0];
  const result=runPortfolioBacktest(data,parsed.data);
  return NextResponse.json(result,{headers:{'Cache-Control':'no-store'}});
 }catch(e){
  const message=e instanceof Error?e.message:'Portfolio simulation failed';
  if(message.includes('candles')||message.includes('historical period'))
   return NextResponse.json({error:message},{status:400});
  console.error('Portfolio research simulation failed',e);
  return NextResponse.json({error:'Portfolio simulation failed. Check server logs.'},{status:500});
 }
}
