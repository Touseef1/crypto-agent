import {redirect} from 'next/navigation';
import {getAdmin} from '@/lib/auth';
import TradeSetupTerminal from './terminal';
export default async function SetupsPage(){const user=await getAdmin();if(!user)redirect('/login');return <TradeSetupTerminal/>;}
