import os
from pathlib import Path
import time
from typing import Dict, List, Optional

import pandas as pd
import requests

EASTERN_TZ = "US/Eastern"
UTC_TZ = "UTC"
DEFAULT_RETRY_ATTEMPTS = 8
DEFAULT_RETRY_BASE_SECONDS = 5


class PolygonError(RuntimeError):
    pass


def _get_api_key() -> str:
    key = os.getenv("POLYGON_API_KEY")
    if key:
        return key

    # Allow loading secrets from a local .env file without extra dependencies.
    env_candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent / ".env",
    ]
    for env_path in env_candidates:
        loaded = _read_key_from_env_file(env_path=env_path, key_name="POLYGON_API_KEY")
        if loaded:
            os.environ["POLYGON_API_KEY"] = loaded
            return loaded

    if not key:
        searched = ", ".join(str(p) for p in env_candidates)
        raise PolygonError(
            "POLYGON_API_KEY environment variable is not set. "
            "Set it in your shell or .env file before running the data pipeline. "
            f"Searched .env paths: {searched}"
        )
    return key


def _read_key_from_env_file(env_path: Path, key_name: str) -> Optional[str]:
    if not env_path.exists() or not env_path.is_file():
        return None

    try:
        content = env_path.read_text(encoding="utf-8")
    except OSError:
        return None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue

        lhs, rhs = line.split("=", 1)
        if lhs.strip() != key_name:
            continue

        value = rhs.strip()
        if value.startswith(("\"", "'")) and value.endswith(("\"", "'")) and len(value) >= 2:
            value = value[1:-1]
        return value or None

    return None


def fetch_polygon_aggregates(
    ticker: str,
    multiplier: int,
    timespan: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    chunk_days: Optional[int] = None,
) -> pd.DataFrame:
    """
    Fetch aggregated bars from Polygon.io /v2/aggs/ticker/{ticker}/range/...

    Returns a DataFrame with columns: Open, High, Low, Close, Volume.
    All timestamps converted to US/Eastern.
    """
    api_key = _get_api_key()

    def _to_utc_timestamp(value: Optional[str], fallback: pd.Timestamp) -> pd.Timestamp:
        if value is None:
            return fallback
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            return ts.tz_localize(UTC_TZ)
        return ts.tz_convert(UTC_TZ)

    now_utc = pd.Timestamp.utcnow()
    end_dt = _to_utc_timestamp(end, now_utc)
    start_dt = _to_utc_timestamp(start, end_dt - pd.Timedelta(days=730))

    if end_dt < start_dt:
        raise PolygonError(
            f"Invalid date range for {ticker}: start={start_dt} is after end={end_dt}"
        )

    if chunk_days is None:
        # Keep 5-minute 24/7 assets below 50k bars per call while minimizing request count.
        # 160 days * 288 bars/day = 46080 bars.
        chunk_days = 160 if timespan == "minute" else 180

    all_results: List[Dict] = []
    cursor = start_dt.normalize()
    range_end = end_dt.normalize()

    while cursor <= range_end:
        chunk_end = min(cursor + pd.Timedelta(days=chunk_days - 1), range_end)
        start_str = cursor.strftime("%Y-%m-%d")
        end_str = chunk_end.strftime("%Y-%m-%d")

        range_results = _fetch_polygon_range(
            ticker=ticker,
            multiplier=multiplier,
            timespan=timespan,
            start_str=start_str,
            end_str=end_str,
            api_key=api_key,
        )
        all_results.extend(range_results)
        cursor = chunk_end + pd.Timedelta(days=1)

    results = all_results
    if not results:
        return pd.DataFrame()

    records = []
    for r in results:
        # t: timestamp in ms since epoch (UTC)
        ts = pd.to_datetime(r["t"], unit="ms", utc=True).tz_convert(EASTERN_TZ)
        records.append(
            {
                "timestamp": ts,
                "Open": r.get("o"),
                "High": r.get("h"),
                "Low": r.get("l"),
                "Close": r.get("c"),
                "Volume": r.get("v"),
            }
        )

    df = pd.DataFrame.from_records(records).set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df = df[(df.index >= start_dt.tz_convert(EASTERN_TZ)) & (df.index <= end_dt.tz_convert(EASTERN_TZ))]
    return df


def _fetch_polygon_range(
    ticker: str,
    multiplier: int,
    timespan: str,
    start_str: str,
    end_str: str,
    api_key: str,
) -> List[Dict]:
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/"
        f"{multiplier}/{timespan}/{start_str}/{end_str}"
    )
    params: Dict[str, str] = {
        "adjusted": "true",
        "sort": "asc",
        "limit": "50000",
        "apiKey": api_key,
    }

    out: List[Dict] = []
    while True:
        payload = _request_json_with_retries(url=url, params=params)
        out.extend(payload.get("results", []))

        next_url = payload.get("next_url")
        if not next_url:
            break

        # next_url omits auth params; only apiKey is needed for continuation.
        url = next_url
        params = {"apiKey": api_key}

    return out


def _request_json_with_retries(url: str, params: Dict[str, str]) -> Dict:
    attempts = 0
    while True:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json()

        retryable = resp.status_code == 429 or 500 <= resp.status_code <= 599
        if not retryable or attempts >= DEFAULT_RETRY_ATTEMPTS:
            raise PolygonError(f"Polygon error {resp.status_code}: {resp.text}")

        retry_after_header = resp.headers.get("Retry-After")
        retry_after_seconds: Optional[int] = None
        if retry_after_header and retry_after_header.isdigit():
            retry_after_seconds = int(retry_after_header)

        if retry_after_seconds is None:
            retry_after_seconds = min(60, DEFAULT_RETRY_BASE_SECONDS * (2 ** attempts))

        time.sleep(max(1, retry_after_seconds))
        attempts += 1


def download_polygon_5m(
    ticker: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """
    Convenience wrapper for 5-minute bars from Polygon (multiplier=5, timespan=minute).
    """
    return fetch_polygon_aggregates(
        ticker=ticker,
        multiplier=5,
        timespan="minute",
        start=start,
        end=end,
        chunk_days=160,
    )
