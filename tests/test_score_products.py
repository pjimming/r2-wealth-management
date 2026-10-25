from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import score_products as scoring  # noqa: E402


TEMPLATE = SKILL_ROOT / "assets" / "product_pool_template.csv"


def run_template() -> tuple[list[dict], list[dict], list[str]]:
    rows = scoring.load_rows(TEMPLATE)
    return scoring.score_rows(
        rows,
        min_history=3,
        max_drawdown=0.5,
        max_liquidity=None,
    )


class TemplateScoringTests(unittest.TestCase):
    def test_template_uses_term_adjusted_reference_and_excludes_cash(self) -> None:
        passed, excluded, _ = run_template()
        by_code = {row["code"]: row for row in passed}
        excluded_by_code = {row["code"]: row for row in excluded}

        self.assertEqual(
            set(by_code),
            {"SHORT030A", "SHORT030B", "MED090A", "MED090B", "LONG180A"},
        )
        self.assertAlmostEqual(by_code["SHORT030A"]["reference_yield_pct"], 1.883)
        self.assertAlmostEqual(by_code["SHORT030B"]["reference_yield_pct"], 1.84)
        self.assertAlmostEqual(by_code["LONG180A"]["reference_yield_pct"], 2.28)
        self.assertAlmostEqual(by_code["MED090A"]["app_selection_score"], 2.126)

        for code in ("CASH001", "CASH002"):
            self.assertEqual(excluded_by_code[code]["bucket"], "cash")
            self.assertIsNone(excluded_by_code[code]["app_selection_score"])
            self.assertFalse(excluded_by_code[code]["evidence_scoring"])
            self.assertFalse(excluded_by_code[code]["evidence_automatic"])
            self.assertTrue(
                any("日开产品只展示" in reason for reason in excluded_by_code[code]["reasons"])
            )

        self.assertEqual(
            excluded_by_code["LONG180B"]["reference_yield_status"],
            "unavailable",
        )
        self.assertIsNone(excluded_by_code["LONG180B"]["reference_yield_pct"])
        self.assertEqual(excluded_by_code["R3SAMPLE"]["risk"], "R3")

    def test_total_score_and_selection_score_are_separate(self) -> None:
        passed, _, _ = run_template()
        for row in passed:
            self.assertIn("total_score", row)
            self.assertIn("app_selection_score", row)
            self.assertGreaterEqual(row["total_score"], 0)
        self.assertNotEqual(
            passed[0]["total_score"],
            passed[0]["app_selection_score"],
        )


class RowSemanticsTests(unittest.TestCase):
    def _score_rows(self, rows: list[dict[str, object]]) -> tuple[list[dict], list[dict]]:
        fields = sorted({key for row in rows for key in row})
        if "name" not in fields:
            fields.append("name")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "pool.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            loaded = scoring.load_rows(path)
            passed, excluded, _ = scoring.score_rows(
                loaded,
                min_history=3,
                max_drawdown=0.5,
                max_liquidity=None,
            )
            return passed, excluded

    def test_zero_is_valid_return(self) -> None:
        passed, excluded = self._score_rows(
            [
                {
                    "name": "zero",
                    "code": "ZERO",
                    "risk_level": "R2",
                    "term_days": 7,
                    "annualized_yield": 0,
                    "return_1m_annualized": 0,
                    "return_3m_annualized": 0,
                    "return_6m_annualized": 0,
                    "max_drawdown_pct": 0.01,
                    "fee_bps": 0,
                    "liquidity_days": 1,
                    "quota_access": "easy",
                    "history_months": 12,
                }
            ]
        )
        self.assertFalse(excluded)
        self.assertEqual(len(passed), 1)
        self.assertEqual(passed[0]["reference_yield_pct"], 0)

    def test_modern_unavailable_does_not_fallback(self) -> None:
        passed, excluded = self._score_rows(
            [
                {
                    "name": "modern-missing",
                    "code": "MODERN",
                    "risk_level": "R2",
                    "term_days": 180,
                    "annualized_yield": 5,
                    "return_1m_annualized": 5,
                    "reference_yield_pct": 5,
                    "max_drawdown_pct": 0.01,
                    "fee_bps": 0,
                    "liquidity_days": 1,
                    "quota_access": "easy",
                    "history_months": 2,
                }
            ]
        )
        self.assertFalse(passed)
        self.assertIsNone(excluded[0]["reference_yield_pct"])
        self.assertEqual(
            excluded[0]["reference_yield_reason"],
            "no_available_horizons",
        )


if __name__ == "__main__":
    unittest.main()
