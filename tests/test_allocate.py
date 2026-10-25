from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import allocate as allocator  # noqa: E402
import evidence  # noqa: E402


def write_pool(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "name",
        "code",
        "issuer",
        "risk_level",
        "term_days",
        "score",
        "min_amount",
        "annualized_yield",
        "return_1m_annualized",
        "return_3m_annualized",
        "return_6m_annualized",
        "return_1y_annualized",
        "reference_yield_pct",
        "evidence_tier",
        "history_months",
        "capacity",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class LoadPoolTests(unittest.TestCase):
    def test_cash_unknown_and_unavailable_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pool = Path(temp_dir) / "pool.csv"
            write_pool(
                pool,
                [
                    {
                        "name": "cash",
                        "code": "CASH",
                        "issuer": "issuer",
                        "risk_level": "R2",
                        "term_days": 0,
                        "score": 90,
                        "min_amount": 1,
                        "annualized_yield": 2,
                        "return_1m_annualized": 2,
                        "return_3m_annualized": 2,
                    },
                    {
                        "name": "fraction",
                        "code": "FRAC",
                        "issuer": "issuer",
                        "risk_level": "R2",
                        "term_days": 1.5,
                        "score": 90,
                        "min_amount": 1,
                        "annualized_yield": 2,
                    },
                    {
                        "name": "zero-short",
                        "code": "ZERO",
                        "issuer": "issuer",
                        "risk_level": "R2",
                        "term_days": 7,
                        "score": 70,
                        "min_amount": 1000,
                        "annualized_yield": 0,
                        "return_1m_annualized": 0,
                        "return_3m_annualized": 0,
                        "return_6m_annualized": 0,
                        "history_months": 12,
                    },
                    {
                        "name": "one-month-long",
                        "code": "ONE",
                        "issuer": "issuer",
                        "risk_level": "R2",
                        "term_days": 180,
                        "score": 90,
                        "min_amount": 1000,
                        "annualized_yield": 3,
                        "return_1m_annualized": 3,
                        "reference_yield_pct": 3,
                        "history_months": 2,
                    },
                ],
            )
            products, warnings = allocator.load_pool(pool)
            self.assertEqual([product.code for product in products], ["ZERO"])
            self.assertEqual(products[0].bucket, "short")
            self.assertEqual(products[0].annualized_yield, 0)
            self.assertEqual(products[0].reference_yield_status, "available")
            joined = "\n".join(warnings)
            self.assertIn("日开展示层", joined)
            self.assertIn("必须是非负整数", joined)
            self.assertIn("不可用", joined)

    def test_modern_unavailable_does_not_fallback_to_legacy_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pool = Path(temp_dir) / "pool.csv"
            write_pool(
                pool,
                [
                    {
                        "name": "modern-missing",
                        "code": "MODERN",
                        "issuer": "issuer",
                        "risk_level": "R2",
                        "term_days": 90,
                        "score": 70,
                        "min_amount": 1000,
                        "annualized_yield": 2.5,
                        "reference_yield_pct": 2.4,
                        "history_months": 12,
                    }
                ],
            )
            products, _ = allocator.load_pool(pool)
            self.assertEqual(products, [])

    def test_pure_legacy_row_can_use_explicit_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pool = Path(temp_dir) / "pool.csv"
            fields = [
                "name",
                "code",
                "issuer",
                "risk_level",
                "term_days",
                "score",
                "min_amount",
                "annualized_yield",
            ]
            with pool.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow(
                    {
                        "name": "legacy",
                        "code": "OLD",
                        "issuer": "issuer",
                        "risk_level": "R2",
                        "term_days": 90,
                        "score": 70,
                        "min_amount": 1000,
                        "annualized_yield": 2.5,
                    }
                )
            products, _ = allocator.load_pool(pool)
            self.assertEqual(len(products), 1)
            self.assertEqual(products[0].annualized_yield, 2.5)
            self.assertEqual(products[0].evidence_tier, "legacy")


class AllocationTests(unittest.TestCase):
    def test_daily_open_has_no_allocation_bucket(self) -> None:
        result = allocator.allocate(
            amount=100_000,
            profile_name="balanced",
            cash_reserve=0,
            target=3,
            min_unit=1000,
            max_product_pct=0.25,
            evidence_caps={
                "six_month": {"single_pct": 0.10, "aggregate_pct": 0.20},
                "three_month": {"single_pct": 0.10, "aggregate_pct": 0.20},
            },
            products=[],
        )
        self.assertEqual(
            {item["bucket"] for item in result["bucket_targets"]},
            {"short", "medium", "long"},
        )
        self.assertEqual(result["assumptions"]["daily_open_target_pct"], 0)

    def test_three_bucket_labels_and_targets(self) -> None:
        result = allocator.allocate(
            amount=300_000,
            profile_name="balanced",
            cash_reserve=0,
            target=3,
            min_unit=1000,
            max_product_pct=0.25,
            evidence_caps={
                "six_month": {"single_pct": 0.10, "aggregate_pct": 0.20},
                "three_month": {"single_pct": 0.10, "aggregate_pct": 0.20},
            },
            products=[],
        )
        labels = {
            item["bucket"]: item["label"]
            for item in result["bucket_targets"]
        }
        self.assertEqual(labels["short"], "短期限 1–30天")
        self.assertEqual(labels["medium"], "中期限 31–100天")
        self.assertEqual(labels["long"], "长期限 101天+")
        self.assertEqual(
            sum(item["target_amount"] for item in result["bucket_targets"]),
            300_000,
        )
        self.assertEqual(
            result["assumptions"]["yield_policy_version"],
            evidence.POLICY_VERSION,
        )

    def test_one_month_caps_match_current_workspace(self) -> None:
        self.assertEqual(
            evidence.EVIDENCE_POLICIES["one_month"]["single_cap_pct"],
            0.05,
        )
        self.assertEqual(
            evidence.EVIDENCE_POLICIES["one_month"]["aggregate_cap_pct"],
            0.05,
        )


if __name__ == "__main__":
    unittest.main()
