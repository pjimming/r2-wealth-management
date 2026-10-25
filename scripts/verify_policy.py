#!/usr/bin/env python3
"""Compare the Skill yield policy with the workbench implementation."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

from evidence import (
    calculate_reference_yield,
    calculate_yield_metrics,
    bucket_for_term,
    front_load_deduction,
    round_half_away_from_zero,
)


NODE_SCRIPT = r"""
const fs = require('node:fs');
const path = require('node:path');
const policy = require(path.join(process.argv[1], 'lib', 'yield-policy.js'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const reference = (product) => {
  const result = policy.calculateReferenceYield(product);
  return {
    status: result.status,
    reason: result.reason,
    value_pct: result.value_pct,
    available_horizons: result.available_horizons,
    missing_horizons: result.missing_horizons,
  };
};
const output = {
  term_boundaries: input.term_boundary_cases.map((item) =>
    policy.bucketForTerm(item.term_days),
  ),
  references: input.reference_cases.map((item) => reference(item.product)),
  scores: input.score_cases.map((item) => {
    const schemeResults = Object.fromEntries(
      ['A', 'B', 'C'].map((scheme) => [
        scheme,
        policy.calculateYieldMetrics(item.product, {
          frontLoadScheme: scheme,
        }),
      ]),
    );
    const result = schemeResults.B;
    return {
      reference_yield_pct: result.reference_yield_pct,
      observation_score: result.observation_score,
      selection_score_A: schemeResults.A.selection_score,
      selection_score_B: schemeResults.B.selection_score,
      selection_score_C: schemeResults.C.selection_score,
    };
  }),
  rounding: input.rounding_cases.map((item) =>
    policy.roundHalfAwayFromZero(item.value),
  ),
  front_load: input.front_load_gap_cases.map((item) => ({
    A: policy.frontLoadDeduction(
      'long',
      { return_6m: 2, return_1y: 2 + item.gap_pp },
      'A',
    ),
    B: policy.frontLoadDeduction(
      'long',
      { return_6m: 2, return_1y: 2 + item.gap_pp },
      'B',
    ),
    C: policy.frontLoadDeduction(
      'long',
      { return_6m: 2, return_1y: 2 + item.gap_pp },
      'C',
    ),
  })),
};
process.stdout.write(JSON.stringify(output));
"""


def reference_fields(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": result["status"],
        "reason": result["reason"],
        "value_pct": result["value_pct"],
        "available_horizons": result["available_horizons"],
        "missing_horizons": result["missing_horizons"],
    }


def score_fields(product: dict[str, Any]) -> dict[str, Any]:
    scheme_results = {
        scheme: calculate_yield_metrics(
            product,
            front_load_scheme=scheme,
        )
        for scheme in ("A", "B", "C")
    }
    result = scheme_results["B"]
    return {
        "reference_yield_pct": result["reference_yield_pct"],
        "observation_score": result["observation_score"],
        "selection_score_A": scheme_results["A"]["selection_score"],
        "selection_score_B": scheme_results["B"]["selection_score"],
        "selection_score_C": scheme_results["C"]["selection_score"],
    }


def assert_close(
    expected: Any,
    actual: Any,
    context: str,
) -> None:
    if isinstance(expected, dict) or isinstance(actual, dict):
        if not isinstance(expected, dict) or not isinstance(actual, dict):
            raise AssertionError(
                f"{context}: expected {expected!r}, got {actual!r}"
            )
        if set(expected) != set(actual):
            raise AssertionError(
                f"{context}: keys differ, expected {sorted(expected)}, "
                f"got {sorted(actual)}"
            )
        for key in expected:
            assert_close(expected[key], actual[key], f"{context}.{key}")
        return
    if isinstance(expected, list) or isinstance(actual, list):
        if not isinstance(expected, list) or not isinstance(actual, list):
            raise AssertionError(
                f"{context}: expected {expected!r}, got {actual!r}"
            )
        if len(expected) != len(actual):
            raise AssertionError(
                f"{context}: lengths differ, expected {len(expected)}, "
                f"got {len(actual)}"
            )
        for index, (left, right) in enumerate(zip(expected, actual)):
            assert_close(left, right, f"{context}[{index}]")
        return
    if isinstance(expected, float) or isinstance(actual, float):
        if expected is None or actual is None:
            if expected is not actual:
                raise AssertionError(
                    f"{context}: expected {expected!r}, got {actual!r}"
                )
            return
        if not math.isclose(
            float(expected),
            float(actual),
            rel_tol=0,
            abs_tol=1e-12,
        ):
            raise AssertionError(
                f"{context}: expected {expected!r}, got {actual!r}"
            )
        return
    if expected != actual:
        raise AssertionError(
            f"{context}: expected {expected!r}, got {actual!r}"
        )


def run_node(
    node_executable: str,
    app_root: Path,
    golden: dict[str, Any],
) -> dict[str, Any]:
    completed = subprocess.run(
        [node_executable, "-e", NODE_SCRIPT, str(app_root)],
        input=json.dumps(golden, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Node policy verification failed:\n"
            f"{completed.stderr or completed.stdout}"
        )
    return json.loads(completed.stdout)


def verify(
    golden_path: Path,
    app_root: Path,
    node_executable: str,
) -> dict[str, Any]:
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    node = run_node(node_executable, app_root, golden)

    python = {
        "term_boundaries": [
            bucket_for_term(item["term_days"])
            for item in golden["term_boundary_cases"]
        ],
        "references": [
            reference_fields(calculate_reference_yield(item["product"]))
            for item in golden["reference_cases"]
        ],
        "scores": [
            score_fields(item["product"])
            for item in golden["score_cases"]
        ],
        "rounding": [
            round_half_away_from_zero(item["value"])
            for item in golden["rounding_cases"]
        ],
        "front_load": [
            {
                scheme: front_load_deduction(
                    "long",
                    {"return_6m": 2, "return_1y": 2 + item["gap_pp"]},
                    scheme,
                )
                for scheme in ("A", "B", "C")
            }
            for item in golden["front_load_gap_cases"]
        ],
    }

    expected = {
        "term_boundaries": [
            item["expected_bucket"]
            for item in golden["term_boundary_cases"]
        ],
        "references": [
            item["expected"]
            for item in golden["reference_cases"]
        ],
        "scores": [
            item["expected"]
            for item in golden["score_cases"]
        ],
        "rounding": [
            item["expected"]
            for item in golden["rounding_cases"]
        ],
        "front_load": [
            item["expected"]
            for item in golden["front_load_gap_cases"]
        ],
    }

    for group, expected_values in expected.items():
        for index, expected_value in enumerate(expected_values):
            context = f"{group}[{index}] Python vs golden"
            assert_close(expected_value, python[group][index], context)
            context = f"{group}[{index}] Node vs Python"
            assert_close(python[group][index], node[group][index], context)

    return {
        "ok": True,
        "golden_file": str(golden_path),
        "app_root": str(app_root),
        "policy_version": golden["policy_version"],
        "counts": {
            key: len(value)
            for key, value in python.items()
        },
    }


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="只读比较 Skill 与工作台的期限收益策略"
    )
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument(
        "--golden",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "assets"
        / "yield_policy_golden_cases.json",
    )
    parser.add_argument("--node", default="node", help="Node.js 可执行文件")
    args = parser.parse_args(argv)

    if not (args.app_root / "lib" / "yield-policy.js").exists():
        print(
            f"工作台策略文件不存在: {args.app_root / 'lib' / 'yield-policy.js'}",
            file=sys.stderr,
        )
        return 2
    try:
        result = verify(args.golden, args.app_root, args.node)
    except (OSError, ValueError, RuntimeError, AssertionError) as exc:
        print(f"策略校验失败: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
