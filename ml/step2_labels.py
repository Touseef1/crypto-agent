"""Step 2 research: 1m first-hit triple-barrier labels on existing 5m features.

Read-only MySQL input; separate outputs leave Phase 1 baselines untouched.
No real orders. All timestamps UTC; no lookahead in features.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse, unquote
import os

import numpy as np
import pandas as pd

from ml.phase1 import STEP, FEATURE_COLUMNS, load_mysql, validate, continuous_segments, add_higher_timeframes

MINUTE = pd.Timedelta(minutes=1)


def load_minutes(symbol):
    import pymysql
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL is required")
    u = urlparse(url)
    if u.scheme != "mysql":
        raise ValueError("DATABASE_URL must use mysql://")
    conn = pymysql.connect(
        host=u.hostname, port=u.port or 3306,
        user=unquote(u.username or ""), password=unquote(u.password or ""),
        database=u.path.lstrip("/"), cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SET time_zone = '+00:00'")
            cur.execute(
                "SELECT openTime, `open`, high, low, `close`, volume "
                "FROM MarketCandle WHERE symbol=%s AND `interval`='1m' "
                "ORDER BY openTime", (symbol,)
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        raise ValueError("No stored 1m candles for " + symbol)
    df = pd.DataFrame(rows)
    df["openTime"] = pd.to_datetime(df["openTime"], utc=True)
    df = df.set_index("openTime").astype(float)
    if df.index.has_duplicates or not df.index.is_monotonic_increasing:
        raise ValueError("Duplicate or unordered 1m candles")
    if not ((df.index.second == 0) & (df.index.microsecond == 0)).all():
        raise ValueError("Misaligned 1m candles")
    if not np.isfinite(df[["open", "high", "low", "close", "volume"]].to_numpy()).all():
        raise ValueError("Nonfinite 1m OHLCV")
    if not ((df["low"] > 0) & (df["high"] >= df[["open", "close"]].max(axis=1))
            & (df["low"] <= df[["open", "close"]].min(axis=1))
            & (df["volume"] >= 0)).all():
        raise ValueError("Invalid 1m OHLCV")
    return df


def label_segment(frame, minute, features, horizon, tp_atr, sl_atr):
    """Label only windows with every required 1m bar present.

    Entry at next 5m open; check 1m bars from entry through horizon end.
    Both barriers hit in the same 1m candle -> SL first (conservative).
    A missing 1m candle invalidates the entire window, not just the gap.
    """
    if horizon < 1 or tp_atr <= 0 or sl_atr <= 0:
        raise ValueError("Invalid barrier configuration")
    n = len(frame)
    if n <= horizon:
        return pd.DataFrame(), 0
    m_times = minute.index.asi8
    m_high = minute["high"].to_numpy(float)
    m_low = minute["low"].to_numpy(float)
    m_close = minute["close"].to_numpy(float)
    f_times = frame.index.asi8
    f_open = frame["open"].to_numpy(float)
    f_close = frame["close"].to_numpy(float)
    atr = features["atr14_pct"].to_numpy(float) * f_close
    ns_min = int(MINUTE.value)
    expected = horizon * 5
    records = []
    skipped = 0
    # Only process decision points with complete future 1m paths.
    for i in range(n - horizon):
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        entry_time = f_times[i + 1]
        start = int(np.searchsorted(m_times, entry_time))
        stop = start + expected
        if stop > len(m_times) or m_times[start] != entry_time or m_times[stop - 1] != entry_time + (expected - 1) * ns_min:
            skipped += 1
            continue
        if np.any(np.diff(m_times[start:stop]) != ns_min):
            skipped += 1
            continue
        # A 5m open should match its first 1m open; otherwise source data conflicts.
        if not np.isclose(f_open[i + 1], float(minute["open"].iloc[start]), rtol=1e-8, atol=1e-8):
            skipped += 1
            continue
        entry = f_open[i + 1]
        for side in (1, -1):
            tp = entry + side * tp_atr * atr[i]
            sl = entry - side * sl_atr * atr[i]
            outcome = 0
            exit_pos = stop - 1
            for j in range(start, stop):
                take = (m_high[j] >= tp) if side == 1 else (m_low[j] <= tp)
                loss = (m_low[j] <= sl) if side == 1 else (m_high[j] >= sl)
                if loss or take:
                    outcome = -1 if loss else 1
                    exit_pos = j
                    break
            exit_price = sl if outcome == -1 else tp if outcome == 1 else m_close[exit_pos]
            gross_return = side * (exit_price / entry - 1)
            records.append((i, side, outcome, pd.Timestamp(m_times[exit_pos], tz="UTC"),
                            entry, tp, sl, exit_price, gross_return))
    cols = ["row", "side", "outcome", "exit_candle_open_utc", "entry",
            "take_profit", "stop_loss", "exit_price", "gross_return"]
    return pd.DataFrame.from_records(records, columns=cols), skipped


def make_dataset(frame, minute, horizon, tp_atr, sl_atr):
    validate(frame)
    segments = continuous_segments(frame)
    parts = []
    skipped = 0
    for segment in segments:
        if len(segment) <= horizon:
            continue
        features = add_higher_timeframes(segment)
        labels, missing = label_segment(segment, minute, features, horizon, tp_atr, sl_atr)
        skipped += missing
        if labels.empty:
            continue
        part = features.iloc[labels["row"].to_numpy()][FEATURE_COLUMNS].reset_index().rename(
            columns={"openTime": "decision_candle_open_utc"}
        )
        for col in labels.columns:
            if col != "row":
                part[col] = labels[col].to_numpy()
        part = part.replace([np.inf, -np.inf], np.nan).dropna(subset=FEATURE_COLUMNS)
        parts.append(part)
    if not parts:
        raise ValueError("No valid 1m-labeled examples")
    data = pd.concat(parts, ignore_index=True).sort_values(
        ["decision_candle_open_utc", "side"], kind="stable"
    ).reset_index(drop=True)
    # Overlapping event windows share information. This inverse-concurrency
    # approximation is for analysis; chronological purging is still required.
    # Use event durations on 1m grid to calculate average concurrent events.
    starts = pd.to_datetime(data["decision_candle_open_utc"], utc=True).astype("int64").to_numpy() + STEP.value
    ends = pd.to_datetime(data["exit_candle_open_utc"], utc=True).astype("int64").to_numpy() + MINUTE.value
    timeline = np.unique(np.concatenate((starts, ends)))
    increments = np.zeros(len(timeline) + 1, dtype=np.int64)
    np.add.at(increments, np.searchsorted(timeline, starts), 1)
    np.add.at(increments, np.searchsorted(timeline, ends), -1)
    # Concurrency is defined on intervals between unique event boundaries.\n    # There are len(timeline)-1 intervals, not len(timeline) points.\n    concurrency = np.cumsum(increments)[:len(timeline) - 1]
    inverse = np.divide(1.0, concurrency, out=np.zeros_like(concurrency, dtype=float), where=concurrency > 0)
    duration = np.diff(timeline).astype(float)
    prefix = np.concatenate(([0.0], np.cumsum(inverse * duration)))
    a = np.searchsorted(timeline, starts)
    b = np.searchsorted(timeline, ends)
    data["uniqueness_weight"] = (prefix[b] - prefix[a]) / np.maximum((ends - starts).astype(float), 1.0)
    return data, {"continuous_segments": len(segments), "skipped_incomplete_1m_windows": skipped}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", choices=["BTCUSDT", "ETHUSDT"], required=True)
    p.add_argument("--horizon", type=int, default=24, help="Number of future 5m bars")
    p.add_argument("--tp-atr", type=float, default=2.0)
    p.add_argument("--sl-atr", type=float, default=1.5)
    p.add_argument("--output-dir", default="ml/data/step2")
    args = p.parse_args()
    if args.horizon < 1 or args.tp_atr <= 0 or args.sl_atr <= 0:
        p.error("horizon must be positive and barriers must be > 0")
    frame = load_mysql(args.symbol)
    frame = frame.loc[frame.index + STEP <= pd.Timestamp.now(tz="UTC")]
    minute = load_minutes(args.symbol)
    minute = minute.loc[minute.index + MINUTE <= pd.Timestamp.now(tz="UTC")]
    data, diagnostics = make_dataset(frame, minute, args.horizon, args.tp_atr, args.sl_atr)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{args.symbol.lower()}_1m_first_hit_h{args.horizon}_tp{args.tp_atr:g}_sl{args.sl_atr:g}"
    target = out / (stem + ".csv")
    data.to_csv(target, index=False)
    meta = {"symbol": args.symbol, "rows": len(data), "source_5m": len(frame),
            "source_1m": len(minute), "horizon_5m_bars": args.horizon,
            "tp_atr": args.tp_atr, "sl_atr": args.sl_atr,
            "entry": "next 5m open", "label_source": "1m first-hit",
            "same_1m_tie": "SL first", "timeout": "last 1m close",
            "gross_return_excludes_costs": True,
            "uniqueness_weight": "inverse concurrent event exposure; approximate",
            **diagnostics}
    (out / (stem + ".json")).write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"output": str(target), **meta}, indent=2))


if __name__ == "__main__":
    main()
