import { NextRequest,NextResponse } from 'next/server';
import { z } from 'zod';
import { getAdmin,sameOrigin } from '@/lib/auth';
import { prisma } from '@/lib/db';
import { paperOrder,PaperTradeError,quote } from '@/lib/paper';
export const dynamic='force-dynamic';
const schema=z.object({symbol:z.enum(['BTCUSDT','ETHUSDT']),side:z.enum(['BUY','SELL']),quantity:z.string().regex(/^\\d+(?:\\.\\d{1,8})?$/),key:z.string().min(8).max(100)});
export async function GET(){
  const user=await getAdmin();if(!user)return NextResponse.json({error:'Unauthorized'},{status:401});
  const account=await prisma.tradingAccount.findFirst({where:{userId:user.id,mode:'PAPER'},include:{balances:true,orders:{take:30,orderBy:{createdAt:'desc'},include:{fills:true}}}});
  if(!account)return NextResponse.json({error:'Account not initialized'},{status:404});
  return NextResponse.json({balances:account.balances.map(b=>({asset:b.asset,available:b.available.toString()})),orders:account.orders.map(o=>({id:o.id,symbol:o.symbol,side:o.side,status:o.status,quantity:o.quantity.toString(),price:o.fills[0]?.price.toString(),fee:o.fills[0]?.fee.toString(),createdAt:o.createdAt}))},{headers:{'Cache-Control':'no-store'}});
}
export async function POST(request:NextRequest){
  const user=await getAdmin();if(!user)return NextResponse.json({error:'Unauthorized'},{status:401});
  if(!sameOrigin(request))return NextResponse.json({error:'Invalid origin'},{status:403});
  try{
    const input=schema.parse(await request.json());
    const referencePrice=await quote(input.symbol);
    const order=await paperOrder({userId:user.id,...input,referencePrice});
    return NextResponse.json({orderId:order.id,status:order.status,fillPrice:order.fills[0]?.price.toString()});
  }catch(e){
    if(e instanceof z.ZodError||e instanceof PaperTradeError)return NextResponse.json({error:e.message},{status:400});
    console.error('Paper order error',e);
    return NextResponse.json({error:'Unable to execute paper order'},{status:500});
  }
}
