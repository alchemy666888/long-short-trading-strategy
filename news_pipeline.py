from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from long_short_config import ANALYSIS_NEWS_PATH


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


CATALYST_KEYWORDS: Dict[str, List[str]] = {
    "rates_inflation": ["cpi", "ppi", "inflation", "rates", "fed", "ecb", "boe", "yield"],
    "growth": ["gdp", "employment", "jobs", "pmi", "manufacturing", "retail sales", "growth"],
    "geopolitics": ["war", "tariff", "sanction", "election", "conflict", "geopolitical"],
    "energy": ["opec", "oil", "gas", "inventory", "eia", "supply"],
    "crypto_reg": ["sec", "etf", "regulation", "exchange", "stablecoin", "crypto"],
    "equity_micro": ["earnings", "guidance", "buyback", "downgrade", "upgrade", "valuation"],
}


ASSET_CLASS_KEYWORDS: Dict[str, List[str]] = {
    "stock": ["equity", "stock", "s&p", "nasdaq", "earnings", "tech"],
    "forex": ["fx", "usd", "eur", "aud", "currency", "dollar"],
    "metal": ["gold", "silver", "copper", "metals", "xau", "xag"],
    "crypto": ["btc", "bitcoin", "eth", "ethereum", "sol", "xrp", "crypto"],
}


REGION_KEYWORDS: Dict[str, List[str]] = {
    "US": ["us", "federal reserve", "washington", "wall street", "new york"],
    "Europe": ["euro", "ecb", "france", "germany", "uk", "boe"],
    "Asia-Pacific": ["china", "japan", "australia", "apac", "asia"],
    "EM": ["emerging", "latam", "brazil", "india", "turkey", "south africa"],
}


def _ensure_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def _parse_assets(value: object) -> List[str]:
    if isinstance(value, list):
        return [str(v).strip().upper() for v in value if str(v).strip()]
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []

    text = str(value).strip()
    if not text:
        return []

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(v).strip().upper() for v in parsed if str(v).strip()]
        except Exception:
            pass

    return [part.strip().upper() for part in text.split(",") if part.strip()]


def _match_label(text: str, table: Dict[str, List[str]], fallback: str) -> str:
    text_l = text.lower()
    best = fallback
    best_hits = 0
    for label, keywords in table.items():
        hits = sum(1 for kw in keywords if kw in text_l)
        if hits > best_hits:
            best_hits = hits
            best = label
    return best


def _headline_key(headline: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", headline.lower()).strip()
    return re.sub(r"\s+", " ", normalized)


def _load_jsonl(path: Path) -> pd.DataFrame:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return pd.DataFrame(rows)


def _load_json(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return pd.DataFrame(payload)
    if isinstance(payload, dict) and "records" in payload and isinstance(payload["records"], list):
        return pd.DataFrame(payload["records"])
    raise ValueError(f"Unsupported JSON format in {path}")


def _load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def normalize_news_records(news_df: pd.DataFrame) -> pd.DataFrame:
    if news_df.empty:
        return pd.DataFrame(columns=NEWS_COLUMNS)

    frame = news_df.copy()

    for col in NEWS_COLUMNS:
        if col not in frame.columns:
            frame[col] = np.nan

    frame["published_at_utc"] = _ensure_utc(frame["published_at_utc"])
    frame["ingested_at_utc"] = _ensure_utc(frame["ingested_at_utc"]).fillna(frame["published_at_utc"])

    frame["headline"] = frame["headline"].astype(str).fillna("")
    frame["body"] = frame["body"].astype(str).fillna("")
    frame["source"] = frame["source"].fillna("unknown").astype(str)
    frame["language"] = frame["language"].fillna("en").astype(str)

    frame["assets"] = frame["assets"].apply(_parse_assets)

    inferred_class = []
    inferred_region = []
    inferred_catalyst = []

    for _, row in frame.iterrows():
        text = f"{row['headline']} {row['body']}"
        inferred_class.append(_match_label(text, ASSET_CLASS_KEYWORDS, fallback="macro"))
        inferred_region.append(_match_label(text, REGION_KEYWORDS, fallback="US"))
        inferred_catalyst.append(_match_label(text, CATALYST_KEYWORDS, fallback="macro"))

    frame["asset_class"] = frame["asset_class"].fillna(pd.Series(inferred_class, index=frame.index)).astype(str)
    frame["region"] = frame["region"].fillna(pd.Series(inferred_region, index=frame.index)).astype(str)
    frame["catalyst_type"] = frame["catalyst_type"].fillna(pd.Series(inferred_catalyst, index=frame.index)).astype(str)

    if frame["sentiment_score"].isna().all():
        frame["sentiment_score"] = 0.0
    frame["sentiment_score"] = pd.to_numeric(frame["sentiment_score"], errors="coerce").fillna(0.0).clip(-1.0, 1.0)

    frame = frame.dropna(subset=["published_at_utc", "ingested_at_utc"]).copy()
    frame = frame.sort_values(["published_at_utc", "ingested_at_utc", "source"]).reset_index(drop=True)

    # Near-duplicate collapse by normalized headline + publication day.
    headline_key = frame["headline"].map(_headline_key)
    day_key = frame["published_at_utc"].dt.strftime("%Y-%m-%d")
    dedup_key = headline_key + "|" + day_key.fillna("")
    frame = frame.loc[~dedup_key.duplicated()].copy()

    return frame[NEWS_COLUMNS].reset_index(drop=True)


def load_historical_news(path: str = ANALYSIS_NEWS_PATH) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        return pd.DataFrame(columns=NEWS_COLUMNS)

    if file_path.suffix.lower() in {".jsonl", ".jl"}:
        raw = _load_jsonl(file_path)
    elif file_path.suffix.lower() == ".json":
        raw = _load_json(file_path)
    elif file_path.suffix.lower() in {".csv", ".txt"}:
        raw = _load_csv(file_path)
    else:
        raise ValueError(f"Unsupported news file extension: {file_path.suffix}")

    return normalize_news_records(raw)


def news_coverage_diagnostics(news_df: pd.DataFrame) -> Dict:
    if news_df.empty:
        return {
            "rows": 0,
            "days": 0,
            "sources": 0,
            "asset_classes": {},
            "regions": {},
            "catalysts": {},
        }

    days = pd.to_datetime(news_df["published_at_utc"], errors="coerce", utc=True).dt.date
    return {
        "rows": int(len(news_df)),
        "days": int(days.nunique()),
        "sources": int(news_df["source"].nunique()),
        "asset_classes": news_df["asset_class"].value_counts().to_dict(),
        "regions": news_df["region"].value_counts().to_dict(),
        "catalysts": news_df["catalyst_type"].value_counts().to_dict(),
    }
