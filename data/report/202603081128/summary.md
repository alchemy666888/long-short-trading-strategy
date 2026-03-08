# Backtest Summary (v6)

## 1. Scenario Overview
### base
- Total return: 26.77%
- Sharpe: 1.413
- Max drawdown: -6.06%
### stress_1p5x
- Total return: 26.61%
- Sharpe: 1.407
- Max drawdown: -6.10%
### stress_2p0x_delay
- Total return: 34.54%
- Sharpe: 1.401
- Max drawdown: -10.34%
### stress_missing_data
- Total return: 0.00%
- Sharpe: nan
- Max drawdown: 0.00%
### stress_liquidity
- Total return: 26.73%
- Sharpe: 1.410
- Max drawdown: -6.05%
### stress_borrow_funding
- Total return: 26.36%
- Sharpe: 1.394
- Max drawdown: -6.17%

## 2. v6 vs v5 Comparison
- Base Sharpe uplift: 0.713
- Stress 1.5x Sharpe uplift: 0.718
- Overlay high-Q contribution share: 1.000

## 3. Acceptance Checks
- oos_sharpe_uplift_ge_0p20: PASS
- max_drawdown_not_worse_than_v5: PASS
- cost_stress_sharpe_uplift_ge_0p10: PASS
- overlay_contrib_high_q_ge_60pct: PASS
- worst_fold_not_worse_than_v5: FAIL

**Decision: refine**
