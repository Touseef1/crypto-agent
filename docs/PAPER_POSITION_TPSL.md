# Paper positions and automatic TP/SL

This feature is **paper trading only**. It never sends orders to Binance. Binance public ticker prices are used to simulate fills; fills, balances, cost basis, realized P&L and TP/SL are saved in MySQL.

## Setup

1. Pull latest code, install dependencies and generate Prisma client:
   ```bash
   git pull origin main
   npm install
   npm run db:generate
   npx prisma migrate deploy --schema packages/database/prisma/schema.prisma
   ```
2. In the root `.env` (not committed), set:
   ```env
   TRADING_MODE=PAPER
   LIVE_TRADING_ENABLED=false
   PAPER_MONITOR_SECRET=replace-with-a-random-secret-of-at-least-24-characters
   PAPER_MONITOR_URL=http://localhost:3000
   PAPER_MONITOR_INTERVAL_MS=5000
   ```
   Ensure the Next.js server process also receives PAPER_MONITOR_SECRET (e.g. put it in `apps/web/.env.local` as well when running Next from the workspace).
3. Start the Next.js application in one terminal: `npm run dev`.
4. Start the server-side monitor in **another terminal**: `npm run paper:monitor`. Keep it running independently of the browser. On deployment, use a supervised process manager. Do not expose the secret.
5. Open `/setups`, enter USDT amount, absolute SL and TP **prices**, and BUY. The Open Positions list supports editing brackets and closing the full position.

## Important limitations

- Automatic SL/TP is **not active unless the monitor process is running**. It polls Binance prices approximately every 5 seconds, not tick-by-tick; outages, market gaps and polling delay may cause fills beyond the target.
- Only spot-long positions. SELL closes or reduces held coin; no shorts.
- Positions created by the old paper engine before this upgrade have no position cost basis and are not automatically imported.
- This implementation uses a basic per-symbol aggregate position, not per-order lots or multiple independent TP targets.
- The strategy signal is informational and does not automatically open positions.
- Position P&L is recorded on simulated sells; this screen does not yet display live mark-to-market unrealized P&L.
- Monitor endpoint requires a strong secret and paper-only environment variables.
- Always test with virtual funds and verify DB balances before depending on the automation.
