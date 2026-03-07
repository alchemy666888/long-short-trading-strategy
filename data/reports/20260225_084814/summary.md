# Backtest Summary (v5)

## 1. Hypothesis
Weekly-regime plus daily trend/reversal scoring with 4H staged execution can preserve net edge under friction and turnover constraints.

## 2. Scenarios
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

## 3. Regime-State Attribution (Base)
### RISK_ON
- Total return: nan%
- Sharpe: nan
- Max drawdown: nan%
### NEUTRAL
- Total return: 12.79%
- Sharpe: 0.844
- Max drawdown: -10.29%
### RISK_OFF
- Total return: -0.58%
- Sharpe: -1.417
- Max drawdown: -1.43%

## 4. Turnover Decomposition (Base)
- Raw turnover (avg daily): 21.93%
- Turnover after no-trade band (avg daily): 21.93%
- Throttled turnover (avg daily): 11.05%
- Median daily turnover: 0.00%

## 5. Execution Diagnostics (Base)
- Executed trades: 78
- Deferred trades: 77
- Canceled trades: 143
- Avg slippage (bps) by quality bucket:
  - high: 1.00
  - medium: 3.00
  - low: 6.00

## 6. Breadth and Eligibility (Base)
- Average active assets: 1.22
- Average active categories: 0.60
- Mean max-category share: 0.22

## 7. Cost Drag by Asset Class (Base)
- stock: $326.88
- forex: $191.51
- metal: $358.06
- crypto: $6,378.65

## 8. Risk Event Ledger (Base)
- Total risk events: 266
- breadth_gate_block: 242
- stop_loss: 11
- time_stop: 7
- portfolio_dd5_cut: 3
- portfolio_dd20_flat: 3

## 9. Acceptance Gate and Decision
- base_sharpe_ge_0_9: FAIL
- base_maxdd_le_12pct: PASS
- stress_1p5x_sharpe_ge_0_4: PASS
- stress_2p0x_delay_non_negative_total_return: PASS
- median_daily_turnover_le_35pct: PASS

**Decision: refine**
