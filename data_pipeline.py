from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from data_quality import build_data_quality_report, load_data_quality_report
from long_short_config import ASSETS, BACKTEST_END_DATE, BACKTEST_START_DATE
from polygon_client import download_polygon_5m

DATA_DIR = "data"
RAW_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
EASTERN_TZ = "US/Eastern"

QUALITY_REPORT_PATH = Path(PROCESSED_DIR) / "data_quality_report_v5.json"


def ensure_dirs() -> None:
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)


def download_all_assets(
    start: str = None,
    end: str = None,
    period: str = None,
    force: bool = False,
) -> None:
    if period is not None:
        print("[WARN] --period is ignored in Polygon-only mode.")

    ensure_dirs()

    for name, meta in ASSETS.items():
        provider = str(meta.get("provider", "")).lower()
        raw_path = os.path.join(RAW_DIR, f"{name}.csv")
        if os.path.exists(raw_path) and not force:
            continue

        if provider != "polygon":
            raise ValueError(
                f"{name} is configured with provider={provider!r}. "
                "All assets must use provider='polygon'."
            )

        polygon_ticker = meta.get("polygon_ticker")
        if not polygon_ticker:
            raise ValueError(f"{name} is missing required 'polygon_ticker' in config.")

        try:
            df = download_polygon_5m(
                ticker=str(polygon_ticker),
                start=start,
                end=end,
            )
        except Exception as exc:
            raise RuntimeError(f"Polygon download failed for {name} ({polygon_ticker}): {exc}") from exc

        if df.empty:
            raise RuntimeError(f"Polygon returned no data for {name} ({polygon_ticker}).")

        df.to_csv(raw_path)


def load_raw_asset(name: str) -> pd.DataFrame:
    raw_path = os.path.join(RAW_DIR, f"{name}.csv")
    if not os.path.exists(raw_path):
        raise FileNotFoundError(f"Raw data not found for {name}: {raw_path}")

    df = pd.read_csv(raw_path, index_col=0)
    idx = pd.to_datetime(pd.Index(df.index.astype(str)), errors="coerce", utc=True, format="mixed")
    df = df.loc[~pd.isna(idx)].copy()
    df.index = idx[~pd.isna(idx)]

    if isinstance(df.index, pd.DatetimeIndex):
        if df.index.tz is None:
            df.index = df.index.tz_localize(EASTERN_TZ)
        else:
            df.index = df.index.tz_convert(EASTERN_TZ)

    return df.sort_index()


def _standardize_ohlc_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    rename_map = {col: col.capitalize() for col in df.columns}
    df = df.rename(columns=rename_map)
    needed = ["Open", "High", "Low", "Close"]
    if any(col not in df.columns for col in needed):
        return pd.DataFrame(columns=needed)

    out = df[needed].copy()
    for col in needed:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna(subset=needed)
    return out


def _resample_asset_ohlc(df: pd.DataFrame, rule: str) -> Tuple[pd.DataFrame, pd.Series]:
    if df.empty:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close"]), pd.Series(dtype=bool)

    ohlc = df[["Open", "High", "Low", "Close"]].resample(rule, label="right", closed="right").agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
        }
    )
    expected = df["Close"].resample(rule, label="right", closed="right").count() > 0

    for col in ["Open", "High", "Low", "Close"]:
        ohlc.loc[~expected, col] = np.nan

    return ohlc.sort_index(), expected.sort_index()


def _assemble_wide(series_map: Dict[str, pd.Series], index: pd.DatetimeIndex) -> pd.DataFrame:
    frame = pd.DataFrame({asset: s.reindex(index) for asset, s in series_map.items()}, index=index)
    return frame.apply(pd.to_numeric, errors="coerce").sort_index()


def build_v5_matrices(write_quality_report: bool = True) -> Dict[str, pd.DataFrame]:
    ensure_dirs()

    opens_1d: Dict[str, pd.Series] = {}
    highs_1d: Dict[str, pd.Series] = {}
    lows_1d: Dict[str, pd.Series] = {}
    closes_1d: Dict[str, pd.Series] = {}

    opens_4h: Dict[str, pd.Series] = {}
    highs_4h: Dict[str, pd.Series] = {}
    lows_4h: Dict[str, pd.Series] = {}
    closes_4h: Dict[str, pd.Series] = {}

    expected_1d: Dict[str, pd.Series] = {}
    expected_4h: Dict[str, pd.Series] = {}

    for asset in ASSETS.keys():
        try:
            raw = load_raw_asset(asset)
        except FileNotFoundError:
            continue

        raw = _standardize_ohlc_columns(raw)
        if raw.empty:
            continue

        ohlc_1d, exp_1d = _resample_asset_ohlc(raw, "1D")
        ohlc_4h, exp_4h = _resample_asset_ohlc(raw, "4h")

        opens_1d[asset] = ohlc_1d["Open"]
        highs_1d[asset] = ohlc_1d["High"]
        lows_1d[asset] = ohlc_1d["Low"]
        closes_1d[asset] = ohlc_1d["Close"]

        opens_4h[asset] = ohlc_4h["Open"]
        highs_4h[asset] = ohlc_4h["High"]
        lows_4h[asset] = ohlc_4h["Low"]
        closes_4h[asset] = ohlc_4h["Close"]

        expected_1d[asset] = exp_1d
        expected_4h[asset] = exp_4h

    if not closes_1d or not closes_4h:
        raise ValueError("No processed 1D/4H data could be built from raw inputs.")

    idx_1d = pd.DatetimeIndex(sorted(set().union(*(s.index for s in closes_1d.values()))), tz=EASTERN_TZ)
    idx_4h = pd.DatetimeIndex(sorted(set().union(*(s.index for s in closes_4h.values()))), tz=EASTERN_TZ)

    matrices = {
        "opens_1d": _assemble_wide(opens_1d, idx_1d),
        "highs_1d": _assemble_wide(highs_1d, idx_1d),
        "lows_1d": _assemble_wide(lows_1d, idx_1d),
        "closes_1d": _assemble_wide(closes_1d, idx_1d),
        "opens_4h": _assemble_wide(opens_4h, idx_4h),
        "highs_4h": _assemble_wide(highs_4h, idx_4h),
        "lows_4h": _assemble_wide(lows_4h, idx_4h),
        "closes_4h": _assemble_wide(closes_4h, idx_4h),
    }

    expected_1d_df = _assemble_wide(expected_1d, idx_1d).fillna(0.0).astype(bool)
    expected_4h_df = _assemble_wide(expected_4h, idx_4h).fillna(0.0).astype(bool)

    for key, frame in matrices.items():
        frame.to_pickle(Path(PROCESSED_DIR) / f"{key}.pkl")

    # Keep legacy file names mapped to 4H for backward compatibility.
    matrices["opens_4h"].to_pickle(Path(PROCESSED_DIR) / "opens.pkl")
    matrices["highs_4h"].to_pickle(Path(PROCESSED_DIR) / "highs.pkl")
    matrices["lows_4h"].to_pickle(Path(PROCESSED_DIR) / "lows.pkl")
    matrices["closes_4h"].to_pickle(Path(PROCESSED_DIR) / "closes.pkl")

    if write_quality_report:
        build_data_quality_report(
            closes_1d=matrices["closes_1d"],
            closes_4h=matrices["closes_4h"],
            expected_1d=expected_1d_df,
            expected_4h=expected_4h_df,
            output_path=QUALITY_REPORT_PATH,
        )

    return matrices


def load_processed_ohlc_v5(require_quality_pass: bool = True) -> Tuple[Dict[str, pd.DataFrame], Dict]:
    ensure_dirs()

    required_paths = {
        name: Path(PROCESSED_DIR) / f"{name}.pkl"
        for name in [
            "opens_1d",
            "highs_1d",
            "lows_1d",
            "closes_1d",
            "opens_4h",
            "highs_4h",
            "lows_4h",
            "closes_4h",
        ]
    }

    if not all(path.exists() for path in required_paths.values()):
        build_v5_matrices(write_quality_report=True)

    matrices = {name: pd.read_pickle(path) for name, path in required_paths.items()}

    quality = load_data_quality_report(QUALITY_REPORT_PATH)
    if not quality:
        quality = build_data_quality_report(
            closes_1d=matrices["closes_1d"],
            closes_4h=matrices["closes_4h"],
            expected_1d=matrices["closes_1d"].notna(),
            expected_4h=matrices["closes_4h"].notna(),
            output_path=QUALITY_REPORT_PATH,
        )

    if require_quality_pass and not bool(quality.get("hard_pass", False)):
        exclusions = quality.get("exclusions", {})
        reasons = []
        for asset, why in exclusions.items():
            reasons.append(f"{asset}: {', '.join(why)}")
        reason_text = " | ".join(reasons) if reasons else "unknown_quality_failure"
        raise ValueError(f"v5 data-quality hard gate failed. {reason_text}")

    return matrices, quality


def load_processed_ohlc() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    matrices, _ = load_processed_ohlc_v5(require_quality_pass=False)
    return (
        matrices["opens_4h"],
        matrices["highs_4h"],
        matrices["lows_4h"],
        matrices["closes_4h"],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build v5 canonical 1D/4H OHLC matrices and quality gates.")
    parser.add_argument("--start", default=BACKTEST_START_DATE)
    parser.add_argument("--end", default=BACKTEST_END_DATE)
    parser.add_argument("--period", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--skip-quality-report", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.build_only:
        download_all_assets(
            start=args.start,
            end=args.end,
            period=args.period,
            force=args.force,
        )

    matrices = build_v5_matrices(write_quality_report=not args.skip_quality_report)
    print("Built v5 matrices:")
    for name in sorted(matrices.keys()):
        print(f"- {name}: {matrices[name].shape}")

    if not args.skip_quality_report:
        quality = load_data_quality_report(QUALITY_REPORT_PATH)
        print(f"- quality_report: {QUALITY_REPORT_PATH}")
        print(f"- quality_hard_pass: {quality.get('hard_pass', False)}")


if __name__ == "__main__":
    main()
