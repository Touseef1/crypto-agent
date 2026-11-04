-- Read-only historical candle quality audit for BTCUSDT and ETHUSDT.
-- Run in MySQL 8 / phpMyAdmin. Dates interpreted in UTC.
SET time_zone = '+00:00';

-- 1. Coverage, duplicates-independent estimated slots, and date ranges.
SELECT symbol,`interval`,COUNT(*) AS stored_rows,
 MIN(openTime) AS first_open_utc,MAX(openTime) AS last_open_utc,
 CASE `interval` WHEN '1m' THEN 60 WHEN '5m' THEN 300 WHEN '15m' THEN 900 WHEN '1h' THEN 3600 WHEN '4h' THEN 14400 WHEN '1d' THEN 86400 END AS interval_seconds,
 FLOOR(TIMESTAMPDIFF(SECOND,MIN(openTime),MAX(openTime)) /
 CASE `interval` WHEN '1m' THEN 60 WHEN '5m' THEN 300 WHEN '15m' THEN 900 WHEN '1h' THEN 3600 WHEN '4h' THEN 14400 WHEN '1d' THEN 86400 END)+1 AS expected_slots,
 FLOOR(TIMESTAMPDIFF(SECOND,MIN(openTime),MAX(openTime)) /
 CASE `interval` WHEN '1m' THEN 60 WHEN '5m' THEN 300 WHEN '15m' THEN 900 WHEN '1h' THEN 3600 WHEN '4h' THEN 14400 WHEN '1d' THEN 86400 END)+1-COUNT(*) AS missing_slots_estimate
FROM MarketCandle
WHERE symbol IN ('BTCUSDT','ETHUSDT') AND `interval` IN ('1m','5m','15m','1h','4h','1d')
GROUP BY symbol,`interval` ORDER BY symbol,`interval`;

-- 2. Exact timestamp gaps / overlaps by timeframe.
WITH ordered AS (
 SELECT symbol,`interval`,openTime,
 LAG(openTime) OVER(PARTITION BY symbol,`interval` ORDER BY openTime) AS prev_time,
 CASE `interval` WHEN '1m' THEN 60 WHEN '5m' THEN 300 WHEN '15m' THEN 900 WHEN '1h' THEN 3600 WHEN '4h' THEN 14400 WHEN '1d' THEN 86400 END AS seconds_per_bar
 FROM MarketCandle WHERE symbol IN ('BTCUSDT','ETHUSDT') AND `interval` IN ('1m','5m','15m','1h','4h','1d')
), differences AS (
 SELECT *,TIMESTAMPDIFF(SECOND,prev_time,openTime) AS elapsed_seconds FROM ordered
)
SELECT symbol,`interval`,COUNT(*) AS irregular_transitions,
 SUM(CASE WHEN elapsed_seconds>seconds_per_bar THEN 1 ELSE 0 END) AS gap_events,
 SUM(CASE WHEN elapsed_seconds>seconds_per_bar THEN FLOOR(elapsed_seconds/seconds_per_bar)-1 ELSE 0 END) AS missing_bars,
 SUM(CASE WHEN elapsed_seconds<seconds_per_bar THEN 1 ELSE 0 END) AS overlapping_or_off_grid_events
FROM differences WHERE prev_time IS NOT NULL AND elapsed_seconds<>seconds_per_bar
GROUP BY symbol,`interval` ORDER BY symbol,`interval`;

-- 3. Duplicate keys.
SELECT symbol,`interval`,openTime,COUNT(*) AS duplicate_rows
FROM MarketCandle WHERE symbol IN ('BTCUSDT','ETHUSDT')
GROUP BY symbol,`interval`,openTime HAVING COUNT(*)>1 LIMIT 50;

-- 4. Invalid OHLCV and candle time boundaries.
SELECT symbol,`interval`,COUNT(*) AS invalid_rows
FROM MarketCandle
WHERE symbol IN ('BTCUSDT','ETHUSDT') AND `interval` IN ('1m','5m','15m','1h','4h','1d')
AND (open<=0 OR high<=0 OR low<=0 OR close<=0 OR volume<0
 OR high<low OR high<GREATEST(open,close) OR low>LEAST(open,close)
 OR closeTime<=openTime)
GROUP BY symbol,`interval`;

-- 5. Misaligned open timestamps.
SELECT symbol,`interval`,COUNT(*) AS misaligned_rows
FROM MarketCandle
WHERE symbol IN ('BTCUSDT','ETHUSDT') AND `interval` IN ('1m','5m','15m','1h','4h','1d')
AND MOD(UNIX_TIMESTAMP(openTime),CASE `interval` WHEN '1m' THEN 60 WHEN '5m' THEN 300 WHEN '15m' THEN 900 WHEN '1h' THEN 3600 WHEN '4h' THEN 14400 WHEN '1d' THEN 86400 END)<>0
GROUP BY symbol,`interval`;

-- 6. Compare fully covered 5m candles against 1m aggregation.
-- A 5m candle is checked only when all five underlying 1m rows exist.
WITH minute_bars AS (
 SELECT symbol,FLOOR(UNIX_TIMESTAMP(openTime)/300)*300 AS bucket,
 COUNT(*) AS n,MIN(openTime) AS first_open,MAX(openTime) AS last_open,
 MAX(high) AS agg_high,MIN(low) AS agg_low,SUM(volume) AS agg_volume
 FROM MarketCandle WHERE `interval`='1m' AND symbol IN ('BTCUSDT','ETHUSDT')
 GROUP BY symbol,FLOOR(UNIX_TIMESTAMP(openTime)/300)
), aggregated AS (
 SELECT m.symbol,m.bucket,m.n,
 (SELECT x.open FROM MarketCandle x WHERE x.symbol=m.symbol AND x.`interval`='1m' AND x.openTime=m.first_open LIMIT 1) AS agg_open,
 (SELECT x.close FROM MarketCandle x WHERE x.symbol=m.symbol AND x.`interval`='1m' AND x.openTime=m.last_open LIMIT 1) AS agg_close,
 m.agg_high,m.agg_low,m.agg_volume
 FROM minute_bars m WHERE m.n=5
)
SELECT c.symbol,COUNT(*) AS compared_5m,
 SUM(CASE WHEN ABS(c.open-a.agg_open)>0.00000001 OR ABS(c.high-a.agg_high)>0.00000001
 OR ABS(c.low-a.agg_low)>0.00000001 OR ABS(c.close-a.agg_close)>0.00000001
 OR ABS(c.volume-a.agg_volume)>GREATEST(0.00000001,a.agg_volume*0.000001)
 THEN 1 ELSE 0 END) AS mismatched_5m
FROM MarketCandle c JOIN aggregated a ON a.symbol=c.symbol AND a.bucket=UNIX_TIMESTAMP(c.openTime)
WHERE c.`interval`='5m'
GROUP BY c.symbol;
