from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from long_short_config import (
    ASSETS,
    CATEGORY_GROSS_CAP,
    GROSS_LEVERAGE_FLOOR,
    NAME_WEIGHT_CAP,
    PORTFOLIO_DOLLAR_NEUTRAL_TOL,
    SCORE_CLIP,
    V5_DAILY_WINDOWS,
)

ASSET_CLASS_BY_ASSET: Dict[str, str] = {
    asset: str(meta.get("asset_class", "unknown")) for asset, meta in ASSETS.items()
}
CLASS_MEMBERS: Dict[str, List[str]] = defaultdict(list)
for _asset, _asset_class in ASSET_CLASS_BY_ASSET.items():
    CLASS_MEMBERS[_asset_class].append(_asset)


def get_asset_class(asset: str) -> str:
    return ASSET_CLASS_BY_ASSET.get(asset, "unknown")


def cross_sectional_zscores(frame: pd.DataFrame) -> pd.DataFrame:
    mean = frame.mean(axis=1)
    std = frame.std(axis=1).replace(0.0, np.nan)
    return frame.sub(mean, axis=0).div(std, axis=0)


def compute_atr(
    highs: pd.DataFrame,
    lows: pd.DataFrame,
    closes: pd.DataFrame,
    lookback: int,
) -> pd.DataFrame:
    prev_close = closes.shift(1)
    tr1 = highs - lows
    tr2 = (highs - prev_close).abs()
    tr3 = (lows - prev_close).abs()
    tr = pd.DataFrame(
        np.maximum.reduce([tr1.values, tr2.values, tr3.values]),
        index=closes.index,
        columns=closes.columns,
    )
    return tr.rolling(lookback, min_periods=lookback).mean()


def compute_v5_daily_stack(closes_1d: pd.DataFrame, weekly_score_daily: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    log_price = np.log(closes_1d.where(closes_1d > 0.0))

    ret20 = log_price - log_price.shift(V5_DAILY_WINDOWS["ret_20d"])
    ret60 = log_price - log_price.shift(V5_DAILY_WINDOWS["ret_60d"])
    ret120 = log_price - log_price.shift(V5_DAILY_WINDOWS["ret_120d"])
    ret5 = log_price - log_price.shift(V5_DAILY_WINDOWS["ret_5d"])

    z20 = cross_sectional_zscores(ret20)
    z60 = cross_sectional_zscores(ret60)
    z120 = cross_sectional_zscores(ret120)
    z5 = cross_sectional_zscores(ret5)

    trend = (0.50 * z20) + (0.30 * z60) + (0.20 * z120)
    reversal = -z5
    s_raw = (0.75 * trend) + (0.25 * reversal)

    align_factor = 1.0 + (0.25 * np.sign(s_raw) * np.sign(weekly_score_daily.reindex_like(s_raw)))
    s_align = s_raw * align_factor

    returns = closes_1d.pct_change(fill_method=None)
    ewma_vol_20 = returns.ewm(halflife=20, min_periods=20).std().replace(0.0, np.nan)

    score = s_align.div(ewma_vol_20.clip(lower=1e-4)).clip(lower=-SCORE_CLIP, upper=SCORE_CLIP)

    return {
        "trend": trend,
        "reversal": reversal,
        "s_raw": s_raw,
        "s_align": s_align,
        "score": score.replace([np.inf, -np.inf], np.nan),
        "vol": ewma_vol_20,
        "returns": returns,
    }


def compute_shrunk_covariance(return_window: pd.DataFrame, shrink: float = 0.30) -> pd.DataFrame:
    if return_window.empty:
        return pd.DataFrame()

    cov = return_window.cov(min_periods=max(20, len(return_window) // 4))
    if cov.empty:
        return cov

    diag = np.diag(np.diag(cov.fillna(0.0).values))
    shrunk = ((1.0 - shrink) * cov.fillna(0.0).values) + (shrink * diag)
    return pd.DataFrame(shrunk, index=cov.index, columns=cov.columns)


def _apply_category_caps(weights: pd.Series, category_cap: float) -> pd.Series:
    adjusted = weights.copy()
    cat_gross: Dict[str, float] = defaultdict(float)
    for asset, w in adjusted.items():
        cat_gross[get_asset_class(asset)] += abs(float(w))

    for category, gross in cat_gross.items():
        if gross <= category_cap or gross <= 0:
            continue
        scale = category_cap / gross
        for asset in adjusted.index:
            if get_asset_class(asset) == category:
                adjusted.at[asset] *= scale

    return adjusted


def enforce_weight_constraints(
    weights: pd.Series,
    gross_cap: float,
) -> pd.Series:
    w = weights.copy().fillna(0.0)

    # Hard single-name cap
    w = w.clip(lower=-NAME_WEIGHT_CAP, upper=NAME_WEIGHT_CAP)

    # Category cap
    w = _apply_category_caps(w, CATEGORY_GROSS_CAP)

    long_mask = w > 0
    short_mask = w < 0
    long_sum = float(w[long_mask].sum())
    short_sum = float((-w[short_mask]).sum())

    target_gross = max(0.0, gross_cap)
    if long_sum > 0:
        w.loc[long_mask] *= (0.5 * target_gross) / long_sum
    if short_sum > 0:
        w.loc[short_mask] *= (0.5 * target_gross) / short_sum

    net = float(w.sum())
    if abs(net) > PORTFOLIO_DOLLAR_NEUTRAL_TOL:
        if net > 0 and w[w > 0].sum() > 0:
            w.loc[w > 0] *= max(0.0, (w[w > 0].sum() - (net - PORTFOLIO_DOLLAR_NEUTRAL_TOL)) / w[w > 0].sum())
        elif net < 0 and (-w[w < 0].sum()) > 0:
            short_sum_now = -w[w < 0].sum()
            adjust = abs(net) - PORTFOLIO_DOLLAR_NEUTRAL_TOL
            w.loc[w < 0] *= max(0.0, (short_sum_now - adjust) / short_sum_now)

    gross = float(w.abs().sum())
    if gross > max(target_gross, 1e-8):
        w *= target_gross / gross

    # Keep minimum gross only when any risk is active.
    if target_gross >= GROSS_LEVERAGE_FLOOR and gross > 0 and gross < GROSS_LEVERAGE_FLOOR:
        w *= GROSS_LEVERAGE_FLOOR / gross

    return w.fillna(0.0)


def build_daily_target_weights(
    score_row: pd.Series,
    vol_row: pd.Series,
    prev_weights: pd.Series,
    cov_matrix: pd.DataFrame,
    gross_cap: float,
    side_tilt: float,
    min_per_side: int = 4,
) -> Tuple[pd.Series, Dict[str, float]]:
    idx = score_row.index
    prev = prev_weights.reindex(idx).fillna(0.0)

    score = score_row.copy().astype(float)
    vol = vol_row.reindex(idx).astype(float)

    valid = score.notna() & vol.notna() & (vol > 0)
    if valid.sum() < max(8, 2 * min_per_side):
        return pd.Series(0.0, index=idx), {
            "active_assets": 0,
            "active_categories": 0,
            "max_category_share": 1.0,
            "reason": "insufficient_valid_assets",
        }

    score = score[valid]
    vol = vol[valid]

    # Side aggressiveness via score scaling, while maintaining near-dollar-neutral budgets.
    tilt = float(np.clip(side_tilt, -0.20, 0.20))
    score_adj = score.copy()
    score_adj.loc[score_adj > 0] *= (1.0 + max(0.0, tilt))
    score_adj.loc[score_adj < 0] *= (1.0 + max(0.0, -tilt))

    if not cov_matrix.empty:
        cov = cov_matrix.reindex(index=score_adj.index, columns=score_adj.index).fillna(0.0)
        risk_load = cov.dot(prev.reindex(score_adj.index).fillna(0.0))
        score_adj = score_adj - (0.15 * risk_load)

    q70 = float(score_adj.quantile(0.70))
    q30 = float(score_adj.quantile(0.30))

    longs = score_adj[score_adj >= q70].sort_values(ascending=False)
    shorts = score_adj[score_adj <= q30].sort_values(ascending=True)

    if len(longs) < min_per_side or len(shorts) < min_per_side:
        return pd.Series(0.0, index=idx), {
            "active_assets": 0,
            "active_categories": 0,
            "max_category_share": 1.0,
            "reason": "insufficient_candidates",
        }

    long_raw = (longs / vol.reindex(longs.index)).clip(lower=0.0)
    short_raw = ((-shorts) / vol.reindex(shorts.index)).clip(lower=0.0)

    if long_raw.sum() <= 0 or short_raw.sum() <= 0:
        return pd.Series(0.0, index=idx), {
            "active_assets": 0,
            "active_categories": 0,
            "max_category_share": 1.0,
            "reason": "invalid_raw_weights",
        }

    raw_weights = pd.Series(0.0, index=idx)
    raw_weights.loc[long_raw.index] = long_raw / long_raw.sum()
    raw_weights.loc[short_raw.index] = -(short_raw / short_raw.sum())

    target = enforce_weight_constraints(raw_weights, gross_cap=max(gross_cap, 0.0))

    active = target[target.abs() > 1e-8]
    class_gross: Dict[str, float] = defaultdict(float)
    for asset, w in active.items():
        class_gross[get_asset_class(asset)] += abs(float(w))

    active_assets = int(len(active))
    active_categories = int(len(class_gross))
    max_cat_share = float(max(class_gross.values()) / max(active.abs().sum(), 1e-8)) if class_gross else 1.0

    return target, {
        "active_assets": active_assets,
        "active_categories": active_categories,
        "max_category_share": max_cat_share,
        "reason": "ok",
    }
