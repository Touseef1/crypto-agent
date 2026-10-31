import { redirect } from 'next/navigation';
import { getAdmin } from '@/lib/auth';
import MarketTerminal from './terminal';
export const dynamic = 'force-dynamic';
export default async function MarketsPage() {
  if (!await getAdmin()) redirect('/login');
  return <MarketTerminal />;
}
