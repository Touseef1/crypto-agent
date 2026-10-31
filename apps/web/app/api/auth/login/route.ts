import { NextResponse } from 'next/server';
import { compare } from 'bcryptjs';
import { z } from 'zod';
import { prisma } from '@/lib/db';
import { createToken,hashToken,sameOrigin } from '@/lib/auth';
const schema=z.object({email:z.email(),password:z.string().min(1).max(200)});
export async function POST(req:Request){if(!sameOrigin(req))return NextResponse.json({error:'Invalid request origin'},{status:403});let body;try{body=schema.parse(await req.json())}catch{return NextResponse.json({error:'Invalid credentials'},{status:400})}
const email=body.email.toLowerCase();const since=new Date(Date.now()-15*60*1000);const attempts=await prisma.loginAttempt.count({where:{email,createdAt:{gte:since}}});if(attempts>=8)return NextResponse.json({error:'Too many attempts. Try again later.'},{status:429});
const user=await prisma.user.findUnique({where:{email}});const valid=user?.isActive&&await compare(body.password,user.passwordHash);if(!valid){await prisma.loginAttempt.create({data:{email}});return NextResponse.json({error:'Invalid credentials'},{status:401})}
await prisma.loginAttempt.deleteMany({where:{email}});const token=createToken();await prisma.session.create({data:{userId:user.id,tokenHash:hashToken(token),expiresAt:new Date(Date.now()+8*60*60*1000)}});await prisma.auditLog.create({data:{userId:user.id,action:'LOGIN',entity:'Session'}});
const res=NextResponse.json({ok:true});res.cookies.set('cryptobot_session',token,{httpOnly:true,secure:process.env.NODE_ENV==='production',sameSite:'strict',path:'/',maxAge:8*60*60});return res;}