# Backtest Summary (v5)

## 1. Scenario Overview
### base
- Total return: 12.13%
- Sharpe: 0.772
- Max drawdown: -10.81%
### stress_1p5x
- Total return: 11.73%
- Sharpe: 0.746
- Max drawdown: -10.86%
### stress_2p0x_delay
- Total return: 14.72%
- Sharpe: 0.932
- Max drawdown: -9.54%
### stress_missing_data
- Total return: -5.53%
- Sharpe: -0.376
- Max drawdown: -11.00%
### stress_liquidity
- Total return: 12.45%
- Sharpe: 0.793
- Max drawdown: -10.70%
### stress_borrow_funding
- Total return: 11.28%
- Sharpe: 0.718
- Max drawdown: -10.94%

## 3. Acceptance Checks
- base_sharpe_ge_0_9: FAIL
- base_maxdd_le_12pct: PASS
- stress_1p5x_sharpe_ge_0_4: PASS
- stress_2p0x_delay_non_negative_total_return: PASS
- median_daily_turnover_le_35pct: PASS

**Decision: refine**
