import os
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests

EASTERN_TZ = "US/Eastern"


class PolygonError(RuntimeError):
    pass


def _get_api_key() -> str:
    key = os.getenv("POLYGON_API_KEY")
    if not key:
        raise PolygonError(
            "POLYGON_API_KEY environment variable is not set. "
            "Set it to your Polygon.io API key before running the data pipeline."
        )
    return key


def fetch_polygon_aggregates(
    ticker: str,
    multiplier: int,
    timespan: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch aggregated bars from Polygon.io /v2/aggs/ticker/{ticker}/range/...

    Returns a DataFrame with columns: Open, High, Low, Close, Volume.
    All timestamps converted to US/Eastern.
    """
    api_key = _get_api_key()

    now = datetime.utcnow()
    if end:
        end_dt = datetime.fromisoformat(end)
    else:
        end_dt = now
    if start:
        start_dt = datetime.fromisoformat(start)
    else:
        # Default to ~2 years back
        start_dt = end_dt - timedelta(days=730)

    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/"
        f"{multiplier}/{timespan}/{start_str}/{end_str}"
    )
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50000,
        "apiKey": api_key,
    }

    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code != 200:
        raise PolygonError(f"Polygon error {resp.status_code}: {resp.text}")

    data = resp.json()
    results = data.get("results", [])
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
    return df


def download_polygon_5m(
    ticker: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """
    Convenience wrapper for 5-minute bars from Polygon (multiplier=5, timespan=minute).
    """
    return fetch_polygon_aggregates(ticker=ticker, multiplier=5, timespan="minute", start=start, end=end)

