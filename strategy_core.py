from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from long_short_config import REBALANCE_TIMES


LOOKBACK = 36
ENTRY_Z = 2.0
STOP_Z = 3.5


@dataclass
class PositionTarget:
    asset: str
    side: int  # +1 long, -1 short
    notional: float


def compute_zscores(closes: pd.DataFrame) -> pd.DataFrame:
    rolling_mean = closes.rolling(LOOKBACK, min_periods=LOOKBACK).mean()
    rolling_std = closes.rolling(LOOKBACK, min_periods=LOOKBACK).std()
    z = (closes - rolling_mean) / rolling_std
    z = z.replace([np.inf, -np.inf], np.nan)
    return z


def compute_volatility(closes: pd.DataFrame) -> pd.DataFrame:
    returns = closes.pct_change()
    vol = returns.rolling(LOOKBACK, min_periods=LOOKBACK).std()
    return vol


def select_long_short_candidates(
    zscores: pd.Series,
    max_per_side: int = 3,
) -> Tuple[List[str], List[str]]:
    longs = zscores[zscores < -ENTRY_Z].sort_values(ascending=True)
    shorts = zscores[zscores > ENTRY_Z].sort_values(ascending=False)

    n = min(len(longs), len(shorts), max_per_side)
    if n <= 0:
        return [], []

    long_list = longs.head(n).index.tolist()
    short_list = shorts.head(n).index.tolist()
    return long_list, short_list


def compute_equal_risk_targets(
    timestamp: pd.Timestamp,
    closes: pd.DataFrame,
    volatility: pd.DataFrame,
    capital: float,
    risk_budget_fraction: float = 0.01,
) -> Dict[pd.Timestamp, List[PositionTarget]]:
    """
    Pre-compute portfolio targets at each rebalance timestamp.

    Returns:
        dict mapping rebalance timestamp to list of PositionTarget.
    """
    targets: Dict[pd.Timestamp, List[PositionTarget]] = {}

    for ts, row in closes.iterrows():
        if ts.strftime("%H:%M") not in REBALANCE_TIMES:
            continue

        z_row = compute_zscores(closes.loc[:ts]).iloc[-1]
        vol_row = volatility.loc[ts]
        long_assets, short_assets = select_long_short_candidates(z_row)
        if not long_assets or not short_assets:
            continue

        assets = long_assets + short_assets
        vol_values = vol_row[assets].replace(0, np.nan).dropna()
        if vol_values.empty:
            continue

        total_risk_budget = capital * risk_budget_fraction
        per_position_risk = total_risk_budget / (2 * len(long_assets)) if long_assets else 0

        current_close = closes.loc[ts, assets]
        ts_targets: List[PositionTarget] = []

        for asset in long_assets:
            sigma = vol_row[asset]
            if sigma <= 0 or np.isnan(sigma):
                continue
            price = current_close[asset]
            if price <= 0 or np.isnan(price):
                continue
            notional = per_position_risk / sigma if sigma > 0 else 0
            ts_targets.append(PositionTarget(asset=asset, side=1, notional=notional))

        for asset in short_assets:
            sigma = vol_row[asset]
            if sigma <= 0 or np.isnan(sigma):
                continue
            price = current_close[asset]
            if price <= 0 or np.isnan(price):
                continue
            notional = per_position_risk / sigma if sigma > 0 else 0
            ts_targets.append(PositionTarget(asset=asset, side=-1, notional=notional))

        if ts_targets:
            targets[ts] = ts_targets

    return targets
