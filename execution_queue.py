from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from long_short_config import (
    EXEC_MAX_DEFERS,
    EXEC_QUALITY_FULL_THRESHOLD,
    EXEC_QUALITY_HALF_THRESHOLD,
    EXEC_WINDOWS_PER_DAY,
    NET_EDGE_COST_MULTIPLE,
)


SLIPPAGE_BPS_BY_BUCKET = {
    "high": 1.0,
    "medium": 3.0,
    "low": 6.0,
}


def build_execution_features(closes_4h: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    ema20 = closes_4h.ewm(span=20, min_periods=20).mean()
    ema50 = closes_4h.ewm(span=50, min_periods=50).mean()
    ret1 = closes_4h.pct_change(fill_method=None)
    return {"ema20": ema20, "ema50": ema50, "ret1": ret1}


def _quality_bucket(quality: float) -> str:
    if quality >= EXEC_QUALITY_FULL_THRESHOLD:
        return "high"
    if quality >= EXEC_QUALITY_HALF_THRESHOLD:
        return "medium"
    return "low"


def _quality_score(side: float, price: float, ema20: float, ema50: float, ret1: float) -> float:
    if np.isnan(price) or np.isnan(ema20) or np.isnan(ema50):
        return 0.0

    if side >= 0:
        trend_score = 1.0 if ema20 > ema50 else 0.0
    else:
        trend_score = 1.0 if ema20 < ema50 else 0.0

    pullback = 1.0 - min(1.0, abs((price - ema20) / max(abs(ema20), 1e-8)) * 25.0)
    liquidity = 1.0 - min(1.0, abs(ret1) * 30.0) if not np.isnan(ret1) else 0.0

    quality = (0.5 * trend_score) + (0.3 * pullback) + (0.2 * liquidity)
    return float(np.clip(quality, 0.0, 1.0))


def _execution_windows(closes_4h: pd.DataFrame, exec_day: pd.Timestamp) -> pd.DatetimeIndex:
    day_mask = closes_4h.index.normalize() == exec_day.normalize()
    bars = closes_4h.index[day_mask]
    return bars[:EXEC_WINDOWS_PER_DAY]


def execute_order_slice(
    order_deltas: pd.Series,
    exec_day: pd.Timestamp,
    closes_4h: pd.DataFrame,
    features_4h: Dict[str, pd.DataFrame],
    score_row: pd.Series,
    cost_bps_by_asset: Dict[str, float],
    liquidity_haircut: float = 1.0,
) -> Tuple[pd.Series, Dict, List[Dict]]:
    bars = _execution_windows(closes_4h, exec_day)
    filled = pd.Series(0.0, index=order_deltas.index)

    stats = {
        "executed": 0,
        "deferred": 0,
        "canceled": 0,
        "bucket_counts": {"high": 0, "medium": 0, "low": 0},
        "slippage_bps": {"high": [], "medium": [], "low": []},
        "reasons": defaultdict(int),
    }
    logs: List[Dict] = []

    for asset, delta in order_deltas.items():
        if np.isnan(delta) or abs(delta) <= 0:
            continue

        expected_edge = float(abs(score_row.get(asset, np.nan)))
        round_trip_cost = 2.0 * float(cost_bps_by_asset.get(asset, 0.0)) / 10000.0

        if np.isnan(expected_edge) or expected_edge <= (NET_EDGE_COST_MULTIPLE * round_trip_cost):
            stats["canceled"] += 1
            stats["reasons"]["net_edge"] += 1
            logs.append(
                {
                    "asset": asset,
                    "decision": "cancel",
                    "reason": "net_edge",
                    "requested_delta": float(delta),
                    "filled_delta": 0.0,
                    "quality": None,
                }
            )
            continue

        if len(bars) == 0:
            stats["canceled"] += 1
            stats["reasons"]["no_4h_window"] += 1
            logs.append(
                {
                    "asset": asset,
                    "decision": "cancel",
                    "reason": "no_4h_window",
                    "requested_delta": float(delta),
                    "filled_delta": 0.0,
                    "quality": None,
                }
            )
            continue

        remaining = float(delta)
        defers = 0
        chosen_quality = None

        for bar in bars:
            px = closes_4h.at[bar, asset] if asset in closes_4h.columns else np.nan
            ema20 = features_4h["ema20"].at[bar, asset] if asset in features_4h["ema20"].columns else np.nan
            ema50 = features_4h["ema50"].at[bar, asset] if asset in features_4h["ema50"].columns else np.nan
            ret1 = features_4h["ret1"].at[bar, asset] if asset in features_4h["ret1"].columns else np.nan

            quality = _quality_score(np.sign(delta), px, ema20, ema50, ret1)
            bucket = _quality_bucket(quality)

            chosen_quality = quality
            stats["bucket_counts"][bucket] += 1
            stats["slippage_bps"][bucket].append(SLIPPAGE_BPS_BY_BUCKET[bucket])

            if bucket == "high":
                fill_ratio = 1.0
            elif bucket == "medium":
                fill_ratio = 0.5
            else:
                fill_ratio = 0.0

            fill_ratio = max(0.0, min(1.0, fill_ratio * liquidity_haircut))

            if fill_ratio <= 0.0:
                defers += 1
                if defers >= EXEC_MAX_DEFERS:
                    break
                continue

            fill = remaining * fill_ratio
            filled.at[asset] += fill
            remaining -= fill

            if abs(remaining) <= 1e-6:
                break

        filled_amt = float(filled.at[asset])
        if abs(filled_amt) > 1e-6 and abs(remaining) <= 1e-6:
            stats["executed"] += 1
            decision = "execute"
            reason = "filled"
        elif abs(filled_amt) > 1e-6:
            stats["deferred"] += 1
            stats["reasons"]["partial_fill"] += 1
            decision = "defer"
            reason = "partial_fill"
        else:
            stats["canceled"] += 1
            stats["reasons"]["quality_reject"] += 1
            decision = "cancel"
            reason = "quality_reject"

        logs.append(
            {
                "asset": asset,
                "decision": decision,
                "reason": reason,
                "requested_delta": float(delta),
                "filled_delta": filled_amt,
                "quality": None if chosen_quality is None else round(float(chosen_quality), 4),
            }
        )

    return filled, stats, logs
