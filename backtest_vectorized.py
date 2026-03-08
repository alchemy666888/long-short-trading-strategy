from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from analysis_report_builder import build_daily_reports
from analysis_scoring import (
    apply_overlay_ablation,
    build_overlay_frames,
    compute_conflict_multipliers,
    compute_v6_scores,
    overlay_summary_table,
)
from data_pipeline import load_processed_ohlc_v5
from execution_queue import execute_order_slice, build_execution_features
from idea_engine import build_daily_idea_table, enforce_theme_concentration_cap
from long_short_config import (
    ANALYSIS_CUTOFF_HOUR_ET,
    ANALYSIS_IDEAS_PATH,
    ANALYSIS_MACRO_CALENDAR_PATH,
    ANALYSIS_MAX_THEME_SHARE,
    ANALYSIS_MIN_REPORT_RELIABILITY,
    ANALYSIS_MIN_SCENARIO_CONFIDENCE,
    ANALYSIS_MIN_SOURCES_PER_CATALYST,
    ANALYSIS_NEWS_PATH,
    ANALYSIS_OVERLAYS_PATH,
    ANALYSIS_REPORTS_DIR,
    ASSETS,
    ATR_LOOKBACK_DAYS,
    BACKTEST_END_DATE,
    BACKTEST_LEVERAGE_MULTIPLIER,
    BACKTEST_START_DATE,
    BETA_BY_ASSET,
    BREADTH_MAX_CATEGORY_SHARE,
    BREADTH_MIN_ACTIVE_ASSETS,
    BREADTH_MIN_CATEGORIES,
    CAPITAL,
    CORR_GROSS_CAP,
    CORR_LOOKBACK_DAYS,
    CORR_TRIGGER,
    DAILY_TURNOVER_CAP,
    DD_20D_FLAT_DAYS,
    DD_20D_TRIGGER,
    DD_5D_COOLDOWN_DAYS,
    DD_5D_GROSS_REDUCTION,
    DD_5D_TRIGGER,
    DEFAULT_TRANSACTION_COST_BPS,
    HIGH_VOL_Z_TRIGGER,
    INITIAL_STOP_ATR_MULTIPLE,
    MIN_HOLD_DAYS,
    NO_TRADE_BAND,
    PANIC_GROSS_CAP,
    PANIC_MOMENTUM_MULTIPLIER,
    PARTIAL_REBALANCE_MAX_STEP,
    PARTIAL_REBALANCE_MIN_STEP,
    STRATEGY_VERSION,
    TIME_STOP_DAYS,
    TRAIL_ACTIVATION_R,
    TRAIL_ATR_MULTIPLE,
    TRANSACTION_COST_BPS_BY_CLASS,
    V6_CRISIS_LONG_REDUCTION,
    V6_CRISIS_MACRO_THRESHOLD,
    V6_HIGH_BETA_CLASSES,
    V6_REPORT_GROSS_SCALE_BASE,
    V6_REPORT_GROSS_SCALE_MULT,
    V6_SEVERE_UNCERTAINTY_GROSS_CAP,
)
from macro_calendar import load_macro_calendar, macro_coverage_diagnostics
from news_pipeline import load_historical_news, news_coverage_diagnostics
from regime import build_regime_context
from strategy_core import (
    build_daily_target_weights,
    compute_atr,
    compute_shrunk_covariance,
    compute_v5_daily_stack,
    enforce_weight_constraints,
    get_asset_class,
)
from turnover import apply_turnover_controls


@dataclass
class PositionState:
    side: int
    entry_date: pd.Timestamp
    entry_price: float
    stop_price: float
    initial_r: float
    trailing_active: bool
    extreme_price: float
    hold_days: int


def _cost_bps_for_asset(asset: str, multiplier: float = 1.0) -> float:
    asset_class = get_asset_class(asset)
    bps = float(TRANSACTION_COST_BPS_BY_CLASS.get(asset_class, DEFAULT_TRANSACTION_COST_BPS))
    return bps * multiplier


def _state_metrics(returns: pd.Series) -> Dict[str, float]:
    returns = returns.dropna()
    if returns.empty:
        return {
            "bars": 0,
            "total_return_pct": np.nan,
            "annualized_return_pct": np.nan,
            "annualized_volatility_pct": np.nan,
            "sharpe": np.nan,
            "max_drawdown_pct": np.nan,
        }

    cumulative = (1.0 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative / running_max) - 1.0

    total_return = float(cumulative.iloc[-1] - 1.0)
    ann_return = float((1.0 + total_return) ** (252.0 / len(returns)) - 1.0) if len(returns) > 0 else np.nan
    ann_vol = float(returns.std() * np.sqrt(252.0)) if len(returns) > 1 else np.nan
    sharpe = ann_return / ann_vol if ann_vol and not np.isnan(ann_vol) else np.nan

    return {
        "bars": int(len(returns)),
        "total_return_pct": total_return * 100.0,
        "annualized_return_pct": ann_return * 100.0 if not np.isnan(ann_return) else np.nan,
        "annualized_volatility_pct": ann_vol * 100.0 if not np.isnan(ann_vol) else np.nan,
        "sharpe": float(sharpe) if not np.isnan(sharpe) else np.nan,
        "max_drawdown_pct": float(drawdown.min() * 100.0),
    }


def _average_pairwise_corr(returns_window: pd.DataFrame) -> float:
    if returns_window.empty or returns_window.shape[1] < 2:
        return np.nan

    corr = returns_window.corr(min_periods=max(10, len(returns_window) // 4))
    if corr.empty:
        return np.nan

    vals = corr.values
    mask = ~np.eye(vals.shape[0], dtype=bool)
    off_diag = vals[mask]
    off_diag = off_diag[~np.isnan(off_diag)]
    if len(off_diag) == 0:
        return np.nan
    return float(np.mean(off_diag))


def _apply_missing_data_stress(
    closes_1d: pd.DataFrame,
    closes_4h: pd.DataFrame,
    ratio: float,
    seed: int,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if ratio <= 0:
        return closes_1d, closes_4h

    rng = np.random.default_rng(seed)

    c1 = closes_1d.copy()
    c4 = closes_4h.copy()

    mask_1d = rng.random(c1.shape) < ratio
    mask_4h = rng.random(c4.shape) < ratio

    warmup_1d = min(130, len(c1))
    warmup_4h = min(260, len(c4))

    if warmup_1d > 0:
        mask_1d[:warmup_1d, :] = False
    if warmup_4h > 0:
        mask_4h[:warmup_4h, :] = False

    c1 = c1.mask(mask_1d)
    c4 = c4.mask(mask_4h)
    return c1, c4


def _persist_analysis_artifacts(overlay_table: pd.DataFrame, idea_table: pd.DataFrame) -> None:
    overlay_path = Path(ANALYSIS_OVERLAYS_PATH)
    idea_path = Path(ANALYSIS_IDEAS_PATH)

    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    idea_path.parent.mkdir(parents=True, exist_ok=True)

    overlay_table.to_pickle(overlay_path)
    idea_table.to_pickle(idea_path)


def run_backtest(
    cost_multiplier: float = 1.0,
    one_day_delay: bool = False,
    missing_data_ratio: float = 0.0,
    liquidity_haircut: float = 1.0,
    short_borrow_bps_per_day: float = 0.0,
    seed: int = 7,
    leverage_multiplier: float = BACKTEST_LEVERAGE_MULTIPLIER,
    strategy_version: str = STRATEGY_VERSION,
    analysis_ablation: Optional[str] = None,
    persist_analysis_artifacts: bool = False,
) -> Dict:
    strategy_version = str(strategy_version).lower().strip()
    if strategy_version not in {"v5", "v6"}:
        raise ValueError(f"Unsupported strategy version: {strategy_version}")
    if leverage_multiplier <= 0:
        raise ValueError(f"leverage_multiplier must be > 0, got {leverage_multiplier}")

    matrices, quality_report = load_processed_ohlc_v5(require_quality_pass=True)

    opens_1d = matrices["opens_1d"].copy()
    highs_1d = matrices["highs_1d"].copy()
    lows_1d = matrices["lows_1d"].copy()
    closes_1d = matrices["closes_1d"].copy()
    closes_4h = matrices["closes_4h"].copy()

    if missing_data_ratio > 0:
        closes_1d, closes_4h = _apply_missing_data_stress(
            closes_1d=closes_1d,
            closes_4h=closes_4h,
            ratio=missing_data_ratio,
            seed=seed,
        )

    tz = closes_1d.index.tz
    start_ts = pd.Timestamp(BACKTEST_START_DATE)
    end_ts = pd.Timestamp(BACKTEST_END_DATE) + pd.Timedelta(days=1)
    if tz is not None:
        start_ts = start_ts.tz_localize(tz)
        end_ts = end_ts.tz_localize(tz)

    day_mask = (closes_1d.index >= start_ts) & (closes_1d.index < end_ts)
    daily_index = closes_1d.index[day_mask]

    if len(daily_index) < 200:
        raise ValueError(
            f"Not enough daily bars in backtest range ({len(daily_index)}). "
            "Build longer history before running backtest."
        )

    opens_1d = opens_1d.reindex(daily_index)
    highs_1d = highs_1d.reindex(daily_index)
    lows_1d = lows_1d.reindex(daily_index)
    closes_1d = closes_1d.reindex(daily_index)

    eligible_assets = quality_report.get("breadth", {}).get("eligible_assets_list", [])
    assets = [asset for asset in closes_1d.columns if asset in ASSETS and asset in eligible_assets]
    if not assets:
        raise ValueError("No eligible assets remain after data-quality gating.")
    closes_1d = closes_1d[assets]
    opens_1d = opens_1d[assets]
    highs_1d = highs_1d[assets]
    lows_1d = lows_1d[assets]

    regime_df, weekly_score_daily = build_regime_context(closes_1d)
    signal_bundle = compute_v5_daily_stack(closes_1d=closes_1d, weekly_score_daily=weekly_score_daily)
    base_score = signal_bundle["score"]
    vol = signal_bundle["vol"]
    daily_returns = signal_bundle["returns"]
    atr14 = compute_atr(highs_1d, lows_1d, closes_1d, lookback=ATR_LOOKBACK_DAYS)

    closes_4h = closes_4h.reindex(columns=assets)
    exec_features = build_execution_features(closes_4h)

    weights = pd.Series(0.0, index=assets)
    states: Dict[str, PositionState] = {}

    equity = float(CAPITAL)
    equity_index: List[pd.Timestamp] = [daily_index[0]]
    equity_values: List[float] = [equity]
    net_returns: List[float] = [0.0]

    weights_history: Dict[pd.Timestamp, pd.Series] = {daily_index[0]: weights.copy()}

    turnover_raw: List[float] = []
    turnover_throttled: List[float] = []
    turnover_after_band: List[float] = []

    execution_counts = Counter()
    execution_bucket_counts = Counter()
    execution_bucket_slippage: Dict[str, List[float]] = {"high": [], "medium": [], "low": []}

    cost_drag_by_class = defaultdict(float)
    risk_events: List[Dict] = []
    breadth_history: List[Dict] = []

    dd5_cooldown = 0
    dd20_flat = 0
    corr_cap_active = False

    score_for_target = base_score
    conflict_multipliers = pd.DataFrame(1.0, index=base_score.index, columns=base_score.columns)

    reports_by_day: Dict[pd.Timestamp, Dict] = {}
    overlays: Dict[str, object] = {}
    overlay_table = pd.DataFrame(index=daily_index)
    idea_rows: List[pd.DataFrame] = []
    analysis_daily_ledger: List[Dict] = []

    analysis_data_diagnostics = {
        "news": {"rows": 0, "days": 0, "sources": 0, "asset_classes": {}, "regions": {}, "catalysts": {}},
        "macro": {"rows": 0, "days": 0, "regions": {}, "importance": {}},
    }

    if strategy_version == "v6":
        news_df = load_historical_news(path=ANALYSIS_NEWS_PATH)
        macro_df = load_macro_calendar(path=ANALYSIS_MACRO_CALENDAR_PATH)

        analysis_data_diagnostics = {
            "news": news_coverage_diagnostics(news_df),
            "macro": macro_coverage_diagnostics(macro_df),
        }

        report_output_dir = ANALYSIS_REPORTS_DIR if persist_analysis_artifacts else None
        reports_by_day = build_daily_reports(
            daily_index=daily_index,
            closes_1d=closes_1d,
            assets=assets,
            asset_class_by_asset={asset: get_asset_class(asset) for asset in assets},
            news_df=news_df,
            macro_df=macro_df,
            cutoff_hour_et=ANALYSIS_CUTOFF_HOUR_ET,
            min_sources_per_catalyst=ANALYSIS_MIN_SOURCES_PER_CATALYST,
            output_dir=report_output_dir,
        )

        overlays = build_overlay_frames(
            reports_by_day=reports_by_day,
            assets=assets,
            asset_class_by_asset={asset: get_asset_class(asset) for asset in assets},
        )
        overlays = apply_overlay_ablation(overlays, analysis_ablation)

        score_for_target = compute_v6_scores(
            base_scores=base_score,
            overlays=overlays,
            asset_class_by_asset={asset: get_asset_class(asset) for asset in assets},
            beta_by_asset=BETA_BY_ASSET,
        )

        conflict_multipliers = compute_conflict_multipliers(
            base_scores=base_score,
            asset_overlay=overlays["asset_overlay"],
        )

        overlay_table = overlay_summary_table(overlays=overlays)

    for i in range(1, len(daily_index)):
        ts = daily_index[i]
        prev_equity = equity

        effective_weights = weights * float(leverage_multiplier)
        ret_row = daily_returns.loc[ts].reindex(assets).fillna(0.0)
        gross_short = float((-effective_weights[effective_weights < 0]).sum())
        borrow_cost_return = gross_short * (short_borrow_bps_per_day / 10000.0)
        pnl_return = float((effective_weights * ret_row).sum()) - borrow_cost_return
        equity *= max(0.0, 1.0 + pnl_return)

        forced_exit_assets = []
        for asset in list(states.keys()):
            if abs(weights.get(asset, 0.0)) <= 1e-10:
                del states[asset]
                continue

            st = states[asset]
            st.hold_days += 1

            high = highs_1d.at[ts, asset] if asset in highs_1d.columns else np.nan
            low = lows_1d.at[ts, asset] if asset in lows_1d.columns else np.nan
            atr_val = atr14.at[ts, asset] if asset in atr14.columns else np.nan

            if st.side > 0:
                if not np.isnan(high):
                    st.extreme_price = max(st.extreme_price, float(high))
                if st.initial_r > 0 and not st.trailing_active:
                    if (st.extreme_price - st.entry_price) / st.initial_r >= TRAIL_ACTIVATION_R:
                        st.trailing_active = True
                if st.trailing_active and not np.isnan(atr_val):
                    st.stop_price = max(st.stop_price, st.extreme_price - (TRAIL_ATR_MULTIPLE * float(atr_val)))
                if not np.isnan(low) and low <= st.stop_price:
                    forced_exit_assets.append((asset, "stop_loss"))
                    continue
            else:
                if not np.isnan(low):
                    st.extreme_price = min(st.extreme_price, float(low))
                if st.initial_r > 0 and not st.trailing_active:
                    if (st.entry_price - st.extreme_price) / st.initial_r >= TRAIL_ACTIVATION_R:
                        st.trailing_active = True
                if st.trailing_active and not np.isnan(atr_val):
                    st.stop_price = min(st.stop_price, st.extreme_price + (TRAIL_ATR_MULTIPLE * float(atr_val)))
                if not np.isnan(high) and high >= st.stop_price:
                    forced_exit_assets.append((asset, "stop_loss"))
                    continue

            score_now = score_for_target.at[ts, asset] if asset in score_for_target.columns else np.nan
            if st.hold_days >= TIME_STOP_DAYS and (np.isnan(score_now) or abs(score_now) < 0.25):
                forced_exit_assets.append((asset, "time_stop"))

        for asset, reason in forced_exit_assets:
            cur = float(weights.get(asset, 0.0))
            if abs(cur) <= 1e-10:
                continue

            delta = -cur
            bps = _cost_bps_for_asset(asset, cost_multiplier)
            cost = abs(delta) * float(leverage_multiplier) * equity * (bps / 10000.0)
            equity -= cost
            cost_drag_by_class[get_asset_class(asset)] += cost
            weights.at[asset] = 0.0
            if asset in states:
                del states[asset]
            risk_events.append({"timestamp": str(ts), "event": reason, "asset": asset})

        if len(equity_values) >= 5:
            eq5 = equity_values[-5:] + [equity]
            dd5 = (eq5[-1] / max(eq5)) - 1.0
            if dd5 <= DD_5D_TRIGGER and dd5_cooldown == 0:
                dd5_cooldown = DD_5D_COOLDOWN_DAYS
                risk_events.append({"timestamp": str(ts), "event": "portfolio_dd5_cut", "value": round(dd5, 4)})

        if len(equity_values) >= 20:
            eq20 = equity_values[-20:] + [equity]
            dd20 = (eq20[-1] / max(eq20)) - 1.0
            if dd20 <= DD_20D_TRIGGER and dd20_flat == 0:
                dd20_flat = DD_20D_FLAT_DAYS
                risk_events.append({"timestamp": str(ts), "event": "portfolio_dd20_flat", "value": round(dd20, 4)})

        regime_row = regime_df.loc[ts]
        regime_cap = float(regime_row.get("leverage_cap", 1.0))
        side_tilt = float(regime_row.get("side_tilt", 0.0))

        score_row = score_for_target.loc[ts].reindex(assets)
        if bool(regime_row.get("panic", False)):
            score_row = score_row * PANIC_MOMENTUM_MULTIPLIER
            regime_cap = min(regime_cap, PANIC_GROSS_CAP)

        if dd5_cooldown > 0:
            regime_cap *= max(0.0, 1.0 - DD_5D_GROSS_REDUCTION)
        if dd20_flat > 0:
            regime_cap = 0.0

        report_valid = True
        c_t = 1.0
        q_t = 1.0
        m_t = 0.0
        event_mult = 1.0
        theme_by_asset: Dict[str, str] = {}

        if strategy_version == "v6":
            report_valid = bool(overlays["report_valid"].get(ts, False))
            c_t = float(overlays["scenario_confidence"].get(ts, 0.0))
            q_t = float(overlays["reliability"].get(ts, 0.0))
            m_t = float(overlays["macro_overlay"].get(ts, 0.0))
            event_mult = float(overlays["event_risk_multiplier"].get(ts, 1.0))
            theme_by_asset = overlays["theme_by_day"].get(ts, {})

            conf_scale = V6_REPORT_GROSS_SCALE_BASE + (V6_REPORT_GROSS_SCALE_MULT * c_t * q_t)
            regime_cap *= max(0.0, conf_scale)
            regime_cap *= event_mult

            if analysis_ablation != "no_quality":
                if c_t < ANALYSIS_MIN_SCENARIO_CONFIDENCE or q_t < ANALYSIS_MIN_REPORT_RELIABILITY:
                    regime_cap = min(regime_cap, V6_SEVERE_UNCERTAINTY_GROSS_CAP)
                if not report_valid:
                    regime_cap = 0.0
                    risk_events.append({"timestamp": str(ts), "event": "report_invalid_derisk_only"})

        corr_window = daily_returns.loc[:ts, assets].tail(CORR_LOOKBACK_DAYS)
        avg_corr = _average_pairwise_corr(corr_window)
        market_vol_z = float(regime_row.get("market_vol_z", np.nan))
        corr_condition = (not np.isnan(avg_corr)) and (avg_corr > CORR_TRIGGER) and (
            not np.isnan(market_vol_z) and market_vol_z > HIGH_VOL_Z_TRIGGER
        )

        if corr_condition:
            regime_cap = min(regime_cap, CORR_GROSS_CAP)
            if not corr_cap_active:
                risk_events.append(
                    {
                        "timestamp": str(ts),
                        "event": "corr_vol_gross_cap",
                        "avg_corr": round(avg_corr, 4),
                        "market_vol_z": round(market_vol_z, 4),
                    }
                )
                corr_cap_active = True
        else:
            corr_cap_active = False

        cov_window = daily_returns.loc[:ts, assets].tail(120)
        cov_matrix = compute_shrunk_covariance(cov_window)

        if strategy_version == "v6" and (analysis_ablation != "no_quality") and (not report_valid):
            target = (weights * 0.5).reindex(assets).fillna(0.0)
            target_diag = {
                "active_assets": int((target.abs() > 1e-8).sum()),
                "active_categories": int(len(set(get_asset_class(a) for a in target[target.abs() > 1e-8].index))),
                "max_category_share": float(1.0),
                "reason": "report_invalid_derisk_only",
            }
        else:
            target, target_diag = build_daily_target_weights(
                score_row=score_row,
                vol_row=vol.loc[ts].reindex(assets),
                prev_weights=weights,
                cov_matrix=cov_matrix,
                gross_cap=max(0.0, regime_cap),
                side_tilt=side_tilt,
                min_per_side=4,
            )

            if (
                target_diag.get("active_assets", 0) < BREADTH_MIN_ACTIVE_ASSETS
                or target_diag.get("active_categories", 0) < BREADTH_MIN_CATEGORIES
                or target_diag.get("max_category_share", 1.0) > BREADTH_MAX_CATEGORY_SHARE
            ):
                target = pd.Series(0.0, index=assets)
                risk_events.append(
                    {
                        "timestamp": str(ts),
                        "event": "breadth_gate_block",
                        "active_assets": int(target_diag.get("active_assets", 0)),
                        "active_categories": int(target_diag.get("active_categories", 0)),
                    }
                )

        for asset, st in states.items():
            if st.hold_days >= MIN_HOLD_DAYS:
                continue
            cur = float(weights.get(asset, 0.0))
            tgt = float(target.get(asset, 0.0))
            if np.sign(cur) != np.sign(tgt) or abs(tgt) < abs(cur):
                target.at[asset] = cur

        if strategy_version == "v6":
            asset_overlay_row = overlays["asset_overlay"].loc[ts].reindex(assets).fillna(0.0)
            cost_bps_by_asset = {asset: _cost_bps_for_asset(asset, cost_multiplier) for asset in assets}

            idea_table_day = build_daily_idea_table(
                ts=ts,
                assets=assets,
                scores_row=score_row,
                asset_overlay_row=asset_overlay_row,
                scenario_confidence=c_t,
                reliability=q_t,
                report_valid=report_valid,
                cost_bps_by_asset=cost_bps_by_asset,
                theme_by_asset=theme_by_asset,
            )
            idea_rows.append(idea_table_day)

            quant_gate_map = (
                idea_table_day.set_index("asset")["quant_gate_pass"].to_dict() if not idea_table_day.empty else {}
            )
            for asset in assets:
                if bool(quant_gate_map.get(asset, False)):
                    continue
                cur = float(weights.get(asset, 0.0))
                tgt = float(target.get(asset, 0.0))
                if abs(tgt) > abs(cur):
                    target.at[asset] = cur

            conflict_row = conflict_multipliers.loc[ts].reindex(assets).fillna(1.0)
            target = (target * conflict_row).reindex(assets).fillna(0.0)

            if m_t <= V6_CRISIS_MACRO_THRESHOLD:
                for asset in assets:
                    if get_asset_class(asset) in V6_HIGH_BETA_CLASSES and float(target.get(asset, 0.0)) > 0:
                        target.at[asset] *= (1.0 - V6_CRISIS_LONG_REDUCTION)

            target = enforce_theme_concentration_cap(
                weights=target,
                theme_by_asset=theme_by_asset,
                max_theme_share=ANALYSIS_MAX_THEME_SHARE,
            )

            analysis_daily_ledger.append(
                {
                    "timestamp": ts,
                    "report_valid": bool(report_valid),
                    "M_t": float(m_t),
                    "C_t": float(c_t),
                    "Q_t": float(q_t),
                    "event_risk_multiplier": float(event_mult),
                    "gross_cap_effective": float(regime_cap),
                }
            )

        target = enforce_weight_constraints(target.reindex(assets).fillna(0.0), gross_cap=max(0.0, regime_cap))

        controlled_target, turn_diag = apply_turnover_controls(
            current_weights=weights,
            target_weights=target,
            no_trade_band=NO_TRADE_BAND,
            turnover_cap=DAILY_TURNOVER_CAP,
            partial_step_min=PARTIAL_REBALANCE_MIN_STEP,
            partial_step_max=PARTIAL_REBALANCE_MAX_STEP,
        )

        turnover_raw.append(turn_diag["raw_turnover"])
        turnover_after_band.append(turn_diag["turnover_after_band"])
        turnover_throttled.append(turn_diag["throttled_turnover"])

        desired_delta = controlled_target - weights

        future_days = daily_index[daily_index > ts]
        delay_steps = 1 if one_day_delay else 0
        exec_day: Optional[pd.Timestamp] = future_days[delay_steps] if len(future_days) > delay_steps else None

        filled_delta = pd.Series(0.0, index=assets)
        if exec_day is not None:
            cost_bps_by_asset = {asset: _cost_bps_for_asset(asset, cost_multiplier) for asset in assets}
            filled_delta, exec_stats, _ = execute_order_slice(
                order_deltas=desired_delta,
                exec_day=exec_day,
                closes_4h=closes_4h,
                features_4h=exec_features,
                score_row=score_row,
                cost_bps_by_asset=cost_bps_by_asset,
                liquidity_haircut=liquidity_haircut,
            )

            execution_counts.update(
                {
                    "executed": int(exec_stats.get("executed", 0)),
                    "deferred": int(exec_stats.get("deferred", 0)),
                    "canceled": int(exec_stats.get("canceled", 0)),
                }
            )
            execution_bucket_counts.update(exec_stats.get("bucket_counts", {}))
            for bucket, values in exec_stats.get("slippage_bps", {}).items():
                execution_bucket_slippage.setdefault(bucket, []).extend([float(v) for v in values])

        weights = (weights + filled_delta).reindex(assets).fillna(0.0)
        weights = enforce_weight_constraints(weights, gross_cap=max(0.0, regime_cap))

        daily_trade_cost = 0.0
        for asset, delta in filled_delta.items():
            if abs(float(delta)) <= 1e-10:
                continue

            bps = _cost_bps_for_asset(asset, cost_multiplier)
            trade_cost = abs(float(delta)) * float(leverage_multiplier) * equity * (bps / 10000.0)
            daily_trade_cost += trade_cost
            cost_drag_by_class[get_asset_class(asset)] += trade_cost

        equity -= daily_trade_cost

        for asset in assets:
            w = float(weights.get(asset, 0.0))
            if abs(w) <= 1e-10:
                if asset in states:
                    del states[asset]
                continue

            side = 1 if w > 0 else -1
            close_px = closes_1d.at[ts, asset] if asset in closes_1d.columns else np.nan
            atr_val = atr14.at[ts, asset] if asset in atr14.columns else np.nan

            if np.isnan(close_px) or close_px <= 0:
                continue

            if np.isnan(atr_val) or atr_val <= 0:
                atr_val = max(0.001 * close_px, close_px * 0.02)

            initial_r = INITIAL_STOP_ATR_MULTIPLE * float(atr_val)
            stop_price = close_px - initial_r if side > 0 else close_px + initial_r

            prev_state = states.get(asset)
            if prev_state is None or prev_state.side != side:
                states[asset] = PositionState(
                    side=side,
                    entry_date=ts,
                    entry_price=float(close_px),
                    stop_price=float(stop_price),
                    initial_r=float(initial_r),
                    trailing_active=False,
                    extreme_price=float(close_px),
                    hold_days=0,
                )

        active_assets = [a for a, w in weights.items() if abs(float(w)) > 1e-8]
        active_classes = Counter(get_asset_class(a) for a in active_assets)
        max_share = max(active_classes.values()) / max(len(active_assets), 1) if active_classes else 0.0

        breadth_history.append(
            {
                "timestamp": ts,
                "active_assets": len(active_assets),
                "active_categories": len(active_classes),
                "max_category_share": float(max_share),
                "eligible_assets": int(quality_report.get("breadth", {}).get("eligible_assets", 0)),
            }
        )

        if dd5_cooldown > 0:
            dd5_cooldown -= 1
        if dd20_flat > 0:
            dd20_flat -= 1

        equity_index.append(ts)
        equity_values.append(float(equity))
        weights_history[ts] = weights.copy()

        net_ret = (equity / prev_equity) - 1.0 if prev_equity > 0 else 0.0
        net_returns.append(float(net_ret))

    equity_series = pd.Series(equity_values, index=equity_index, name="equity")
    returns_series = pd.Series(net_returns, index=equity_index, name="daily_return")
    weights_df = pd.DataFrame(weights_history).T.reindex(equity_index).fillna(0.0)

    regime_aligned = regime_df.reindex(returns_series.index)
    regime_attr = {}
    for state in ["RISK_ON", "NEUTRAL", "RISK_OFF"]:
        state_returns = returns_series[regime_aligned["state"] == state]
        regime_attr[state] = _state_metrics(state_returns)

    total_cost_drag = float(sum(cost_drag_by_class.values()))
    median_turnover = float(np.median(turnover_throttled)) if turnover_throttled else 0.0

    diagnostics = {
        "strategy_version": strategy_version,
        "leverage_multiplier": float(leverage_multiplier),
        "quality": quality_report,
        "regime_attribution": regime_attr,
        "turnover": {
            "avg_raw_turnover": float(np.mean(turnover_raw)) if turnover_raw else 0.0,
            "avg_turnover_after_band": float(np.mean(turnover_after_band)) if turnover_after_band else 0.0,
            "avg_throttled_turnover": float(np.mean(turnover_throttled)) if turnover_throttled else 0.0,
            "median_daily_turnover_pct": median_turnover * 100.0,
        },
        "execution": {
            "counts": {
                "executed": int(execution_counts.get("executed", 0)),
                "deferred": int(execution_counts.get("deferred", 0)),
                "canceled": int(execution_counts.get("canceled", 0)),
            },
            "bucket_counts": dict(execution_bucket_counts),
            "avg_slippage_bps_by_bucket": {
                bucket: (float(np.mean(vals)) if vals else np.nan)
                for bucket, vals in execution_bucket_slippage.items()
            },
        },
        "cost_drag": {
            "total_cost_drag": total_cost_drag,
            "cost_drag_pct_of_starting_capital": (total_cost_drag / CAPITAL) * 100.0,
            "by_asset_class": {k: float(v) for k, v in cost_drag_by_class.items()},
        },
        "breadth": {
            "average_active_assets": float(np.mean([x["active_assets"] for x in breadth_history])) if breadth_history else 0.0,
            "average_active_categories": float(np.mean([x["active_categories"] for x in breadth_history])) if breadth_history else 0.0,
            "max_category_share_mean": float(np.mean([x["max_category_share"] for x in breadth_history])) if breadth_history else 0.0,
            "history": breadth_history,
        },
        "risk_events": {
            "count": len(risk_events),
            "by_type": dict(Counter(evt["event"] for evt in risk_events)),
            "ledger": risk_events,
        },
    }

    idea_table = pd.concat(idea_rows, axis=0, ignore_index=True) if idea_rows else pd.DataFrame()

    if strategy_version == "v6":
        if overlay_table.empty:
            overlay_table = pd.DataFrame(index=daily_index)

        overlay_strength = (score_for_target - base_score).abs().mean(axis=1).fillna(0.0)
        q_series = overlays.get("reliability", pd.Series(0.0, index=overlay_strength.index))
        high_q_mask = q_series.reindex(overlay_strength.index).fillna(0.0) >= ANALYSIS_MIN_REPORT_RELIABILITY

        overlay_total = float(overlay_strength.sum())
        overlay_high_q = float(overlay_strength[high_q_mask].sum()) if overlay_total > 0 else np.nan
        overlay_high_q_share = float(overlay_high_q / overlay_total) if overlay_total > 0 else np.nan

        diagnostics["analysis"] = {
            "ablation_mode": analysis_ablation,
            "report_valid_rate": float(overlays["report_valid"].mean()) if "report_valid" in overlays else 0.0,
            "mean_q_t": float(overlays["reliability"].mean()) if "reliability" in overlays else 0.0,
            "mean_c_t": float(overlays["scenario_confidence"].mean()) if "scenario_confidence" in overlays else 0.0,
            "overlay_high_q_share": overlay_high_q_share,
            "daily_ledger": analysis_daily_ledger,
            "data_coverage": analysis_data_diagnostics,
        }

        if persist_analysis_artifacts:
            _persist_analysis_artifacts(overlay_table=overlay_table, idea_table=idea_table)

    return {
        "equity": equity_series,
        "daily_returns": returns_series,
        "weights": weights_df,
        "diagnostics": diagnostics,
        "overlay_table": overlay_table,
        "idea_table": idea_table,
    }


if __name__ == "__main__":
    base = run_backtest(
        cost_multiplier=1.0,
        one_day_delay=False,
        missing_data_ratio=0.0,
        liquidity_haircut=1.0,
        short_borrow_bps_per_day=0.0,
        strategy_version=STRATEGY_VERSION,
    )
    print(base["equity"].tail())
    print(base["diagnostics"]["turnover"])
