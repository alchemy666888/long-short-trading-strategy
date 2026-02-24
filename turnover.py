from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd


def apply_turnover_controls(
    current_weights: pd.Series,
    target_weights: pd.Series,
    no_trade_band: float,
    turnover_cap: float,
    partial_step_min: float,
    partial_step_max: float,
) -> Tuple[pd.Series, Dict[str, float]]:
    current = current_weights.reindex(target_weights.index).fillna(0.0)
    target = target_weights.fillna(0.0)

    raw_delta = target - current
    raw_turnover = float(raw_delta.abs().sum())

    delta_after_band = raw_delta.copy()
    delta_after_band[delta_after_band.abs() < no_trade_band] = 0.0
    turnover_after_band = float(delta_after_band.abs().sum())

    if turnover_after_band <= 0.0:
        return current.copy(), {
            "raw_turnover": raw_turnover,
            "turnover_after_band": turnover_after_band,
            "throttled_turnover": 0.0,
            "step": 0.0,
        }

    if turnover_cap <= 0:
        step = partial_step_min
    else:
        pressure = turnover_after_band / turnover_cap
        if pressure <= 1.0:
            step = partial_step_max
        else:
            step = 1.0 / pressure
            step = max(partial_step_min, min(partial_step_max, step))

    controlled = current + (delta_after_band * step)
    throttled_turnover = float((controlled - current).abs().sum())

    return controlled, {
        "raw_turnover": raw_turnover,
        "turnover_after_band": turnover_after_band,
        "throttled_turnover": throttled_turnover,
        "step": float(step),
    }
