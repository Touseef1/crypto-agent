import {NextRequest,NextResponse} from 'next/server';
import {z} from 'zod';
import {Prisma} from '@prisma/client';
import {getAdmin,sameOrigin} from '@/lib/auth';
import {prisma} from '@/lib/db';
import {paperOrder,PaperTradeError,quote} from '@/lib/paper';
export const dynamic='force-dynamic';
const schema=z.discriminatedUnion('action',[
 z.object({action:z.literal('BUY'),symbol:z.enum(['BTCUSDT','ETHUSDT']),usdtAmount:z.string().regex(/^[0-9]+(?:\.[0-9]{1,8})?$/),stopLoss:z.number().positive(),takeProfit:z.number().positive(),key:z.string().uuid()}),
 z.object({action:z.literal('CLOSE'),positionId:z.string().min(1),key:z.string().uuid()}),
 z.object({action:z.literal('UPDATE'),positionId:z.string().min(1),stopLoss:z.number().positive(),takeProfit:z.number().positive()})
]);
export async function GET(){
 const user=await getAdmin();if(!user)return NextResponse.json({error:'Unauthorized'},{status:401});
 const account=await prisma.tradingAccount.findFirst({where:{userId:user.id,mode:'PAPER'},include:{positions:{where:{status:'OPEN'},orderBy:{openedAt:'desc'}}}});
 if(!account)return NextResponse.json({error:'Paper account unavailable'},{status:404});
 const prices=await Promise.allSettled(['BTCUSDT','ETHUSDT'].map(s=>quote(s as 'BTCUSDT'|'ETHUSDT')));
 const current=new Map<string,Prisma.Decimal>();
 prices.forEach((v,i)=>{if(v.status==='fulfilled')current.set(['BTCUSDT','ETHUSDT'][i],v.value)});
 return NextResponse.json({positions:account.positions.map(p=>{const market=current.get(p.symbol);return {id:p.id,symbol:p.symbol,quantity:p.quantity.toString(),avgEntry:p.avgEntry.toString(),stopLoss:p.stopLoss?.toString()??null,takeProfit:p.takeProfit?.toString()??null,realizedPnl:p.realizedPnl.toString(),currentPrice:market?.toString()??null,unrealizedPnl:market?market.mul('0.9995').mul('0.999').minus(p.avgEntry).mul(p.quantity).toString():null,openedAt:p.openedAt}})},{headers:{'Cache-Control':'no-store'}});
}
export async function POST(req:NextRequest){
 const user=await getAdmin();if(!user)return NextResponse.json({error:'Unauthorized'},{status:401});
 if(!sameOrigin(req))return NextResponse.json({error:'Invalid origin'},{status:403});
 const parsed=schema.safeParse(await req.json().catch(()=>null));
 if(!parsed.success)return NextResponse.json({error:parsed.error.issues.map(x=>x.path.join('.')+': '+x.message).join('; ')},{status:400});
 const x=parsed.data;
 try{
  if(x.action==='BUY'){
   const account=await prisma.tradingAccount.findFirst({where:{userId:user.id,mode:'PAPER'},include:{positions:{where:{status:'OPEN'}}}});
   if(!account)throw new PaperTradeError('Paper account not initialized');
   if(account.positions.length>=2&&!account.positions.some(p=>p.symbol===x.symbol))throw new PaperTradeError('Maximum 2 open positions');
   const price=await quote(x.symbol);
   const amount=new Prisma.Decimal(x.usdtAmount);
   if(amount.lte(0))throw new PaperTradeError('USDT amount must be positive');
   const qty=amount.div(price.mul('1.0005').mul('1.001')).toDecimalPlaces(8,Prisma.Decimal.ROUND_DOWN);
   if(qty.lte(0))throw new PaperTradeError('Amount too small');
   const order=await paperOrder({userId:user.id,symbol:x.symbol,side:'BUY',quantity:qty.toFixed(8),key:x.key,referencePrice:price,stopLoss:String(x.stopLoss),takeProfit:String(x.takeProfit)});
   return NextResponse.json({orderId:order.id,status:order.status});
  }
  const p=await prisma.position.findFirst({where:{id:x.positionId,status:'OPEN',account:{userId:user.id,mode:'PAPER'}}});
  if(!p)throw new PaperTradeError('Open position not found');
  if(x.action==='UPDATE'){
   if(x.stopLoss>=Number(p.avgEntry)||x.takeProfit<=Number(p.avgEntry)||x.stopLoss>=x.takeProfit)throw new PaperTradeError('SL must be below entry and TP above entry');
   await prisma.position.update({where:{id:p.id},data:{stopLoss:String(x.stopLoss),takeProfit:String(x.takeProfit)}});
   return NextResponse.json({updated:true});
  }
  const price=await quote(p.symbol as 'BTCUSDT'|'ETHUSDT');
  const order=await paperOrder({userId:user.id,symbol:p.symbol as 'BTCUSDT'|'ETHUSDT',side:'SELL',quantity:p.quantity.toFixed(8),key:x.key,referencePrice:price});
  return NextResponse.json({orderId:order.id,status:order.status});
 }catch(e){if(e instanceof PaperTradeError)return NextResponse.json({error:e.message},{status:400});console.error('Position error',e);return NextResponse.json({error:'Unable to process paper position'},{status:500});}
}
