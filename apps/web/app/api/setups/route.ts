import {NextRequest,NextResponse} from 'next/server';
import {z} from 'zod';
import {getAdmin} from '@/lib/auth';
import {getSetup} from '@/lib/setup-service';
export const dynamic='force-dynamic';
const query=z.object({symbol:z.enum(['BTCUSDT','ETHUSDT']),interval:z.enum(['5m','15m','1h','4h'])});
export async function GET(request:NextRequest){
 const user=await getAdmin();if(!user)return NextResponse.json({error:'Unauthorized'},{status:401});
 const parsed=query.safeParse(Object.fromEntries(new URL(request.url).searchParams));
 if(!parsed.success)return NextResponse.json({error:'Invalid symbol or interval'},{status:400});
 try{const setup=await getSetup(user.id,parsed.data.symbol,parsed.data.interval);
 return NextResponse.json(setup,{headers:{'Cache-Control':'private, max-age=5'}});
 }catch(e){console.error('Setup error',e);return NextResponse.json({error:'Setup unavailable; check historical market data and server logs'},{status:503});}
}
