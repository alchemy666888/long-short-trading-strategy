# Vibe Coding Development Plan: Long-Short Strategy v3 (Python)

## 1) Strategy understanding summary (from `long-short-trading-strategy-v3.md`)

Your v3 design is a **research-rigorous, backtest-first, zero-discretion** long-short framework focused on robustness over headline in-sample return. The strategy combines:

- **Cross-sectional, multi-horizon momentum** (20/60/120-bar returns with weighted z-scores),
- **Volatility normalization** via EWMA volatility,
- **Correlation-aware long/short pairing** (prefer cross-category, low correlation pairs),
- **Strict portfolio/risk constraints** (gross, dollar-neutrality tolerance, category caps, risk contribution cap),
- **Deterministic entry/exit stack** (ATR-defined R, stop/target, momentum decay, correlation breakdown, time stop),
- **Execution realism** (next-bar fills, baseline cost model + mandatory stress friction tests),
- **Hard validation governance** (walk-forward, holdout, robustness matrix, regime slicing, sample-size gates, bias audits),
- **Decision gates** (deploy/refine/abandon) based on OOS quality and stability plateaus.

In short: v3 is not just a signal recipe; it is a **full quantitative research protocol** with deployment-grade acceptance criteria.

---

## 2) Development goals for the Python implementation

1. Build a **modular, auditable Python research system** that reproduces v3 rules exactly.
2. Separate concerns: data contract, signal generation, portfolio construction, execution simulation, analytics.
3. Make every run reproducible via configs + deterministic logs.
4. Optimize for **robustness diagnostics** (stress, regime, walk-forward), not parameter overfitting.

---

## 3) Recommended repository structure

```text
project/
  pyproject.toml
  README.md
  configs/
    strategy_v3_base.yaml
    stress_profiles.yaml
    sweep_grid_v3.yaml
  src/
    data/
      loaders.py
      cleaning.py
      alignment.py
      eligibility.py
      corporate_actions.py
    features/
      returns.py
      momentum.py
      volatility.py
      stretch.py
      correlation.py
    portfolio/
      ranking.py
      pairing.py
      sizing.py
      constraints.py
    execution/
      fill_model.py
      cost_model.py
      order_simulator.py
    backtest/
      engine.py
      walkforward.py
      robustness.py
      regime.py
      bias_audit.py
    reporting/
      metrics.py
      plots.py
      report_builder.py
    utils/
      time.py
      logging.py
      validation.py
  tests/
    unit/
    integration/
    regression/
  notebooks/
  outputs/
```

---

## 4) Vibe coding roadmap (phased)

## Phase A — Data contract and bias-proof foundations

### Deliverables
- 5-minute OHLCV ingestion + ET normalization.
- Eligibility engine:
  - 120 trading days history for correlation context,
  - 120 bars for momentum windows,
  - stale bar rejection (>2 intervals),
  - spread + liquidity checks.
- Data hygiene:
  - point-in-time-safe return computation,
  - no forward-fill across market-closed gaps,
  - consistent corporate action handling,
  - 1-bar return winsorization (0.5%/99.5%).
- Mandatory data-quality log artifact per run.

### Python implementation notes
- `pandas`/`polars` for tabular handling, `numpy` for vector math.
- Standardize timestamps to UTC internally, convert to ET only for schedule logic/reporting.
- Build `DataContractValidator` class that fails fast with explicit reasons.

### Definition of done
- `pytest -k data_contract` passes.
- A sample run emits `outputs/<run_id>/data_quality_report.json` with exclusions and missing-bar events.

---

## Phase B — Signal layer (deterministic and testable)

### Deliverables
- Momentum core:
  - compute k-bar log returns (20/60/120),
  - cross-sectional z-score each rebalance timestamp,
  - weighted composite score,
  - EWMA vol normalization (half-life 30 bars).
- Stretch filter implementation using SMA/SD 36.
- Correlation/shrinkage engine:
  - hourly return resampling,
  - 60-day rolling correlations,
  - shrinkage: `0.7*Sigma + 0.3*I*avg_var`.

### Python implementation notes
- Keep feature calculation as pure functions for easy unit tests.
- Use explicit NaN policy and eligibility masks before ranking.

### Definition of done
- Unit tests verify formula parity on synthetic fixtures.
- Snapshot test confirms stable scores across code refactors.

---

## Phase C — Portfolio construction and constraints

### Deliverables
- Rebalance scheduler: 10:00 / 12:00 / 14:00 ET only.
- Quartile candidate selection from `M*`.
- Pairing algorithm:
  - iterate longs by descending `M*`,
  - choose weakest short, prefer different category,
  - enforce correlation preference (`rho < 0.25`, ideal negative),
  - fallback same-category only if constraints remain feasible.
- Sizing:
  - inverse-vol signed raw weights,
  - sequential constraint enforcement:
    1. dollar-neutral tolerance,
    2. gross leverage <= 3,
    3. category gross <= 35%,
    4. single-name risk contribution <= 15%,
  - if infeasible: proportional scale then prune lowest `|M*|` names.

### Python implementation notes
- Implement constraints as composable validators with rich diagnostics.
- Store rejected candidate reasons for post-mortem.

### Definition of done
- Integration tests confirm constraints are never violated in produced portfolios.
- Pairing decisions are fully reproducible from saved inputs.

---

## Phase D — Execution simulator + risk lifecycle

### Deliverables
- Next-bar-open execution only.
- Entry gate includes expected edge > round-trip cost + 0.2R buffer.
- ATR-based risk model:
  - stop = 1.25 × ATR(20, 5m),
  - target = 2.25 × ATR(20, 5m),
  - breakeven stop shift at +1R.
- Exit hierarchy engine (first trigger wins): stop, target, momentum decay, correlation breakdown, time-stop 15:55 ET.

### Python implementation notes
- Event-driven state machine per position to avoid ambiguous exit precedence.
- Persist full blotter with trigger source labels.

### Definition of done
- Regression test replays a deterministic day and validates expected fill/exit chronology.

---

## Phase E — Cost and stress framework (must-pass gate)

### Deliverables
- Baseline cost model by asset class:
  - crypto: taker bps + funding proxy,
  - equities: bps + short borrow fee,
  - FX/metals: spread + half-spread slippage proxy.
- Stress scenarios:
  - slippage multiplier 1.5x and 2.0x,
  - one-bar delayed execution,
  - worst-case fill proxy,
  - partial fill / rejection simulation.

### Python implementation notes
- Centralize costs in configurable profiles (`stress_profiles.yaml`).
- Ensure all scenario runs are traceable to exact config hash.

### Definition of done
- Stress run matrix generated automatically for each strategy run.
- Report highlights whether expectancy survives >=1.5x friction.

---

## Phase F — Validation protocol automation (core v3 upgrade)

### Deliverables
- Split engine:
  - in-sample first 60%,
  - rolling walk-forward (3m train / 1m test),
  - untouched final 20% holdout.
- Robustness matrix sweeps:
  - stop multiplier grid,
  - target multiplier grid,
  - rebalance timing offsets,
  - cost stress levels.
- Regime segmentation:
  - high/low vol,
  - trend/range,
  - risk-on/risk-off.
- Sample size gates and bias audit checklist.

### Python implementation notes
- Use experiment runner (`hydra` or lightweight YAML runner) for parallel sweeps.
- Save all results as tidy parquet + summary JSON for reproducible analysis.

### Definition of done
- Single command produces a full validation bundle and pass/fail decision flags.

---

## Phase G — Reporting and decision engine

### Deliverables
Automate the required backtest report sections:
1. hypothesis,
2. rules snapshot,
3. data coverage/exclusions,
4. headline metrics,
5. trade stats,
6. stress tests,
7. parameter heatmaps,
8. regime table,
9. failure analysis,
10. deploy/refine/abandon decision.

### Python implementation notes
- Generate both Markdown and JSON report artifacts.
- Add deterministic run IDs tied to git commit + config digest.

### Definition of done
- `outputs/<run_id>/report.md` fully matches v3 required format.

---

## 5) Engineering standards for Python implementation

- Type hints everywhere (`mypy`-friendly).
- Lint/format: `ruff` + `black`.
- Testing pyramid:
  - unit tests for formulas,
  - integration tests for pipeline continuity,
  - regression tests to guard strategy drift.
- Configuration-first design; avoid hard-coded constants.
- Every module logs assumptions and rejected data/positions.

---

## 6) Suggested first sprint backlog (high-impact sequence)

1. Implement `DataContractValidator` + eligibility masks.
2. Implement momentum/vol/stretch features with tests.
3. Implement rebalance scheduler + quartile ranking.
4. Implement pairing + constraint engine with diagnostics.
5. Implement order simulator and exit hierarchy.
6. Implement baseline + stress cost model profiles.
7. Implement walk-forward + holdout orchestration.
8. Implement report builder and decision gates.

---

## 7) Explicit non-goals (to prevent overfitting)

- No discretionary trade overrides.
- No adding extra alpha factors unless stability clearly improves.
- No deployment decision before sample-size and stress gates pass.
- No optimization based on a single best parameter point; require plateau behavior.

---

## 8) Final success criteria for v3 coding effort

The Python system is considered successful when:

1. It faithfully reproduces v3 rules end-to-end.
2. It emits complete audit/report artifacts for every run.
3. It demonstrates robust OOS behavior, not fragile in-sample tuning.
4. It can clearly classify outcomes as **deploy**, **refine**, or **abandon** from objective gates.
