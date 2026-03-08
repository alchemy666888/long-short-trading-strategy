# Long-Short Trading Strategy v6 (Analysis-First Daily Intelligence + Daily Core + 4H Execution + Weekly Regime)

## 0) Why v6 exists

v5 fixed major structural issues (timeframe mismatch, turnover fragility, and weak cross-asset participation), but it still treats market intelligence as optional context.

v6 upgrades the process so **daily market analysis is mandatory and upstream**:
- First: build a structured daily macro/news/sentiment view.
- Then: generate and filter trading ideas with that view.
- Finally: execute only when intelligence and systematic signals are aligned enough to justify cost/risk.

This keeps v5's quantitative discipline while making idea generation more adaptive to real-world catalysts.

---

## 1) v6 objective

Build a cross-asset long/short portfolio that:
1. Uses weekly regime for structural bias.
2. Uses daily quantitative signals for baseline direction and sizing.
3. Uses a mandatory daily market-analysis layer to shape conviction, filters, and risk budget.
4. Uses 4H execution quality gates to minimize adverse fills and unnecessary turnover.

---

## 2) Analysis-first operating sequence (hard requirement)

Every trading day follows this order:
1. Produce `Daily Market Analysis Report` (macro, regional, asset, historical analogs, sentiment/flows, scenarios, trade ideas draft).
2. Convert report into numeric overlays and confidence scores.
3. Re-rank and filter trade candidates from the systematic model using those overlays.
4. Optimize portfolio under turnover/risk constraints.
5. Execute in 4H windows with quality checks.

If step 1 or 2 fails quality gates, the strategy cannot deploy new risk.

---

## 3) Daily Market Analysis contract

The report (from `doc/daily-market-analysis.md`) is now a formal input, not a narrative attachment.

## 3.1 Required sections per day

1. Global macro summary.
2. Regional drivers (US, Europe, Asia-Pacific, EM).
3. Asset-specific catalysts (metals, energy, US equities, crypto, FX).
4. Historical analogs and reaction templates.
5. Sentiment and money flow.
6. Base/bull/bear scenario map.
7. Draft actionable ideas (entry/target/stop/horizon).

## 3.2 Quality gates for report usability

`REPORT_VALID = TRUE` only if all pass:
1. All 7 sections populated.
2. At least 3 independent high-quality, diverse sources for each major catalyst.
3. Scenario probabilities sum to 100% for each traded asset class.
4. Each drafted trade idea includes explicit invalidation risk.
5. Report timestamp is fresh for the current trading day.

If any gate fails: no expansion of gross exposure; only risk-reducing trades allowed.

---

## 4) Intelligence-to-signal translation layer

v6 introduces an explicit mapping from qualitative analysis to quantitative controls.

For day `t` and asset `i`:

## 4.1 Macro Regime Overlay `M_t` in [-1, +1]

Constructed from macro section:
- Rates/inflation impulse.
- Growth impulse.
- Geopolitical risk impulse.

Interpretation:
- `+1`: pro-risk / pro-cyclical.
- `0`: neutral.
- `-1`: defensive / risk-off.

## 4.2 Cross-Asset Flow Overlay `F_c,t` in [-1, +1]

Per asset class `c` (metals, energy, equities, crypto, FX), from sentiment and money-flow section.
- Positive if flows and positioning support longs.
- Negative if flows support shorts or defensive positioning.

## 4.3 Asset Catalyst Score `A_i,t` in [-1, +1]

From asset-specific catalysts + historical analogs:
- Directional sign from catalyst bias.
- Magnitude from catalyst strength and historical consistency.

## 4.4 Scenario Confidence `C_t` in [0, 1]

From scenario section:
- Higher when base case is clear and evidence is coherent.
- Lower when regime is unstable or evidence is conflicting.

## 4.5 Report Reliability `Q_t` in [0, 1]

From report quality checks:
- Completeness, source depth, and contradiction level.
- `Q_t < 0.6` triggers conservative mode.

---

## 5) Multi-timeframe alpha stack (v6)

## 5.1 Weekly regime layer (unchanged base)

Use v5 weekly score:

`W_i = 0.45*Z(ret_26w) + 0.35*Z(ret_52w) + 0.20*Z((MA_20w/MA_40w)-1)`

This still governs structural risk-on/off posture and leverage bands.

## 5.2 Daily base score (unchanged core)

`T_i = 0.50*Z(ret_20d) + 0.30*Z(ret_60d) + 0.20*Z(ret_120d)`

`RV_i = -Z(ret_5d)`

`S_raw_i = 0.75*T_i + 0.25*RV_i`

`S_align_i = S_raw_i * (1 + 0.25*sign(S_raw_i)*sign(W_i))`

`S_base_i = clip(S_align_i / max(EWMA_vol_20d_i, vol_floor), -3, +3)`

## 5.3 Analysis-adjusted score (new)

Let `c(i)` be the asset class of asset `i`, and `beta_i` be asset sensitivity to macro regime.

`S_v6_i = clip(S_base_i * (1 + 0.20*A_i,t + 0.15*F_c(i),t + 0.10*beta_i*M_t) * (0.5 + 0.5*Q_t), -3, +3)`

Interpretation:
- Strong, reliable analysis can increase/decrease conviction.
- Low reliability (`Q_t`) automatically shrinks signal impact.
- Macro/class overlays modify sizing, not raw price series.

## 5.4 Conflict and veto rules (new)

1. **Hard conflict veto**: if `sign(S_base_i)` is opposite to `sign(A_i,t)` and `|A_i,t| >= 0.7`, cap target weight at 50% of normal.
2. **Severe uncertainty**: if `C_t < 0.4` or `Q_t < 0.6`, cap gross at `1.0x`.
3. **Crisis alignment**: if `M_t <= -0.7`, reduce long risk in high-beta classes by 30%.

## 5.5 4H execution layer (kept from v5)

Execution remains implementation-only:
- Quality >= 0.7: execute planned slice.
- 0.3 to 0.7: execute 50%, re-check next 4H bar.
- < 0.3: defer, cancel after 2 failed 4H bars.

---

## 6) Daily idea generation framework (new first-class block)

Ideas are generated only after the report is complete.

## 6.1 Theme extraction

From report, produce 3-6 high-conviction themes:
- Example: "real-yield compression favors gold."
- Example: "risk-off plus demand scare pressures crude."

## 6.2 Idea drafting

For each theme, define:
- Trade direction and instrument.
- Entry trigger.
- Target and stop.
- Time horizon.
- Explicit invalidation condition.

## 6.3 Quant confirmation gate

An idea is tradable only if:
1. `|S_v6_i| >= 1.0`.
2. Net edge > `2.0x` estimated round-trip cost.
3. Liquidity/spread state passes execution constraints.
4. Trade does not violate regime/risk caps.

If narrative is strong but quant gate fails: keep on watchlist, no trade.

## 6.4 Idea scoring and rank

`IdeaScore_i = 0.45*|S_v6_i| + 0.25*|A_i,t| + 0.15*C_t + 0.15*Q_t`

Trade highest scores first within turnover and class caps.

---

## 7) Portfolio construction updates

Use v5 optimization structure with `S_v6_i` replacing `S_i`.

Objective:

`max sum_i(w_i*S_v6_i) + lambda_theme*sum_i(|w_i|*ThemeAlign_i) - lambda_turn*sum_i(|w_i-w_prev_i|) - lambda_risk*(w'*Sigma*w)`

Subject to v5 constraints plus:
1. Theme concentration cap: no single daily theme contributes > 35% of gross risk.
2. Report-confidence scaling: effective gross cap multiplied by `(0.7 + 0.3*C_t*Q_t)`.
3. Event-risk cap: around high-impact scheduled events, reduce affected class gross by 20%-40%.

---

## 8) Risk management additions

Keep v5 stops/drawdown controls and add analysis-aware controls:
1. **Narrative invalidation exit**: if key thesis condition breaks, exit or halve within next execution window.
2. **Headline shock protocol**: if a new catalyst contradicts current day report, freeze new adds until report refresh.
3. **Confidence decay**: if `Q_t` drops for 2 consecutive days, step down gross by 25%.
4. **Crowding check**: if sentiment is one-sided and price is overextended, reduce new entries despite positive signal.

---

## 9) Daily operating timetable (example)

1. Pre-open: complete report and quality gates.
2. Post-report: compute `M_t`, `F_c,t`, `A_i,t`, `C_t`, `Q_t`.
3. Signal step: compute `S_v6_i` and candidate ideas.
4. Rebalance decision: generate target portfolio.
5. Execution: route across next 4H windows.
6. End-of-day: attribute PnL to base signal vs analysis overlay.

---

## 10) Validation protocol for v6

v6 must beat v5 on both returns and implementation robustness.

## 10.1 A/B backtest design

1. Baseline: v5 logic.
2. Treatment: v6 (analysis overlays + idea gating).
3. Same universe, costs, borrow assumptions, and delays.

## 10.2 Required diagnostics

1. Incremental Sharpe/Calmar from overlays.
2. Hit-rate uplift for analysis-approved vs non-approved ideas.
3. Turnover impact from veto/conflict rules.
4. Regime attribution: performance in risk-on/risk-off/neutral periods.
5. Failure analysis for days with low `Q_t` or low `C_t`.

## 10.3 Minimum acceptance criteria

1. OOS Sharpe improvement vs v5 >= +0.20.
2. Max drawdown no worse than v5.
3. Cost-stress (1.5x) Sharpe >= v5 by +0.10.
4. At least 60% of overlay contribution comes from high-`Q_t` days.
5. No degradation in worst-fold walk-forward result.

---

## 11) Fallback modes

1. **No report available**: no new positions; allow only de-risking and stop management.
2. **Low reliability report (`Q_t < 0.6`)**: trade at reduced gross and stricter thresholds.
3. **Contradictory report update intraday**: pause additions until recompute.

---

## 12) v6 vs v5 summary

- v5: signal-first with optional context.
- v6: **analysis-first**, then signal confirmation.
- v6 introduces formal intelligence translation (`M_t`, `F_c,t`, `A_i,t`, `C_t`, `Q_t`).
- v6 adds thesis conflict vetoes, confidence-scaled gross, and narrative invalidation controls.
- v6 keeps v5's weekly/daily/4H architecture, turnover discipline, and risk engine.

---

## 13) Source anchor inside this repo

1. Daily analysis framework: `doc/daily-market-analysis.md`
2. Current strategy baseline: `doc/long-short-trading-strategy-v5.md`
3. Performance context: `doc/performance_review_latest.md`
