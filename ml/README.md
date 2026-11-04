# Phase 0 — Candle storage audit (no ML training)

## Verified from source
- `MarketCandle` stores symbol, interval, openTime, closeTime, OHLC and volume as MySQL DECIMAL(30,12).
- `@@unique([symbol,interval,openTime])` prevents duplicate stored timestamps.
- `apps/web/lib/market.ts` retrieves Binance public klines and `persistClosedCandles` writes only interval `5m` with `skipDuplicates:true`.
- `apps/web/app/api/market/sync/route.ts` fetches at most 1,000 recent candles per request. It does not implement a complete historical backfill or gap repair.
- `apps/web/app/api/backtests/route.ts` uses the newest 1,000 closed stored 5m candles, rejects non-consecutive open times, and runs long-only next-open simulation.
- `apps/web/lib/setup-service.ts` obtains 5m/15m/1h/4h closed bars from public Binance directly; these higher-timeframe bars are not persisted by the current sync function.

## Execute read-only audit
```bash
cd ~/Downloads/cryptobot-phase1/cryptobot
git pull origin main
mysql -u cryptobot -p cryptobot < ml/audit/candle_quality.sql | tee phase0-candle-audit.txt
```
Replace database/user names if different. Do not share database passwords. This file contains SELECT statements only.

## Interpretation
- Date range: `first_open_utc` to `last_open_utc`.
- `missing_slots_estimate`: expected 5-minute slots minus stored rows within each symbol's stored range.
- Gap detail: every consecutive timestamp difference greater than 300 seconds; `missing_candles` is the count of absent 5-minute intervals.
- Duplicate query should return no rows due to unique constraint.
- Invalid OHLCV and misalignment queries should return no rows.
- No row for a symbol means no stored 5m candles for that symbol; it does **not** mean zero missing candles.
- The script does not count missing candles before the first stored row or after the last stored row. Choose an explicit intended historical range for that audit.

## Data risks
1. Only 1,000 recent 5m candles are fetched per sync (~83h20m); repeated sync does not build years of reliable history without scheduling and range backfill.
2. `parseCandles` silently deduplicates API rows; store quality counters before deduplication in a later phase.
3. No source endpoint, ingestion timestamp, exchange dataset revision, or checksum fields are stored per candle.
4. Higher timeframe features must use **completed** 1h/4h bars whose closeTime is at or before each 5m decision timestamp.
5. Existing backtester uses numeric floating point internally; ML features can use float after validated ingestion, but order accounting should stay Decimal.
6. The current database has not been queried by this audit; actual counts and ranges are unknown until the SQL is executed.

## Proposed folder layout
```text
ml/
  README.md
  audit/candle_quality.sql
  data/                 # ignored raw exports; never commit sensitive data
  features/             # Phase 1 indicators and time-safe joins
  labels/               # Phase 1 long/short triple-barrier labels
  training/             # Phase 2 walk-forward and calibration
  inference/            # Phase 3 ONNX export and contracts
  tests/
  artifacts/            # model versions and reproducibility metadata
packages/core/src/ml/   # shared TS prediction types, Phase 3
apps/web/app/api/ml/    # prediction API, Phase 3
```

## Acceptance criteria for Phase 0
- Run the SQL against the real MySQL database.
- Save results for BTCUSDT and ETHUSDT: first/last UTC timestamps, stored count, expected slots, missing slots, exact gap locations, duplicates, invalid OHLCV, alignment.
- Decide target historical training period and gap-repair method.
- **Do not start Phase 1** until the quality report has been reviewed.
