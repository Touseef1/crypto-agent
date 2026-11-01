import { NextRequest,NextResponse } from 'next/server';
import { z } from 'zod';
import { Prisma } from '@prisma/client';
import { getAdmin,sameOrigin } from '@/lib/auth';
import { prisma } from '@/lib/db';
import { paperOrder,PaperTradeError,quote } from '@/lib/paper';
export const dynamic='force-dynamic';
const schema=z.object({symbol:z.enum(['BTCUSDT','ETHUSDT']),side:z.enum(['BUY','SELL']),quantity:z.string().regex(/^[0-9]+(?:\.[0-9]{1,8})?$/).optional(),usdtAmount:z.string().regex(/^[0-9]+(?:\.[0-9]{1,8})?$/).optional(),key:z.string().min(8).max(100)});
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
    if ((input.quantity === undefined) === (input.usdtAmount === undefined)) return NextResponse.json({error:'Provide exactly one of quantity or usdtAmount'},{status:400});
    const referencePrice=await quote(input.symbol);
    let quantity=input.quantity;
    if(input.usdtAmount!==undefined){
      const amount=new Prisma.Decimal(input.usdtAmount);
      if(!amount.isFinite()||amount.lte(0))return NextResponse.json({error:'USDT amount must be greater than zero'},{status:400});
      const slippage=new Prisma.Decimal('0.0005');
      const fee=new Prisma.Decimal('0.001');
      const price=input.side==='BUY'?referencePrice.mul(new Prisma.Decimal(1).plus(slippage)):referencePrice.mul(new Prisma.Decimal(1).minus(slippage));
      const divisor=input.side==='BUY'?price.mul(new Prisma.Decimal(1).plus(fee)):price.mul(new Prisma.Decimal(1).minus(fee));
      quantity=amount.div(divisor).toDecimalPlaces(8,Prisma.Decimal.ROUND_DOWN).toFixed(8);
      if(new Prisma.Decimal(quantity).lte(0))return NextResponse.json({error:'USDT amount too small for 8-decimal coin precision'},{status:400});
    }
    const order=await paperOrder({userId:user.id,symbol:input.symbol,side:input.side,quantity:quantity!,key:input.key,referencePrice});
    return NextResponse.json({orderId:order.id,status:order.status,fillPrice:order.fills[0]?.price.toString()});
  }catch(e){
    if(e instanceof z.ZodError)return NextResponse.json({error:e.issues.map(issue=>issue.path.join('.')+': '+issue.message).join('; ')},{status:400});
    if(e instanceof PaperTradeError)return NextResponse.json({error:e.message},{status:400});
    console.error('Paper order error',e);
    return NextResponse.json({error:'Unable to execute paper order'},{status:500});
  }
}
