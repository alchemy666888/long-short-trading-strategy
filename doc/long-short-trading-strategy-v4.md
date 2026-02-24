# Long-Short Trading Strategy v4 (Data-Integrity + Friction-First Edition)

## 0) Why v4 exists

The latest performance review shows the previous implementation should be abandoned in its current form because realized results are strongly negative, extremely cost-sensitive, and inconsistent with the stated multi-asset hypothesis.

v4 reframes the strategy around one principle:

> **No edge claim is valid unless data integrity, execution realism, and cross-asset participation are all verified before taking risk.**

---

## 1) What we learned from the latest review (must-fix findings)

1. **Critical data-frequency mismatch**: several FX/metals series are hourly while the strategy trades on a 5-minute grid.
2. **Universe participation collapse**: FX/metals coverage is near-inactive in-session, so the portfolio is not truly diversified as designed.
3. **Feature invalidation**: key signals (e.g., volatility-normalized momentum) are null for whole asset classes.
4. **Execution timing drift**: rebalance logic is effectively one bar late relative to intended schedule.
5. **Weak gross edge**: performance deteriorates sharply as realistic costs/delay are added.

**Interpretation:** model underperformance is structural, not a simple parameter-tuning problem.

---

## 2) Research-informed principles used in v4

The v4 design uses well-established quantitative ideas that consistently appear in institutional research and peer-reviewed literature:

1. **Time-series momentum exists but is regime-dependent and implementation-sensitive** (basis for trend component).
2. **Volatility scaling/targeting can stabilize risk-adjusted returns** when done with disciplined constraints.
3. **Transaction costs and turnover dominate intraday alpha decay**, so expected edge must be net-of-cost at decision time.
4. **Purged/embargoed walk-forward validation is preferred** for high-frequency overlap to reduce leakage bias.
5. **Breadth and independence matter**: if cross-asset breadth collapses, portfolio behavior becomes fragile and correlated.

---

## 3) v4 strategy hypothesis

A long-short portfolio that trades only when:
- data-quality gates pass,
- cross-asset breadth is healthy,
- and expected net alpha exceeds a dynamic cost hurdle,

can deliver materially better robustness than the prior always-on intraday rebalance design.

---

## 4) Data contract (hard gates, pre-trade)

## 4.1 Frequency integrity gate
For each asset/day:
- infer median bar interval,
- require interval == target frequency (5m) within tolerance,
- if failed: asset excluded for that day and logged.

## 4.2 Session coverage gate
For each asset/day in tradable session:
- coverage ratio = non-null bars / expected bars,
- require coverage >= 90% for equities/crypto and >= 85% for FX/metals,
- two consecutive failures => disable asset for rolling 5 trading days.

## 4.3 Feature readiness gate
Before signal formation:
- require valid EWMA vol, momentum windows, and microstructure fields,
- require feature completeness >= 95% over rolling 2 days,
- else no-trade for that asset.

## 4.4 Universe breadth gate
At each rebalance timestamp:
- require at least 8 active assets,
- require at least 3 categories represented,
- require no category > 55% of active names.

If gate fails: hold/flatten to risk-minimized state (no new entries).

---

## 5) Signal stack (simple and robust)

## 5.1 Core return signal
For each asset \(i\):

\[
S^{trend}_{i,t}=0.45Z(r_{24})+0.35Z(r_{72})+0.20Z(r_{288})
\]

- windows on 5m bars (roughly 2h, 6h, 1d),
- cross-sectional z-score clipped to [-3, +3].

## 5.2 Reversal guard (avoid late entries)

\[
S^{rev}_{i,t}=-Z(r_{6})
\]

Use as dampener only (not standalone alpha):

\[
S^{raw}_{i,t}=S^{trend}_{i,t}+0.25S^{rev}_{i,t}
\]

## 5.3 Risk normalization

\[
S^{risk}_{i,t}=\frac{S^{raw}_{i,t}}{\sigma^{EWMA}_{i,t}}
\]

with EWMA half-life = 36 bars and floor volatility to avoid tiny-denominator leverage spikes.

## 5.4 Correlation-aware diversification penalty
Instead of brittle pair-matching first, apply penalty for crowded correlation clusters:

\[
S^{final}_{i,t}=S^{risk}_{i,t}-\lambda\cdot \overline{\rho}_{i,t}^{(+)}
\]

where \(\overline{\rho}^{(+)}\) is average positive correlation to currently selected names.

This preserves signal continuity while discouraging concentration.

---

## 6) Portfolio construction

## 6.1 Candidate selection
- Long bucket: assets with \(S^{final}\) above +q70 percentile.
- Short bucket: assets with \(S^{final}\) below -q30 percentile.
- If one side < 3 assets, skip rebalance.

## 6.2 Optimization objective (lightweight)
Maximize:

\[
\sum_i w_i S^{final}_{i,t} - c\cdot \sum_i |\Delta w_i|
\]

subject to:
- dollar neutrality: \(|\sum_i w_i| \le 0.05\),
- gross leverage \(\le 2.0\),
- single-name cap \(\le 12\%\),
- category gross cap \(\le 35\%\),
- turnover cap per rebalance \(\le 20\%\) gross.

## 6.3 Volatility targeting
- Portfolio target vol: 10% annualized.
- Scale all weights by \(k_t = \min(1.25,\max(0.5, \sigma^*/\hat\sigma_t))\).
- If realized intraday drawdown exceeds 2.5\(\sigma\) expectation, cut risk by 50% until next day.

---

## 7) Execution logic (friction-first)

## 7.1 Rebalance schedule
Reduce frequency from 3/day to 2/day initially:
- 10:00 ET and 14:00 ET.

Rationale: lower turnover and lower signal-chasing risk.

## 7.2 Net-edge entry filter
Before placing any order, require:

\[
\text{ExpectedAlpha}_{i,t} > 1.5\times\text{EstimatedRoundTripCost}_{i,t}
\]

Cost estimate combines spread, impact proxy, borrow/funding fee, and latency slippage.

## 7.3 Order placement
- Primary: passive limit with max wait budget (e.g., 2 bars).
- Fallback: aggressive fill only if edge remains above threshold.
- If partial-fill leaves side imbalance > tolerance, hedge with index/sector proxy or reduce opposite side.

---

## 8) Risk management

1. **Soft stop**: reduce 50% when asset moves -0.9R.
2. **Hard stop**: full exit at -1.3R.
3. **Profit protection**: trailing stop activates after +1.2R.
4. **Time stop**: close residual intraday positions by 15:50 ET.
5. **Kill-switches**:
   - data gate failure spikes,
   - fill ratio < 60% for two rebalances,
   - intraday drawdown > 2.0% NAV.

---

## 9) Validation protocol (deployment barrier)

## 9.1 Required backtests
1. Base assumptions.
2. 1.5x cost stress.
3. 2.0x cost + 1-bar delay stress.
4. Missing-data stress (randomly remove 10% bars for non-equities).
5. Liquidity stress (halve fill probability).

## 9.2 Cross-validation design
- Purged walk-forward with embargo.
- Minimum 12 out-of-sample folds.
- Report fold dispersion, not only aggregate mean.

## 9.3 Acceptance criteria
v4 moves to paper-trading only if:
- OOS Sharpe > 0.8,
- MaxDD < 12%,
- 2.0x cost+delay scenario still non-negative expectancy,
- turnover-adjusted information ratio not concentrated in one month,
- at least 70% of folds positive net PnL.

---

## 10) Implementation plan (practical sequence)

1. **Data repair first**: enforce 5m bars or remove assets.
2. **Add pre-trade data gates + breadth gate**.
3. **Fix rebalance timestamp alignment** (signal time vs execution time explicitly separated).
4. **Integrate net-edge cost filter** before order generation.
5. **Reduce rebalance frequency and turnover caps**.
6. **Run full stress matrix + purged walk-forward**.
7. **Promote only if acceptance criteria pass**.

---

## 11) v4 vs v3 delta summary

- From "strategy optimization" -> **"data integrity + execution realism first"**.
- From static rebalance activity -> **conditional trading based on breadth and net edge**.
- From correlation-based pair selection -> **correlation-penalized scoring + constrained optimization**.
- From unconstrained turnover tendency -> **explicit turnover and cost hurdle constraints**.
- From single-run judgement -> **fold-dispersion and stress-first deployment gate**.

---

## 12) Final note

Given the latest review, the most important improvement is not a new signal formula. It is **institutional-quality control of data, costs, and execution assumptions**. If those controls are strict, alpha quality can be judged honestly; if not, any apparent edge is likely backtest noise.
