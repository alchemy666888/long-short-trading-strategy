# Vibe Coding Development Plan: Long-Short Strategy v5 (Daily + 4H + Weekly)

## 1) Strategy understanding summary (from `long-short-trading-strategy-v5.md`)

v5 is a **multi-timeframe, friction-aware long/short system** designed to fix the v3/v4 failure modes (negative net edge, cost fragility, and broken cross-asset participation).

Core architecture:
1. **Weekly layer** sets regime and risk posture (`RISK_ON`, `NEUTRAL`, `RISK_OFF`).
2. **Daily layer** generates directional cross-asset scores and portfolio targets.
3. **4H layer** controls execution quality and staged order release.

Core design intent:
- preserve trend alpha while reducing chase risk using a small reversal dampener,
- enforce strict turnover and net-edge constraints,
- keep data integrity as a hard precondition for taking risk.

In short: v5 is not an indicator tweak. It is an execution-aware portfolio system with explicit deployment gates.

---

## 2) Development goals for the Python implementation

1. Migrate from the current 5-minute loop to a **daily target + 4H execution queue** engine.
2. Implement weekly regime scoring and tie it directly to leverage, side balance, and risk-off behavior.
3. Add robust data-quality gates for `1D`, `4H`, and derived `1W` features.
4. Make turnover/cost control first-class: no-trade bands, minimum holds, partial rebalancing.
5. Preserve reproducibility and auditability across every run artifact.

---

## 3) Recommended code changes in this repository

Primary files to modify:
1. `long_short_config.py`
2. `data_pipeline.py`
3. `strategy_core.py`
4. `backtest_vectorized.py`
5. `backtest_report.py`

Recommended new modules (optional but strongly preferred for maintainability):
- `execution_queue.py` (4H staged execution state machine)
- `regime.py` (weekly regime scoring + crash-state flags)
- `data_quality.py` (frequency/coverage/feature gates)
- `turnover.py` (no-trade band + partial-rebalance utilities)

---

## 4) Vibe coding roadmap (phased)

## Phase A - Migration scaffold and guardrails

### Deliverables
1. Freeze baseline output artifacts from current engine for comparison.
2. Add new config namespace for v5 timeframes and constraints.
3. Add run metadata schema to capture strategy version and config hash.

### Tasks
1. Add `PRIMARY_TIMEFRAME = "1D"`, `EXEC_TIMEFRAME = "4H"`, `REGIME_TIMEFRAME = "1W"`.
2. Add v5 constants:
   - weekly windows (26w, 52w, MA20w/MA40w),
   - daily windows (20d, 60d, 120d, 5d),
   - turnover constraints (no-trade band, partial-step bounds),
   - regime leverage caps.
3. Keep old v3 parameters under a separate block for rollback/testing.

### Definition of done
- Config imports are deterministic and v5 parameters are centralized.
- Backtest run metadata includes `strategy_version = "v5"`.

---

## Phase B - Data pipeline for 1D/4H/1W contract

### Deliverables
1. Canonical `1D` and `4H` OHLC matrices.
2. Derived `1W` series from daily data.
3. Hard data-quality gating artifacts.

### Tasks
1. Extend ingestion/build to output:
   - `opens_1d.pkl`, `highs_1d.pkl`, `lows_1d.pkl`, `closes_1d.pkl`
   - `opens_4h.pkl`, `highs_4h.pkl`, `lows_4h.pkl`, `closes_4h.pkl`
2. Add frequency checks:
   - median interval validation for 1D and 4H streams.
3. Add coverage checks:
   - daily coverage >= 98% over rolling 90d,
   - 4H coverage >= 95% over rolling 30d.
4. Add feature readiness checks:
   - completeness thresholds for weekly and daily features.
5. Emit `data_quality_report_v5.json` with exclusions and reasons.

### Definition of done
- Backtest cannot run if hard data gates fail.
- Report includes per-asset eligibility timeline and gate failures.

---

## Phase C - Weekly regime + daily signal engine

### Deliverables
1. Weekly regime score `W_i`.
2. Daily score stack `T_i`, `RV_i`, `S_raw_i`, `S_align_i`, `S_i`.
3. Panic/crash-state de-risking switch.

### Tasks
1. Implement weekly features:
   - `ret_26w`, `ret_52w`, `MA20w/MA40w - 1`, cross-sectional z-scores.
2. Implement daily features:
   - `ret_20d`, `ret_60d`, `ret_120d`, `ret_5d` dampener, EWMA vol normalization.
3. Implement alignment and clipping rules from v5 doc.
4. Implement portfolio regime label and map to leverage cap/side aggressiveness.
5. Implement panic-state trigger from market return + vol-z condition.

### Definition of done
- Unit tests validate each feature formula on synthetic fixtures.
- No look-ahead leakage across weekly/daily boundary alignment.

---

## Phase D - Portfolio construction with turnover-aware objective

### Deliverables
1. Candidate selection by daily percentile thresholds.
2. Constrained optimizer with turnover penalty.
3. No-trade band and minimum-hold enforcement.

### Tasks
1. Implement long bucket `q70+` and short bucket `q30-`.
2. Enforce breadth gates at rebalance:
   - >= 10 active assets, >= 3 categories, no category > 45%.
3. Implement objective:
   - signal reward,
   - turnover penalty,
   - covariance risk penalty.
4. Enforce constraints:
   - dollar-neutral tolerance,
   - regime-dependent gross cap,
   - name and category caps,
   - expected one-day turnover cap.
5. Add partial target-convergence logic when turnover pressure is high.

### Definition of done
- Produced target weights satisfy constraints in all integration tests.
- Turnover diagnostics are logged before and after throttling.

---

## Phase E - 4H execution queue and fill simulation

### Deliverables
1. 4H execution quality score and staged execution logic.
2. Net-edge pre-trade filter (`expected edge > 2.0x round-trip cost`).
3. Deterministic fill and cancellation behavior for deferred slices.

### Tasks
1. Create execution queue from daily targets.
2. For each 4H slot, compute:
   - 4H trend confirmation,
   - pullback quality,
   - spread/liquidity quality.
3. Execute by score bucket:
   - high quality: full slice,
   - medium quality: half slice,
   - low quality: defer and cancel after two failures.
4. Add partial-fill handling and carry-forward state.
5. Add per-asset-class transaction model and slippage hooks.

### Definition of done
- Replay test confirms consistent trade chronology for a fixed seed and dataset.
- Execution logs explain each trade as execute/defer/cancel with reason codes.

---

## Phase F - Position and portfolio risk lifecycle

### Deliverables
1. Position-level stop/trail/time-stop behavior from v5.
2. Portfolio-level drawdown and correlation kill-switches.
3. Regime-linked gross scaling logic.

### Tasks
1. Implement stop stack:
   - initial stop `2.0 x ATR(14d)`,
   - trailing after `+1.5R`,
   - time stop after 15 trading days.
2. Implement portfolio controls:
   - 5-day drawdown reduction,
   - 20-day drawdown flatten trigger,
   - high-correlation + high-vol gross cap.
3. Add kill-switch event logging and cooldown windows.

### Definition of done
- Risk controls trigger exactly once per qualifying event.
- Post-run audit file contains all risk actions with timestamps and causes.

---

## Phase G - Validation framework and decision gate automation

### Deliverables
1. Required stress matrix runs.
2. Walk-forward validation bundle.
3. Automated pass/fail against v5 acceptance criteria.

### Tasks
1. Implement scenarios:
   - base,
   - 1.5x costs,
   - 2.0x costs + delay,
   - missing-data stress,
   - liquidity stress,
   - borrow/funding stress.
2. Implement rolling walk-forward runner with embargo/purge logic.
3. Compute fold dispersion and worst-fold quality.
4. Build deployment gate evaluator using v5 thresholds.

### Definition of done
- One command produces `decision = deploy/refine/abandon` plus rationale.
- All scenario outputs are versioned and reproducible.

---

## 5) Reporting upgrades required

Add the following to `summary.md` and `summary.json`:
1. Regime-state attribution (return, Sharpe, drawdown per state).
2. Turnover decomposition:
   - raw turnover vs throttled turnover,
   - cost drag by asset class.
3. Execution quality diagnostics:
   - executed/deferred/canceled trade counts,
   - average slippage by quality bucket.
4. Breadth and eligibility diagnostics over time.
5. Risk-event ledger summary (stops, kill-switches, cooldown entries).

---

## 6) Engineering standards for v5 implementation

1. Type hints across strategy path (`mypy`-friendly).
2. Deterministic backtests for fixed inputs/config.
3. Config-first constants, no hidden hard-coded thresholds.
4. Unit tests for formulas and gating logic.
5. Integration tests for end-to-end event ordering.
6. Regression tests to detect strategy drift from intended v5 rules.

---

## 7) Suggested first sprint backlog (high impact)

1. Build 1D/4H data outputs and hard quality gates.
2. Implement weekly+daily feature engine with tests.
3. Replace 5m rebalance loop with daily target loop.
4. Add 4H execution queue and net-edge filter.
5. Add turnover throttle (no-trade band + partial rebalancing).
6. Add v5 report metrics and scenario runner skeleton.

---

## 8) Fine-tune experiment queue (post-baseline)

Run only after baseline v5 is stable:
1. Crash-state switch sensitivity (vol-z and return thresholds).
2. Adaptive no-trade band by spread/vol regime.
3. Asset-class-specific rebalance cadence.
4. Dispersion filter on/off with threshold sweep.
5. Regime-conditioned nonlinear leverage map.

---

## 9) Explicit non-goals (to avoid overfitting)

1. No discretionary overrides in backtest execution.
2. No factor additions beyond v5 baseline before acceptance-gate evidence.
3. No parameter selection from single best run; require stable plateau behavior.
4. No deployment decision without full stress matrix and walk-forward bundle.

---

## 10) Final success criteria for the v5 coding effort

The implementation is successful when:
1. v5 rules are reproduced exactly with no look-ahead leakage.
2. Data/feature/eligibility gates are enforced and auditable.
3. Cost and turnover controls materially reduce fragility versus v3/v4 behavior.
4. Validation outputs are sufficient to classify outcomes as **deploy**, **refine**, or **abandon** from objective gates.
