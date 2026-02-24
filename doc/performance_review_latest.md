# Backtest, Data, and Strategy Review (latest)

## Scope
- Reviewed `data/reports/latest` backtest outputs.
- Audited `data/raw` and `data/processed` historical data consistency against 5-minute backtest assumptions.
- Reviewed strategy implementation in `strategy_core.py`, `backtest_vectorized.py`, and configuration in `long_short_config.py`.

## 1) Backtest report understanding
From `data/reports/latest/summary.json` and `summary.md`:
- Base case total return: **-28.78%** with Sharpe **-3.995** and max drawdown **-28.93%**.
- Stress 1.5x cost total return: **-45.36%**, Sharpe **-5.252**.
- Stress 2.0x cost + 1-bar delay total return: **-62.46%**, Sharpe **-5.811**.
- Decision in the report is **"abandon"**.

Distribution-level behavior from report CSVs:
- Monthly returns are mostly negative after July, including a severe **-19.36%** month in October.
- Daily/bar return profile is heavily negatively skewed by win-rate (from command-line diagnostics): low positive-hit frequency with persistent drift down.

## 2) Historical data issues found
### A. Mixed bar frequencies (critical)
Raw files for several non-equity assets are **hourly (60m mode)**, not 5m:
- `AUDUSD`, `EURUSD`, `GOLD`, `SILVER`, `COPPER` have 60-minute mode bar spacing.

This conflicts with the 5-minute backtest grid (`_build_session_index` and strategy logic) and causes sparse participation.

### B. Severe session coverage gaps for FX/metals in processed data
During the backtest regular-session index, approximate non-null close coverage is:
- Stocks: ~95%
- Crypto: ~100%
- FX/metals: only ~8.5% to 8.8%

So the portfolio universe is effectively much smaller and unbalanced versus intended multi-asset design.

### C. Feature invalidation for FX/metals
Because EWMA vol uses 5m-like continuity (`ewm(..., min_periods=30)`) while these assets are hourly-sparse on a 5m grid, the model features for those assets are mostly unusable.
In diagnostics, `m_star` non-null ratio is effectively:
- `EURUSD`, `AUDUSD`, `GOLD`, `SILVER`, `COPPER`: **0%**

Net: these assets are configured but functionally inactive in signal generation.

## 3) Strategy/design reasons performance is bad
### A. Universe implementation mismatch vs. hypothesis
The hypothesis claims multi-asset, correlation-aware cross-asset robustness, but due data quality/frequency mismatch the strategy runs mostly on equities + crypto. That reduces diversification and can worsen momentum whipsaw losses.

### B. Rebalance timing drift relative to documented schedule
The rebalance trigger checks `signal_ts` time (previous bar) against `REBALANCE_TIMES`:
- Implementation can execute entries one bar later than nominal schedule (e.g., signal at 10:00, execution at ~10:05 open under normal mode), creating practical slippage-like degradation.

### C. Correlation estimation likely mis-specified
`rolling_hourly_correlation` uses hourly returns and `tail(24 * 60)`, i.e. ~1440 hourly points (~60 days), while comments/intent imply a shorter rolling horizon. This can make pairing slow/reactive. Also the shrinkage combines correlation with identity scaled by average variance, mixing units.

### D. Strong cost sensitivity reveals weak pre-cost edge
Performance collapses as friction assumptions are increased (base -> 1.5x -> 2.0x+delay), which indicates the gross signal edge is insufficient for realistic implementation.

### E. Intraday mechanics likely over-trading relative to signal quality
Three daily rebalances with ATR stop/target and median-rank exits can create frequent turnover; when alpha is weak/noisy, costs dominate quickly.

## 4) Prioritized root-cause list
1. **Data frequency mismatch** (hourly FX/metals in a 5m strategy) invalidates intended multi-asset signal set.
2. **Sparse/invalid feature coverage** for entire asset classes (0% usable momentum score on several assets).
3. **Weak signal robustness to friction** (dramatic decay in stress scenarios).
4. **Execution schedule alignment/slippage artifact** from signal timestamp gating.
5. **Potentially stale/mis-scaled correlation pairing inputs**.

## 5) Immediate remediation suggestions
- Rebuild all assets at true 5m granularity for the exact backtest window; exclude any asset that cannot meet that quality threshold.
- Add automated data-quality gates before backtest (bar-frequency check, in-session coverage threshold, feature-availability threshold).
- Enforce minimum active universe breadth before trading each rebalance.
- Fix rebalance scheduling to explicit execution timestamps and separately model delay only in stress tests.
- Revisit correlation window and shrinkage formulation to keep units consistent and responsive.
