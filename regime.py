from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from long_short_config import (
    MARKET_PROXY_ASSET,
    PANIC_RETURN_LOOKBACK_DAYS,
    PANIC_VOL_Z_THRESHOLD,
    REGIME_GROSS_CAP_BY_STATE,
    REGIME_RISK_OFF_THRESHOLD,
    REGIME_RISK_ON_THRESHOLD,
    REGIME_SIDE_TILT_BY_STATE,
    V5_WEEKLY_WINDOWS,
)


def _cross_sectional_zscores(frame: pd.DataFrame) -> pd.DataFrame:
    mean = frame.mean(axis=1)
    std = frame.std(axis=1).replace(0.0, np.nan)
    return frame.sub(mean, axis=0).div(std, axis=0)


def compute_weekly_score(closes_1d: pd.DataFrame) -> pd.DataFrame:
    weekly_close = closes_1d.resample("W-FRI").last().dropna(how="all")
    log_price = np.log(weekly_close.where(weekly_close > 0.0))

    weekly_len = len(weekly_close)
    fast_window = min(V5_WEEKLY_WINDOWS["ma_fast"], max(6, weekly_len // 2))
    slow_window = min(V5_WEEKLY_WINDOWS["ma_slow"], max(fast_window + 4, (2 * weekly_len) // 3))

    ret26 = log_price - log_price.shift(V5_WEEKLY_WINDOWS["ret_26w"])
    ret52 = log_price - log_price.shift(V5_WEEKLY_WINDOWS["ret_52w"])

    ma_fast = weekly_close.rolling(fast_window, min_periods=max(4, fast_window // 2)).mean()
    ma_slow = weekly_close.rolling(slow_window, min_periods=max(6, slow_window // 2)).mean()
    trend = (ma_fast / ma_slow) - 1.0

    z26 = _cross_sectional_zscores(ret26)
    z52 = _cross_sectional_zscores(ret52)
    ztrend = _cross_sectional_zscores(trend)

    weighted_sum = (0.45 * z26.fillna(0.0)) + (0.35 * z52.fillna(0.0)) + (0.20 * ztrend.fillna(0.0))
    available_weight = (
        (0.45 * z26.notna().astype(float))
        + (0.35 * z52.notna().astype(float))
        + (0.20 * ztrend.notna().astype(float))
    )
    weekly_score = weighted_sum.div(available_weight.replace(0.0, np.nan))
    return weekly_score.replace([np.inf, -np.inf], np.nan)


def build_regime_context(closes_1d: pd.DataFrame, market_asset: str = MARKET_PROXY_ASSET) -> Tuple[pd.DataFrame, pd.DataFrame]:
    weekly_score = compute_weekly_score(closes_1d)
    daily_weekly_score = weekly_score.reindex(closes_1d.index, method="ffill")

    market_returns = closes_1d.get(market_asset, pd.Series(index=closes_1d.index, dtype=float)).pct_change(fill_method=None)
    market_ret_20d = closes_1d.get(market_asset, pd.Series(index=closes_1d.index, dtype=float)).pct_change(
        PANIC_RETURN_LOOKBACK_DAYS,
        fill_method=None,
    )

    market_vol_20 = market_returns.rolling(20, min_periods=20).std()
    market_vol_mean = market_vol_20.rolling(252, min_periods=60).mean()
    market_vol_std = market_vol_20.rolling(252, min_periods=60).std().replace(0.0, np.nan)
    market_vol_z = (market_vol_20 - market_vol_mean) / market_vol_std

    panic = (market_ret_20d < 0.0) & (market_vol_z > PANIC_VOL_Z_THRESHOLD)

    regime_score = daily_weekly_score.median(axis=1)

    state = pd.Series("NEUTRAL", index=closes_1d.index, dtype="object")
    state.loc[(regime_score > REGIME_RISK_ON_THRESHOLD) & (~panic.fillna(False))] = "RISK_ON"
    state.loc[(regime_score < REGIME_RISK_OFF_THRESHOLD) | panic.fillna(False)] = "RISK_OFF"

    leverage_cap = state.map(REGIME_GROSS_CAP_BY_STATE).astype(float)
    side_tilt = state.map(REGIME_SIDE_TILT_BY_STATE).astype(float)

    regime_df = pd.DataFrame(
        {
            "regime_score": regime_score,
            "state": state,
            "leverage_cap": leverage_cap,
            "side_tilt": side_tilt,
            "panic": panic.fillna(False),
            "market_vol_z": market_vol_z,
            "market_ret_20d": market_ret_20d,
        }
    )

    return regime_df, daily_weekly_score
