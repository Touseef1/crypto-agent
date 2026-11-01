import { Prisma, type OrderSide } from '@prisma/client';
import { prisma } from '@/lib/db';
import { binanceJson, type SymbolName } from '@/lib/market';

const D=Prisma.Decimal;
const feeRate=new D('0.001');
const slippage=new D('0.0005');
const maxFraction=new D('0.20');
const minNotional=new D('10');
export class PaperTradeError extends Error {}
export async function quote(symbol:SymbolName):Promise<D>{
  const raw=await binanceJson('/api/v3/ticker/price?symbol='+symbol) as {price?:string};
  if(!raw.price||!new D(raw.price).isFinite()||new D(raw.price).lte(0))throw new PaperTradeError('Invalid market price');
  return new D(raw.price);
}
export async function paperOrder(input:{userId:string;symbol:SymbolName;side:OrderSide;quantity:string;key:string;referencePrice:D;stopLoss?:string;takeProfit?:string}) {
  if(process.env.TRADING_MODE!=='PAPER'||process.env.LIVE_TRADING_ENABLED!=='false')throw new PaperTradeError('Paper trading safety configuration required');
  const qty=new D(input.quantity);
  const sl=input.stopLoss===undefined?null:new D(input.stopLoss);
  const tp=input.takeProfit===undefined?null:new D(input.takeProfit);
  if((sl&&!sl.isFinite())||(tp&&!tp.isFinite())||(sl&&sl.lte(0))||(tp&&tp.lte(0)))throw new PaperTradeError('Invalid TP/SL prices');
  if(input.side==='SELL'&&(sl||tp))throw new PaperTradeError('TP/SL can only be set on BUY');
  if(!qty.isFinite()||qty.lte(0)||qty.decimalPlaces()>8)throw new PaperTradeError('Invalid quantity (maximum 8 decimals)');
  if(!/^[a-zA-Z0-9:_-]{8,100}$/.test(input.key))throw new PaperTradeError('Invalid idempotency key');
  const asset=input.symbol==='BTCUSDT'?'BTC':'ETH';
  const price=input.side==='BUY'?input.referencePrice.mul(new D(1).plus(slippage)):input.referencePrice.mul(new D(1).minus(slippage));
  const gross=qty.mul(price);
  const fee=gross.mul(feeRate);
  if(input.side==='BUY'&&gross.lt(minNotional))throw new PaperTradeError('Minimum paper BUY value is 10 USDT');
  return prisma.$transaction(async tx=>{
    const account=await tx.tradingAccount.findFirst({where:{userId:input.userId,mode:'PAPER'}});
    if(!account)throw new PaperTradeError('Paper account not initialized');
    const existing=await tx.order.findUnique({where:{idempotencyKey:input.key},include:{fills:true}});
    if(existing){if(existing.accountId!==account.id)throw new PaperTradeError('Order key already used');return existing;}
    const usdt=await tx.balance.findUnique({where:{accountId_asset:{accountId:account.id,asset:'USDT'}}});
    const coin=await tx.balance.findUnique({where:{accountId_asset:{accountId:account.id,asset}}});
    if(!usdt||!coin)throw new PaperTradeError('Missing paper balances; run seed');
    const open=await tx.position.findFirst({where:{accountId:account.id,symbol:input.symbol,status:'OPEN'},orderBy:{openedAt:'asc'}});
    if(input.side==='BUY'&&open&&((sl&&open.stopLoss&&!sl.eq(open.stopLoss))||(tp&&open.takeProfit&&!tp.eq(open.takeProfit))))throw new PaperTradeError('Existing position has different TP/SL; close it before opening a new bracket');
    if(input.side==='BUY'){
      if(sl&&sl.gte(price))throw new PaperTradeError('Stop loss must be below BUY execution price');
      if(tp&&tp.lte(price))throw new PaperTradeError('Take profit must be above BUY execution price');
      const total=gross.plus(fee);
      if(usdt.available.lt(total))throw new PaperTradeError('Insufficient USDT');
      // Limit per order to 20% of currently available quote balance.
      if(total.gt(usdt.available.mul(maxFraction)))throw new PaperTradeError('Order exceeds 20% of available USDT');
      await tx.balance.update({where:{id:usdt.id},data:{available:{decrement:total}}});
      await tx.balance.update({where:{id:coin.id},data:{available:{increment:qty}}});
      const cost=gross.plus(fee);
      if(open){const totalQty=open.quantity.plus(qty);await tx.position.update({where:{id:open.id},data:{quantity:totalQty,avgEntry:open.avgEntry.mul(open.quantity).plus(cost).div(totalQty),...(sl?{stopLoss:sl}:{}),...(tp?{takeProfit:tp}:{})}});}
      else await tx.position.create({data:{accountId:account.id,symbol:input.symbol,quantity:qty,avgEntry:cost.div(qty),stopLoss:sl,takeProfit:tp}});
    }else{
      if(coin.available.lt(qty))throw new PaperTradeError('Insufficient asset balance; shorting disabled');
      await tx.balance.update({where:{id:coin.id},data:{available:{decrement:qty}}});
      await tx.balance.update({where:{id:usdt.id},data:{available:{increment:gross.minus(fee)}}});
      if(open){const sold=Prisma.Decimal.min(qty,open.quantity);const remaining=open.quantity.minus(sold);
        const pnl=price.mul(sold).minus(fee.mul(sold).div(qty)).minus(open.avgEntry.mul(sold));
        await tx.position.update({where:{id:open.id},data:{quantity:remaining,realizedPnl:{increment:pnl},status:remaining.lte(0)?'CLOSED':'OPEN',closedAt:remaining.lte(0)?new Date():null}});
      }
    }
    const order=await tx.order.create({data:{accountId:account.id,idempotencyKey:input.key,symbol:input.symbol,side:input.side,status:'FILLED',quantity:qty,requestedPrice:input.referencePrice,fills:{create:{quantity:qty,price,fee,feeAsset:'USDT'}}},include:{fills:true}});
    await tx.balanceLedger.createMany({data:[
      {accountId:account.id,asset:'USDT',amount:input.side==='BUY'?gross.plus(fee).neg():gross.minus(fee),reason:'PAPER_FILL',reference:order.id+':USDT'},
      {accountId:account.id,asset,amount:input.side==='BUY'?qty:qty.neg(),reason:'PAPER_FILL',reference:order.id+':'+asset}
    ]});
    return order;
  },{isolationLevel:Prisma.TransactionIsolationLevel.Serializable,maxWait:5000,timeout:10000});
}
