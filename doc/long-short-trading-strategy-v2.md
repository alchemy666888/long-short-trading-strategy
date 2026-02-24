# Long-Short Trading Strategy v2 (Correlation + Momentum Upgrade)

## 0) What changed from v1 (requested summary before full rewrite)

### Key ideas collected from practitioner/research consensus
> Note: In this execution environment, outbound web access is restricted, so these ideas are based on well-known published quant practices (cross-sectional momentum, time-series momentum, volatility targeting, correlation-aware portfolio construction, and regime/risk overlays).

1. **Momentum is stronger when volatility-normalized** (rank on risk-adjusted returns instead of raw return).
2. **Correlation-aware long/short pairing** can reduce hidden net beta and drawdowns versus naive “top long + top short” selection.
3. **Multi-horizon momentum** (short + medium + long) is typically more stable than single-window momentum.
4. **Volatility targeting and risk parity sizing** usually improve consistency of risk and reduce concentration.
5. **Regime filters** (high-volatility / trend-break regimes) reduce overtrading in mean-reversion noise.
6. **Execution realism** (next-bar execution, spread/slippage, borrow/funding) materially changes PnL distribution.

### Concrete upgrades relative to v1
- Added **asset-category correlation matrix** and **pairing rules** at rebalance.
- Added **momentum engine**: long strongest, short weakest, after risk and liquidity filters.
- Replaced pure Z-score-only selection with **hybrid signal**: momentum + residual stretch (optional mean-reversion alpha).
- Added **explicit entry/exit policy**, **R-multiple targets**, and **risk budget constraints**.
- Added **full backtest plan + report format + performance matrix**.

---

## 1) Strategy objective and universe

Build an intraday-to-swing **market-neutral-ish cross-asset long-short portfolio** using:
- **Cross-category correlation relationships** to pair exposures.
- **Momentum strength ranking** to long strongest / short weakest.
- **Risk controls** to keep portfolio risk, leverage, and drawdown bounded.

### Universe by category (same core assets as v1)
- **Crypto:** BTC, ETH, SOL, XRP
- **Metals:** Gold, Silver, Copper
- **FX:** EUR/USD, AUD/USD
- **Equities:** TSLA, MCD, NVDA, GOOG, SPY

---

## 2) Data, frequency, and preprocessing

### Data frequency
- Signal bar: **5-minute bars**
- Correlation and regime context: use **hourly and daily aggregates** derived from 5-minute bars.

### Required history
- Minimum **120 trading days** for stable correlation estimation.
- Minimum **60 bars** intraday history for fast momentum/risk stats.

### Cleaning/alignment
- Convert all timestamps to **ET**.
- Keep only common tradable windows for all assets (or forward-fill only within conservative tolerance).
- Winsorize extreme 1-bar returns at 0.5/99.5 percentile by asset to reduce bad ticks.

---

## 3) Factor construction

## 3.1 Momentum score (primary alpha)
For asset \(i\) at time \(t\):

\[
M_{i,t} = 0.5\cdot Z(r_{20}) + 0.3\cdot Z(r_{60}) + 0.2\cdot Z(r_{120})
\]

Where:
- \(r_k\): k-bar log return.
- \(Z(\cdot)\): cross-sectional z-score at time \(t\).

Then risk-adjust momentum:

\[
M^*_{i,t} = \frac{M_{i,t}}{\sigma_{i,t}^{EWMA}}
\]

with EWMA volatility half-life = 30 bars.

## 3.2 Correlation matrix (category-level + asset-level)
- Compute rolling correlations on **hourly returns** using a 60-day window.
- Apply simple shrinkage:

\[
\Sigma_{shrunk} = \lambda\Sigma + (1-\lambda)I\bar{\sigma}^2,\; \lambda=0.7
\]

- Produce:
  - **Category correlation matrix** (Crypto/Metals/FX/Equities).
  - **Asset correlation matrix** (all assets).

## 3.3 Relative stretch / reversion overlay (optional)
Preserve your v1 insight:

\[
Z_{i,t} = \frac{P_{i,t} - SMA_{36}(P_i)}{SD_{36}(P_i)}
\]

Use only as secondary timing filter to avoid chasing exhaustion.

---

## 4) Signal logic and portfolio construction

## 4.1 Candidate selection
1. Rank all assets by \(M^*\).
2. **Long bucket:** top quartile (strongest).
3. **Short bucket:** bottom quartile (weakest).
4. Remove assets failing liquidity/spread filters.

## 4.2 Correlation-aware long/short pairing
For each selected long candidate:
1. Prefer a short candidate from a **different category** with:
   - low or negative correlation to the long asset (target \(\rho < 0.25\), ideally \(<0\)), and
   - strong negative momentum score (weakest rank).
2. If no such candidate exists, allow same-category short only if it lowers net factor beta.
3. Solve final weights via constrained optimization:
   - Dollar-neutral: \(\sum w_i \approx 0\)
   - Vol-targeted: \(w_i \propto 1/\sigma_i\)
   - Max single-name risk: 15% of total risk budget.

## 4.3 Entry conditions (all must pass)
- Rebalance times: **10:00, 12:00, 14:00 ET**.
- Asset in long/short candidate bucket by \(M^*\).
- Correlation pairing feasible under constraints.
- Optional anti-chase rule:
  - For longs, avoid new entry if \(Z_{i,t} > +2.5\).
  - For shorts, avoid new entry if \(Z_{i,t} < -2.5\).

## 4.4 Exit conditions
Exit at next bar open when any trigger occurs:
1. **Take-profit:** +1.8R reached.
2. **Stop-loss:** -1.0R reached.
3. **Momentum decay:** long drops below median rank or short rises above median rank.
4. **Correlation breakdown:** paired hedge correlation regime shifts by >2 std from 20-day mean.
5. **Time stop:** max holding 1 trading day (intraday strategy still forced flat by 15:55 ET unless swing mode enabled).

## 4.5 Risk/Reward and trade risk definition
- Define \(R\) per position = distance to stop (ATR-based).
- Initial stop = **1.25 × ATR(20, 5m)** from entry.
- TP = **2.25 × ATR(20, 5m)** from entry. (RR ≈ 1:1.8)
- Trail stop to breakeven after +1.0R.

---

## 5) Position sizing and constraints

- Portfolio volatility target: **10% annualized** equivalent.
- Gross leverage cap: **3.0x**.
- Net exposure cap: **|net| ≤ 15%**.
- Category exposure cap: **35% gross** per category.
- Position size:

\[
w_i = \frac{b_i/\sigma_i}{\sum_j |b_j/\sigma_j|}
\]

where \(b_i\in[-1,+1]\) from long/short signal conviction.

- If constraints violated, shrink all weights proportionally, then drop lowest-conviction names.

---

## 6) Execution policy

- Signals generated on bar close.
- Orders executed at **next 5-minute bar open**.
- Cost model by category:
  - Crypto: 10 bps taker + funding proxy.
  - Equities: 1–2 bps + borrow fee for shorts.
  - FX/Metals: spread + 0.5×spread slippage proxy.
- Reject trade if expected edge < round-trip cost + 0.2R buffer.

---

## 7) Backtest plan

## 7.1 Test design
1. **In-sample development:** first 60% of history.
2. **Walk-forward validation:** rolling 3-month train / 1-month test.
3. **Out-of-sample holdout:** final 20% untouched.
4. **Stress tests:**
   - doubled spread/slippage
   - delayed fill by +1 bar
   - volatility shock days

## 7.2 Baselines to compare
- v1 Z-score strategy (original).
- Momentum-only (no correlation pairing).
- Correlation-only pairing (no momentum ranking).
- v2 full model.

## 7.3 Performance metrics
- CAGR / Annualized return
- Annualized volatility
- Sharpe, Sortino, Calmar
- Max drawdown
- Hit rate
- Profit factor
- Avg win / Avg loss
- Turnover and average holding time
- Beta to SPY and BTC proxies
- Tail metrics: 95% CVaR, worst day/week

---

## 8) Backtest report (template + sample performance matrix)

> Replace sample values below with actual engine output after running the backtest.

| Variant | Ann. Return | Ann. Vol | Sharpe | Sortino | Max DD | Hit Rate | Profit Factor | Turnover/day | Net Beta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v1 Z-score | 11.2% | 14.8% | 0.76 | 1.12 | -18.5% | 49% | 1.18 | 1.9 | 0.11 |
| Momentum-only | 14.6% | 13.9% | 1.05 | 1.57 | -14.3% | 51% | 1.31 | 1.6 | 0.18 |
| Corr-pair-only | 10.4% | 10.2% | 1.02 | 1.46 | -10.8% | 53% | 1.27 | 1.2 | 0.05 |
| **v2 Full (Momentum + Corr + Risk overlays)** | **17.9%** | **12.1%** | **1.48** | **2.21** | **-9.6%** | **55%** | **1.52** | **1.4** | **0.03** |

### Interpretation checklist
- v2 should outperform v1 on **Sharpe, Max DD, and Profit Factor**.
- If turnover increases but Sharpe does not improve, tighten entry thresholds.
- If beta drifts from neutral, strengthen category correlation constraints.

---

## 9) Implementation notes (practical)

- Recompute correlation matrix daily (or every 2 hours for faster adaptation).
- Recompute momentum every rebalance.
- Use robust covariance and cap unstable correlations when data quality degrades.
- Log every signal component (momentum rank, correlation pairing score, costs, final decision) for auditability.

---

## 10) Final recommended default parameters

- Rebalance: 10:00 / 12:00 / 14:00 ET
- Momentum horizons: 20 / 60 / 120 bars
- Momentum weights: 0.5 / 0.3 / 0.2
- Entry buckets: top/bottom quartile by \(M^*\)
- Z-score anti-chase filter: ±2.5
- Stop/TP: 1.25 ATR / 2.25 ATR
- Per-position risk: 0.40% of equity
- Gross leverage cap: 3.0x
- Net exposure cap: 15%
- Daily loss limit: 2.5R portfolio-level (hard stop)
- Forced flat: 15:55 ET (intraday mode)

