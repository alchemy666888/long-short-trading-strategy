# Backtest Summary (v6)

## 1. Scenario Overview
### base
- Total return: 29.52%
- Sharpe: 1.531
- Max drawdown: -10.96%
### stress_1p5x
- Total return: 28.99%
- Sharpe: 1.508
- Max drawdown: -11.14%
### stress_2p0x_delay
- Total return: 38.09%
- Sharpe: 1.865
- Max drawdown: -11.32%
### stress_missing_data
- Total return: 0.00%
- Sharpe: nan
- Max drawdown: 0.00%
### stress_liquidity
- Total return: 30.27%
- Sharpe: 1.563
- Max drawdown: -10.86%
### stress_borrow_funding
- Total return: 28.74%
- Sharpe: 1.493
- Max drawdown: -11.22%

## 2. v6 vs v5 Comparison
- Base Sharpe uplift: 0.867
- Stress 1.5x Sharpe uplift: 0.865
- Overlay high-Q contribution share: 1.000

## 3. Acceptance Checks
- oos_sharpe_uplift_ge_0p20: PASS
- max_drawdown_not_worse_than_v5: PASS
- cost_stress_sharpe_uplift_ge_0p10: PASS
- overlay_contrib_high_q_ge_60pct: PASS
- worst_fold_not_worse_than_v5: FAIL

**Decision: refine**
