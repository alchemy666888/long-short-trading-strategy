from __future__ import annotations

from typing import Dict, Iterable, Mapping, Optional

import numpy as np
import pandas as pd

from long_short_config import (
    SCORE_CLIP,
    V6_CONFLICT_CAP_MULTIPLIER,
    V6_CONFLICT_CATALYST_THRESHOLD,
    V6_OVERLAY_WEIGHTS,
    V6_RELIABILITY_SCALE_FLOOR,
)


def _clip_series(series: pd.Series, low: float, high: float, fill_value: float = 0.0) -> pd.Series:
    return series.fillna(fill_value).clip(lower=low, upper=high)


def build_overlay_frames(
    reports_by_day: Mapping[pd.Timestamp, Dict],
    assets: Iterable[str],
    asset_class_by_asset: Mapping[str, str],
) -> Dict[str, object]:
    day_index = pd.DatetimeIndex(sorted(reports_by_day.keys()))
    asset_list = list(assets)
    class_list = sorted({asset_class_by_asset[a] for a in asset_list})

    macro_overlay = pd.Series(0.0, index=day_index, dtype=float)
    scenario_conf = pd.Series(0.0, index=day_index, dtype=float)
    reliability = pd.Series(0.0, index=day_index, dtype=float)
    report_valid = pd.Series(False, index=day_index, dtype=bool)
    event_risk_multiplier = pd.Series(1.0, index=day_index, dtype=float)

    flow_overlay = pd.DataFrame(0.0, index=day_index, columns=class_list, dtype=float)
    asset_overlay = pd.DataFrame(0.0, index=day_index, columns=asset_list, dtype=float)

    theme_by_day: Dict[pd.Timestamp, Dict[str, str]] = {}

    for day in day_index:
        report = reports_by_day[day]
        quality = report.get("quality", {})

        macro_overlay.at[day] = float(report.get("macro_regime_overlay", 0.0))
        scenario_conf.at[day] = float(report.get("scenario_confidence", 0.0))
        reliability.at[day] = float(quality.get("q_t", 0.0))
        report_valid.at[day] = bool(quality.get("report_valid", False))
        event_risk_multiplier.at[day] = float(report.get("event_risk_multiplier", 1.0))

        class_scores = report.get("class_flow_overlay", {})
        for cls in class_list:
            flow_overlay.at[day, cls] = float(class_scores.get(cls, 0.0))

        asset_scores = report.get("asset_catalyst_scores", {})
        for asset in asset_list:
            asset_overlay.at[day, asset] = float(asset_scores.get(asset, 0.0))

        theme_by_day[day] = {
            str(asset): str(theme)
            for asset, theme in report.get("theme_by_asset", {}).items()
            if asset in asset_list
        }

    overlays = {
        "macro_overlay": _clip_series(macro_overlay, -1.0, 1.0),
        "flow_overlay": flow_overlay.clip(lower=-1.0, upper=1.0),
        "asset_overlay": asset_overlay.clip(lower=-1.0, upper=1.0),
        "scenario_confidence": _clip_series(scenario_conf, 0.0, 1.0),
        "reliability": _clip_series(reliability, 0.0, 1.0),
        "report_valid": report_valid.fillna(False),
        "event_risk_multiplier": _clip_series(event_risk_multiplier, 0.0, 1.0, fill_value=1.0),
        "theme_by_day": theme_by_day,
    }
    return overlays


def apply_overlay_ablation(overlays: Dict[str, object], mode: Optional[str]) -> Dict[str, object]:
    if not mode:
        return overlays

    mode = mode.lower()
    out = {
        key: (value.copy() if hasattr(value, "copy") else value)
        for key, value in overlays.items()
    }

    if mode == "no_macro":
        out["macro_overlay"] = pd.Series(0.0, index=out["macro_overlay"].index, dtype=float)
    elif mode == "no_flow":
        out["flow_overlay"] = pd.DataFrame(
            0.0,
            index=out["flow_overlay"].index,
            columns=out["flow_overlay"].columns,
            dtype=float,
        )
    elif mode == "no_asset":
        out["asset_overlay"] = pd.DataFrame(
            0.0,
            index=out["asset_overlay"].index,
            columns=out["asset_overlay"].columns,
            dtype=float,
        )
    elif mode == "no_quality":
        out["reliability"] = pd.Series(1.0, index=out["reliability"].index, dtype=float)
        out["report_valid"] = pd.Series(True, index=out["report_valid"].index, dtype=bool)
    else:
        raise ValueError(f"Unsupported analysis ablation mode: {mode}")

    return out


def compute_v6_scores(
    base_scores: pd.DataFrame,
    overlays: Dict[str, object],
    asset_class_by_asset: Mapping[str, str],
    beta_by_asset: Mapping[str, float],
) -> pd.DataFrame:
    score = base_scores.copy().astype(float)

    macro_overlay: pd.Series = overlays["macro_overlay"].reindex(score.index).fillna(0.0)
    flow_overlay: pd.DataFrame = overlays["flow_overlay"].reindex(score.index).fillna(0.0)
    asset_overlay: pd.DataFrame = overlays["asset_overlay"].reindex(index=score.index, columns=score.columns).fillna(0.0)
    reliability: pd.Series = overlays["reliability"].reindex(score.index).fillna(0.0)

    result = pd.DataFrame(index=score.index, columns=score.columns, dtype=float)

    for asset in score.columns:
        asset_class = asset_class_by_asset.get(asset, "unknown")
        beta = float(beta_by_asset.get(asset, 1.0))

        class_term = flow_overlay.get(asset_class, pd.Series(0.0, index=score.index))
        asset_term = asset_overlay[asset]

        multiplier = (
            1.0
            + (V6_OVERLAY_WEIGHTS["asset_catalyst"] * asset_term)
            + (V6_OVERLAY_WEIGHTS["cross_asset_flow"] * class_term)
            + (V6_OVERLAY_WEIGHTS["macro_regime_beta"] * beta * macro_overlay)
        )
        reliability_scale = V6_RELIABILITY_SCALE_FLOOR + ((1.0 - V6_RELIABILITY_SCALE_FLOOR) * reliability)

        result[asset] = (score[asset] * multiplier * reliability_scale).clip(lower=-SCORE_CLIP, upper=SCORE_CLIP)

    return result


def compute_conflict_multipliers(
    base_scores: pd.DataFrame,
    asset_overlay: pd.DataFrame,
    threshold: float = V6_CONFLICT_CATALYST_THRESHOLD,
    cap_multiplier: float = V6_CONFLICT_CAP_MULTIPLIER,
) -> pd.DataFrame:
    base = base_scores.reindex_like(asset_overlay)
    overlay = asset_overlay.reindex_like(base).fillna(0.0)

    opposite_sign = (np.sign(base) * np.sign(overlay)) < 0
    strong_overlay = overlay.abs() >= threshold
    veto = opposite_sign & strong_overlay

    multipliers = pd.DataFrame(1.0, index=base.index, columns=base.columns, dtype=float)
    multipliers[veto] = float(cap_multiplier)
    return multipliers


def overlay_summary_table(overlays: Dict[str, object], asset_class: str | None = None) -> pd.DataFrame:
    flow_overlay: pd.DataFrame = overlays["flow_overlay"]

    if asset_class is None:
        flow_series = flow_overlay.mean(axis=1)
    else:
        flow_series = flow_overlay.get(asset_class, pd.Series(0.0, index=flow_overlay.index))

    summary = pd.DataFrame(
        {
            "M_t": overlays["macro_overlay"],
            "F_t": flow_series,
            "C_t": overlays["scenario_confidence"],
            "Q_t": overlays["reliability"],
            "REPORT_VALID": overlays["report_valid"].astype(bool),
            "event_risk_multiplier": overlays["event_risk_multiplier"],
        }
    )
    return summary.sort_index()
