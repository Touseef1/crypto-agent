import { redirect } from 'next/navigation';
import { getAdmin } from '@/lib/auth';
import TradingTerminal from './terminal';
export const dynamic='force-dynamic';
export default async function TradingPage(){if(!await getAdmin())redirect('/login');return <TradingTerminal/>;}
