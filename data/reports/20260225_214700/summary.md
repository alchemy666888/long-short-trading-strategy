# Backtest Summary (v3)

## 1. Hypothesis
Vol-normalized multi-horizon momentum with correlation-aware pairing can survive conservative friction stress.

## 2. Rules snapshot
- 20/60/120 log-return z-score momentum blend with EWMA vol normalization.
- Quartile long/short candidates, correlation-aware pairing.
- ATR(20) risk: stop 1.25x, target 2.25x, rebalance 10:00/12:00/14:00 ET.
- Stress tests include 1.5x cost and 2.0x + one-bar delay.

## 3. Headline metrics

### Base
- Total return: -28.78%
- Sharpe: -3.995
- Max drawdown: -28.93%
### Stress 1.5x
- Total return: -45.36%
- Sharpe: -5.252
- Max drawdown: -45.46%
### Stress 2.0x + delay
- Total return: -62.46%
- Sharpe: -5.811
- Max drawdown: -62.52%

## 4. Decision
**abandon**
