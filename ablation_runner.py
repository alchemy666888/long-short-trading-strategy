from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict

import numpy as np
import pandas as pd

from backtest_vectorized import run_backtest


BARS_PER_YEAR = 252


@dataclass
class AblationSummary:
    total_return_pct: float
    annualized_return_pct: float
    annualized_volatility_pct: float
    sharpe: float
    max_drawdown_pct: float


def _summary(equity: pd.Series) -> AblationSummary:
    equity = equity.dropna()
    daily_returns = equity.pct_change(fill_method=None).dropna()

    if equity.empty:
        return AblationSummary(np.nan, np.nan, np.nan, np.nan, np.nan)

    total_return = (equity.iloc[-1] / equity.iloc[0]) - 1.0
    ann_return = (1.0 + total_return) ** (BARS_PER_YEAR / max(len(daily_returns), 1)) - 1.0
    ann_vol = daily_returns.std() * np.sqrt(BARS_PER_YEAR) if len(daily_returns) > 1 else np.nan
    sharpe = ann_return / ann_vol if ann_vol and not np.isnan(ann_vol) else np.nan

    running_max = equity.cummax()
    drawdown = (equity / running_max) - 1.0

    return AblationSummary(
        total_return_pct=float(total_return * 100.0),
        annualized_return_pct=float(ann_return * 100.0) if not np.isnan(ann_return) else np.nan,
        annualized_volatility_pct=float(ann_vol * 100.0) if not np.isnan(ann_vol) else np.nan,
        sharpe=float(sharpe) if not np.isnan(sharpe) else np.nan,
        max_drawdown_pct=float(drawdown.min() * 100.0),
    )


def run_ablation_suite(seed: int = 7) -> Dict:
    configs = {
        "v5": {"strategy_version": "v5", "analysis_ablation": None},
        "v6_full": {"strategy_version": "v6", "analysis_ablation": None},
        "v6_no_macro": {"strategy_version": "v6", "analysis_ablation": "no_macro"},
        "v6_no_flow": {"strategy_version": "v6", "analysis_ablation": "no_flow"},
        "v6_no_asset": {"strategy_version": "v6", "analysis_ablation": "no_asset"},
        "v6_no_quality": {"strategy_version": "v6", "analysis_ablation": "no_quality"},
    }

    results = {}
    summaries: Dict[str, AblationSummary] = {}
    for name, cfg in configs.items():
        res = run_backtest(
            cost_multiplier=1.0,
            one_day_delay=False,
            missing_data_ratio=0.0,
            liquidity_haircut=1.0,
            short_borrow_bps_per_day=0.0,
            seed=seed,
            strategy_version=cfg["strategy_version"],
            analysis_ablation=cfg["analysis_ablation"],
            persist_analysis_artifacts=False,
        )
        results[name] = res
        summaries[name] = _summary(res["equity"])

    v5 = summaries["v5"]
    deltas_vs_v5 = {}
    for name, summary in summaries.items():
        deltas_vs_v5[name] = {
            "sharpe_delta": float(summary.sharpe - v5.sharpe) if not np.isnan(summary.sharpe) and not np.isnan(v5.sharpe) else np.nan,
            "total_return_delta_pct": float(summary.total_return_pct - v5.total_return_pct)
            if not np.isnan(summary.total_return_pct) and not np.isnan(v5.total_return_pct)
            else np.nan,
            "max_drawdown_delta_pct": float(summary.max_drawdown_pct - v5.max_drawdown_pct)
            if not np.isnan(summary.max_drawdown_pct) and not np.isnan(v5.max_drawdown_pct)
            else np.nan,
        }

    return {
        "summaries": {name: asdict(summary) for name, summary in summaries.items()},
        "deltas_vs_v5": deltas_vs_v5,
    }
