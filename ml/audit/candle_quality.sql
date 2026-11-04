-- CryptoBot Phase 0: read-only MySQL 8 candle quality audit.
-- All timestamps are reported in UTC. Expected spacing: 300 seconds.
-- Run: mysql -u cryptobot -p cryptobot < ml/audit/candle_quality.sql
SET time_zone = '+00:00';
SELECT symbol, interval, COUNT(*) AS stored_rows,
       MIN(openTime) AS first_open_utc, MAX(openTime) AS last_open_utc,
       CASE WHEN COUNT(*)=0 THEN 0 ELSE
         TIMESTAMPDIFF(MINUTE, MIN(openTime), MAX(openTime))/5 + 1 END AS expected_slots,
       CASE WHEN COUNT(*)=0 THEN 0 ELSE
         TIMESTAMPDIFF(MINUTE, MIN(openTime), MAX(openTime))/5 + 1 - COUNT(*) END AS missing_slots_estimate
FROM MarketCandle
WHERE symbol IN ('BTCUSDT','ETHUSDT') AND `interval`='5m'
GROUP BY symbol, interval;
-- Exact gaps: use LAG; also flag non-5m-aligned timestamps.
WITH ordered AS (
 SELECT symbol, openTime,
        LAG(openTime) OVER (PARTITION BY symbol ORDER BY openTime) AS previous_open
 FROM MarketCandle
 WHERE symbol IN ('BTCUSDT','ETHUSDT') AND `interval`='5m'
)
SELECT symbol, previous_open AS gap_after_utc, openTime AS gap_before_utc,
       TIMESTAMPDIFF(SECOND, previous_open, openTime) DIV 300 - 1 AS missing_candles
FROM ordered
WHERE previous_open IS NOT NULL AND TIMESTAMPDIFF(SECOND, previous_open, openTime)>300
ORDER BY symbol, previous_open;
SELECT symbol, `interval`, openTime, COUNT(*) AS duplicates
FROM MarketCandle
WHERE symbol IN ('BTCUSDT','ETHUSDT') AND `interval`='5m'
GROUP BY symbol, `interval`, openTime HAVING COUNT(*)>1;
SELECT symbol, COUNT(*) AS invalid_ohlcv_rows
FROM MarketCandle WHERE symbol IN ('BTCUSDT','ETHUSDT') AND `interval`='5m'
AND (open<=0 OR close<=0 OR high<low OR high<GREATEST(open,close)
OR low>LEAST(open,close) OR volume<0 OR closeTime<=openTime)
GROUP BY symbol;
SELECT symbol, COUNT(*) AS misaligned_open_times
FROM MarketCandle WHERE symbol IN ('BTCUSDT','ETHUSDT') AND `interval`='5m'
AND MOD(UNIX_TIMESTAMP(openTime),300)<>0
GROUP BY symbol;
