from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from long_short_config import (
    ASSETS,
    ENTRY_Z,
    EXIT_Z,
    LOOKBACK,
    MAX_POSITIONS_PER_CLASS_PER_SIDE,
    MAX_POSITIONS_PER_SIDE,
    REGIME_BASELINE_LOOKBACK_BARS,
    REGIME_FILTER_ENABLED,
    REGIME_VOL_LOOKBACK_BARS,
    REGIME_VOL_Z_MAX,
    STOP_Z,
)


ASSET_CLASS_BY_ASSET: Dict[str, str] = {
    asset: str(meta.get("asset_class", "unknown")) for asset, meta in ASSETS.items()
}
CLASS_MEMBERS: Dict[str, List[str]] = defaultdict(list)
for _asset, _asset_class in ASSET_CLASS_BY_ASSET.items():
    CLASS_MEMBERS[_asset_class].append(_asset)


def _rolling_zscore(series: pd.Series, lookback: int) -> pd.Series:
    mean = series.rolling(lookback, min_periods=lookback).mean()
    std = series.rolling(lookback, min_periods=lookback).std()
    z = (series - mean) / std
    return z.replace([np.inf, -np.inf], np.nan)


def _relative_spread_series(closes: pd.DataFrame, asset: str) -> pd.Series:
    log_prices = np.log(closes.where(closes > 0))
    asset_class = ASSET_CLASS_BY_ASSET.get(asset, "unknown")
    peers = [p for p in CLASS_MEMBERS.get(asset_class, []) if p != asset and p in closes.columns]

    if not peers:
        return log_prices[asset]

    # Spread vs class peer basket: robust to absolute price-level differences across assets.
    peer_basket = log_prices[peers].mean(axis=1, skipna=True)
    return log_prices[asset] - peer_basket


def compute_zscores(closes: pd.DataFrame) -> pd.DataFrame:
    zscores = pd.DataFrame(index=closes.index, columns=closes.columns, dtype=float)
    for asset in closes.columns:
        spread = _relative_spread_series(closes=closes, asset=asset)
        zscores[asset] = _rolling_zscore(spread, LOOKBACK)
    return zscores.replace([np.inf, -np.inf], np.nan)


def compute_volatility(closes: pd.DataFrame) -> pd.DataFrame:
    returns = closes.pct_change(fill_method=None)
    vol = returns.rolling(LOOKBACK, min_periods=LOOKBACK).std()
    return vol


def compute_regime_filter(closes: pd.DataFrame) -> pd.Series:
    """
    Return a per-bar boolean gate where True means rebalancing is allowed.

    The gate uses SPY realized volatility z-score vs a trailing baseline.
    If SPY is unavailable, the filter defaults to always-on.
    """
    regime_ok = pd.Series(True, index=closes.index, dtype=bool)
    if not REGIME_FILTER_ENABLED or "SPY" not in closes.columns:
        return regime_ok

    spy_returns = closes["SPY"].pct_change(fill_method=None)
    realized = spy_returns.abs().rolling(
        REGIME_VOL_LOOKBACK_BARS,
        min_periods=REGIME_VOL_LOOKBACK_BARS,
    ).mean()

    baseline_mean = realized.rolling(
        REGIME_BASELINE_LOOKBACK_BARS,
        min_periods=REGIME_BASELINE_LOOKBACK_BARS,
    ).mean()
    baseline_std = realized.rolling(
        REGIME_BASELINE_LOOKBACK_BARS,
        min_periods=REGIME_BASELINE_LOOKBACK_BARS,
    ).std()

    vol_z = (realized - baseline_mean) / baseline_std
    # When baseline is unavailable (NaN), keep trading enabled.
    regime_ok = (vol_z <= REGIME_VOL_Z_MAX) | vol_z.isna()
    return regime_ok.reindex(closes.index, fill_value=True)


def get_asset_class(asset: str) -> str:
    return ASSET_CLASS_BY_ASSET.get(asset, "unknown")


def _pick_diversified(
    candidates: List[str],
    max_per_side: int,
    max_per_class: int,
) -> List[str]:
    selected: List[str] = []
    class_counts: Dict[str, int] = defaultdict(int)

    for asset in candidates:
        asset_class = get_asset_class(asset)
        if class_counts[asset_class] >= max_per_class:
            continue
        selected.append(asset)
        class_counts[asset_class] += 1
        if len(selected) >= max_per_side:
            break

    return selected


def select_long_short_candidates(
    zscores: pd.Series,
    max_per_side: int = MAX_POSITIONS_PER_SIDE,
    max_per_class: int = MAX_POSITIONS_PER_CLASS_PER_SIDE,
    entry_z: float = ENTRY_Z,
) -> Tuple[List[str], List[str]]:
    longs = zscores[zscores < -entry_z].sort_values(ascending=True).index.tolist()
    shorts = zscores[zscores > entry_z].sort_values(ascending=False).index.tolist()

    long_list = _pick_diversified(
        candidates=longs,
        max_per_side=max_per_side,
        max_per_class=max_per_class,
    )
    short_list = _pick_diversified(
        candidates=shorts,
        max_per_side=max_per_side,
        max_per_class=max_per_class,
    )

    n = min(len(long_list), len(short_list), max_per_side)
    if n <= 0:
        return [], []

    return long_list[:n], short_list[:n]
