# Long-Short Intraday Mean-Reversion Strategy (Revised)

## 1) Strategy Objective
Build a market-neutral, intraday long-short portfolio that captures short-horizon mean reversion in a mixed universe (stocks, crypto, metals, FX) while controlling turnover, slippage sensitivity, and regime risk.

## 2) Universe and Trading Session

| Parameter | Value |
| --- | --- |
| Universe | BTC, ETH, SOL, XRP, GOLD, SILVER, COPPER, EURUSD, AUDUSD, TSLA, MCD, NVDA, GOOG, SPY |
| Trading Window | 9:30 AM to 4:00 PM ET |
| Forced EOD Exit | 3:55 PM ET |
| Data Frequency | 5-minute bars (strict) |
| Backtest Window (current requirement) | June 1, 2025 to January 31, 2026 |

## 3) Signal Definition (Updated)

Previous version used raw price z-scores across heterogeneous assets. That design is fragile because level effects differ across asset classes.

Updated signal is **relative-value within asset class**:

1. For each asset, build a peer basket from same asset class excluding itself.
2. Compute spread: `log(price_asset) - mean(log(price_peers))`.
3. Compute rolling z-score of spread over 36 bars.
4. Entry candidates:
- Long when z < `-ENTRY_Z`
- Short when z > `ENTRY_Z`

Current parameters:

| Parameter | Value |
| --- | --- |
| Lookback | 36 bars (3 hours) |
| Entry threshold | 2.2 |
| Exit threshold | 0.0 (cross back to mean) |
| Stop threshold | 3.8 |
| Rebalance times | 10:00, 12:00, 14:00 ET |
| Max positions per side | 3 |
| Max positions per asset class per side | 1 |

## 4) Position Sizing and Portfolio Constraints

- Equal-risk sizing by inverse recent volatility (`std` of 5-minute returns over 36 bars).
- Total risk budget per rebalance: `1%` of current equity.
- Gross leverage cap: `3.0x`.
- Balanced book rule: same number of longs and shorts.
- Re-entry cooldown: after TP/stop exit, same asset cannot re-enter on the same rebalance event.

## 5) Execution Model

- Signals are generated on bar close.
- Orders execute at next bar open (to avoid look-ahead bias).
- Exit checks run each bar (TP/stop).
- Rebalance performs full reset of open positions before opening new targets.
- All positions liquidated at 3:55 PM ET close.

## 6) Regime Filter (New)

Mean reversion degrades during volatility shocks. Rebalance is gated by a volatility regime filter:

- Proxy: SPY absolute 5-minute returns.
- Realized-vol measure: rolling mean over 78 bars.
- Volatility z-score versus 1560-bar baseline.
- Rebalance disabled when volatility z-score > 2.0.

## 7) Transaction Cost Model (Updated)

Flat 10 bps per side was too punitive and unrealistic for liquid instruments. Use class-specific costs:

| Asset Class | Cost (bps per side) |
| --- | --- |
| Stock | 2.0 |
| Forex | 1.0 |
| Metal | 2.0 |
| Crypto | 6.0 |
| Default fallback | 4.0 |

## 8) Data Quality Requirements (Hard Rules)

1. Use genuine 5-minute bars. Do not silently downgrade to 60-minute data.
2. Support chunked/paginated downloads (especially crypto) to avoid API row caps.
3. Preserve sparse NaNs for assets with missing intervals instead of fabricating bars.
4. Only allow tiny forward-fill (1 bar) for assets whose native interval is confirmed as 5-minute.
5. Backtest period must be explicitly filtered to June 2025 through January 2026.

## 9) Baseline Diagnostic (from previous latest report)

Baseline run before this revision:

- Effective range: June 2, 2025 to August 26, 2025 (did not reach January)
- Total return: -4.68%
- Sharpe: -1.17
- Max drawdown: -10.99%

Primary failure modes identified:

1. Incomplete/truncated dataset coverage (especially crypto history caps).
2. Mixed-frequency contamination (5-minute plus 60-minute fallback behavior).
3. Excessively sparse trade activation (low signal breadth at rebalance points).
4. Flat high transaction cost assumption dominating net P&L.

## 10) Validation Targets After Revision

For the revised implementation, monitor:

1. Effective backtest range exactly within June 2025 to January 2026.
2. Trade activation ratio at rebalance times.
3. Net Sharpe and max drawdown after class-specific costs.
4. Turnover and cost drag percentage of capital.
5. Per-asset-class contribution and concentration.

## 11) External Research Basis

- Pair trading and spread mean reversion: [NBER w7032](https://www.nber.org/papers/w7032)
- Residual/stat-arb approach: [Avellaneda & Lee (2010)](https://econpapers.repec.org/RePEc:taf:quantf:v:10:y:2010:i:7:p:761-782)
- Volatility-managed risk: [NBER w22208](https://www.nber.org/papers/w22208)
- Intraday volatility structure: [NBER w5783](https://www.nber.org/papers/w5783)

## 12) Latest Run After Implementation

Using current local raw data and updated code:

- Start: 2025-06-02 09:30 ET
- End: 2026-01-30 16:00 ET
- Total return: -2.18%
- Sharpe: -0.308
- Max drawdown: -10.54%

Interpretation:

1. Strategy behavior improved vs the prior baseline but remains negative.
2. Main blocker is still data coverage quality: Polygon was unavailable in this environment, and Yahoo 5m cannot backfill the full Jun 2025-Jan 2026 period.
3. To complete a clean evaluation, rerun the pipeline with active Polygon access for all assets/classes used in the strategy.
