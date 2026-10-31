import {NextRequest,NextResponse} from 'next/server';
import {z} from 'zod';
import {getAdmin,sameOrigin} from '@/lib/auth';
import {prisma} from '@/lib/db';
import {runBacktest} from '@/lib/backtest';
export const dynamic='force-dynamic';
const schema=z.object({symbol:z.enum(['BTCUSDT','ETHUSDT']),initialBalance:z.number().min(100).max(1000000).default(1000),allocation:z.number().min(0.01).max(0.2).default(0.2)});
export async function GET(){
 const user=await getAdmin();if(!user)return NextResponse.json({error:'Unauthorized'},{status:401});
 const runs=await prisma.backtestRun.findMany({take:20,orderBy:{createdAt:'desc'},include:{_count:{select:{trades:true}}}});
 return NextResponse.json({runs:runs.map(r=>({id:r.id,symbol:r.symbol,status:r.status,createdAt:r.createdAt,initialBalance:r.initialBalance.toString(),finalBalance:r.finalBalance?.toString(),trades:r._count.trades,parameters:r.parameters}))},{headers:{'Cache-Control':'no-store'}});
}
export async function POST(req:NextRequest){
 const user=await getAdmin();if(!user)return NextResponse.json({error:'Unauthorized'},{status:401});
 if(!sameOrigin(req))return NextResponse.json({error:'Invalid origin'},{status:403});
 let input:z.infer<typeof schema>;
 try{input=schema.parse(await req.json());}catch{return NextResponse.json({error:'Invalid parameters'},{status:400});}
 try{
  const rows=await prisma.marketCandle.findMany({where:{symbol:input.symbol,interval:'5m',closeTime:{lt:new Date()}},orderBy:{openTime:'asc'},take:5000});
  if(rows.length<65)return NextResponse.json({error:'Not enough saved 5m candles. Visit Markets and save historical candles first (minimum 65).'}, {status:400});
  // Reject gaps rather than pretending sparse candles are consecutive.
  for(let i=1;i<rows.length;i++)if(rows[i].openTime.getTime()-rows[i-1].openTime.getTime()!==300000)
    return NextResponse.json({error:'Saved 5m candles have gaps. Sync a continuous range before backtesting.'},{status:400});
  const candles=rows.map(r=>({openTime:r.openTime.getTime(),closeTime:r.closeTime.getTime(),open:Number(r.open),high:Number(r.high),low:Number(r.low),close:Number(r.close),volume:Number(r.volume)}));
  const options={initialBalance:input.initialBalance,allocation:input.allocation,feeRate:0.001,slippageRate:0.0005};
  const result=runBacktest(candles,options);
  const run=await prisma.backtestRun.create({data:{symbol:input.symbol,parameters:{...options,interval:'5m',strategy:'RSI_EMA_MACD_V1',metrics:{returnPct:result.returnPct,buyHoldPct:result.buyHoldPct,maxDrawdownPct:result.maxDrawdownPct,winRatePct:result.winRatePct,wins:result.wins,losses:result.losses,openQuantity:result.openQuantity,candlesUsed:result.candlesUsed,startTime:result.startTime,endTime:result.endTime}},status:'COMPLETED',initialBalance:input.initialBalance,finalBalance:result.finalBalance,trades:{create:result.trades.map(t=>({symbol:input.symbol,side:t.side,quantity:t.quantity,price:t.price,fee:t.fee,executedAt:new Date(t.executedAt)}))}}}});
  return NextResponse.json({runId:run.id,...result},{headers:{'Cache-Control':'no-store'}});
 }catch(e){console.error('Backtest failed',e);return NextResponse.json({error:'Backtest failed. Check server logs.'},{status:500});}
}
