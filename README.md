# Long/Short Intraday Mean Reversion (Prototype)

This repo contains a **Phase 1–3 prototype** implementation of the intraday long/short mean reversion strategy described in `long-short-trading-strategy.md`, following `vibe-coding-development-plan-long-short-mean-reversion-strategy.md`.

## What’s included

- **Phase 1**: Download + alignment pipeline for 5-minute OHLCV (Yahoo Finance via `yfinance`)
- **Phase 2**: Z-score signal generation + balanced long/short selection + inverse-volatility sizing
- **Phase 3**: Vectorized backtest loop with **next-bar execution**, flat **0.1% transaction cost per execution**, bar-based exits, and 15:55 liquidation

## Setup

```bash
pip install -r requirements.txt
```

## Polygon API Key (for full 5-minute history)

Option A (shell env):

```bash
export POLYGON_API_KEY="your_key_here"
```

Option B (`.env` file in repo root):

```bash
cp .env.example .env
# edit .env and set POLYGON_API_KEY
```

## Download data (Yahoo Finance)

```bash
python data_pipeline.py --force --start 2025-06-01 --end 2026-01-31
```

Outputs:
- `data/raw/*.csv`
- `data/processed/opens.pkl`
- `data/processed/closes.pkl`

Note:
- Yahoo Finance intraday history is limited (often ~60 days for **5-minute** bars).
- To keep the **full universe for free**, this repo downloads **stocks at 60-minute bars** (longer history) and downloads other assets at **5-minute bars**.
- All series are then aligned onto a **5-minute grid** via forward-fill so the portfolio backtest can run on a unified timeline.
- If `POLYGON_API_KEY` is not set (or Polygon fails), the pipeline now auto-falls back to Yahoo for Polygon-configured assets.
- For older Yahoo ranges (outside ~60 days), the downloader auto-switches `5m` requests to `60m` to avoid hard failures.

## Run backtest

```bash
python backtest_vectorized.py
```

This prints the tail of the equity series.

## Generate backtest report

```bash
python backtest_report.py
```

This runs the backtest and writes a report bundle to:
- `data/reports/<timestamp>/summary.md`
- `data/reports/<timestamp>/summary.json`
- `data/reports/<timestamp>/equity.csv`
- `data/reports/<timestamp>/bar_returns.csv`
- `data/reports/<timestamp>/daily_returns.csv`
- `data/reports/<timestamp>/monthly_returns.csv`
- `data/reports/<timestamp>/equity_curve.png`
- `data/reports/<timestamp>/drawdown.png`

Optional:
- `python backtest_report.py --no-plots`
- `python backtest_report.py --output-dir data/reports/latest`

## Configuration

Edit `/Users/antee/Documents/projects/long-short-trading-strategy/long_short_config.py` to change assets, capital, cost assumptions, and backtest dates:
- `BACKTEST_START_DATE = "2025-06-01"`
- `BACKTEST_END_DATE = "2026-01-31"`
