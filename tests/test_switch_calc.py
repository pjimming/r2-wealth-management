from __future__ import annotations

import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import switch_calc  # noqa: E402


class CompoundSwitchTests(unittest.TestCase):
    def test_compound_horizon_with_idle_days(self) -> None:
        result = switch_calc.calculate(
            amount=100_000,
            current_yield_pct=3.0,
            remaining_days=90,
            redemption_fee_bps=0,
            idle_days=3,
            new_yield_pct=3.5,
            purchase_fee_bps=0,
        )
        values = result["results"]
        self.assertAlmostEqual(values["current_gross"], 731.51, places=2)
        self.assertAlmostEqual(values["new_gross"], 823.35, places=2)
        self.assertAlmostEqual(values["difference"], 91.84, places=2)
        self.assertAlmostEqual(
            values["break_even_yield_pct"],
            3.105,
            places=4,
        )
        self.assertAlmostEqual(values["idle_cost"], 28.51, places=2)
        self.assertIn("值得切换", result["verdict"])
        self.assertIn("复利计算", result["note"])

    def test_zero_idle_days_uses_current_yield_as_fee_free_break_even(self) -> None:
        result = switch_calc.calculate(
            amount=50_000,
            current_yield_pct=2.8,
            remaining_days=180,
            redemption_fee_bps=0,
            idle_days=0,
            new_yield_pct=3.2,
            purchase_fee_bps=0,
        )
        self.assertAlmostEqual(
            result["results"]["break_even_yield_pct"],
            2.8,
            places=10,
        )
        self.assertGreater(result["results"]["difference"], 0)

    def test_fees_raise_break_even_yield(self) -> None:
        result = switch_calc.calculate(
            amount=100_000,
            current_yield_pct=3.0,
            remaining_days=90,
            redemption_fee_bps=100,
            idle_days=3,
            new_yield_pct=3.5,
            purchase_fee_bps=100,
        )
        self.assertAlmostEqual(
            result["results"]["break_even_yield_pct"],
            11.97,
            places=2,
        )
        self.assertAlmostEqual(result["results"]["fee_drag"], 2_000, places=2)
        self.assertLess(result["results"]["difference"], 0)

    def test_no_earning_days_has_no_break_even(self) -> None:
        result = switch_calc.calculate(
            amount=10_000,
            current_yield_pct=3.0,
            remaining_days=2,
            redemption_fee_bps=0,
            idle_days=2,
            new_yield_pct=4.0,
            purchase_fee_bps=0,
        )
        self.assertEqual(result["results"]["new_days"], 0)
        self.assertIsNone(result["results"]["break_even_yield_pct"])
        self.assertIn("没有计息时间", result["verdict"])

    def test_invalid_yield_and_fee_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "大于 -100%"):
            switch_calc.calculate(1000, -100, 30, 0, 0, 3, 0)
        with self.assertRaisesRegex(ValueError, "费率不能为负"):
            switch_calc.calculate(1000, 3, 30, -1, 0, 3, 0)


if __name__ == "__main__":
    unittest.main()
