# Phase 1 — Offline feature engineering and triple-barrier labeling

Phase 1 is **paper/research only**. It does not train a model, modify MySQL, call Binance, or execute orders.

## Setup (from repository root)

```bash
git pull origin main
python3 -m venv .venv-ml
source .venv-ml/bin/activate
pip install -r ml/requirements.txt
python -m unittest discover -s ml/tests -v
```

Set DATABASE_URL from your existing local environment **without publishing the password**. The Python process needs a valid `mysql://USER:PASSWORD@HOST:PORT/cryptobot` URL. For example, load your existing `.env` securely using your normal local environment management. The account needs only SELECT on MarketCandle.

```bash
python -m ml.phase1 --symbol BTCUSDT
python -m ml.phase1 --symbol ETHUSDT
```

Output is written to `ml/data/<symbol>_5m_phase1.csv` and a JSON manifest. Do **not** commit generated datasets or database credentials.

## Definitions

- Source: ordered, gap-free, closed 5m candles from MySQL. If the newest candle is still open, wait for it to close before generating a production research dataset.
- Decision: close of candle i. Features are known at that time, including the current completed 5m bar.
- Entry: next candle open (i+1). No same-bar entry.
- Labels: long (+1 side) and short (-1 side), separately. Outcome +1 = TP first, -1 = SL first, 0 = neither within horizon.
- Default horizon = 24 bars (2 hours); TP = 2 × ATR14; SL = 1.5 × ATR14. ATR is calculated at decision time.
- If TP and SL are touched within the same OHLC candle, assume **SL first**; intrabar ordering is unknowable.
- Higher timeframes: 1h and 4h built from **complete groups** of 5m candles, joined only after the higher-timeframe bar closes.
- Feature warm-up and trailing horizon rows are removed. Features do not use future bars, while labels intentionally do.
- Labels currently do **not** include trading fees, slippage, funding, or a precise intrabar execution path. Phase 2/5 must account for costs and realistic execution.
- No time-based train/test split is performed in Phase 1; chronological purged walk-forward validation belongs to Phase 2.

## Quality checks

`validate()` rejects missing 5m timestamps, duplicates, bad ordering, non-UTC input, nonfinite OHLCV, misaligned timestamps, and invalid price ranges. Run `ml/audit/candle_quality.sql` before extraction. Check the output manifest and row counts.

## Scope and next phase

Phase 2: train and evaluate calibrated per-side models using walk-forward splits, with purging and embargo and a buy-and-hold/rule-based baseline. Do not use Phase 1 labels as predictions.
