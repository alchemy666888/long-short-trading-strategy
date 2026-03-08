# Backtest Summary (v6)

## 1. Scenario Overview
### base
- Total return: 10.48%
- Sharpe: 0.725
- Max drawdown: -9.29%
### stress_1p5x
- Total return: 10.16%
- Sharpe: 0.703
- Max drawdown: -9.51%
### stress_2p0x_delay
- Total return: 15.14%
- Sharpe: 1.023
- Max drawdown: -6.24%
### stress_missing_data
- Total return: 12.33%
- Sharpe: 1.018
- Max drawdown: -2.14%
### stress_liquidity
- Total return: 10.80%
- Sharpe: 0.743
- Max drawdown: -9.08%
### stress_borrow_funding
- Total return: 9.67%
- Sharpe: 0.670
- Max drawdown: -9.80%

## 2. v6 vs v5 Comparison
- Base Sharpe uplift: 0.061
- Stress 1.5x Sharpe uplift: 0.061
- Overlay high-Q contribution share: 1.000

## 3. Acceptance Checks
- oos_sharpe_uplift_ge_0p20: FAIL
- max_drawdown_not_worse_than_v5: PASS
- cost_stress_sharpe_uplift_ge_0p10: FAIL
- overlay_contrib_high_q_ge_60pct: PASS
- worst_fold_not_worse_than_v5: PASS

**Decision: refine**
