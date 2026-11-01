# Trade Setup Chart (safe preview)

Open `/setups` after signing in. Supported pairs: BTCUSDT, ETHUSDT. Intervals: 5m, 15m, 1h, 4h.

## Setup calculations

The authenticated `GET /api/setups?symbol=BTCUSDT&interval=5m` route loads **closed** Binance candles, reuses `signalFromCandles` in `apps/web/lib/strategy.ts`, checks a higher-timeframe EMA20/EMA50 trend, computes Wilder ATR(14), 2x ATR stop, 1.5R and 3R targets, and an illustrative ATR-scaled projection. The pure calculations live in `packages/core/src/setup.ts`.

The chart is a read-only scenario. SELL means exiting held spot assets, never shorting. Price lines are created using Lightweight Charts v5 series price lines; dotted projection lines are separate line series. The chart does not place any orders.

## Safety and unfinished requirements

- **Place paper trade is intentionally disabled** until complete daily-loss enforcement, reliable open-position tracking, and server-side revalidation are integrated into the existing paper execution path.
- Historical win rate, average win/loss, expectancy, sample size and time-to-exit are **not yet available**. Existing BacktestRun/BacktestTrade rows do not encode enough exact setup configuration or exit reasons to substantiate these metrics. The UI explicitly displays that limitation.
- Current account equity calculation is incomplete for mixed BTC/ETH holdings: it only marks to market the selected symbol. Do not use this value for production risk enforcement.
- Missing daily equity snapshots cause a NO TRADE decision. A snapshot alone does not constitute verified daily-loss enforcement.
- The projection is a deterministic scenario based on ATR, **not a statistically calibrated probability cone**.
- EMA and MACD are reused in the strategy, but indicator overlays/panes and shaded zones remain to be implemented.
- The chart currently reuses a chart instance, but replaces its candle series when a setup response changes; incremental candle update optimization remains to be implemented.
- The API currently uses short private HTTP caching rather than the requested per-candle key cache.

## Run

From repository root:

```bash
npm install
npm run db:generate
npm run test -- tests/setup.test.ts
npm run typecheck
npm run build
npm run dev
```

Navigate to http://localhost:3000/setups. The backend requires a working authenticated session and access to Binance public market data.

**Paper trading simulation. Projections are scenarios based on the strategy and past data, not guaranteed outcomes.**
