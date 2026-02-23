import argparse
import os
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from long_short_config import ASSETS, BACKTEST_END_DATE, BACKTEST_START_DATE
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
    # Yahoo 5m intraday history is limited to recent ~60 days.
    now_utc = pd.Timestamp.utcnow()
    recency_cutoff = now_utc - pd.Timedelta(days=59)

    def _to_utc(ts_value: Optional[str]) -> Optional[pd.Timestamp]:
        if not ts_value:
            return None
        ts = pd.Timestamp(ts_value)
        if ts.tzinfo is None:
            return ts.tz_localize("UTC")
        return ts.tz_convert("UTC")

    start_ts = _to_utc(start)
    end_ts = _to_utc(end) if end else now_utc
    end_ts = min(end_ts, now_utc)

    # Do not silently downgrade to 60m. If 5m data is out of range, return
    # empty so callers can fail fast or fall back to a proper 5m source.
    if interval == "5m":
        if (start_ts is not None and start_ts < recency_cutoff) or end_ts < recency_cutoff:
            print(
                f"[WARN] {yf_symbol}: Yahoo 5m only supports recent history; "
                f"cannot satisfy requested range {start or period} -> {end or 'now'}."
            )
            return pd.DataFrame()

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
        oldest_allowed = end_ts - pd.Timedelta(days=59)

        if start:
            # start_ts already normalized above.
            assert start_ts is not None
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
            try:
                df = download_polygon_5m(
                    ticker=polygon_ticker,
                    start=start,
                    end=end,
                )
            except Exception as exc:
                # Graceful fallback for environments without Polygon credentials.
                fallback_symbol = _infer_yahoo_symbol(name=name, meta=meta)
                if not fallback_symbol:
                    print(
                        f"[WARN] {name}: Polygon unavailable and no Yahoo fallback symbol. "
                        f"Skipping asset. Reason: {exc}"
                    )
                    continue

                fallback_interval = _infer_yahoo_interval(meta=meta)
                fallback_period = period or meta.get("period", "730d")
                print(
                    f"[WARN] {name}: Polygon unavailable. Falling back to Yahoo "
                    f"({fallback_symbol}, interval={fallback_interval})."
                )
                df = download_yfinance(
                    yf_symbol=fallback_symbol,
                    interval=fallback_interval,
                    start=start,
                    end=end,
                    period=fallback_period,
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
            print(f"[WARN] {name}: no data returned; skipping.")
            continue

        df.to_csv(raw_path)


def _infer_yahoo_symbol(name: str, meta: Dict) -> Optional[str]:
    yf_symbol = meta.get("yf_symbol")
    if yf_symbol:
        return str(yf_symbol)

    asset_class = meta.get("asset_class")
    if asset_class == "stock":
        return name
    if asset_class == "crypto":
        return f"{name}-USD"

    return None


def _infer_yahoo_interval(meta: Dict) -> str:
    # Keep fallback intraday interval consistent with backtest frequency.
    configured = meta.get("interval")
    if configured:
        return str(configured)
    return "5m"


def load_raw_asset(name: str) -> pd.DataFrame:
    raw_path = os.path.join(RAW_DIR, f"{name}.csv")
    if not os.path.exists(raw_path):
        raise FileNotFoundError(f"Raw data not found for {name}: {raw_path}")

    df = pd.read_csv(raw_path, index_col=0)
    # Robustly coerce index into a tz-aware DatetimeIndex.
    # yfinance CSV exports often include timezone offsets; we normalize by parsing as UTC then converting.
    raw_index = pd.Index(df.index.astype(str))
    idx = pd.to_datetime(raw_index, errors="coerce", utc=True, format="mixed")

    df = df.loc[~pd.isna(idx)].copy()
    df.index = idx[~pd.isna(idx)]

    if isinstance(df.index, pd.DatetimeIndex):
        if df.index.tz is None:
            df.index = df.index.tz_localize(EASTERN_TZ)
        else:
            df.index = df.index.tz_convert(EASTERN_TZ)

    df = df.sort_index()
    return df


def _infer_mode_bar_minutes(index: pd.DatetimeIndex) -> float:
    if len(index) < 2:
        return np.nan
    diffs = index.to_series().diff().dropna().dt.total_seconds() / 60.0
    if diffs.empty:
        return np.nan
    return float(diffs.mode().iloc[0])


def build_aligned_ohlc() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build aligned 5-minute Open and Close DataFrames for all assets.

    Returns:
        opens, closes: wide DataFrames with datetime index and one column per asset.
    """
    ensure_dirs()
    opens: Dict[str, pd.Series] = {}
    closes: Dict[str, pd.Series] = {}
    native_5m_assets = set()

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
        df = df.dropna(subset=["Open", "Close"])

        mode_bar_minutes = _infer_mode_bar_minutes(df.index)
        if not np.isnan(mode_bar_minutes) and abs(mode_bar_minutes - 5.0) <= 0.5:
            native_5m_assets.add(name)
        else:
            print(
                f"[WARN] {name}: detected non-5m native bar spacing "
                f"({mode_bar_minutes:.2f}m). Data kept sparse without forward-fill."
            )

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

    opens_df = opens_df.reindex(grid_index)
    closes_df = closes_df.reindex(grid_index)

    # Fill only short one-bar gaps for assets that are truly native 5m.
    for asset in opens_df.columns:
        if asset in native_5m_assets:
            opens_df[asset] = opens_df[asset].ffill(limit=1)
            closes_df[asset] = closes_df[asset].ffill(limit=1)

    # Keep each asset NaN outside its observed raw time range.
    for col in opens_df.columns:
        first_open = opens[col].first_valid_index()
        last_open = opens[col].last_valid_index()
        if first_open is not None and last_open is not None:
            outside_range_open = (opens_df.index < first_open) | (opens_df.index > last_open)
            opens_df.loc[outside_range_open, col] = np.nan

        first_close = closes[col].first_valid_index()
        last_close = closes[col].last_valid_index()
        if first_close is not None and last_close is not None:
            outside_range_close = (closes_df.index < first_close) | (closes_df.index > last_close)
            closes_df.loc[outside_range_close, col] = np.nan

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download raw OHLC data and build aligned processed datasets."
    )
    parser.add_argument(
        "--start",
        default=BACKTEST_START_DATE,
        help=f"Start date (YYYY-MM-DD). Default: {BACKTEST_START_DATE}",
    )
    parser.add_argument(
        "--end",
        default=BACKTEST_END_DATE,
        help=f"End date (YYYY-MM-DD). Default: {BACKTEST_END_DATE}",
    )
    parser.add_argument(
        "--period",
        default=None,
        help="Provider period override (mainly for yfinance).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download and overwrite existing raw CSVs.",
    )
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="Skip downloads and only rebuild processed pickles from raw CSVs.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if not args.build_only:
        download_all_assets(
            start=args.start,
            end=args.end,
            period=args.period,
            force=args.force,
        )
    build_aligned_ohlc()
