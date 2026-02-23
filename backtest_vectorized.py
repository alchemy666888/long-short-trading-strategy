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
    ENTRY_Z,
    EXIT_Z,
    MAX_GROSS_LEVERAGE,
    MAX_POSITIONS_PER_CLASS_PER_SIDE,
    MAX_POSITIONS_PER_SIDE,
    REBALANCE_TIMES,
    SIGMA_FLOOR,
    STOP_Z,
    TOTAL_RISK_BUDGET_FRACTION,
    TRANSACTION_COST_BPS_BY_CLASS,
    TRADING_WINDOW_END,
    TRADING_WINDOW_START,
)
from strategy_core import (
    compute_regime_filter,
    compute_volatility,
    compute_zscores,
    get_asset_class,
    select_long_short_candidates,
)


@dataclass
class Position:
    asset: str
    units: float


def _filter_backtest_period(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    start_ts = pd.Timestamp(BACKTEST_START_DATE, tz="US/Eastern")
    end_ts_exclusive = pd.Timestamp(BACKTEST_END_DATE, tz="US/Eastern") + pd.Timedelta(days=1)
    return index[(index >= start_ts) & (index < end_ts_exclusive)]


def _build_session_index() -> pd.DatetimeIndex:
    start_ts = pd.Timestamp(BACKTEST_START_DATE, tz="US/Eastern")
    end_ts_exclusive = pd.Timestamp(BACKTEST_END_DATE, tz="US/Eastern") + pd.Timedelta(days=1)
    full_index = pd.date_range(
        start=start_ts,
        end=end_ts_exclusive - pd.Timedelta(minutes=5),
        freq="5min",
        tz="US/Eastern",
    )
    full_index = full_index[full_index.dayofweek < 5]
    trading_index = full_index.indexer_between_time(TRADING_WINDOW_START, TRADING_WINDOW_END)
    return full_index[trading_index]


def _cost_bps_for_asset(asset: str) -> float:
    asset_class = get_asset_class(asset)
    return float(TRANSACTION_COST_BPS_BY_CLASS.get(asset_class, DEFAULT_TRANSACTION_COST_BPS))


def run_backtest() -> pd.DataFrame:
    opens, closes = load_processed_ohlc()

    # Build explicit session timeline from configured backtest window.
    session_index = _build_session_index()
    session_index = _filter_backtest_period(session_index.sort_values())

    if session_index.empty:
        raise ValueError(
            "No bars available for configured backtest period "
            f"{BACKTEST_START_DATE} to {BACKTEST_END_DATE}."
        )

    opens = opens.reindex(session_index)
    closes = closes.reindex(session_index)

    available_mask = closes.notna().any(axis=1)
    if not available_mask.any():
        raise ValueError(
            "No price observations exist within the configured backtest timeline. "
            "Download data first or broaden provider coverage."
        )

    configured_start = pd.Timestamp(BACKTEST_START_DATE, tz="US/Eastern").date()
    configured_end = pd.Timestamp(BACKTEST_END_DATE, tz="US/Eastern").date()
    first_obs_idx = int(np.argmax(available_mask.values))
    last_obs_idx = int(np.where(available_mask.values)[0][-1])
    actual_start = closes.index[first_obs_idx]
    actual_end = closes.index[last_obs_idx]
    if actual_start.date() > configured_start or actual_end.date() < configured_end:
        warnings.warn(
            "Backtest period is constrained by available data. "
            f"Requested: {BACKTEST_START_DATE} to {BACKTEST_END_DATE}. "
            f"Effective: {actual_start} to {actual_end}.",
            RuntimeWarning,
            stacklevel=2,
        )
    zscores = compute_zscores(closes)
    volatility = compute_volatility(closes)
    regime_ok = compute_regime_filter(closes)

    capital = CAPITAL
    cash = capital
    positions: Dict[str, Position] = {}
    equity_curve: List[float] = []
    equity_index: List[pd.Timestamp] = []

    # Tracks the first rebalance event ID on which an asset can be entered again
    # after a bar-based TP/stop exit.
    reentry_allowed_from_rebalance: Dict[str, int] = {}
    next_rebalance_id = 1

    for i, ts in enumerate(closes.index):
        price_row_open = opens.loc[ts]
        price_row_close = closes.loc[ts]
        z_prev = zscores.iloc[i - 1] if i > 0 else None
        z_prev2 = zscores.iloc[i - 2] if i > 1 else None
        vol_prev = volatility.iloc[i - 1] if i > 0 else None
        signal_ts = closes.index[i - 1] if i > 0 else None
        should_rebalance = (
            signal_ts is not None
            and signal_ts.strftime("%H:%M") in REBALANCE_TIMES
            and z_prev is not None
            and vol_prev is not None
            and bool(regime_ok.get(signal_ts, True))
        )

        # Execute bar-based exit signals at current open (next-bar execution).
        # We trigger exits based on the previous bar close's Z-score.
        if z_prev is not None and positions:
            for asset, pos in list(positions.items()):
                if asset not in z_prev.index:
                    continue
                prev_z = z_prev[asset]
                if np.isnan(prev_z):
                    continue

                prev2_z = np.nan
                if z_prev2 is not None and asset in z_prev2.index:
                    prev2_z = z_prev2[asset]

                is_long = pos.units > 0
                if is_long:
                    crossed_exit = (
                        (not np.isnan(prev2_z) and prev2_z < -EXIT_Z <= prev_z)
                        or (np.isnan(prev2_z) and prev_z >= -EXIT_Z)
                    )
                    exit_due_to_stop = prev_z < -STOP_Z
                else:
                    crossed_exit = (
                        (not np.isnan(prev2_z) and prev2_z > EXIT_Z >= prev_z)
                        or (np.isnan(prev2_z) and prev_z <= EXIT_Z)
                    )
                    exit_due_to_stop = prev_z > STOP_Z
                exit_due_to_tp = crossed_exit

                if not (exit_due_to_tp or exit_due_to_stop):
                    continue

                exit_price = price_row_open.get(asset, np.nan)
                if np.isnan(exit_price) or exit_price <= 0:
                    exit_price = price_row_close.get(asset, np.nan)
                    if np.isnan(exit_price) or exit_price <= 0:
                        continue

                notional = abs(pos.units * exit_price)
                cost_bps = _cost_bps_for_asset(asset)
                cost = notional * (cost_bps / 10000)
                cash += pos.units * exit_price
                cash -= cost
                del positions[asset]
                # If an exit is processed on a rebalance bar, prevent same-bar
                # re-entry and wait until the following rebalance event.
                reentry_allowed_from_rebalance[asset] = (
                    next_rebalance_id + 1 if should_rebalance else next_rebalance_id
                )

        # Rebalance uses the previous bar close signal and current bar open execution.
        if should_rebalance:
            long_candidates, short_candidates = select_long_short_candidates(
                zscores=z_prev,
                max_per_side=MAX_POSITIONS_PER_SIDE,
                max_per_class=MAX_POSITIONS_PER_CLASS_PER_SIDE,
                entry_z=ENTRY_Z,
            )

            # Close all existing positions at current open
            for asset, pos in list(positions.items()):
                exit_price = price_row_open.get(asset, np.nan)
                if np.isnan(exit_price) or exit_price <= 0:
                    exit_price = price_row_close.get(asset, np.nan)
                    if np.isnan(exit_price) or exit_price <= 0:
                        continue
                notional = abs(pos.units * exit_price)
                cost_bps = _cost_bps_for_asset(asset)
                cost = notional * (cost_bps / 10000)
                cash += pos.units * exit_price
                cash -= cost
                del positions[asset]

            def is_tradeable(asset: str) -> bool:
                if reentry_allowed_from_rebalance.get(asset, 1) > next_rebalance_id:
                    return False
                sigma = vol_prev.get(asset, np.nan)
                price = price_row_open.get(asset, np.nan)
                return (
                    not np.isnan(sigma)
                    and sigma > 0
                    and not np.isnan(price)
                    and price > 0
                )

            valid_longs = [a for a in long_candidates if is_tradeable(a)]
            valid_shorts = [a for a in short_candidates if is_tradeable(a)]
            n = min(len(valid_longs), len(valid_shorts), MAX_POSITIONS_PER_SIDE)
            longs = valid_longs[:n]
            shorts = valid_shorts[:n]

            if longs and shorts:
                capital_base = max(float(cash), 0.0)
                total_risk_budget = capital_base * TOTAL_RISK_BUDGET_FRACTION
                per_position_risk = total_risk_budget / (2 * n)

                # Build raw targets
                target_units: Dict[str, float] = {}
                for asset in longs + shorts:
                    side = 1 if asset in longs else -1
                    sigma_eff = max(float(vol_prev[asset]), SIGMA_FLOOR)
                    price = float(price_row_open[asset])
                    target_notional = per_position_risk / sigma_eff
                    units = (target_notional / price) * side
                    if np.isnan(units) or units == 0:
                        continue
                    target_units[asset] = float(units)

                # Enforce gross leverage cap
                gross = sum(abs(u * price_row_open[a]) for a, u in target_units.items())
                max_gross = capital_base * MAX_GROSS_LEVERAGE
                scale = 1.0
                if gross > 0 and gross > max_gross:
                    scale = max_gross / gross

                for asset, units in target_units.items():
                    price = float(price_row_open[asset])
                    units *= scale
                    notional = abs(units * price)
                    cost_bps = _cost_bps_for_asset(asset)
                    cost = notional * (cost_bps / 10000)
                    cash -= units * price
                    cash -= cost
                    positions[asset] = Position(asset=asset, units=units)

            next_rebalance_id += 1

        # End-of-day liquidation at 15:55 close (per spec).
        if ts.strftime("%H:%M") == "15:55" and positions:
            for asset, pos in list(positions.items()):
                exit_price = price_row_close.get(asset, np.nan)
                if np.isnan(exit_price) or exit_price <= 0:
                    continue
                notional = abs(pos.units * exit_price)
                cost_bps = _cost_bps_for_asset(asset)
                cost = notional * (cost_bps / 10000)
                cash += pos.units * exit_price
                cash -= cost
                del positions[asset]

        # Mark-to-market portfolio
        portfolio_value = cash
        for asset, pos in positions.items():
            if np.isnan(price_row_close[asset]):
                continue
            portfolio_value += pos.units * price_row_close[asset]

        equity_index.append(ts)
        equity_curve.append(portfolio_value)

    equity_series = pd.Series(equity_curve, index=equity_index, name="equity")
    return equity_series.to_frame()


if __name__ == "__main__":
    equity = run_backtest()
    print(equity.tail())
