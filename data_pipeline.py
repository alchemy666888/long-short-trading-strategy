import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

import pandas as pd
import yfinance as yf

from long_short_config import ASSETS
from polygon_client import download_polygon_5m


DATA_DIR = "data"
RAW_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
EASTERN_TZ = "US/Eastern"


def ensure_dirs() -> None:
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)


def _to_eastern_index(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is None:
        # yfinance often returns tz-naive; treat as UTC then convert.
        df = df.tz_localize("UTC")
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.tz_convert(EASTERN_TZ).sort_index()
    return df


def download_yfinance(
    yf_symbol: str,
    interval: str,
    start: str = None,
    end: str = None,
    period: str = "730d",
) -> pd.DataFrame:
    """
    Download historical OHLCV from Yahoo Finance for a single symbol.

    Uses US/Eastern timezone for all timestamps.
    """
    # Yahoo intraday limits are interval-dependent. For 5m we clamp to ~60 days.
    now_utc = pd.Timestamp.utcnow()

    yf_kwargs: Dict[str, str] = {"interval": interval, "progress": False}

    if start or end:
        # If caller specifies explicit dates, keep them (except we may clamp 5m).
        if start:
            yf_kwargs["start"] = start
        if end:
            yf_kwargs["end"] = end
    else:
        yf_kwargs["period"] = period

    if interval == "5m":
        # Clamp any request to the last ~59 days to avoid Yahoo hard errors.
        end_ts = pd.Timestamp(end).tz_localize("UTC") if end else now_utc
        if end_ts.tzinfo is None:
            end_ts = end_ts.tz_localize("UTC")
        end_ts = min(end_ts, now_utc)
        oldest_allowed = end_ts - pd.Timedelta(days=59)

        if start:
            start_ts = pd.Timestamp(start)
            if start_ts.tzinfo is None:
                start_ts = start_ts.tz_localize("UTC")
            else:
                start_ts = start_ts.tz_convert("UTC")
        else:
            start_ts = oldest_allowed

        if start_ts < oldest_allowed:
            start_ts = oldest_allowed

        yf_kwargs.pop("period", None)
        yf_kwargs["start"] = start_ts.strftime("%Y-%m-%d")
        yf_kwargs["end"] = (end_ts + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    df = yf.download(yf_symbol, **yf_kwargs)
    df = _to_eastern_index(df)
    if df.empty:
        return df

    df = df[~df.index.duplicated(keep="last")]
    return df


def download_all_assets(
    start: str = None,
    end: str = None,
    period: str = None,
    force: bool = False,
) -> None:
    """
    Download OHLCV for all configured assets and cache to CSV.
    """
    ensure_dirs()
    for name, meta in ASSETS.items():
        provider = meta.get("provider", "yahoo")
        raw_path = os.path.join(RAW_DIR, f"{name}.csv")
        if os.path.exists(raw_path) and not force:
            continue

        if provider == "polygon":
            polygon_ticker = meta["polygon_ticker"]
            df = download_polygon_5m(
                ticker=polygon_ticker,
                start=start,
                end=end,
            )
        else:
            yf_symbol = meta["yf_symbol"]
            interval = meta.get("interval", "5m")
            default_period = meta.get("period", "60d")
            effective_period = period or default_period
            df = download_yfinance(
                yf_symbol=yf_symbol,
                interval=interval,
                start=start,
                end=end,
                period=effective_period,
            )
        if df.empty:
            continue

        df.to_csv(raw_path)


def load_raw_asset(name: str) -> pd.DataFrame:
    raw_path = os.path.join(RAW_DIR, f"{name}.csv")
    if not os.path.exists(raw_path):
        raise FileNotFoundError(f"Raw data not found for {name}: {raw_path}")

    df = pd.read_csv(raw_path, index_col=0, parse_dates=True)
    # Robustly coerce index into a tz-aware DatetimeIndex.
    # yfinance CSV exports often include timezone offsets; we normalize by parsing as UTC then converting.
    idx = pd.to_datetime(df.index, errors="coerce", utc=True)
    if idx.isna().any():
        # Fallback: parse without forcing UTC, then localize/convert as needed.
        idx2 = pd.to_datetime(df.index, errors="coerce")
        if isinstance(idx2, pd.DatetimeIndex) and idx2.tz is None:
            idx2 = idx2.tz_localize(EASTERN_TZ)
        idx = idx2

    df = df.loc[~pd.isna(idx)].copy()
    df.index = idx[~pd.isna(idx)]

    if isinstance(df.index, pd.DatetimeIndex):
        if df.index.tz is None:
            df.index = df.index.tz_localize(EASTERN_TZ)
        else:
            df.index = df.index.tz_convert(EASTERN_TZ)

    df = df.sort_index()
    return df


def build_aligned_ohlc() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build aligned 5-minute Open and Close DataFrames for all assets.

    Returns:
        opens, closes: wide DataFrames with datetime index and one column per asset.
    """
    ensure_dirs()
    opens: Dict[str, pd.Series] = {}
    closes: Dict[str, pd.Series] = {}

    for name in ASSETS.keys():
        df = load_raw_asset(name)
        # Keep only 5-min bars; index already at 5m resolution from download
        # Filter to regular trading hours for stocks; keep full session for others.
        if df.empty:
            continue

        # Standardize columns
        df = df.rename(
            columns={
                col: col.capitalize()
                for col in df.columns
            }
        )
        if "Open" not in df.columns or "Close" not in df.columns:
            continue

        # Coerce to numeric (raw CSVs can contain strings depending on locale/formatting)
        df["Open"] = pd.to_numeric(df["Open"], errors="coerce")
        df["Close"] = pd.to_numeric(df["Close"], errors="coerce")

        opens[name] = df["Open"]
        closes[name] = df["Close"]

    if not closes:
        raise ValueError("No close data available to build aligned DataFrames.")

    opens_df = pd.DataFrame(opens).sort_index()
    closes_df = pd.DataFrame(closes).sort_index()

    # Enforce numeric dtype across the wide frames (any leftover strings -> NaN)
    opens_df = opens_df.apply(pd.to_numeric, errors="coerce")
    closes_df = closes_df.apply(pd.to_numeric, errors="coerce")

    # Align on a 5-minute grid for a unified backtest timeline.
    full_index = opens_df.index.union(closes_df.index)
    if not isinstance(full_index, pd.DatetimeIndex):
        full_index = pd.to_datetime(full_index, errors="coerce", utc=True).tz_convert(EASTERN_TZ)
    full_index = full_index.dropna().unique().sort_values()

    start_ts = full_index.min().floor("5min")
    end_ts = full_index.max().ceil("5min")
    grid_index = pd.date_range(start=start_ts, end=end_ts, freq="5min", tz=EASTERN_TZ)

    # Upsample/downsample to 5-minute grid by forward-filling last known bar values.
    opens_df = opens_df.reindex(grid_index).ffill()
    closes_df = closes_df.reindex(grid_index).ffill()

    # Persist processed data (pickle avoids requiring pyarrow/fastparquet)
    opens_df.to_pickle(os.path.join(PROCESSED_DIR, "opens.pkl"))
    closes_df.to_pickle(os.path.join(PROCESSED_DIR, "closes.pkl"))

    return opens_df, closes_df


def load_processed_ohlc() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load processed opens and closes if already built, else build them.
    """
    ensure_dirs()
    opens_path = os.path.join(PROCESSED_DIR, "opens.pkl")
    closes_path = os.path.join(PROCESSED_DIR, "closes.pkl")

    if os.path.exists(opens_path) and os.path.exists(closes_path):
        opens = pd.read_pickle(opens_path)
        closes = pd.read_pickle(closes_path)
        return opens, closes

    return build_aligned_ohlc()


if __name__ == "__main__":
    # Example CLI-style usage: download data and build aligned datasets.
    download_all_assets()
    build_aligned_ohlc()
