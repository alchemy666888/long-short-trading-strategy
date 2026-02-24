# Long/Short Mean Reversion Strategy (v3 Upgrade)

This repository now implements a **v3-oriented, backtest-first** long/short framework based on:
- multi-horizon momentum (20/60/120 log-return z-scores),
- EWMA volatility normalization,
- quartile candidate selection,
- correlation-aware long/short pairing,
- ATR-based risk exits,
- stress-friction evaluation (1.5x and 2.0x+delay scenarios).

## 1) Setup

```bash
pip install -r requirements.txt
```

Optional Polygon key for richer 5-minute history:

```bash
cp .env.example .env
# set POLYGON_API_KEY=...
```

## 2) Build data

Download raw data and build aligned processed OHLC pickles:

```bash
python data_pipeline.py --force --start 2025-06-01 --end 2026-01-31
```

Generated processed files:
- `data/processed/opens.pkl`
- `data/processed/highs.pkl`
- `data/processed/lows.pkl`
- `data/processed/closes.pkl`

If you already have raw CSV files and only want to rebuild processed matrices:

```bash
python data_pipeline.py --build-only
```

## 3) Run the backtest

```bash
python backtest_vectorized.py
```

This runs the v3-style strategy and prints the equity tail.

## 4) Generate full report bundle

```bash
python backtest_report.py
```

Outputs (timestamped directory under `data/reports/`):
- `summary.md`
- `summary.json`
- `equity.csv`
- `equity_stress_1p5x.csv`
- `equity_stress_2p0x_delay.csv`
- `equity_curve.png` (unless `--no-plots`)

Useful options:

```bash
python backtest_report.py --no-plots
python backtest_report.py --output-dir data/reports/latest
```

## 5) Config knobs

Edit `long_short_config.py` for:
- date window,
- rebalance schedule,
- cost assumptions by asset class,
- leverage limits.

## 6) Notes

- Yahoo intraday 5m coverage is limited; Polygon is preferred for deeper history.
- The current implementation prioritizes v3 core mechanics and stress validation flow.
