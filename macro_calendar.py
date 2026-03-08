from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

from long_short_config import ANALYSIS_EVENT_RISK_REDUCTION_MAX, ANALYSIS_EVENT_RISK_REDUCTION_MIN, ANALYSIS_MACRO_CALENDAR_PATH


MACRO_COLUMNS = [
    "release_timestamp_utc",
    "event_name",
    "region",
    "actual",
    "consensus",
    "prior",
    "revision",
    "importance",
    "asset_classes",
]


def _load_json(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return pd.DataFrame(payload)
    if isinstance(payload, dict) and "events" in payload and isinstance(payload["events"], list):
        return pd.DataFrame(payload["events"])
    raise ValueError(f"Unsupported macro-calendar JSON in {path}")


def _parse_asset_classes(value: object) -> str:
    if isinstance(value, list):
        return ",".join(str(v).strip().lower() for v in value if str(v).strip())
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "stock,forex,metal,crypto"
    text = str(value).strip().lower()
    return text if text else "stock,forex,metal,crypto"


def normalize_macro_calendar(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=MACRO_COLUMNS)

    frame = df.copy()
    for col in MACRO_COLUMNS:
        if col not in frame.columns:
            frame[col] = np.nan

    frame["release_timestamp_utc"] = pd.to_datetime(frame["release_timestamp_utc"], errors="coerce", utc=True)
    frame["event_name"] = frame["event_name"].fillna("unknown_event").astype(str)
    frame["region"] = frame["region"].fillna("US").astype(str)
    frame["importance"] = (
        frame["importance"]
        .fillna("medium")
        .astype(str)
        .str.strip()
        .str.lower()
        .replace({"high impact": "high", "low impact": "low"})
    )

    for col in ["actual", "consensus", "prior", "revision"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")

    frame["asset_classes"] = frame["asset_classes"].apply(_parse_asset_classes)

    frame = frame.dropna(subset=["release_timestamp_utc"]).sort_values("release_timestamp_utc")
    frame = frame.reset_index(drop=True)
    return frame[MACRO_COLUMNS]


def load_macro_calendar(path: str = ANALYSIS_MACRO_CALENDAR_PATH) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        return pd.DataFrame(columns=MACRO_COLUMNS)

    if file_path.suffix.lower() == ".csv":
        raw = pd.read_csv(file_path)
    elif file_path.suffix.lower() in {".json", ".jsonl", ".jl"}:
        raw = _load_json(file_path)
    else:
        raise ValueError(f"Unsupported macro calendar format: {file_path.suffix}")

    return normalize_macro_calendar(raw)


def macro_surprise_score(macro_events: pd.DataFrame) -> float:
    if macro_events.empty:
        return 0.0

    frame = macro_events.copy()
    surprise = frame["actual"] - frame["consensus"]
    denom = frame["consensus"].abs().replace(0.0, np.nan)
    surprise = (surprise / denom).replace([np.inf, -np.inf], np.nan).dropna()

    if surprise.empty:
        return 0.0

    clipped = surprise.clip(-0.05, 0.05) / 0.05
    return float(np.clip(clipped.mean(), -1.0, 1.0))


def event_risk_multiplier(macro_events: pd.DataFrame, day: pd.Timestamp) -> float:
    if macro_events.empty:
        return 1.0

    day_utc = pd.Timestamp(day)
    if day_utc.tzinfo is None:
        day_utc = day_utc.tz_localize("UTC")
    else:
        day_utc = day_utc.tz_convert("UTC")

    start = day_utc.normalize()
    end = start + pd.Timedelta(days=1)

    events = macro_events.copy()
    events["release_timestamp_utc"] = pd.to_datetime(events["release_timestamp_utc"], errors="coerce", utc=True)
    window = events[(events["release_timestamp_utc"] >= start) & (events["release_timestamp_utc"] < end)]

    if window.empty:
        return 1.0

    high_count = int((window["importance"] == "high").sum())
    med_count = int((window["importance"] == "medium").sum())

    reduction = 0.0
    if high_count > 0:
        reduction += ANALYSIS_EVENT_RISK_REDUCTION_MIN
        reduction += min(ANALYSIS_EVENT_RISK_REDUCTION_MAX - ANALYSIS_EVENT_RISK_REDUCTION_MIN, 0.05 * max(high_count - 1, 0))
    elif med_count >= 2:
        reduction += 0.10

    reduction = float(np.clip(reduction, 0.0, ANALYSIS_EVENT_RISK_REDUCTION_MAX))
    return float(np.clip(1.0 - reduction, 0.0, 1.0))


def macro_coverage_diagnostics(macro_df: pd.DataFrame) -> Dict:
    if macro_df.empty:
        return {"rows": 0, "days": 0, "regions": {}, "importance": {}}

    days = pd.to_datetime(macro_df["release_timestamp_utc"], errors="coerce", utc=True).dt.date
    return {
        "rows": int(len(macro_df)),
        "days": int(days.nunique()),
        "regions": macro_df["region"].value_counts().to_dict(),
        "importance": macro_df["importance"].value_counts().to_dict(),
    }
