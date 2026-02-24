# Long-Short Trading Strategy v3 (Backtest-First Robustness Edition)

## 0) Objective of v3

v3 is a **backtest-optimized refinement** of v2. The goal is not to maximize in-sample return, but to define a strategy that is:
- fully systematic (zero discretion),
- resilient to slippage/cost assumptions,
- stable across parameter perturbations,
- auditable for bias control,
- deployable only if it survives pessimistic validation.

---

## 1) One-sentence hypothesis

A cross-asset long-short portfolio that combines **volatility-normalized multi-horizon momentum** with **correlation-aware pairing** should deliver more stable risk-adjusted returns than naïve ranking, and should remain profitable under conservative execution friction.

---

## 2) Universe and data contract (strict for backtests)

## 2.1 Tradable universe
- **Crypto:** BTC, ETH, SOL, XRP
- **Metals:** GOLD, SILVER, COPPER
- **FX:** EURUSD, AUDUSD
- **Equities:** TSLA, MCD, NVDA, GOOG, SPY

## 2.2 Frequency and timestamps
- Base bar frequency: **5-minute OHLCV**.
- Timezone normalization: **America/New_York (ET)**.
- Signals generated on bar close at eligible rebalance timestamps.
- Orders executed at **next bar open only** (no same-bar fill).

## 2.3 Minimum history and eligibility
At timestamp \(t\), an asset is tradable only if:
- ≥ 120 trading days of history exists for correlation context,
- ≥ 120 bars exists for momentum windows,
- latest bar is not stale (no missing close beyond 2 bar intervals),
- spread and liquidity filters pass.

## 2.4 Data hygiene and bias controls
- Returns are computed using only data available up to \(t\).
- No forward-filled prices across market-closed gaps.
- Corporate actions for equities must be adjusted consistently.
- Winsorize 1-bar returns at asset-level [0.5%, 99.5%] percentiles.
- Every backtest run logs data exclusions and missing-bar events.

---

## 3) Signal model (fewer moving parts, explicit formulas)

## 3.1 Momentum core signal
For each asset \(i\):

\[
M_{i,t} = 0.5\cdot Z(r_{20}) + 0.3\cdot Z(r_{60}) + 0.2\cdot Z(r_{120})
\]

Where:
- \(r_k\): k-bar log return,
- \(Z(\cdot)\): cross-sectional z-score at time \(t\).

Risk normalization:

\[
M^*_{i,t} = \frac{M_{i,t}}{\sigma^{EWMA}_{i,t}}
\]

with EWMA volatility half-life = 30 bars.

## 3.2 Secondary stretch filter (timing guard, not primary alpha)

\[
Z^{stretch}_{i,t} = \frac{P_{i,t} - SMA_{36}(P_i)}{SD_{36}(P_i)}
\]

Use only for anti-chase filtering:
- skip long entries if \(Z^{stretch}_{i,t} > +2.5\),
- skip short entries if \(Z^{stretch}_{i,t} < -2.5\).

## 3.3 Correlation context and shrinkage
- Compute rolling correlation on **hourly returns**, 60-day lookback.
- Shrinkage:

\[
\Sigma_{shrunk} = 0.7\Sigma + 0.3I\bar{\sigma}^2
\]

- Maintain category-level and asset-level matrices for pairing and risk constraints.

---

## 4) Portfolio construction rules (zero discretion)

## 4.1 Rebalance schedule
Rebalance only at **10:00, 12:00, 14:00 ET**.

## 4.2 Candidate buckets
At each rebalance time:
1. Rank assets by \(M^*\).
2. Long candidates = top quartile.
3. Short candidates = bottom quartile.
4. Remove assets failing tradability/liquidity/spread checks.

## 4.3 Pairing algorithm
For each long candidate (descending \(M^*\)):
1. Find short candidate with weakest \(M^*\) subject to:
   - preferred different category,
   - pair correlation target \(\rho < 0.25\) (ideal \(< 0\)).
2. If unavailable, allow same-category short only if net beta and exposure caps remain valid.
3. Stop pairing when no feasible short remains.

## 4.4 Sizing and constraints
Raw conviction \(b_i\in\{-1,+1\}\) from side.

Risk-scaled pre-weights:

\[
w_i^{raw}=\frac{b_i/\sigma_i}{\sum_j|b_j/\sigma_j|}
\]

Then enforce in order:
1. Dollar-neutral target: \(|\sum_i w_i| \le 0.15\),
2. Gross leverage: \(\sum_i|w_i| \le 3.0\),
3. Category gross cap: 35%,
4. Single-name risk contribution cap: 15%.

If constraints fail, proportionally scale then drop lowest-\(|M^*|\) names until valid.

---

## 5) Entry, exits, and risk definition

## 5.1 Entry
A position is opened at next bar open only when all pass:
- asset in selected long/short pair set,
- anti-chase stretch filter passes,
- expected edge exceeds round-trip cost + 0.2R buffer.

## 5.2 R definition and protective levels
- \(R\) = ATR-based stop distance at entry.
- Stop distance = **1.25 × ATR(20, 5m)**.
- Profit target = **2.25 × ATR(20, 5m)** (~1:1.8 RR).
- Move stop to breakeven after +1.0R.

## 5.3 Exit hierarchy (first trigger wins)
1. Stop-loss hit (-1.0R),
2. Take-profit hit (+1.8R equivalent),
3. Momentum decay (long below median rank / short above median rank),
4. Correlation breakdown (>2 std shift vs 20-day pair baseline),
5. Time stop: forced flat by 15:55 ET (unless explicit swing-mode backtest variant).

---

## 6) Execution and cost model (baseline + stress)

## 6.1 Baseline cost model
- **Crypto:** 10 bps taker + funding proxy.
- **Equities:** 1–2 bps + borrow fee on shorts.
- **FX/Metals:** spread + 0.5×spread slippage proxy.

## 6.2 Stress friction model (must pass)
Apply punitive assumptions:
- slippage = 1.5× to 2.0× baseline,
- one-bar delayed execution variant,
- worst-case fill proxy (buy at ask+1 tick, sell at bid-1 tick where representable),
- partial-fill/rejection scenario by dropping a fraction of intended fills.

Strategy is not deployment-ready if expectancy disappears under these assumptions.

---

## 7) Backtest protocol (primary change in v3)

## 7.1 Test splits
1. **In-sample development:** first 60%.
2. **Walk-forward:** rolling 3-month train / 1-month test.
3. **Final holdout:** last 20% untouched until end.

## 7.2 Robustness matrix
For each model variant, run grid sweeps:
- Stop multiplier: {0.5, 0.75, 1.0, 1.25, 1.5} × baseline.
- Target multiplier: {0.8, 0.9, 1.0, 1.1, 1.2} × baseline.
- Rebalance timing offset: {-30, -15, 0, +15, +30} minutes.
- Cost stress: {1.0x, 1.5x, 2.0x}.

Pass criterion: performance should show **plateaus**, not isolated spikes.

## 7.3 Regime segmentation
Evaluate separately in:
- High vs low volatility regimes,
- Trending vs range-bound periods,
- Risk-on vs risk-off proxies.

Requirement: acceptable behavior in all regimes; no catastrophic single-regime failure.

## 7.4 Sample size gates
- Hard minimum: 30 trades (diagnostic only).
- Research minimum: 100 trades.
- Preferred confidence: 200+ trades.

No production decision on <100 trades.

## 7.5 Bias audit checklist (must log)
- Look-ahead bias checks,
- Survivorship bias notes (especially equities universe construction),
- Data alignment/timestamp audit,
- Parameter count discipline and overfitting flags.

---

## 8) Decision framework (deploy / refine / abandon)

## 8.1 Deploy candidate
Only if all are true:
- Positive OOS expectancy,
- OOS Sharpe at least 50% of in-sample Sharpe,
- Profitable under ≥1.5× friction stress,
- No regime with catastrophic drawdown beyond risk mandate,
- Parameter stability plateau confirmed.

## 8.2 Refine
Use when logic survives but thresholds are unstable or sample size insufficient.

## 8.3 Abandon
If edge depends on narrow parameter tuning, unrealistic fills, or one favorable regime.

---

## 9) Required backtest report format

Each run must include:
1. **Hypothesis statement** (one sentence).
2. **Rules snapshot** (entry/exit/sizing/filters).
3. **Data coverage + exclusions**.
4. **Headline metrics**: Ann return, vol, Sharpe, Sortino, Calmar, MaxDD, PF, turnover, holding time.
5. **Trade stats**: count, hit rate, avg win/loss, expectancy.
6. **Stress tests** (cost, delay, fill quality).
7. **Parameter heatmaps** (at least stop × target).
8. **Regime table**.
9. **Failure analysis**: what broke first and why.
10. **Decision**: deploy/refine/abandon with rationale.

---

## 10) Implementation notes for your current repository

- Keep v2 as benchmark baseline and compare v3 directly.
- Run at least four variants:
  1. v1 Z-score,
  2. Momentum-only,
  3. Correlation-pair-only,
  4. v3 full model.
- Prefer simple, round-number parameters and avoid adding new degrees of freedom unless justified by a stability gain.
- Spend most iteration time trying to break v3, not optimizing headline return.

---

## 11) Summary of v3 upgrades vs v2

1. Added explicit **hypothesis-first** statement.
2. Tightened **zero-discretion rule codification** for reproducibility.
3. Elevated **stress friction and worst-case execution tests** to mandatory gates.
4. Added **parameter robustness matrix** and plateau requirement.
5. Added **sample-size and regime acceptance gates** before deployment.
6. Added formal **deploy/refine/abandon** decision framework.
7. Added required **failure analysis section** in every report.

This transforms the strategy from a strong design (v2) into a **backtest-rigorous research process (v3)** suitable for systematic validation and live-readiness screening.
