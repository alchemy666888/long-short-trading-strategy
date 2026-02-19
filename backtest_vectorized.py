from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import pandas as pd

from data_pipeline import load_processed_ohlc
from long_short_config import (
    CAPITAL,
    REBALANCE_TIMES,
    TRANSACTION_COST_BPS,
    TRADING_WINDOW_END,
    TRADING_WINDOW_START,
)
from strategy_core import (
    LOOKBACK,
    STOP_Z,
    compute_volatility,
    compute_zscores,
    select_long_short_candidates,
)


@dataclass
class Position:
    asset: str
    units: float


def run_backtest() -> pd.DataFrame:
    opens, closes = load_processed_ohlc()

    zscores = compute_zscores(closes)
    volatility = compute_volatility(closes)

    # Simulate only within the strategy trading window.
    exec_index = closes.between_time(TRADING_WINDOW_START, TRADING_WINDOW_END).index
    opens = opens.loc[exec_index]
    closes = closes.loc[exec_index]
    zscores = zscores.loc[exec_index]
    volatility = volatility.loc[exec_index]

    capital = CAPITAL
    cash = capital
    positions: Dict[str, Position] = {}
    equity_curve: List[float] = []
    equity_index: List[pd.Timestamp] = []

    total_risk_budget_frac = 0.01
    max_per_side = 3
    max_gross_leverage = 4.0
    sigma_floor = 1e-4  # floor on std(returns) to avoid extreme sizing

    for i, ts in enumerate(closes.index):
        price_row_open = opens.loc[ts]
        price_row_close = closes.loc[ts]
        z_row = zscores.loc[ts]
        vol_row = volatility.loc[ts]

        # Skip until we have enough history
        if i < LOOKBACK:
            portfolio_value = cash + sum(
                pos.units * price_row_close[pos.asset] for pos in positions.values()
            )
            equity_index.append(ts)
            equity_curve.append(portfolio_value)
            continue

        # Execute bar-based exit signals at current open (next-bar execution).
        # We trigger exits based on the previous bar close's Z-score.
        z_prev = zscores.iloc[i - 1] if i > 0 else None
        if z_prev is not None and positions:
            for asset, pos in list(positions.items()):
                if asset not in z_prev.index:
                    continue
                prev_z = z_prev[asset]
                if np.isnan(prev_z):
                    continue

                is_long = pos.units > 0
                exit_due_to_tp = (is_long and prev_z >= 0) or ((not is_long) and prev_z <= 0)
                exit_due_to_stop = (is_long and prev_z <= -STOP_Z) or ((not is_long) and prev_z >= STOP_Z)

                if not (exit_due_to_tp or exit_due_to_stop):
                    continue

                exit_price = price_row_open.get(asset, np.nan)
                if np.isnan(exit_price) or exit_price <= 0:
                    continue

                notional = abs(pos.units * exit_price)
                cost = notional * (TRANSACTION_COST_BPS / 10000)
                cash += pos.units * exit_price
                cash -= cost
                del positions[asset]

        # Rebalance at rebalance times using previous bar's close as signal,
        # executing at current bar's open (next-bar execution).
        if ts.strftime("%H:%M") in REBALANCE_TIMES:
            longs, shorts = select_long_short_candidates(z_row, max_per_side=max_per_side)

            # Close all existing positions at current open
            for asset, pos in list(positions.items()):
                if np.isnan(price_row_open[asset]):
                    continue
                exit_price = price_row_open[asset]
                notional = abs(pos.units * exit_price)
                cost = notional * (TRANSACTION_COST_BPS / 10000)
                cash += pos.units * exit_price
                cash -= cost
                del positions[asset]

            if longs and shorts:
                num_positions = 2 * min(len(longs), len(shorts), max_per_side)
                if num_positions > 0:
                    total_risk_budget = capital * total_risk_budget_frac
                    per_position_risk = total_risk_budget / num_positions

                    # Build raw targets
                    target_units: Dict[str, float] = {}
                    for asset in longs + shorts:
                        side = 1 if asset in longs else -1
                        sigma = vol_row.get(asset, np.nan)
                        price = price_row_open.get(asset, np.nan)
                        if np.isnan(sigma) or np.isnan(price) or price <= 0:
                            continue
                        sigma_eff = max(float(sigma), sigma_floor)
                        target_notional = per_position_risk / sigma_eff
                        units = (target_notional / price) * side
                        if np.isnan(units) or units == 0:
                            continue
                        target_units[asset] = float(units)

                    # Enforce gross leverage cap
                    gross = sum(abs(u * price_row_open[a]) for a, u in target_units.items())
                    max_gross = capital * max_gross_leverage
                    scale = 1.0
                    if gross > 0 and gross > max_gross:
                        scale = max_gross / gross

                    for asset, units in target_units.items():
                        price = float(price_row_open[asset])
                        units *= scale
                        notional = abs(units * price)
                        cost = notional * (TRANSACTION_COST_BPS / 10000)
                        cash -= units * price
                        cash -= cost
                        positions[asset] = Position(asset=asset, units=units)

        # End-of-day liquidation at 15:55 close (per spec).
        if ts.strftime("%H:%M") == "15:55" and positions:
            for asset, pos in list(positions.items()):
                exit_price = price_row_close.get(asset, np.nan)
                if np.isnan(exit_price) or exit_price <= 0:
                    continue
                notional = abs(pos.units * exit_price)
                cost = notional * (TRANSACTION_COST_BPS / 10000)
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
