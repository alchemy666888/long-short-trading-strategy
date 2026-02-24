from dataclasses import dataclass
from typing import Dict, List
import warnings

import numpy as np
import pandas as pd

from data_pipeline import load_processed_ohlc
from long_short_config import (
    BACKTEST_END_DATE,
    BACKTEST_START_DATE,
    CAPITAL,
    DEFAULT_TRANSACTION_COST_BPS,
    MAX_GROSS_LEVERAGE,
    REBALANCE_TIMES,
    TRANSACTION_COST_BPS_BY_CLASS,
    TRADING_WINDOW_END,
    TRADING_WINDOW_START,
)
from strategy_core import (
    build_target_weights,
    compute_atr,
    compute_v3_features,
    get_asset_class,
    pair_candidates,
    rolling_hourly_correlation,
    select_quartile_candidates,
)


@dataclass
class Position:
    asset: str
    units: float
    side: int
    entry_price: float
    stop_price: float
    target_price: float
    r_value: float
    pair_asset: str


def _filter_backtest_period(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    start_ts = pd.Timestamp(BACKTEST_START_DATE, tz="US/Eastern")
    end_ts_exclusive = pd.Timestamp(BACKTEST_END_DATE, tz="US/Eastern") + pd.Timedelta(days=1)
    return index[(index >= start_ts) & (index < end_ts_exclusive)]


def _build_session_index() -> pd.DatetimeIndex:
    start_ts = pd.Timestamp(BACKTEST_START_DATE, tz="US/Eastern")
    end_ts_exclusive = pd.Timestamp(BACKTEST_END_DATE, tz="US/Eastern") + pd.Timedelta(days=1)
    full_index = pd.date_range(start=start_ts, end=end_ts_exclusive - pd.Timedelta(minutes=5), freq="5min", tz="US/Eastern")
    full_index = full_index[full_index.dayofweek < 5]
    trading_index = full_index.indexer_between_time(TRADING_WINDOW_START, TRADING_WINDOW_END)
    return full_index[trading_index]


def _cost_bps_for_asset(asset: str, multiplier: float = 1.0) -> float:
    asset_class = get_asset_class(asset)
    return float(TRANSACTION_COST_BPS_BY_CLASS.get(asset_class, DEFAULT_TRANSACTION_COST_BPS)) * multiplier


def run_backtest(cost_multiplier: float = 1.0, one_bar_delay: bool = False) -> pd.DataFrame:
    opens, highs, lows, closes = load_processed_ohlc()

    session_index = _build_session_index()
    session_index = _filter_backtest_period(session_index.sort_values())
    opens = opens.reindex(session_index)
    highs = highs.reindex(session_index)
    lows = lows.reindex(session_index)
    closes = closes.reindex(session_index)

    available_mask = closes.notna().any(axis=1)
    if not available_mask.any():
        raise ValueError("No price observations exist within the configured backtest timeline.")

    actual_start = closes.index[int(np.argmax(available_mask.values))]
    actual_end = closes.index[int(np.where(available_mask.values)[0][-1])]
    if actual_start.date() > pd.Timestamp(BACKTEST_START_DATE).date() or actual_end.date() < pd.Timestamp(BACKTEST_END_DATE).date():
        warnings.warn(f"Effective backtest period constrained by data: {actual_start} to {actual_end}", RuntimeWarning, stacklevel=2)

    m_star, ewma_vol, stretch = compute_v3_features(closes)
    atr = compute_atr(highs=highs, lows=lows, closes=closes, lookback=20)
    corr_by_hour = rolling_hourly_correlation(closes)

    cash = float(CAPITAL)
    positions: Dict[str, Position] = {}
    equity_curve: List[float] = []
    equity_index: List[pd.Timestamp] = []

    for i, ts in enumerate(closes.index):
        price_row_open = opens.loc[ts]
        price_row_close = closes.loc[ts]

        signal_idx = i - (2 if one_bar_delay else 1)
        signal_ts = closes.index[signal_idx] if signal_idx >= 0 else None
        scores = m_star.iloc[signal_idx] if signal_idx >= 0 else None
        vol = ewma_vol.iloc[signal_idx] if signal_idx >= 0 else None
        stretch_signal = stretch.iloc[signal_idx] if signal_idx >= 0 else None
        atr_signal = atr.iloc[signal_idx] if signal_idx >= 0 else None

        # exits first
        if positions:
            rank_scores = scores if scores is not None else pd.Series(dtype=float)
            median_score = rank_scores.median() if len(rank_scores.dropna()) else np.nan
            for asset, pos in list(positions.items()):
                low = lows.loc[ts].get(asset, np.nan)
                high = highs.loc[ts].get(asset, np.nan)
                open_px = price_row_open.get(asset, np.nan)
                close_px = price_row_close.get(asset, np.nan)
                exit_price = np.nan

                if pos.side > 0:
                    if not np.isnan(low) and low <= pos.stop_price:
                        exit_price = pos.stop_price
                    elif not np.isnan(high) and high >= pos.target_price:
                        exit_price = pos.target_price
                else:
                    if not np.isnan(high) and high >= pos.stop_price:
                        exit_price = pos.stop_price
                    elif not np.isnan(low) and low <= pos.target_price:
                        exit_price = pos.target_price

                if np.isnan(exit_price) and asset in rank_scores.index and not np.isnan(median_score):
                    if pos.side > 0 and rank_scores[asset] < median_score:
                        exit_price = open_px
                    if pos.side < 0 and rank_scores[asset] > median_score:
                        exit_price = open_px

                if ts.strftime("%H:%M") == "15:55" and np.isnan(exit_price):
                    exit_price = close_px

                if np.isnan(exit_price) or exit_price <= 0:
                    continue

                notional = abs(pos.units * exit_price)
                cost = notional * (_cost_bps_for_asset(asset, cost_multiplier) / 10000)
                cash += pos.units * exit_price - cost
                del positions[asset]

        should_rebalance = signal_ts is not None and signal_ts.strftime("%H:%M") in REBALANCE_TIMES
        if should_rebalance and scores is not None and vol is not None and atr_signal is not None and stretch_signal is not None:
            longs, shorts = select_quartile_candidates(scores)
            longs = [a for a in longs if stretch_signal.get(a, np.nan) <= 2.5]
            shorts = [a for a in shorts if stretch_signal.get(a, np.nan) >= -2.5]

            hour_key = signal_ts.floor("1h")
            corr = corr_by_hour.get(hour_key)
            pairs = pair_candidates(longs=longs, shorts=shorts, scores=scores, corr=corr)
            weights = build_target_weights(pairs=pairs, vol=vol, scores=scores)

            for asset, weight in weights.items():
                if asset in positions:
                    continue
                px = price_row_open.get(asset, np.nan)
                atr_val = atr_signal.get(asset, np.nan)
                if np.isnan(px) or px <= 0 or np.isnan(atr_val) or atr_val <= 0:
                    continue

                stop_dist = 1.25 * float(atr_val)
                target_dist = 2.25 * float(atr_val)
                expected_edge = abs(scores.get(asset, np.nan))
                roundtrip_cost = 2 * (_cost_bps_for_asset(asset, cost_multiplier) / 10000)
                if np.isnan(expected_edge) or expected_edge <= (roundtrip_cost + 0.02):
                    continue

                alloc_notional = CAPITAL * min(abs(weight), 0.35)
                units = alloc_notional / px
                side = 1 if weight > 0 else -1
                units *= side

                gross_after = sum(abs(p.units * price_row_open.get(a, np.nan)) for a, p in positions.items()) + abs(units * px)
                if gross_after > CAPITAL * MAX_GROSS_LEVERAGE:
                    continue

                entry_notional = abs(units * px)
                entry_cost = entry_notional * (_cost_bps_for_asset(asset, cost_multiplier) / 10000)
                cash -= units * px + entry_cost

                if side > 0:
                    stop_price = px - stop_dist
                    target_price = px + target_dist
                else:
                    stop_price = px + stop_dist
                    target_price = px - target_dist

                pair_asset = next((s for l, s in pairs if l == asset), next((l for l, s in pairs if s == asset), ""))
                positions[asset] = Position(asset=asset, units=units, side=side, entry_price=px, stop_price=stop_price, target_price=target_price, r_value=stop_dist, pair_asset=pair_asset)

        portfolio_value = cash
        for asset, pos in positions.items():
            px = price_row_close.get(asset, np.nan)
            if not np.isnan(px):
                portfolio_value += pos.units * px

        equity_index.append(ts)
        equity_curve.append(portfolio_value)

    return pd.Series(equity_curve, index=equity_index, name="equity").to_frame()


if __name__ == "__main__":
    print(run_backtest().tail())
