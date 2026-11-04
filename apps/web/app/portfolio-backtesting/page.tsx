import {redirect} from 'next/navigation';
import {getAdmin} from '@/lib/auth';
import PortfolioTerminal from './terminal';
export const dynamic='force-dynamic';
export default async function PortfolioPage(){
 if(!await getAdmin())redirect('/login');
 return <PortfolioTerminal/>;
}
