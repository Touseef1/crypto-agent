import {NextRequest,NextResponse} from 'next/server';
import {getAdmin,sameOrigin} from '@/lib/auth';
import {prisma} from '@/lib/db';
export async function POST(req:NextRequest){
 const user=await getAdmin();
 if(!user)return NextResponse.json({error:'Unauthorized'},{status:401});
 if(!sameOrigin(req))return NextResponse.json({error:'Invalid origin'},{status:403});
 const account=await prisma.tradingAccount.findFirst({where:{userId:user.id,mode:'PAPER'}});
 if(!account)return NextResponse.json({error:'Paper account not found'},{status:404});
 await prisma.tradingAccount.update({where:{id:account.id},data:{botState:account.botState==='PAUSED'?'STOPPED':'PAUSED'}});
 return NextResponse.redirect(new URL('/dashboard',req.url),303);
}
