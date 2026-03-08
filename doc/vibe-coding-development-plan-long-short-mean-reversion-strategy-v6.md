# Vibe Coding Development Plan: Long-Short Strategy v6 (Analysis-First + Historical News Backtest)

## 1) Strategy understanding summary (from `long-short-trading-strategy-v6.md`)

v6 is an **analysis-first, multi-timeframe cross-asset long/short system**:
1. Daily market analysis is a hard pre-trade requirement.
2. Analysis output is converted into quantitative overlays (`M_t`, `F_c,t`, `A_i,t`, `C_t`, `Q_t`).
3. Weekly + daily systematic signal remains the baseline engine.
4. 4H layer remains execution-quality control.
5. Portfolio/risk controls are tightened by report reliability and scenario confidence.

Key difference vs v5:
- v5: signal-first with optional context.
- v6: analysis-first, then quant confirmation and execution.

---

## 2) Development objective for this coding cycle

Build a production-grade research/backtest pipeline that can:
1. Fetch and store **historical market data + historical news/events**.
2. Reconstruct each day’s market analysis report using only information available at that time.
3. Translate report outputs to v6 overlays (`M_t`, `F_c,t`, `A_i,t`, `C_t`, `Q_t`) and idea scores.
4. Run point-in-time backtests comparing v6 vs v5 under realistic cost and delay assumptions.
5. Produce an auditable decision output: `deploy`, `refine`, or `abandon`.

---

## 3) Required repository scope (planned modules)

Existing files to extend:
1. `long_short_config.py`
2. `data_pipeline.py`
3. `strategy_core.py`
4. `backtest_vectorized.py`
5. `backtest_report.py`
6. `data_quality.py`
7. `regime.py`
8. `execution_queue.py`
9. `turnover.py`

New modules recommended:
1. `news_pipeline.py` for historical news/event ingestion and normalization.
2. `macro_calendar.py` for macro release schedule and point-in-time release alignment.
3. `analysis_report_builder.py` for daily report reconstruction.
4. `analysis_scoring.py` for mapping report content to `M_t`, `F_c,t`, `A_i,t`, `C_t`, `Q_t`.
5. `analysis_quality.py` for report validity and reliability scoring.
6. `idea_engine.py` for theme extraction, idea scoring, and quant-gate checks.
7. `pit_store.py` for point-in-time data access helpers.
8. `ablation_runner.py` for v5 vs v6 controlled experiments.

---

## 4) Data architecture and point-in-time contract

## 4.1 Market data layers

1. Canonical bars:
   - `1D` OHLCV
   - `4H` OHLCV
   - `1W` derived from `1D`
2. Universe metadata:
   - asset class, region, liquidity tier, borrow/funding metadata.
3. Corporate and instrument events:
   - earnings windows, contract roll schedule, major listings/delistings.

## 4.2 News and macro data layers

1. Historical news feed with:
   - `published_at_utc`
   - `ingested_at_utc`
   - source id, headline/body, language, region tags
   - linked asset(s)/asset class tags
2. Macro release feed with:
   - event name, release timestamp, country/region
   - actual, consensus, prior, revision metadata
3. Optional positioning/sentiment feed:
   - COT-style positioning, risk sentiment indices, crypto flows, ETF flows.

## 4.3 Point-in-time safeguards (non-negotiable)

1. All daily analysis must read data only where `timestamp <= analysis_cutoff_t`.
2. Keep both `published_at_utc` and `ingested_at_utc`; backtest must use the later of the two.
3. Use revision-aware macro records; initial prints only unless explicitly modeling revision lag.
4. Maintain survivorship-safe universe snapshots by date.
5. Every run must persist a data snapshot hash and source manifest.

---

## 5) Vibe coding roadmap (phased)

## Phase A - Baseline freeze and v6 contracts

### Deliverables
1. Versioned baseline outputs for current v5 engine.
2. Formal schema for daily analysis report and overlays.
3. Config namespace for v6 analysis-first parameters.

### Tasks
1. Freeze v5 run artifacts and config hash for comparison.
2. Define report schema fields for the 7 required sections.
3. Define overlay schema:
   - `M_t`, `F_c,t`, `A_i,t`, `C_t`, `Q_t`, `REPORT_VALID`.
4. Add config parameters:
   - analysis cutoff time, min source count, quality thresholds, overlay weights.

### Definition of done
1. One canonical JSON schema exists for report and overlay artifacts.
2. v5 and v6 runs are reproducibly distinguishable by metadata.

---

## Phase B - Historical market data pipeline hardening

### Deliverables
1. `1D`, `4H`, `1W` market feature matrices for full backtest period.
2. Data quality gates aligned with v6 requirements.
3. Date-aligned universe eligibility snapshots.

### Tasks
1. Extend ingestion to produce canonical bar datasets by timeframe.
2. Enforce frequency and coverage thresholds.
3. Persist per-asset eligibility flags by day.
4. Emit market data quality report with gate failures.

### Definition of done
1. Backtest blocks new risk when mandatory market data gates fail.
2. All timeframe joins are leakage-safe and calendar-consistent.

---

## Phase C - Historical news and macro ingestion

### Deliverables
1. Normalized historical news/event dataset.
2. Macro event calendar with release-time alignment.
3. Daily ingest logs and source coverage diagnostics.

### Tasks
1. Build connector(s) to fetch historical news for backtest period.
2. Normalize records into a common schema and timezone.
3. Classify each record by region, asset class, and catalyst type.
4. Deduplicate near-identical headlines across sources.
5. Build macro release table with actual/consensus/prior metadata.
6. Track source quality and missing-day coverage.

### Definition of done
1. Historical coverage is measurable by date/source/asset class.
2. Data can be queried strictly point-in-time by analysis cutoff.

---

## Phase D - Daily market analysis reconstruction engine

### Deliverables
1. Deterministic daily report builder for historical dates.
2. Per-day report validity status and quality score components.
3. Structured output matching v6 required sections.

### Tasks
1. For each trading day, assemble macro/regional/asset/historical/sentiment/scenario blocks.
2. Enforce section completeness and minimum source depth rules.
3. Build scenario probability assignment and sum-to-100 checks.
4. Generate draft trade ideas with explicit invalidation fields.
5. Compute `REPORT_VALID` and diagnostic reason codes.

### Definition of done
1. Every backtest day has either a valid report or explicit invalid reasons.
2. Report artifacts are stored for replay and audit.

---

## Phase E - Intelligence-to-signal translation and idea scoring

### Deliverables
1. Time series for `M_t`, `F_c,t`, `A_i,t`, `C_t`, `Q_t`.
2. `S_v6_i` computation pipeline and conflict/veto flags.
3. Daily idea score table with quant-gate status.

### Tasks
1. Implement scoring rules from report output to overlay variables.
2. Build reliability/confidence logic and conservative-mode triggers.
3. Integrate overlays into `S_v6_i` and clipping rules.
4. Apply hard conflict veto and uncertainty caps.
5. Compute `IdeaScore_i` and quant confirmation gate outcomes.

### Definition of done
1. Overlay values are reproducible and explainable from stored report inputs.
2. Each executed idea has a full lineage: report -> overlay -> score -> trade decision.

---

## Phase F - Backtest engine integration (analysis-first flow)

### Deliverables
1. Event loop updated to enforce report-first sequencing.
2. Portfolio optimizer uses `S_v6_i` and confidence-scaled gross caps.
3. 4H execution queue remains active with v6 constraints.

### Tasks
1. Insert pre-trade dependency: report and overlays must exist before signal deployment.
2. If `REPORT_VALID = FALSE`, allow only de-risking and risk-control actions.
3. Replace `S_i` with `S_v6_i` in target construction.
4. Apply theme concentration and event-risk caps.
5. Keep no-trade bands, partial rebalancing, and net-edge filter.

### Definition of done
1. Chronology is strict: report generation precedes signal and order generation.
2. Integration tests confirm no-trade behavior when report gates fail.

---

## Phase G - Validation matrix and ablation framework

### Deliverables
1. Controlled v5 vs v6 A/B backtest runner.
2. Full stress matrix with cost, delay, missing-data, liquidity, borrow shocks.
3. Walk-forward validation with purge/embargo.

### Tasks
1. Run baseline v5 and treatment v6 on identical universe and dates.
2. Measure incremental contribution of analysis overlays.
3. Run ablations:
   - remove `M_t`,
   - remove `F_c,t`,
   - remove `A_i,t`,
   - disable quality gating.
4. Report fold dispersion and worst-fold outcomes.
5. Evaluate against v6 minimum acceptance criteria.

### Definition of done
1. Final scorecard includes both performance and robustness deltas vs v5.
2. Decision output is objective and reproducible.

---

## Phase H - Reporting, auditability, and run artifacts

### Deliverables
1. Daily and aggregate reports with analysis-overlay attribution.
2. Comprehensive run manifest for reproducibility.
3. Debug views for failed report days and vetoed ideas.

### Tasks
1. Extend `summary.md` and `summary.json` with:
   - overlay contribution attribution,
   - hit-rate by report quality bucket,
   - turnover and cost impact from veto rules,
   - regime-state performance.
2. Save artifacts per run:
   - daily reports,
   - overlay time series,
   - idea table with gate decisions,
   - executed/deferred/canceled orders and reasons.
3. Build failure dashboards for:
   - low `Q_t` clusters,
   - `REPORT_VALID = FALSE` days,
   - thesis invalidation exits.

### Definition of done
1. Any trade can be explained from source data to execution decision.
2. Research reruns produce identical outputs for fixed snapshots.

---

## 6) Backtest experiment design for historical news-driven v6

1. Use rolling walk-forward (example: 3-year train, 6-month test).
2. Run both pre-cost and post-cost performance.
3. Run stress cases:
   - 1.5x and 2.0x costs,
   - 1-day execution delay,
   - random news-dropout stress,
   - macro-release timestamp jitter stress.
4. Segment diagnostics by:
   - risk-on/risk-off/neutral regime,
   - high vs low `Q_t`,
   - high vs low `C_t`,
   - major macro event weeks vs normal weeks.
5. Require confidence intervals on incremental v6 uplift, not just point estimates.

---

## 7) Engineering standards

1. Deterministic run mode for reproducible research.
2. Config-first thresholds and weights; no hidden constants.
3. Strict schema validation for report and overlay artifacts.
4. Unit tests for scoring formulas and gating logic.
5. Integration tests for time-order correctness and no-lookahead guarantees.
6. Regression tests on representative date windows.

---

## 8) First sprint backlog (highest leverage)

1. Finalize v6 report and overlay schemas.
2. Build historical news ingestion with point-in-time timestamps.
3. Build deterministic daily report reconstruction for historical dates.
4. Implement overlay translation (`M_t`, `F_c,t`, `A_i,t`, `C_t`, `Q_t`).
5. Wire analysis-first gating into backtest chronology.
6. Produce first v5 vs v6 ablation report on a limited pilot window.

---

## 9) Explicit non-goals for this cycle

1. No live trading deployment changes before validation gates pass.
2. No broad feature expansion beyond v6 contract.
3. No parameter tuning from a single best sample period.
4. No discretionary override path inside historical backtests.

---

## 10) Success criteria for v6 coding plan execution

The plan is successful when:
1. Backtests can reconstruct daily analysis from historical news/market data without lookahead leakage.
2. v6 logic is fully auditable from source event to executed trade.
3. v6 demonstrates robust, statistically defensible improvement vs v5 under base and stress scenarios.
4. Final decision (`deploy` / `refine` / `abandon`) is produced by objective gates, not manual interpretation.
