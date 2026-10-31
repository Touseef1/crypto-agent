import {redirect} from 'next/navigation';
import {getAdmin} from '@/lib/auth';
import BacktestTerminal from './terminal';
export const dynamic='force-dynamic';
export default async function BacktestingPage(){if(!await getAdmin())redirect('/login');return <BacktestTerminal/>;}
