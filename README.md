# Long/Short Mean Reversion Strategy (v5)

This repository now runs a **v5 multi-timeframe engine**:
- `1W` regime scoring (`RISK_ON` / `NEUTRAL` / `RISK_OFF`),
- `1D` cross-asset signal and target construction,
- `4H` staged execution with quality gating,
- hard data-quality gates and friction stress testing.

## 1) Setup

```bash
pip install -r requirements.txt
```

Polygon API key is required (all assets now pull from Polygon):

```bash
cp .env.example .env
# set POLYGON_API_KEY=...
```

## 2) Build Data (Polygon-only, 1D + 4H + Quality Gates)

If you already have raw CSV files in `data/raw`, build processed v5 matrices only:

```bash
python data_pipeline.py --build-only
```

Or fetch fresh raw data from Polygon then build:

```bash
python data_pipeline.py --force --start 2025-06-01 --end 2026-01-31
```

Main outputs:
- `data/processed/opens_1d.pkl`
- `data/processed/highs_1d.pkl`
- `data/processed/lows_1d.pkl`
- `data/processed/closes_1d.pkl`
- `data/processed/opens_4h.pkl`
- `data/processed/highs_4h.pkl`
- `data/processed/lows_4h.pkl`
- `data/processed/closes_4h.pkl`
- `data/processed/data_quality_report_v5.json`

Backtest runs with hard data gates; if the quality report fails, the engine will stop with reasons.

## 3) Run the v5 Backtest

```bash
python backtest_vectorized.py
```

This runs the base scenario and prints the latest equity values plus turnover diagnostics.

## 4) Run Full Scenario Matrix + Report Bundle

```bash
python backtest_report.py
```

Optional:

```bash
python backtest_report.py --no-plots
python backtest_report.py --output-dir data/reports/latest
```

Report outputs include:
- scenario equity CSVs (`base`, `1.5x cost`, `2.0x + delay`, missing-data, liquidity, borrow/funding)
- `summary.md`
- `summary.json`
- `daily_returns.csv`
- `monthly_returns.csv`
- `equity_curve.png` (unless `--no-plots`)

## 5) Key Config Knobs

Edit `long_short_config.py` to tune:
- regime thresholds/caps,
- turnover controls (`NO_TRADE_BAND`, partial rebalance bounds, turnover cap),
- execution thresholds (`EXEC_QUALITY_*`, net-edge multiple),
- stress settings,
- backtest window and capital.

## 6) Development Plan Reference

Primary plan used for this implementation:
- `doc/vibe-coding-development-plan-long-short-mean-reversion-strategy-v5.md`

Strategy spec:
- `doc/long-short-trading-strategy-v5.md`
