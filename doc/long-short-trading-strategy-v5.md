# Long-Short Trading Strategy v5 (Daily Core + 4H Execution + Weekly Regime)

## 0) Why v5 exists

The latest review (`doc/performance_review_latest.md`) shows the current implementation is not tradable:
- Base return: **-28.78%**, Sharpe **-3.995**, MaxDD **-28.93%**.
- 1.5x cost stress: **-45.36%**.
- 2.0x cost + delay stress: **-62.46%**.
- Decision: **abandon**.

Primary failure modes were data-frequency mismatch, sparse/inactive cross-asset participation, and cost/turnover fragility.

v5 keeps the v4 data-integrity mindset, but updates the model to your intended trading horizon:
- **Trading timeframe (core decisions): daily**
- **Lower timeframe (execution/timing): 4H**
- **Higher timeframe (regime): weekly**

---

## 1) v5 objective

Build a cross-asset long/short portfolio that:
1. Uses weekly context to avoid trading against major regime.
2. Uses daily signals for position direction and sizing.
3. Uses 4H execution gates to reduce chasing and realized costs.
4. Enforces strict turnover controls so gross alpha survives friction.

---

## 2) Research anchors used in v5

Research-backed findings (sources at the end) mapped to design:

1. Time-series momentum is persistent across assets at medium horizons (roughly 1-12 months), with later reversal.  
Inference for v5: use weekly+daily trend features, not intraday noise as core alpha.

2. Trend-following has delivered long-run cross-asset performance with low correlation to traditional beta and better crisis behavior in many episodes.  
Inference for v5: keep trend as primary signal, but apply regime/risk controls.

3. Momentum crashes are state-dependent (panic/rebound regimes), and risk-managed momentum improves robustness.  
Inference for v5: add panic-state de-risking and dynamic gross leverage.

4. Transaction costs can erase anomaly returns when turnover is high; turnover mitigation materially matters.  
Inference for v5: add no-trade bands, partial rebalancing, and holding buffers.

5. With trading costs, optimal policy is partial movement toward target, not full instant turnover.  
Inference for v5: rebalance using gradual target convergence.

6. Stop-loss rules can improve behavior at longer sampling intervals in specific settings.  
Inference for v5: keep stops, but use them as risk controls (not alpha generators).

---

## 3) Multi-timeframe architecture

## 3.1 Weekly layer (higher timeframe: regime)

For each asset `i` at week `t`:

`W_i = 0.45*Z(ret_26w) + 0.35*Z(ret_52w) + 0.20*Z((MA_20w/MA_40w)-1)`

Portfolio regime state:
- `RISK_ON` if cross-asset median(`W_i`) > +0.25 and market stress filter is normal.
- `NEUTRAL` if between -0.25 and +0.25.
- `RISK_OFF` if < -0.25 or stress filter is elevated.

Weekly layer controls:
- Gross leverage range (`0.8x` to `1.8x`).
- Side aggressiveness (shorts favored in `RISK_OFF`, balanced in `NEUTRAL`, longs favored in `RISK_ON`).
- Momentum crash protection switch.

## 3.2 Daily layer (core signal and targets)

Trend core:

`T_i = 0.50*Z(ret_20d) + 0.30*Z(ret_60d) + 0.20*Z(ret_120d)`

Entry-timing dampener (anti-chase):

`RV_i = -Z(ret_5d)`

Raw daily score:

`S_raw_i = 0.75*T_i + 0.25*RV_i`

Weekly alignment boost/penalty:

`S_align_i = S_raw_i * (1 + 0.25*sign(S_raw_i)*sign(W_i))`

Risk-normalized score:

`S_i = clip(S_align_i / max(EWMA_vol_20d_i, vol_floor), -3, +3)`

Panic-state de-risking (momentum crash guard):
- If broad-market 20d return < 0 and market-vol z-score > 1.5:
  - reduce momentum coefficient by 50%,
  - cap gross at `1.0x`,
  - widen entry threshold.

## 3.3 4H layer (lower timeframe: execution timing)

Daily target is computed once; 4H is only for implementation quality.

For each planned trade, define a 4H execution quality score:
- trend confirmation on 4H (`EMA20 > EMA50` for longs, inverse for shorts),
- pullback quality (distance from 4H VWAP/EMA band),
- spread/liquidity state.

Execution schedule per trade:
- Quality >= 0.7: execute 100% of planned slice.
- 0.3 to 0.7: execute 50%, re-check next 4H bar.
- < 0.3: defer, cancel after 2 failed 4H bars.

---

## 4) Data contract (hard gates)

v5 removes 5-minute dependency. Canonical bars:
- `1D` and `4H` stored directly.
- `1W` derived from `1D` (consistent session calendar).

Hard pre-trade gates:
1. Frequency integrity:
   - median interval must match `1D` / `4H` target (with tolerance).
2. Coverage:
   - daily coverage >= 98% over rolling 90 days.
   - 4H coverage >= 95% over rolling 30 days.
3. Feature readiness:
   - valid `W_i`, `S_i`, vol estimates >= 97% completeness.
4. Breadth:
   - at rebalance: >= 10 active assets, >= 3 categories, no category > 45% of active universe.

If any gate fails: no new risk in that name (or portfolio-level hold if breadth fails).

---

## 5) Portfolio construction

## 5.1 Candidate selection

At each daily rebalance:
- Long candidates: `S_i >= q70`.
- Short candidates: `S_i <= q30`.
- Require at least 4 assets per side after gates.

## 5.2 Optimization target

Maximize:

`sum_i(w_i * S_i) - lambda_turn * sum_i(|w_i - w_prev_i|) - lambda_risk * (w' * Sigma * w)`

Subject to:
- Dollar neutrality: `abs(sum_i w_i) <= 0.03`
- Gross leverage: `0.8 <= gross <= regime_cap`
- Single-name cap: `10%`
- Category gross cap: `30%`
- Expected one-day turnover cap: `15%`

Covariance model:
- `Sigma` from daily returns (120d lookback),
- shrinkage estimator (Ledoit-Wolf style) for stability.

## 5.3 Volatility targeting

- Portfolio target vol: `10%` annualized (range: 8%-12%).
- Scaling factor `k = clip(target_vol / forecast_vol_20d, 0.6, 1.2)`.
- In `RISK_OFF`, hard cap `k <= 0.85`.

---

## 6) Execution and cost controls (4H implementation)

1. Daily target generation after daily close.
2. Execute through next tradable 4H windows (max 2 windows per signal day).
3. Net-edge filter before order release:
   - expected edge must exceed `2.0x` estimated round-trip cost.
4. No-trade band:
   - skip updates where `abs(target - current) < 25 bps` notional.
5. Minimum hold rule:
   - hold at least 3 trading days unless stop/kill-switch is hit.
6. Partial rebalancing:
   - move only 50%-70% toward target in one day when turnover pressure is high.

---

## 7) Risk management

Position-level:
1. Initial stop: `2.0 x ATR(14d)` from entry.
2. Trailing stop activates after `+1.5R`, using `1.0 x ATR(14d)` trail.
3. Time stop: exit after 15 trading days if edge has decayed.

Portfolio-level:
1. If 5-day drawdown > 4%: cut gross by 35% for 5 days.
2. If 20-day drawdown > 8%: flatten to minimal-risk state and wait for weekly reset.
3. If average pairwise correlation > 0.75 and vol z-score > 2: cap gross at `0.8x`.

---

## 8) Fine-tune ideas to test first

1. **Crash-state switch**: dynamically reduce momentum exposure in panic/rebound states.
2. **Adaptive no-trade band**: wider bands when spread/volatility rises.
3. **Class-specific rebalance cadence**: slower for metals/FX, faster for crypto.
4. **Dispersion filter**: trade only when cross-sectional signal dispersion is above threshold.
5. **Signal half-life weighting**: increase weight for slower-decay predictors in high-cost conditions.
6. **Turnover budget per asset class**: fixed daily turnover sleeves by class.
7. **Short borrow stress model**: explicit borrow/funding shock penalty in short ranking.
8. **4H adverse-selection guard**: cancel entries after repeated 4H rejection against daily direction.
9. **Regime-conditioned leverage map**: nonlinear leverage schedule from weekly regime score.
10. **Data-quality confidence score**: scale position size by data confidence, not only signal strength.

---

## 9) Validation protocol (deployment barrier)

## 9.1 Backtests required
1. Base case.
2. 1.5x transaction-cost stress.
3. 2.0x transaction-cost stress + 1-day execution delay.
4. Missing-data stress (random 5%-10% bar removal).
5. Liquidity stress (fill probability haircut).
6. Short-borrow/funding stress.

## 9.2 Cross-validation
- Rolling walk-forward (example: 3-year train, 6-month test).
- Purged/embargoed splits to reduce overlap leakage.
- Report fold dispersion and worst-fold results.

## 9.3 Minimum acceptance criteria
- OOS Sharpe >= 0.9
- OOS MaxDD <= 12%
- 1.5x-cost scenario Sharpe >= 0.4
- 2.0x+delay scenario non-negative expectancy
- Median monthly turnover <= 35%
- >= 70% positive OOS folds

---

## 10) Implementation map for this repo

1. `long_short_config.py`
   - add `PRIMARY_TIMEFRAME = "1D"`, `EXEC_TIMEFRAME = "4H"`, weekly regime params, turnover bands.
2. `data_pipeline.py`
   - ingest/align 1D and 4H bars; build weekly from daily.
3. `strategy_core.py`
   - replace v3 feature block with `compute_v5_weekly_daily_scores()`.
4. `backtest_vectorized.py`
   - shift from 5m event loop to daily target loop + 4H execution queue.
5. `backtest_report.py`
   - add turnover decomposition, regime-state attribution, stress matrix outputs.

---

## 11) v5 vs v4 delta summary

- Keeps v4 integrity-first philosophy.
- Replaces intraday-centric mechanics with **daily alpha + 4H execution + weekly regime**.
- Strengthens turnover/cost controls using partial-rebalance logic.
- Adds explicit momentum-crash guardrails and regime-conditioned leverage.

---

## 12) Sources used

1. Performance review in repo: `doc/performance_review_latest.md` and `data/reports/latest/summary.json`
2. Time-series momentum evidence: [Moskowitz, Ooi, Pedersen (2012)](https://ideas.repec.org/a/eee/jfinec/v104y2012i2p228-250.html)
3. Long-run trend evidence: [Hurst, Ooi, Pedersen (2017)](https://research.cbs.dk/en/publications/a-century-of-evidence-on-trend-following-investing/)
4. Momentum crash state dependence: [Daniel, Moskowitz (NBER w20439)](https://www.nber.org/papers/w20439)
5. Risk-managed momentum: [Barroso, Santa-Clara (2015)](https://ideas.repec.org/a/eee/jfinec/v116y2015i1p111-120.html)
6. Volatility-managed portfolios: [Moreira, Muir (NBER w22208)](https://www.nber.org/papers/w22208)
7. Trading-cost mitigation and turnover limits: [Novy-Marx, Velikov (NBER w20721)](https://www.nber.org/papers/w20721)
8. Partial trading toward target with costs: [Garleanu, Pedersen (NBER w15205)](https://www.nber.org/papers/w15205)
9. Stop-loss behavior at longer frequencies: [Kaminski, Lo (2014)](https://ideas.repec.org/a/eee/finmar/v18y2014icp234-254.html)
10. Cross-asset value/momentum structure: [Asness, Moskowitz, Pedersen (2013)](https://www.aqr.com/Insights/Research/Journal-Article/Value-and-Momentum-Everywhere)
11. Trend/timing reference for higher-timeframe filters: [Faber (SSRN 962461)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461)
