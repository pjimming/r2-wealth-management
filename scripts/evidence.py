#!/usr/bin/env python3
"""Shared return-history evidence tiers for R2 product tools."""

from __future__ import annotations

from typing import Any


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
        "single_cap_pct": 0.10,
        "aggregate_cap_pct": 0.10,
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
        return float(text)
    except ValueError:
        return None


def reference_yield(
    return_3m: float | None,
    return_6m: float | None,
    return_1y: float | None,
) -> float | None:
    parts = [
        (return_3m, 0.5),
        (return_6m, 0.3),
        (return_1y, 0.2),
    ]
    available = [(value, weight) for value, weight in parts if value is not None]
    if not available:
        return None
    total_weight = sum(weight for _, weight in available)
    return round(
        sum(value * weight for value, weight in available) / total_weight,
        4,
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
    return "legacy" if all(
        value is None for value in (return_1m, return_3m, return_6m, return_1y)
    ) else "no_data"


def effective_reference_yield(
    return_3m: float | None,
    return_6m: float | None,
    return_1y: float | None,
    reported_reference: float | None,
    fallback_yield: float | None,
) -> float | None:
    computed = reference_yield(return_3m, return_6m, return_1y)
    if computed is not None:
        return computed
    if reported_reference is not None:
        return reported_reference
    return fallback_yield
