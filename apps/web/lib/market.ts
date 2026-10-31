import { prisma } from '@/lib/db';

export const SYMBOLS = ['BTCUSDT', 'ETHUSDT'] as const;
export type SymbolName = (typeof SYMBOLS)[number];
export const INTERVAL = '5m';
export const CHART_INTERVALS = ['5m', '10m', '15m', '1h'] as const;
export type ChartInterval = (typeof CHART_INTERVALS)[number];
export function validInterval(value: string | null): ChartInterval | null {
  return CHART_INTERVALS.find(interval => interval === value) ?? (value === null ? '5m' : null);
}
const API = 'https://data-api.binance.vision';

export function validSymbol(value: string | null): SymbolName {
  return value === 'ETHUSDT' ? 'ETHUSDT' : 'BTCUSDT';
}

export type Candle = {
  openTime: number; closeTime: number;
  open: number; high: number; low: number; close: number; volume: number;
};

export async function binanceJson(path: string): Promise<unknown> {
  const response = await fetch(API + path, { cache: 'no-store', signal: AbortSignal.timeout(12000) });
  if (!response.ok) throw new Error('Binance market API returned ' + response.status);
  return response.json();
}

export function parseCandles(raw: unknown): Candle[] {
  if (!Array.isArray(raw)) throw new Error('Unexpected candle response');
  return raw.map((entry) => {
    if (!Array.isArray(entry) || entry.length < 7) throw new Error('Invalid candle record');
    const [openTime, open, high, low, close, volume, closeTime] = entry;
    const c = { openTime: Number(openTime), open: Number(open), high: Number(high),
      low: Number(low), close: Number(close), volume: Number(volume), closeTime: Number(closeTime) };
    if (!Object.values(c).every(Number.isFinite) || c.openTime >= c.closeTime ||
        c.low > c.high || c.open <= 0 || c.close <= 0 || c.high < Math.max(c.open,c.close) ||
        c.low > Math.min(c.open,c.close) || c.volume < 0) throw new Error('Invalid candle values');
    return c;
  }).sort((a,b) => a.openTime - b.openTime).filter((c,i,all) => i === 0 || c.openTime !== all[i-1].openTime);
}

export async function fetchCandles(symbol: SymbolName, limit = 200, endTime?: number, interval: '5m' | '15m' | '1h' = '5m'): Promise<Candle[]> {
  const query = new URLSearchParams({ symbol, interval, limit: String(Math.min(Math.max(limit,1),1000)) });
  if (endTime !== undefined) query.set('endTime', String(endTime));
  return parseCandles(await binanceJson('/api/v3/klines?' + query.toString()));
}

export async function persistClosedCandles(symbol: SymbolName, candles: Candle[]): Promise<number> {
  const now = Date.now();
  const closed = candles.filter(c => c.closeTime < now);
  if (!closed.length) return 0;
  await prisma.marketCandle.createMany({
    data: closed.map(c => ({
      symbol, interval: INTERVAL, openTime: new Date(c.openTime), closeTime: new Date(c.closeTime),
      open: c.open.toString(), high: c.high.toString(), low: c.low.toString(),
      close: c.close.toString(), volume: c.volume.toString()
    })),
    skipDuplicates: true
  });
  return closed.length;
}

/** Build complete UTC-aligned 10m candles from consecutive 5m Binance klines. */
export function aggregateTenMinuteCandles(candles: Candle[]): Candle[] {
  const bucketMs = 10 * 60 * 1000;
  const fiveMs = 5 * 60 * 1000;
  const grouped = new Map<number, Candle[]>();
  for (const candle of candles) {
    const bucket = Math.floor(candle.openTime / bucketMs) * bucketMs;
    const group = grouped.get(bucket) ?? [];
    group.push(candle);
    grouped.set(bucket, group);
  }
  return [...grouped.entries()].sort(([a],[b]) => a-b).flatMap(([start, group]) => {
    group.sort((a,b) => a.openTime-b.openTime);
    if (group.length !== 2 || group[0].openTime !== start || group[1].openTime !== start + fiveMs) return [];
    const [first, last] = group;
    return [{
      openTime:start, closeTime:last.closeTime, open:first.open, close:last.close,
      high:Math.max(first.high,last.high), low:Math.min(first.low,last.low),
      volume:first.volume+last.volume
    }];
  });
}
