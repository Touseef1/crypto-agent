# Safety review implementation status — 2 November 2026

## Changes pushed
- Paper-order transaction now locks the trading account, balance rows (in asset order), and matching open positions using MySQL `SELECT ... FOR UPDATE` before modifying funds.
- Existing unique idempotency keys remain in place; stale monitor bracket exits are rejected when the tracked position is already closed.
- Monitor updates a `BotConfiguration` heartbeat on each authenticated polling request. Dashboard shows HEALTHY if the last check is less than 30 seconds old, otherwise OFFLINE / STALE.
- Dashboard displays tracked open-position count and an authenticated pause/resume action. Pausing blocks new BUY orders; TP/SL protective SELL exits still run while the monitor worker is online.
- Existing TP/SL monitoring worker remains a separate process. Monitor heartbeat does not guarantee that every price or exit was processed successfully.

## Not yet implemented — do not treat these as finished
- Enforced daily loss cap, snapshot-based equity reconciliation and a complete risk panel.
- Distributed singleton monitor lease, persistent position CLOSING state, and deadlock retry policy.
- Complete dashboard equity, win rate, equity curve, activity log and redesign matching the separate canvas.
- One-screen sizing percentage presets, chart snapshot journal, notification integration.
- Real exchangeInfo filter validation, adaptive spread/slippage, backtest gap-fill models and walk-forward testing.
- Automatic legacy holdings reconciliation and end-to-end/integration test suite.
- Verified browser screenshots (previous documentation images are illustrative).

## Deployment and validation
1. Pull latest code and run `npm install && npm run db:generate && npm run typecheck && npm run build`.
2. Apply migrations with `npx prisma migrate deploy --schema packages/database/prisma/schema.prisma`.
3. Start the web app and the independent monitor process, and check the dashboard heartbeat updates.
4. Test two concurrent BUY requests, simultaneous manual SELL and monitor SELL, repeat idempotency keys, and simulated monitor outages against a disposable paper account.
5. Do not use real money; this system has not been verified against your running deployment.

## Operational runbook
If dashboard shows OFFLINE / STALE: check the worker process, `PAPER_MONITOR_SECRET`, `PAPER_MONITOR_URL`, network access to Binance public data and server logs. Restart the worker under a supervisor such as systemd/PM2. Inspect open positions and balances before restarting. Pausing new buys does not liquidate holdings or turn off protective exits.

## Backup
Before migrations, back up MySQL with `mysqldump --single-transaction -u <user> -p cryptobot > cryptobot-backup.sql`. Restore into a separate test database with `mysql -u <user> -p cryptobot_test < cryptobot-backup.sql` after creating that database. Protect backups and do not commit credentials.
