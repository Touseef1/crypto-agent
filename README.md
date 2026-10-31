# CryptoBot — Phase 2

Personal cryptocurrency **paper-trading** application. **No real trading is implemented.**

## Requirements
Node.js 20.9+ (22 recommended), npm, MySQL 8, optional phpMyAdmin.

## Local setup
1. `npm install`
2. Copy `.env.example` to `.env` in the repository root; change `DATABASE_URL`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD` (minimum 12 characters). Never commit `.env`.
3. Create MySQL database and restricted user (adjust the password):
   ```sql
   CREATE DATABASE cryptobot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'cryptobot'@'localhost' IDENTIFIED BY 'change_this_password';
   GRANT ALL PRIVILEGES ON cryptobot.* TO 'cryptobot'@'localhost';
   ```
4. `npm run db:generate`
5. `npm run db:migrate` (requires running MySQL and valid credentials)
6. `npm run db:seed` (safe to run repeatedly; does not reset balances)
7. `npm run dev` and open `http://localhost:3000/login`.

**Important:** Next.js reads environment variables from `apps/web/.env.local` or its process environment. For local development, copy root `.env` to `apps/web/.env.local` as well, or export the variables in your shell before starting Next.js. Root `.env` is used by Prisma CLI and seed script.

## Useful commands
- `npm run build`
- `npm run typecheck`
- `npm run test`
- `npm run dev`
- `npm run db:migrate`

## phpMyAdmin
Open `http://localhost/phpmyadmin`, log in with a MySQL user authorized to access `cryptobot`, and select the database. phpMyAdmin is a database administration UI, not the data store; MySQL stores all records.

## Feature status
- Phase 1: schema, authentication, seed and dashboard foundation implemented in source.
- Phase 2: BTCUSDT/ETHUSDT Binance public REST snapshots, browser WebSocket trade updates, multi-timeframe candlestick chart, authenticated on-demand candle sync to MySQL with deduplication. Market feed reconnects automatically; candle sync is manual and limited to the most recent 1000 candles per request.
- Phase 3: manual paper BUY/SELL execution with virtual balances, fee/slippage simulation, 20% per-order BUY cap, minimum notional, no shorting, serializable database transactions, order history, and RSI/EMA/MACD informational signals. Unattended automated execution, stop-loss/take-profit and portfolio drawdown controls are not yet implemented.
- Phase 4: backtesting **not implemented**.
- Phase 5–6: full reporting and stabilization **not implemented**.

Phase 2 usage: sign in and visit /markets; select BTC/ETH and choose “Save historical candles” to persist closed 5-minute candles. Browser needs access to Binance public WebSocket; the server needs outbound access to data-api.binance.vision. No order execution or real trading is enabled. Verify data completeness before using candles for strategy/backtesting.\n\nDo not start the bot or rely on financial outputs until later phases are implemented and tested.
# crypto-agent

## Phase 2 candlestick charts
Open `/markets` after login and select BTC/USDT or ETH/USDT. Choose 5m, 10m, 15m or 1h. The chart shows OHLC candlesticks (green up / red down), UTC timestamps and hover details. Binance natively supports 5m, 15m and 1h; 10m is derived from complete pairs of UTC-aligned 5m candles. The latest native Binance candle can be incomplete. The **Save historical candles** action still saves closed 5m candles only, independently of the selected chart timeframe. No trading orders are sent.

## Phase 3 — paper trading
Visit `/trading` after signing in. Select BTCUSDT or ETHUSDT, BUY/SELL and a quantity; review the virtual-funds confirmation before submitting. The server fetches a Binance public quote and simulates 0.1% fee and 0.05% adverse slippage. No real Binance order endpoint or API keys are used. Signals are calculated from **closed 5-minute candles** and never trigger orders automatically. The BUY cap is 20% of available USDT per order, not a full portfolio-risk system. Do not use this version for unattended trading or real money.\n