# Vibe Coding Development Plan: Long-Short Mean-Reversion (Revised)

## Goal
Ship a robust intraday backtesting workflow for the revised strategy spec, with strict 5-minute data integrity and a required backtest interval of **June 2025 through January 2026**.

## Guiding Principles

1. Ship small, testable increments.
2. Fail fast on bad data instead of silently coercing.
3. Keep signal logic simple, explainable, and auditable.
4. Separate baseline diagnostics from optimization experiments.

## Phase 1: Data Pipeline Hardening

### Objectives
- Guarantee 5-minute consistency.
- Prevent hidden truncation from provider limits.
- Produce aligned open/close matrices with explicit sparsity.

### Tasks
1. Implement Polygon chunked history downloads for long ranges.
2. Avoid silent Yahoo 60m fallback for 5m requests.
3. Parse and sanitize raw CSVs robustly (including multi-row Yahoo headers).
4. Infer native bar spacing per asset and mark non-5m assets.
5. Forward-fill only one-bar gaps for native 5m assets; keep others sparse.
6. Rebuild processed pickles (`opens.pkl`, `closes.pkl`).

### Acceptance Criteria
- No mixed-frequency contamination in processed data.
- Crypto history is not capped to early-period truncation when Polygon access is available.
- Data range can support backtest filtering through January 2026.

## Phase 2: Strategy Logic Upgrade

### Objectives
- Replace raw-level z-score with class-relative spread z-score.
- Add volatility regime gating.
- Improve execution realism with class-specific costs.

### Tasks
1. Build peer-basket spread per asset: `log(asset) - mean(log(peers))`.
2. Compute rolling z-score (36 bars).
3. Add diversified selection limits (max positions per class per side).
4. Add SPY realized-volatility z-score regime filter.
5. Keep next-bar execution and intrabar TP/stop checks.
6. Use per-class cost assumptions and leverage/risk caps.

### Acceptance Criteria
- Signals and orders are reproducible from saved input bars.
- No look-ahead bias in order timing.
- Cost model and risk parameters are configurable in one place.

## Phase 3: Backtest Engine and Reporting

### Objectives
- Enforce required evaluation window.
- Produce reliable diagnostics for iterative tuning.

### Tasks
1. Filter backtest to June 1, 2025 through January 31, 2026.
2. Remove anchor-asset gating that can unintentionally truncate period.
3. Generate equity, bar, daily, monthly returns, and summary report.
4. Track turnover/cost drag in diagnostic scripts.

### Acceptance Criteria
- `summary.md` and `summary.json` reflect requested period bounds.
- Report artifacts in `data/reports/latest` are internally consistent.

## Phase 4: Parameter Sweep and Robustness

### Objectives
- Evaluate if edge survives realistic costs.
- Prioritize stable parameter regions over single-point best Sharpe.

### Core Sweep Grid
- Lookback: 24, 36, 48
- Entry z: 1.8, 2.2, 2.5
- Stop z: 3.2, 3.8, 4.2
- Risk budget fraction: 0.75%, 1.0%, 1.25%

### Analysis Outputs
1. Net Sharpe, annualized return, max drawdown.
2. Trade count and rebalance activation ratio.
3. Cost drag as % of starting capital.
4. Exposure breakdown by asset class.

## Phase 5: Production-Readiness Enhancements

### Recommended Next Enhancements
1. Exchange-calendar-driven session construction (NYSE calendar).
2. Slippage model tied to volatility and spread proxies.
3. Walk-forward parameter selection.
4. Per-asset liquidity and min-notional constraints.
5. Trade blotter export for detailed post-trade analytics.

## Execution Checklist for This Iteration

1. Update docs and config parameters.
2. Implement data pipeline hardening.
3. Implement signal/risk/cost upgrades in strategy/backtest code.
4. Rebuild processed data and rerun backtest report.
5. Review metrics; iterate only if diagnostics are coherent.

## Current Status (This Iteration)

1. Code and docs are updated and backtest rerun completed.
2. Backtest timeline now reaches the required end session (January 30, 2026 close).
3. Remaining blocker: full 5-minute data backfill is incomplete without Polygon access; Yahoo 5m is recent-history-limited.
