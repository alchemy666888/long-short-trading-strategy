from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from long_short_config import ANALYSIS_MIN_REPORT_RELIABILITY, ANALYSIS_MIN_SOURCES_PER_CATALYST


REQUIRED_SECTIONS = [
    "macro_summary",
    "regional_drivers",
    "asset_catalysts",
    "historical_analogs",
    "sentiment_money_flow",
    "scenario_map",
    "trade_ideas",
]


def _section_populated(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _sections_completeness(report: Dict) -> Tuple[float, List[str]]:
    missing = [section for section in REQUIRED_SECTIONS if not _section_populated(report.get(section))]
    score = (len(REQUIRED_SECTIONS) - len(missing)) / len(REQUIRED_SECTIONS)
    return float(score), missing


def _source_depth(
    report: Dict,
    min_sources_per_catalyst: int,
) -> Tuple[float, bool, Dict[str, int], Dict[str, Dict[str, float]], List[str], float]:
    counts = report.get("source_counts_by_catalyst", {})
    if not isinstance(counts, dict) or not counts:
        return 0.0, False, {}, {}, ["missing_source_counts"], 0.0

    normalized = {str(k): int(v) for k, v in counts.items()}
    min_count = min(normalized.values()) if normalized else 0
    avg_count = float(np.mean(list(normalized.values()))) if normalized else 0.0

    source_diversity_raw = report.get("source_diversity_by_catalyst", {})
    normalized_diversity: Dict[str, Dict[str, float]] = {}
    diversity_failures: List[str] = []

    if isinstance(source_diversity_raw, dict):
        for catalyst, payload in source_diversity_raw.items():
            if not isinstance(payload, dict):
                continue
            unique_sources = float(payload.get("unique_sources", 0.0))
            max_source_share = float(payload.get("max_source_share", 1.0))
            normalized_diversity[str(catalyst)] = {
                "unique_sources": unique_sources,
                "max_source_share": max_source_share,
            }

    for catalyst in normalized.keys():
        payload = normalized_diversity.get(catalyst, {})
        unique_sources = float(payload.get("unique_sources", 0.0))
        max_source_share = float(payload.get("max_source_share", 1.0))

        if unique_sources < min_sources_per_catalyst:
            diversity_failures.append(f"{catalyst}:unique_sources<{min_sources_per_catalyst}")
        if max_source_share > 0.70:
            diversity_failures.append(f"{catalyst}:max_source_share>{0.70:.2f}")

    depth_score = float(np.clip(avg_count / max(min_sources_per_catalyst, 1), 0.0, 1.0))
    diversity_score = float(np.clip(1.0 - (len(diversity_failures) / max(len(normalized), 1)), 0.0, 1.0))

    source_count_gate = min_count >= min_sources_per_catalyst
    gate_pass = source_count_gate and (len(diversity_failures) == 0)
    blended_score = (0.70 * depth_score) + (0.30 * diversity_score)
    return blended_score, gate_pass, normalized, normalized_diversity, diversity_failures, diversity_score


def _scenario_probability_checks(report: Dict) -> Tuple[float, bool, List[str], Dict[str, float]]:
    scenarios = report.get("scenario_map", {})
    if not isinstance(scenarios, dict) or not scenarios:
        return 0.0, False, ["missing_scenario_map"], {}

    errors = []
    sums: Dict[str, float] = {}
    valid_count = 0

    for group, payload in scenarios.items():
        if not isinstance(payload, dict):
            errors.append(f"{group}:invalid_payload")
            continue

        base = float(payload.get("base", np.nan))
        bull = float(payload.get("bull", np.nan))
        bear = float(payload.get("bear", np.nan))

        if any(np.isnan(x) for x in [base, bull, bear]):
            errors.append(f"{group}:missing_probs")
            continue

        total = base + bull + bear
        sums[str(group)] = float(total)
        if abs(total - 1.0) <= 0.02:
            valid_count += 1
        else:
            errors.append(f"{group}:sum={total:.4f}")

    score = valid_count / max(len(scenarios), 1)
    return float(score), len(errors) == 0, errors, sums


def _idea_invalidation_checks(report: Dict) -> Tuple[float, bool]:
    ideas = report.get("trade_ideas", [])
    if not isinstance(ideas, list) or not ideas:
        return 0.0, False

    good = 0
    for idea in ideas:
        if not isinstance(idea, dict):
            continue
        invalidation = idea.get("invalidation")
        if isinstance(invalidation, str) and invalidation.strip():
            good += 1

    ratio = good / len(ideas)
    return float(ratio), bool(good == len(ideas))


def _freshness_check(report: Dict) -> Tuple[float, bool]:
    trading_day = pd.to_datetime(report.get("trading_day"), errors="coerce")
    generated_at = pd.to_datetime(report.get("generated_at_utc"), errors="coerce")

    if pd.isna(trading_day) or pd.isna(generated_at):
        return 0.0, False

    if generated_at.tzinfo is None:
        generated_at = generated_at.tz_localize("UTC")
    else:
        generated_at = generated_at.tz_convert("UTC")

    if trading_day.tzinfo is not None:
        trading_day = trading_day.tz_convert(generated_at.tz)

    is_same_day = generated_at.date() == trading_day.date()
    return (1.0 if is_same_day else 0.0), bool(is_same_day)


def evaluate_report_quality(
    report: Dict,
    min_sources_per_catalyst: int = ANALYSIS_MIN_SOURCES_PER_CATALYST,
) -> Dict:
    completeness_score, missing_sections = _sections_completeness(report)
    (
        source_depth_score,
        source_gate_pass,
        source_counts,
        source_diversity,
        source_diversity_failures,
        source_diversity_score,
    ) = _source_depth(report, min_sources_per_catalyst=min_sources_per_catalyst)
    scenario_score, scenario_gate_pass, scenario_errors, scenario_sums = _scenario_probability_checks(report)
    invalidation_score, invalidation_gate_pass = _idea_invalidation_checks(report)
    freshness_score, freshness_gate_pass = _freshness_check(report)

    contradiction_count = int(report.get("contradiction_count", 0) or 0)
    contradiction_penalty = float(np.clip(0.15 * contradiction_count, 0.0, 0.45))

    raw_q = (
        (0.25 * completeness_score)
        + (0.25 * source_depth_score)
        + (0.20 * scenario_score)
        + (0.15 * invalidation_score)
        + (0.15 * freshness_score)
    )
    q_t = float(np.clip(raw_q - contradiction_penalty, 0.0, 1.0))

    report_valid = (
        len(missing_sections) == 0
        and source_gate_pass
        and scenario_gate_pass
        and invalidation_gate_pass
        and freshness_gate_pass
    )

    reasons: List[str] = []
    if missing_sections:
        reasons.append(f"missing_sections={','.join(missing_sections)}")
    if not source_gate_pass:
        reasons.append("insufficient_sources")
    if source_diversity_failures:
        reasons.append(f"insufficient_source_diversity={';'.join(source_diversity_failures)}")
    if not scenario_gate_pass:
        reasons.append(f"scenario_probabilities={';'.join(scenario_errors)}")
    if not invalidation_gate_pass:
        reasons.append("missing_trade_invalidation")
    if not freshness_gate_pass:
        reasons.append("stale_report")

    return {
        "report_valid": bool(report_valid),
        "q_t": q_t,
        "conservative_mode": bool(q_t < ANALYSIS_MIN_REPORT_RELIABILITY),
        "components": {
            "completeness": float(completeness_score),
            "source_depth": float(source_depth_score),
            "source_diversity": float(source_diversity_score),
            "scenario_consistency": float(scenario_score),
            "idea_invalidation": float(invalidation_score),
            "freshness": float(freshness_score),
            "contradiction_penalty": float(contradiction_penalty),
        },
        "gates": {
            "sections_complete": len(missing_sections) == 0,
            "source_depth": bool(source_gate_pass),
            "source_diversity": len(source_diversity_failures) == 0,
            "scenario_probabilities": bool(scenario_gate_pass),
            "idea_invalidation": bool(invalidation_gate_pass),
            "freshness": bool(freshness_gate_pass),
        },
        "reason_codes": reasons,
        "source_counts_by_catalyst": source_counts,
        "source_diversity_by_catalyst": source_diversity,
        "source_diversity_failures": source_diversity_failures,
        "scenario_probability_sums": scenario_sums,
    }
