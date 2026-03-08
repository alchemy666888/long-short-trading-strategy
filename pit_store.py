from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd


NEWS_COLUMNS = [
    "published_at_utc",
    "ingested_at_utc",
    "source",
    "headline",
    "body",
    "language",
    "region",
    "asset_class",
    "assets",
    "catalyst_type",
    "sentiment_score",
]


MACRO_COLUMNS = [
    "release_timestamp_utc",
    "event_name",
    "region",
    "actual",
    "consensus",
    "prior",
    "revision",
    "importance",
]


def _to_utc_timestamp(value: object) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts


def point_in_time_news(news_df: pd.DataFrame, cutoff_ts: pd.Timestamp) -> pd.DataFrame:
    if news_df.empty:
        return pd.DataFrame(columns=NEWS_COLUMNS)

    cutoff_utc = _to_utc_timestamp(cutoff_ts)
    frame = news_df.copy()

    published = pd.to_datetime(frame["published_at_utc"], errors="coerce", utc=True)
    ingested = pd.to_datetime(frame["ingested_at_utc"], errors="coerce", utc=True)
    available = pd.DataFrame({"published": published, "ingested": ingested}).max(axis=1)

    frame = frame.loc[available <= cutoff_utc].copy()
    frame = frame.assign(available_at_utc=available.loc[frame.index])
    frame = frame.sort_values("available_at_utc")
    return frame


def point_in_time_macro(macro_df: pd.DataFrame, cutoff_ts: pd.Timestamp) -> pd.DataFrame:
    if macro_df.empty:
        return pd.DataFrame(columns=MACRO_COLUMNS)

    cutoff_utc = _to_utc_timestamp(cutoff_ts)
    frame = macro_df.copy()
    releases = pd.to_datetime(frame["release_timestamp_utc"], errors="coerce", utc=True)
    frame = frame.loc[releases <= cutoff_utc].copy()
    frame["release_timestamp_utc"] = releases.loc[frame.index]
    frame = frame.sort_values("release_timestamp_utc")
    return frame


def snapshot_manifest_hash(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(p) for p in paths):
        digest.update(str(path).encode("utf-8"))
        if not path.exists():
            digest.update(b"MISSING")
            continue

        stat = path.stat()
        digest.update(str(stat.st_size).encode("utf-8"))
        digest.update(str(int(stat.st_mtime_ns)).encode("utf-8"))

        with path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)

    return digest.hexdigest()


def latest_available_timestamp(frame: pd.DataFrame, column: str) -> Optional[pd.Timestamp]:
    if frame.empty or column not in frame.columns:
        return None
    ts = pd.to_datetime(frame[column], errors="coerce", utc=True).dropna()
    if ts.empty:
        return None
    return pd.Timestamp(ts.max())
