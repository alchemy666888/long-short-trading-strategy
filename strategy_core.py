from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from long_short_config import ASSETS

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
    std = frame.std(axis=1).replace(0, np.nan)
    return frame.sub(mean, axis=0).div(std, axis=0)


def compute_v3_features(closes: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    log_prices = np.log(closes.where(closes > 0))

    r20 = log_prices - log_prices.shift(20)
    r60 = log_prices - log_prices.shift(60)
    r120 = log_prices - log_prices.shift(120)

    z20 = cross_sectional_zscores(r20)
    z60 = cross_sectional_zscores(r60)
    z120 = cross_sectional_zscores(r120)

    momentum = 0.5 * z20 + 0.3 * z60 + 0.2 * z120

    returns = closes.pct_change(fill_method=None)
    ewma_vol = returns.ewm(halflife=30, min_periods=30).std().replace(0, np.nan)
    m_star = momentum / ewma_vol

    sma36 = closes.rolling(36, min_periods=36).mean()
    sd36 = closes.rolling(36, min_periods=36).std().replace(0, np.nan)
    stretch = (closes - sma36) / sd36

    return m_star.replace([np.inf, -np.inf], np.nan), ewma_vol, stretch


def compute_atr(highs: pd.DataFrame, lows: pd.DataFrame, closes: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    prev_close = closes.shift(1)
    tr1 = highs - lows
    tr2 = (highs - prev_close).abs()
    tr3 = (lows - prev_close).abs()
    true_range = pd.DataFrame(np.maximum.reduce([tr1.values, tr2.values, tr3.values]), index=closes.index, columns=closes.columns)
    return true_range.rolling(lookback, min_periods=lookback).mean()


def rolling_hourly_correlation(closes: pd.DataFrame) -> Dict[pd.Timestamp, pd.DataFrame]:
    hourly_close = closes.resample("1h").last().dropna(how="all")
    hourly_ret = hourly_close.pct_change(fill_method=None)
    corr_by_time: Dict[pd.Timestamp, pd.DataFrame] = {}
    for ts in hourly_ret.index:
        window = hourly_ret.loc[:ts].tail(24 * 60)
        if len(window) < 120:
            continue
        corr = window.corr(min_periods=60)
        if corr.empty:
            continue
        # simple shrinkage
        avg_var = float(np.nanmean(np.diag(window.cov().values))) if len(window.columns) else np.nan
        shrunk = 0.7 * corr + 0.3 * np.eye(len(corr)) * avg_var
        corr_by_time[ts] = pd.DataFrame(shrunk, index=corr.index, columns=corr.columns)
    return corr_by_time


def select_quartile_candidates(scores: pd.Series) -> Tuple[List[str], List[str]]:
    s = scores.dropna().sort_values()
    if len(s) < 4:
        return [], []
    q = max(1, len(s) // 4)
    shorts = s.head(q).index.tolist()
    longs = s.tail(q).sort_values(ascending=False).index.tolist()
    return longs, shorts


def pair_candidates(
    longs: List[str],
    shorts: List[str],
    scores: pd.Series,
    corr: pd.DataFrame | None,
) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    used_shorts = set()

    for long_asset in longs:
        best_choice = None
        best_key = None
        for short_asset in shorts:
            if short_asset in used_shorts:
                continue
            same_category = get_asset_class(long_asset) == get_asset_class(short_asset)
            rho = np.nan
            if corr is not None and long_asset in corr.index and short_asset in corr.columns:
                rho = float(corr.loc[long_asset, short_asset])

            pref_cross = 0 if not same_category else 1
            corr_penalty = 0
            if not np.isnan(rho):
                corr_penalty = 0 if rho < 0.25 else 1
            key = (pref_cross, corr_penalty, rho if not np.isnan(rho) else 999.0, scores.get(short_asset, 0.0))
            if best_key is None or key < best_key:
                best_key = key
                best_choice = short_asset

        if best_choice is not None:
            pairs.append((long_asset, best_choice))
            used_shorts.add(best_choice)

    return pairs


def build_target_weights(pairs: List[Tuple[str, str]], vol: pd.Series, scores: pd.Series) -> Dict[str, float]:
    raw: Dict[str, float] = {}
    for long_asset, short_asset in pairs:
        for asset, side in ((long_asset, 1.0), (short_asset, -1.0)):
            sigma = vol.get(asset, np.nan)
            if pd.isna(sigma) or sigma <= 0:
                continue
            raw[asset] = side / float(sigma)

    if not raw:
        return {}

    gross = sum(abs(v) for v in raw.values())
    weights = {k: v / gross for k, v in raw.items()}

    # dollar neutrality tolerance
    net = sum(weights.values())
    if abs(net) > 0.15:
        long_sum = sum(v for v in weights.values() if v > 0)
        short_sum = -sum(v for v in weights.values() if v < 0)
        if long_sum > 0 and short_sum > 0:
            for k, v in list(weights.items()):
                if v > 0:
                    weights[k] = v / long_sum * 0.5
                else:
                    weights[k] = v / short_sum * 0.5

    # category gross cap 35% with proportional scaling + optional pruning
    cat_gross: Dict[str, float] = defaultdict(float)
    for asset, w in weights.items():
        cat_gross[get_asset_class(asset)] += abs(w)

    for cat, gross_cat in list(cat_gross.items()):
        if gross_cat <= 0.35:
            continue
        scale = 0.35 / gross_cat
        for asset in list(weights.keys()):
            if get_asset_class(asset) == cat:
                weights[asset] *= scale

    gross = sum(abs(v) for v in weights.values())
    if gross <= 0:
        return {}
    weights = {k: v / gross for k, v in weights.items()}

    violating = [a for a, w in weights.items() if abs(w) > 0.35]
    for asset in violating:
        weights[asset] = np.sign(weights[asset]) * 0.35
    gross = sum(abs(v) for v in weights.values())
    weights = {k: v / gross for k, v in weights.items()}

    return weights
