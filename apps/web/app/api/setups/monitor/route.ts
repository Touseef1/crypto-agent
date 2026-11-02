import {NextRequest,NextResponse} from 'next/server';
import {prisma} from '@/lib/db';
import {paperOrder,quote} from '@/lib/paper';
export const dynamic='force-dynamic';
// Invoke this endpoint from a continuously running trusted worker, not a browser.
export async function POST(req:NextRequest){
 const secret=process.env.PAPER_MONITOR_SECRET;
 if(!secret||secret.length<24||req.headers.get('authorization')!==`Bearer ${secret}`)return NextResponse.json({error:'Unauthorized'},{status:401});
 if(process.env.TRADING_MODE!=='PAPER'||process.env.LIVE_TRADING_ENABLED!=='false')return NextResponse.json({error:'Paper mode required'},{status:503});
 const heartbeat=await prisma.botConfiguration.upsert({where:{key:'paper_monitor_heartbeat'},create:{key:'paper_monitor_heartbeat',value:{checkedAt:new Date().toISOString()}},update:{value:{checkedAt:new Date().toISOString()}}});
 void heartbeat;
 const positions=await prisma.position.findMany({where:{status:'OPEN',OR:[{stopLoss:{not:null}},{takeProfit:{not:null}}]},include:{account:true}});
 const results:{positionId:string;trigger:string;status:string}[]=[];
 for(const p of positions){
  if(p.account.mode!=='PAPER'||p.account.botState==='PAUSED')continue;
  try{
   const price=await quote(p.symbol as 'BTCUSDT'|'ETHUSDT');
   const trigger=p.stopLoss&&price.lte(p.stopLoss)?'SL':p.takeProfit&&price.gte(p.takeProfit)?'TP':null;
   if(!trigger)continue;
   const key=`bracket:${p.id}:${trigger}`;
   // The paper order transaction re-checks balances and records the fill.
   await paperOrder({userId:p.account.userId,symbol:p.symbol as 'BTCUSDT'|'ETHUSDT',side:'SELL',quantity:p.quantity.toFixed(8),key,referencePrice:price});
   results.push({positionId:p.id,trigger,status:'FILLED'});
  }catch(e){console.error('Paper bracket monitor failed',p.id,e);results.push({positionId:p.id,trigger:'ERROR',status:'FAILED'});}
 }
 return NextResponse.json({checked:positions.length,results},{headers:{'Cache-Control':'no-store'}});
}
