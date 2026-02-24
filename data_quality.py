from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

from long_short_config import (
    ASSETS,
    QUALITY_4H_COVERAGE_THRESHOLD,
    QUALITY_BREADTH_MAX_CATEGORY_SHARE,
    QUALITY_BREADTH_MIN_CATEGORIES,
    QUALITY_BREADTH_MIN_ELIGIBLE,
    QUALITY_DAILY_COVERAGE_THRESHOLD,
    QUALITY_FEATURE_COMPLETENESS_THRESHOLD,
)


def _asset_classes() -> Dict[str, str]:
    return {asset: str(meta.get("asset_class", "unknown")) for asset, meta in ASSETS.items()}


def _median_interval_hours(valid_index: pd.DatetimeIndex) -> float:
    if len(valid_index) < 2:
        return np.nan
    diffs = valid_index.to_series().diff().dropna().dt.total_seconds() / 3600.0
    if diffs.empty:
        return np.nan
    return float(diffs.median())


def _rolling_coverage(valid: pd.Series, expected: pd.Series, window: int) -> float:
    expected = expected.fillna(False).astype(bool)
    valid = valid.fillna(False).astype(bool)

    numerator = (valid & expected).astype(float).rolling(window=window, min_periods=max(5, window // 4)).sum()
    denominator = expected.astype(float).rolling(window=window, min_periods=max(5, window // 4)).sum()
    ratio = (numerator / denominator.replace(0.0, np.nan)).dropna()

    if ratio.empty:
        total_den = float(expected.sum())
        if total_den <= 0:
            return 0.0
        return float((valid & expected).sum() / total_den)

    return float(ratio.min())


def _feature_completeness(closes_1d: pd.Series) -> float:
    price = closes_1d.astype(float).dropna()
    if price.empty:
        return 0.0
    log_price = np.log(price.where(price > 0.0))

    ret20 = log_price - log_price.shift(20)
    ret60 = log_price - log_price.shift(60)
    ret120 = log_price - log_price.shift(120)
    ret5 = log_price - log_price.shift(5)

    daily_ret = price.pct_change(fill_method=None)
    ewma_vol = daily_ret.ewm(halflife=20, min_periods=20).std()

    weekly = price.resample("W-FRI").last()
    weekly_log = np.log(weekly.where(weekly > 0.0))

    weekly_len = len(weekly)
    fast_window = min(20, max(6, weekly_len // 2))
    slow_window = min(40, max(fast_window + 4, (2 * weekly_len) // 3))

    ret26w = weekly_log - weekly_log.shift(26)
    ret52w = weekly_log - weekly_log.shift(52)
    ma20w = weekly.rolling(fast_window, min_periods=max(4, fast_window // 2)).mean()
    ma40w = weekly.rolling(slow_window, min_periods=max(6, slow_window // 2)).mean()
    trend_weekly = (ma20w / ma40w) - 1.0

    daily_stack = pd.concat([ret20, ret60, ret120, ret5, ewma_vol], axis=1)

    if len(weekly) >= 60:
        weekly_stack = pd.concat([ret26w, ret52w, trend_weekly], axis=1)
        weekly_eval = weekly_stack.iloc[52:]
    elif len(weekly) >= 30:
        weekly_stack = pd.concat([ret26w, trend_weekly], axis=1)
        weekly_eval = weekly_stack.iloc[26:]
    else:
        weekly_stack = pd.concat([trend_weekly], axis=1)
        weekly_eval = weekly_stack.iloc[20:]

    daily_ready = daily_stack.notna().all(axis=1)
    if daily_ready.any():
        daily_complete = float(daily_ready.loc[daily_ready[daily_ready].index[0] :].mean())
    else:
        daily_complete = 0.0

    weekly_ready = weekly_eval.notna().all(axis=1)
    if weekly_ready.any():
        weekly_complete = float(weekly_ready.loc[weekly_ready[weekly_ready].index[0] :].mean())
    else:
        weekly_complete = 0.0

    return float(min(daily_complete, weekly_complete))


def build_data_quality_report(
    closes_1d: pd.DataFrame,
    closes_4h: pd.DataFrame,
    expected_1d: pd.DataFrame,
    expected_4h: pd.DataFrame,
    output_path: Path,
) -> Dict:
    classes = _asset_classes()

    per_asset: Dict[str, Dict] = {}
    eligible_assets = []

    for asset in closes_1d.columns:
        s1d = closes_1d[asset]
        s4h = closes_4h.get(asset, pd.Series(index=closes_4h.index, dtype=float))

        e1d = expected_1d.get(asset, pd.Series(False, index=closes_1d.index, dtype=bool)).reindex(closes_1d.index, fill_value=False)
        e4h = expected_4h.get(asset, pd.Series(False, index=closes_4h.index, dtype=bool)).reindex(closes_4h.index, fill_value=False)

        idx_1d = s1d[s1d.notna()].index
        idx_4h = s4h[s4h.notna()].index

        freq_1d = _median_interval_hours(idx_1d)
        freq_4h = _median_interval_hours(idx_4h)
        freq_pass_1d = bool(np.isnan(freq_1d) or (18.0 <= freq_1d <= 36.0))
        freq_pass_4h = bool(np.isnan(freq_4h) or (3.0 <= freq_4h <= 8.0))

        cov_1d = _rolling_coverage(s1d.notna(), e1d, window=90)
        cov_4h = _rolling_coverage(s4h.notna(), e4h, window=180)
        cov_pass_1d = cov_1d >= QUALITY_DAILY_COVERAGE_THRESHOLD
        cov_pass_4h = cov_4h >= QUALITY_4H_COVERAGE_THRESHOLD

        feature_complete = _feature_completeness(s1d)
        feature_pass = feature_complete >= QUALITY_FEATURE_COMPLETENESS_THRESHOLD

        reasons = []
        if not freq_pass_1d:
            reasons.append(f"daily_frequency_median_hours={freq_1d:.2f}")
        if not freq_pass_4h:
            reasons.append(f"4h_frequency_median_hours={freq_4h:.2f}")
        if not cov_pass_1d:
            reasons.append(f"daily_coverage_min_90d={cov_1d:.3f}")
        if not cov_pass_4h:
            reasons.append(f"4h_coverage_min_30d={cov_4h:.3f}")
        if not feature_pass:
            reasons.append(f"feature_completeness={feature_complete:.3f}")

        eligible = len(reasons) == 0
        if eligible:
            eligible_assets.append(asset)

        per_asset[asset] = {
            "asset_class": classes.get(asset, "unknown"),
            "frequency_median_hours": {
                "1d": None if np.isnan(freq_1d) else round(freq_1d, 3),
                "4h": None if np.isnan(freq_4h) else round(freq_4h, 3),
            },
            "coverage_min": {
                "1d_90d": round(cov_1d, 4),
                "4h_30d": round(cov_4h, 4),
            },
            "feature_completeness": round(feature_complete, 4),
            "eligible": eligible,
            "reasons": reasons,
        }

    class_counter = Counter(classes[a] for a in eligible_assets)
    eligible_total = len(eligible_assets)
    category_count = len(class_counter)
    max_category_share = (max(class_counter.values()) / eligible_total) if eligible_total else 1.0

    breadth_pass = (
        eligible_total >= QUALITY_BREADTH_MIN_ELIGIBLE
        and category_count >= QUALITY_BREADTH_MIN_CATEGORIES
        and max_category_share <= QUALITY_BREADTH_MAX_CATEGORY_SHARE
    )

    # Hard gate is portfolio-level breadth integrity. Ineligible names are excluded from trading.
    hard_pass = breadth_pass

    report = {
        "hard_pass": hard_pass,
        "breadth_pass": breadth_pass,
        "breadth": {
            "eligible_assets": eligible_total,
            "eligible_categories": category_count,
            "max_category_share": round(max_category_share, 4),
            "eligible_assets_list": sorted(eligible_assets),
            "class_counts": dict(class_counter),
        },
        "thresholds": {
            "daily_coverage_90d": QUALITY_DAILY_COVERAGE_THRESHOLD,
            "4h_coverage_30d": QUALITY_4H_COVERAGE_THRESHOLD,
            "feature_completeness": QUALITY_FEATURE_COMPLETENESS_THRESHOLD,
            "min_eligible_assets": QUALITY_BREADTH_MIN_ELIGIBLE,
            "min_categories": QUALITY_BREADTH_MIN_CATEGORIES,
            "max_category_share": QUALITY_BREADTH_MAX_CATEGORY_SHARE,
        },
        "per_asset": per_asset,
        "exclusions": {
            asset: detail["reasons"]
            for asset, detail in per_asset.items()
            if not detail["eligible"]
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def load_data_quality_report(path: Path) -> Dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
