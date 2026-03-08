from __future__ import annotations

from typing import Dict, Iterable, Mapping

import numpy as np
import pandas as pd

from long_short_config import NET_EDGE_COST_MULTIPLE, V6_IDEA_MIN_ABS_SIGNAL, V6_IDEA_SCORE_WEIGHTS


def build_daily_idea_table(
    ts: pd.Timestamp,
    assets: Iterable[str],
    scores_row: pd.Series,
    asset_overlay_row: pd.Series,
    scenario_confidence: float,
    reliability: float,
    report_valid: bool,
    cost_bps_by_asset: Mapping[str, float],
    theme_by_asset: Mapping[str, str],
    min_abs_signal: float = V6_IDEA_MIN_ABS_SIGNAL,
    net_edge_multiple: float = NET_EDGE_COST_MULTIPLE,
) -> pd.DataFrame:
    rows = []

    for asset in assets:
        s = float(scores_row.get(asset, np.nan))
        a = float(asset_overlay_row.get(asset, 0.0))

        abs_signal = 0.0 if np.isnan(s) else abs(s)
        round_trip_cost = (2.0 * float(cost_bps_by_asset.get(asset, 0.0))) / 10000.0
        edge_ratio = abs_signal / max(round_trip_cost, 1e-8)

        gate_reasons = []
        quant_gate_pass = True

        if not report_valid:
            quant_gate_pass = False
            gate_reasons.append("report_invalid")
        if abs_signal < min_abs_signal:
            quant_gate_pass = False
            gate_reasons.append("weak_signal")
        if edge_ratio <= net_edge_multiple:
            quant_gate_pass = False
            gate_reasons.append("insufficient_net_edge")

        idea_score = (
            (V6_IDEA_SCORE_WEIGHTS["signal"] * abs_signal)
            + (V6_IDEA_SCORE_WEIGHTS["asset_catalyst"] * abs(a))
            + (V6_IDEA_SCORE_WEIGHTS["scenario_confidence"] * scenario_confidence)
            + (V6_IDEA_SCORE_WEIGHTS["report_reliability"] * reliability)
        )

        rows.append(
            {
                "timestamp": ts,
                "asset": asset,
                "theme": str(theme_by_asset.get(asset, "unassigned")),
                "direction": "long" if s > 0 else ("short" if s < 0 else "flat"),
                "signal": s,
                "asset_catalyst": a,
                "scenario_confidence": float(scenario_confidence),
                "report_reliability": float(reliability),
                "idea_score": float(idea_score),
                "edge_ratio": float(edge_ratio),
                "quant_gate_pass": bool(quant_gate_pass),
                "gate_reasons": gate_reasons,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["idea_score", "asset"], ascending=[False, True])


def enforce_theme_concentration_cap(
    weights: pd.Series,
    theme_by_asset: Mapping[str, str],
    max_theme_share: float,
) -> pd.Series:
    w = weights.copy().astype(float)
    gross = float(w.abs().sum())
    if gross <= 0.0:
        return w

    theme_gross: Dict[str, float] = {}
    for asset, val in w.items():
        if abs(float(val)) <= 1e-10:
            continue
        theme = str(theme_by_asset.get(asset, "unassigned"))
        theme_gross[theme] = theme_gross.get(theme, 0.0) + abs(float(val))

    cap = max_theme_share * gross
    for theme, tg in theme_gross.items():
        if tg <= cap or tg <= 0.0:
            continue

        scale = cap / tg
        for asset in w.index:
            if str(theme_by_asset.get(asset, "unassigned")) == theme:
                w.at[asset] = float(w.at[asset]) * scale

    return w
