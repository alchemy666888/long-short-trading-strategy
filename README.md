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

## Download data (Yahoo Finance)

```bash
python data_pipeline.py
```

Outputs:
- `data/raw/*.csv`
- `data/processed/opens.pkl`
- `data/processed/closes.pkl`

Note:
- Yahoo Finance intraday history is limited (often ~60 days for **5-minute** bars).
- To keep the **full universe for free**, this repo downloads **stocks at 60-minute bars** (longer history) and downloads other assets at **5-minute bars**.
- All series are then aligned onto a **5-minute grid** via forward-fill so the portfolio backtest can run on a unified timeline.

## Run backtest

```bash
python backtest_vectorized.py
```

This prints the tail of the equity series.

## Configuration

Edit `long_short_config.py` to change assets, capital, or cost assumptions.

