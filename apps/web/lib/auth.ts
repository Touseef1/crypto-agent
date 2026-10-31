import { cookies } from 'next/headers';
import { createHash, randomBytes } from 'node:crypto';
import { prisma } from './db';
export const hashToken=(token:string)=>createHash('sha256').update(token).digest('hex');
export const createToken=()=>randomBytes(32).toString('hex');
export async function getAdmin(){const token=(await cookies()).get('cryptobot_session')?.value;if(!token)return null;const session=await prisma.session.findUnique({where:{tokenHash:hashToken(token)},include:{user:true}});if(!session||session.expiresAt<=new Date()||!session.user.isActive)return null;return session.user;}
export async function requireAdmin(){const user=await getAdmin();if(!user)throw new Error('UNAUTHORIZED');return user;}
export function sameOrigin(req:Request){const origin=req.headers.get('origin');if(!origin)return false;try{return new URL(origin).host===req.headers.get('host')}catch{return false}}