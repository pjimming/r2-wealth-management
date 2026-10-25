#!/usr/bin/env python3
"""Shared return-history and term-adjusted yield policy for R2 tools."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


POLICY_VERSION = "r2-term-yield-v1"
DEFAULT_FRONT_LOAD_SCHEME = "B"
MAX_SAFE_INTEGER = 9_007_199_254_740_991
HORIZON_ORDER = ("return_1m", "return_3m", "return_6m", "return_1y")
HORIZON_LABELS = {
    "return_1m": "1m",
    "return_3m": "3m",
    "return_6m": "6m",
    "return_1y": "1y",
}
BUCKET_WEIGHTS: dict[str, dict[str, float]] = {
    "cash": {
        "return_1m": 0.70,
        "return_3m": 0.30,
    },
    "short": {
        "return_1m": 0.20,
        "return_3m": 0.50,
        "return_6m": 0.30,
    },
    "medium": {
        "return_3m": 0.50,
        "return_6m": 0.30,
        "return_1y": 0.20,
    },
    "long": {
        "return_3m": 0.20,
        "return_6m": 0.40,
        "return_1y": 0.40,
    },
}
FRONT_LOAD_SCHEMES: dict[str, dict[str, dict[str, float] | None]] = {
    "A": {
        "short": {"threshold_pp": 1.0, "slope": 0.15, "cap": 0.25},
        "medium": {"threshold_pp": 1.0, "slope": 0.15, "cap": 0.25},
        "long": {"threshold_pp": 1.0, "slope": 0.15, "cap": 0.25},
    },
    "B": {
        "short": {"threshold_pp": 1.0, "slope": 0.15, "cap": 0.25},
        "medium": {"threshold_pp": 1.0, "slope": 0.15, "cap": 0.25},
        "long": {"threshold_pp": 1.5, "slope": 0.15, "cap": 0.25},
    },
    "C": {
        "short": {"threshold_pp": 1.0, "slope": 0.15, "cap": 0.25},
        "medium": {"threshold_pp": 1.0, "slope": 0.15, "cap": 0.25},
        "long": None,
    },
}

EVIDENCE_POLICIES: dict[str, dict[str, Any]] = {
    "full_1y": {
        "label": "完整 1Y",
        "scoring": True,
        "automatic": True,
        "single_cap_pct": None,
        "aggregate_cap_pct": None,
    },
    "six_month": {
        "label": "缺 1Y",
        "scoring": True,
        "automatic": True,
        "single_cap_pct": 0.10,
        "aggregate_cap_pct": 0.20,
    },
    "three_month": {
        "label": "仅 3M",
        "scoring": True,
        "automatic": True,
        "single_cap_pct": 0.10,
        "aggregate_cap_pct": 0.20,
    },
    "one_month": {
        "label": "新品观察",
        "scoring": False,
        "automatic": False,
        "single_cap_pct": 0.05,
        "aggregate_cap_pct": 0.05,
    },
    "no_data": {
        "label": "数据待补",
        "scoring": False,
        "automatic": False,
        "single_cap_pct": 0.0,
        "aggregate_cap_pct": 0.0,
    },
    "legacy": {
        "label": "旧格式",
        "scoring": True,
        "automatic": True,
        "single_cap_pct": None,
        "aggregate_cap_pct": None,
    },
}


def number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("%", "").replace(",", "")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def round_half_away_from_zero(value: float, digits: int = 4) -> float | None:
    """Match JavaScript Number rounding used by the workbench."""
    if not math.isfinite(value):
        return None
    factor = 10**digits
    rounded = math.floor(
        abs(value) * factor + 0.5 + 2.220446049250313e-16
    ) / factor
    if rounded == 0:
        return 0.0
    return math.copysign(rounded, value)


def bucket_for_term(term_days: Any) -> str:
    value = number_or_none(term_days)
    if (
        value is None
        or value < 0
        or value > MAX_SAFE_INTEGER
        or not value.is_integer()
    ):
        return "unknown"
    if value == 0:
        return "cash"
    if value <= 30:
        return "short"
    if value <= 100:
        return "medium"
    return "long"


def _normalized_weights(
    bucket: str,
    available_keys: list[str],
    bucket_weights: Mapping[str, Mapping[str, float]],
) -> dict[str, float]:
    weights = bucket_weights.get(bucket)
    if not weights:
        return {}
    total = sum(weights[key] for key in available_keys)
    if total <= 0:
        return {}
    return {
        key: round_half_away_from_zero(weights[key] / total, 10) or 0.0
        for key in available_keys
    }


def calculate_reference_yield(
    product: Mapping[str, Any] | None,
    *,
    bucket: str | None = None,
    bucket_weights: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, Any]:
    values = product or {}
    weights_by_bucket = bucket_weights or BUCKET_WEIGHTS
    resolved_bucket = bucket or bucket_for_term(values.get("term_days"))
    weights = weights_by_bucket.get(resolved_bucket)
    if not weights:
        return {
            "bucket": resolved_bucket,
            "status": "unavailable",
            "reason": "unknown_term",
            "value_pct": None,
            "raw_value_pct": None,
            "available_horizons": [],
            "missing_horizons": [],
            "weight_sum": 0,
            "defined_weights": {},
            "normalized_weights": {},
        }

    declared_keys = [key for key in HORIZON_ORDER if key in weights]
    available_keys = [
        key for key in declared_keys if number_or_none(values.get(key)) is not None
    ]
    missing_horizons = [
        HORIZON_LABELS[key]
        for key in declared_keys
        if key not in available_keys
    ]
    if not available_keys:
        return {
            "bucket": resolved_bucket,
            "status": "unavailable",
            "reason": "no_available_horizons",
            "value_pct": None,
            "raw_value_pct": None,
            "available_horizons": [],
            "missing_horizons": missing_horizons,
            "weight_sum": 0,
            "defined_weights": {
                key: weights[key] for key in declared_keys
            },
            "normalized_weights": {},
        }

    weight_sum = sum(weights[key] for key in available_keys)
    raw_value = (
        sum(
            number_or_none(values.get(key)) * weights[key]
            for key in available_keys
        )
        / weight_sum
    )
    return {
        "bucket": resolved_bucket,
        "status": "available",
        "reason": "partial_history" if missing_horizons else "complete_history",
        "value_pct": round_half_away_from_zero(raw_value),
        "raw_value_pct": raw_value,
        "available_horizons": [
            HORIZON_LABELS[key] for key in available_keys
        ],
        "missing_horizons": missing_horizons,
        "weight_sum": round_half_away_from_zero(weight_sum, 10),
        "defined_weights": {key: weights[key] for key in declared_keys},
        "normalized_weights": _normalized_weights(
            resolved_bucket,
            available_keys,
            weights_by_bucket,
        ),
    }


def divergence_penalty(product: Mapping[str, Any] | None) -> float:
    values = product or {}
    one_month = number_or_none(values.get("return_1m"))
    three_month = number_or_none(values.get("return_3m"))
    if one_month is None or three_month is None:
        return 0.0
    return 0.08 if one_month < three_month - 0.5 else 0.0


def front_load_deduction(
    bucket: str,
    product: Mapping[str, Any] | None,
    scheme: str = DEFAULT_FRONT_LOAD_SCHEME,
) -> float:
    values = product or {}
    rule = FRONT_LOAD_SCHEMES.get(scheme, {}).get(bucket)
    one_year = number_or_none(values.get("return_1y"))
    six_month = number_or_none(values.get("return_6m"))
    if not rule or one_year is None or six_month is None:
        return 0.0
    gap_pp = one_year - six_month
    if gap_pp <= rule["threshold_pp"]:
        return 0.0
    return min(rule["cap"], (gap_pp - rule["threshold_pp"]) * rule["slope"])


def history_bonus(history_months: Any) -> float:
    months = number_or_none(history_months)
    if months is None:
        return 0.0
    if months >= 24:
        return 0.03
    if months >= 18:
        return 0.015
    return 0.0


def calculate_yield_metrics(
    product: Mapping[str, Any] | None,
    *,
    front_load_scheme: str = DEFAULT_FRONT_LOAD_SCHEME,
    bucket: str | None = None,
    bucket_weights: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, Any]:
    values = product or {}
    reference = calculate_reference_yield(
        values,
        bucket=bucket,
        bucket_weights=bucket_weights,
    )
    scoring_bucket = reference["bucket"] in {"short", "medium", "long"}
    if reference["status"] != "available" or not scoring_bucket:
        return {
            "bucket": reference["bucket"],
            "reference": reference,
            "reference_yield_pct": reference["value_pct"],
            "reference_yield_status": reference["status"],
            "reference_yield_reason": reference["reason"],
            "reference_available_horizons": reference["available_horizons"],
            "reference_normalized_weights": reference["normalized_weights"],
            "weighted_yield_pct": reference["value_pct"],
            "observation_score": None,
            "selection_score": None,
            "divergence_penalty_points": 0.0,
            "front_load_penalty_points": 0.0,
            "history_bonus_points": 0.0,
            "yield_policy_version": POLICY_VERSION,
        }

    divergence = divergence_penalty(values)
    observation_raw = reference["raw_value_pct"] - divergence
    front_load = front_load_deduction(
        reference["bucket"],
        values,
        front_load_scheme,
    )
    bonus = history_bonus(values.get("history_months"))
    return {
        "bucket": reference["bucket"],
        "reference": reference,
        "reference_yield_pct": reference["value_pct"],
        "reference_yield_status": reference["status"],
        "reference_yield_reason": reference["reason"],
        "reference_available_horizons": reference["available_horizons"],
        "reference_normalized_weights": reference["normalized_weights"],
        "weighted_yield_pct": reference["value_pct"],
        "observation_score": round_half_away_from_zero(observation_raw),
        "selection_score": round_half_away_from_zero(
            observation_raw - front_load + bonus
        ),
        "divergence_penalty_points": divergence,
        "front_load_penalty_points": front_load,
        "history_bonus_points": bonus,
        "yield_policy_version": POLICY_VERSION,
    }


def reference_yield(
    product: Mapping[str, Any] | None,
    *,
    bucket: str | None = None,
    bucket_weights: Mapping[str, Mapping[str, float]] | None = None,
) -> float | None:
    return calculate_reference_yield(
        product,
        bucket=bucket,
        bucket_weights=bucket_weights,
    )["value_pct"]


def effective_reference_yield(
    product: Mapping[str, Any] | None,
    *,
    reported_reference: Any = None,
    fallback_yield: Any = None,
    allow_legacy: bool = False,
) -> float | None:
    """Return the term-adjusted value, or an explicit legacy fallback only."""
    metrics = calculate_yield_metrics(product)
    if metrics["reference_yield_status"] == "available":
        return metrics["reference_yield_pct"]
    if not allow_legacy:
        return None
    reported = number_or_none(reported_reference)
    if reported is not None:
        return round_half_away_from_zero(reported)
    fallback = number_or_none(fallback_yield)
    return (
        round_half_away_from_zero(fallback)
        if fallback is not None
        else None
    )


def evidence_tier(
    history_months: float | None,
    return_1m: float | None,
    return_3m: float | None,
    return_6m: float | None,
    return_1y: float | None,
    declared: str = "",
) -> str:
    declared = (declared or "").strip()
    if history_months is not None and history_months < 3:
        return "one_month" if return_1m is not None else "no_data"
    if (
        return_1y is not None
        and return_3m is not None
        and return_6m is not None
        and (history_months is None or history_months >= 12)
    ):
        return "full_1y"
    if return_3m is not None and return_6m is not None:
        return "six_month"
    if return_3m is not None:
        return "three_month"
    if return_1m is not None:
        return "one_month"
    if declared in EVIDENCE_POLICIES:
        return declared
    return (
        "legacy"
        if all(
            value is None
            for value in (return_1m, return_3m, return_6m, return_1y)
        )
        else "no_data"
    )
