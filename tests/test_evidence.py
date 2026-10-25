from __future__ import annotations

import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import evidence  # noqa: E402


class TermBoundaryTests(unittest.TestCase):
    def test_term_boundaries_match_workbench(self) -> None:
        cases = (
            (None, "unknown"),
            (-1, "unknown"),
            (1.5, "unknown"),
            (float("nan"), "unknown"),
            (float("inf"), "unknown"),
            (9_007_199_254_740_992, "unknown"),
            (0, "cash"),
            (1, "short"),
            (30, "short"),
            (31, "medium"),
            (100, "medium"),
            (101, "long"),
            ("30", "short"),
            ("31.0", "medium"),
        )
        for term_days, expected in cases:
            with self.subTest(term_days=term_days):
                self.assertEqual(
                    evidence.bucket_for_term(term_days),
                    expected,
                )


class ReferenceYieldTests(unittest.TestCase):
    def test_four_buckets_use_frozen_weights(self) -> None:
        cases = (
            (
                "cash",
                {"return_1m": 2.2, "return_3m": 3.3},
                "complete_history",
                2.53,
                ["1m", "3m"],
                [],
                1,
            ),
            (
                "short",
                {"return_1m": 2, "return_3m": 3, "return_6m": 4},
                "complete_history",
                3.1,
                ["1m", "3m", "6m"],
                [],
                1,
            ),
            (
                "medium",
                {"return_3m": 2, "return_6m": 3, "return_1y": 4},
                "complete_history",
                2.7,
                ["3m", "6m", "1y"],
                [],
                1,
            ),
            (
                "long",
                {"return_3m": 2, "return_6m": 3, "return_1y": 4},
                "complete_history",
                3.2,
                ["3m", "6m", "1y"],
                [],
                1,
            ),
        )
        for bucket, returns, reason, value, available, missing, weight in cases:
            with self.subTest(bucket=bucket):
                result = evidence.calculate_reference_yield(
                    returns,
                    bucket=bucket,
                )
                self.assertEqual(result["status"], "available")
                self.assertEqual(result["reason"], reason)
                self.assertEqual(result["value_pct"], value)
                self.assertEqual(result["available_horizons"], available)
                self.assertEqual(result["missing_horizons"], missing)
                self.assertEqual(result["weight_sum"], weight)

    def test_missing_windows_are_renormalized(self) -> None:
        cases = (
            (
                "cash",
                {"return_3m": 3},
                3,
                ["3m"],
                ["1m"],
                0.3,
                {"return_3m": 1},
            ),
            (
                "short",
                {"return_3m": 3, "return_6m": 4},
                3.375,
                ["3m", "6m"],
                ["1m"],
                0.8,
                {"return_3m": 0.625, "return_6m": 0.375},
            ),
            (
                "medium",
                {"return_3m": 2, "return_1y": 4},
                2.5714,
                ["3m", "1y"],
                ["6m"],
                0.7,
                {"return_3m": 0.7142857143, "return_1y": 0.2857142857},
            ),
            (
                "long",
                {"return_6m": 3, "return_1y": 4},
                3.5,
                ["6m", "1y"],
                ["3m"],
                0.8,
                {"return_6m": 0.5, "return_1y": 0.5},
            ),
        )
        for (
            bucket,
            returns,
            value,
            available,
            missing,
            weight,
            normalized,
        ) in cases:
            with self.subTest(bucket=bucket):
                result = evidence.calculate_reference_yield(
                    returns,
                    bucket=bucket,
                )
                self.assertEqual(result["reason"], "partial_history")
                self.assertEqual(result["value_pct"], value)
                self.assertEqual(result["available_horizons"], available)
                self.assertEqual(result["missing_horizons"], missing)
                self.assertEqual(result["weight_sum"], weight)
                self.assertEqual(result["normalized_weights"], normalized)
                self.assertAlmostEqual(
                    sum(result["normalized_weights"].values()),
                    1.0,
                    places=10,
                )

    def test_zero_is_valid_and_unavailable_is_explicit(self) -> None:
        zero = evidence.calculate_reference_yield(
            {"return_1m": 0, "return_3m": 0},
            bucket="cash",
        )
        self.assertEqual(zero["status"], "available")
        self.assertEqual(zero["value_pct"], 0)

        unavailable = evidence.calculate_reference_yield(
            {
                "return_3m": float("nan"),
                "return_6m": float("inf"),
                "return_1y": "",
            },
            bucket="long",
        )
        self.assertEqual(unavailable["status"], "unavailable")
        self.assertEqual(unavailable["reason"], "no_available_horizons")
        self.assertIsNone(unavailable["value_pct"])
        self.assertEqual(unavailable["missing_horizons"], ["3m", "6m", "1y"])

    def test_unknown_term_is_unavailable(self) -> None:
        result = evidence.calculate_yield_metrics(
            {
                "term_days": 1.5,
                "return_1m": 3,
                "return_3m": 4,
                "return_6m": 5,
                "return_1y": 6,
            }
        )
        self.assertEqual(result["bucket"], "unknown")
        self.assertEqual(result["reference_yield_status"], "unavailable")
        self.assertEqual(result["reference_yield_reason"], "unknown_term")
        self.assertIsNone(result["reference_yield_pct"])
        self.assertIsNone(result["selection_score"])


class ScoringTests(unittest.TestCase):
    def test_rounding_is_half_away_from_zero(self) -> None:
        cases = (
            (1.42875, 1.4288),
            (3.94125, 3.9413),
            (3.49875, 3.4988),
            (-1.42875, -1.4288),
            (0.00004, 0),
            (-0.00004, 0),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(
                    evidence.round_half_away_from_zero(value),
                    expected,
                )

    def test_divergence_and_scheme_b_boundaries(self) -> None:
        divergence_cases = (
            ({"return_1m": None, "return_3m": 2}, 0),
            ({"return_1m": 2, "return_3m": 2.5}, 0),
            ({"return_1m": 1.99, "return_3m": 2.5}, 0.08),
        )
        for product, expected in divergence_cases:
            with self.subTest(product=product):
                self.assertAlmostEqual(
                    evidence.divergence_penalty(product),
                    expected,
                )

        product = {"return_6m": 2, "return_1y": 3.7}
        self.assertAlmostEqual(
            evidence.front_load_deduction("short", product, "B"),
            0.105,
        )
        self.assertAlmostEqual(
            evidence.front_load_deduction("medium", product, "B"),
            0.105,
        )
        self.assertAlmostEqual(
            evidence.front_load_deduction("long", product, "B"),
            0.03,
        )

    def test_metrics_match_frozen_score_cases(self) -> None:
        cases = (
            (
                {
                    "term_days": 7,
                    "return_1m": 1.8,
                    "return_3m": 2.4,
                    "return_6m": 3,
                    "history_months": None,
                },
                2.46,
                2.38,
                2.38,
            ),
            (
                {
                    "term_days": 90,
                    "return_1m": 2.8,
                    "return_3m": 3,
                    "return_6m": 3.5,
                    "return_1y": 4.5,
                    "history_months": 18,
                },
                3.45,
                3.45,
                3.465,
            ),
            (
                {
                    "term_days": 180,
                    "return_1m": 1,
                    "return_3m": 2,
                    "return_6m": 3,
                    "return_1y": 5,
                    "history_months": 24,
                },
                3.6,
                3.52,
                3.475,
            ),
        )
        for product, reference, observation, selection in cases:
            with self.subTest(term_days=product["term_days"]):
                result = evidence.calculate_yield_metrics(product)
                self.assertEqual(result["reference_yield_pct"], reference)
                self.assertEqual(result["weighted_yield_pct"], reference)
                self.assertEqual(result["observation_score"], observation)
                self.assertEqual(result["selection_score"], selection)
                self.assertEqual(
                    result["yield_policy_version"],
                    evidence.POLICY_VERSION,
                )

    def test_cash_has_reference_but_no_scores(self) -> None:
        result = evidence.calculate_yield_metrics(
            {
                "term_days": 0,
                "return_1m": 2,
                "return_3m": 4,
                "history_months": 24,
            }
        )
        self.assertEqual(result["reference_yield_pct"], 2.6)
        self.assertEqual(result["weighted_yield_pct"], 2.6)
        self.assertIsNone(result["observation_score"])
        self.assertIsNone(result["selection_score"])

    def test_modern_unavailable_never_falls_back_but_legacy_can(self) -> None:
        modern = {
            "term_days": 180,
            "return_1m": 4.2,
            "return_3m": None,
            "return_6m": None,
            "return_1y": None,
        }
        self.assertIsNone(
            evidence.effective_reference_yield(
                modern,
                reported_reference=4.0,
                fallback_yield=3.9,
            )
        )
        self.assertEqual(
            evidence.effective_reference_yield(
                modern,
                reported_reference=4.0,
                fallback_yield=3.9,
                allow_legacy=True,
            ),
            4.0,
        )


class EvidenceTierTests(unittest.TestCase):
    def test_one_month_review_caps_match_workspace_policy(self) -> None:
        policy = evidence.EVIDENCE_POLICIES["one_month"]
        self.assertFalse(policy["scoring"])
        self.assertFalse(policy["automatic"])
        self.assertEqual(policy["single_cap_pct"], 0.05)
        self.assertEqual(policy["aggregate_cap_pct"], 0.05)

    def test_evidence_tiers_remain_compatible(self) -> None:
        self.assertEqual(
            evidence.evidence_tier(12, 2, 3, 4, 5),
            "full_1y",
        )
        self.assertEqual(
            evidence.evidence_tier(10, 2, 3, 4, None),
            "six_month",
        )
        self.assertEqual(
            evidence.evidence_tier(4, 2, 3, None, None),
            "three_month",
        )
        self.assertEqual(
            evidence.evidence_tier(2, 2, None, None, None),
            "one_month",
        )
        self.assertEqual(
            evidence.EVIDENCE_POLICIES["one_month"]["single_cap_pct"],
            0.05,
        )
        self.assertEqual(
            evidence.EVIDENCE_POLICIES["one_month"]["aggregate_cap_pct"],
            0.05,
        )
        self.assertEqual(
            evidence.evidence_tier(None, None, None, None, None),
            "legacy",
        )


if __name__ == "__main__":
    unittest.main()
