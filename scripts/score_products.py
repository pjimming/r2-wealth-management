#!/usr/bin/env python3
"""Hard-filter and score R2 products from a CSV.

The score is a transparent decision aid, not a recommendation. Verify all
inputs against the latest product documents before buying.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

from evidence import (
    EVIDENCE_POLICIES,
    effective_reference_yield,
    evidence_tier,
)


WEIGHTS = {
    "stability": 30.0,
    "liquidity": 25.0,
    "yield": 20.0,
    "fees": 15.0,
    "execution": 10.0,
}

ACCESS_SCORES = {
    "easy": 1.0,
    "e": 1.0,
    "易": 1.0,
    "容易": 1.0,
    "medium": 0.6,
    "m": 0.6,
    "中": 0.6,
    "一般": 0.6,
    "hard": 0.2,
    "h": 0.2,
    "难": 0.2,
    "困难": 0.2,
    "unknown": 0.4,
    "": 0.4,
}

BUCKET_ORDER = {"cash": 0, "short": 1, "medium": 2, "long": 3}
BUCKET_LABELS = {
    "cash": "现金",
    "short": "短期",
    "medium": "中期",
    "long": "长期",
}


def bucket_for(term_days: float, name: str = "") -> str:
    text = name.lower()
    if term_days <= 1 or any(k in text for k in ("现金", "活期", "货币", "朝朝宝")):
        return "cash"
    if term_days <= 30:
        return "short"
    if term_days <= 100:
        return "medium"
    return "long"


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def normalize_risk(value: str) -> str:
    risk = (value or "").strip().upper().replace(" ", "")
    if re.match(r"^PR2(?![0-9])", risk):
        return "PR2"
    if re.match(r"^R2(?![0-9])", risk):
        return "R2"
    return risk


def normalize_access(value: str) -> tuple[str, float]:
    key = (value or "").strip().lower()
    if key in ACCESS_SCORES:
        return key or "unknown", ACCESS_SCORES[key]
    if "易" in key:
        return "easy", ACCESS_SCORES["easy"]
    if "难" in key:
        return "hard", ACCESS_SCORES["hard"]
    if "中" in key:
        return "medium", ACCESS_SCORES["medium"]
    return "unknown", ACCESS_SCORES["unknown"]


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV 没有表头")
        required = {"name", "risk_level", "term_days", "annualized_yield"}
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV 缺少列: {', '.join(sorted(missing))}")
        rows: list[dict[str, Any]] = []
        for row_number, row in enumerate(reader, start=2):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            rows.append(
                {
                    "row_number": row_number,
                    "name": name,
                    "code": (row.get("code") or "").strip(),
                    "issuer": (row.get("issuer") or "未知").strip() or "未知",
                    "term_days": parse_number(row.get("term_days")),
                    "risk_raw": (row.get("risk_level") or "").strip(),
                    "risk": normalize_risk(row.get("risk_level") or ""),
                    "annualized_yield": parse_number(row.get("annualized_yield")),
                    "return_1m": parse_number(row.get("return_1m_annualized")),
                    "return_3m": parse_number(row.get("return_3m_annualized")),
                    "return_6m": parse_number(row.get("return_6m_annualized")),
                    "return_1y": parse_number(row.get("return_1y_annualized")),
                    "reported_reference_yield": parse_number(
                        row.get("reference_yield_pct")
                    ),
                    "declared_evidence_tier": (
                        row.get("evidence_tier") or ""
                    ).strip(),
                    "max_drawdown_pct": parse_number(row.get("max_drawdown_pct")),
                    "fee_bps": parse_number(row.get("fee_bps")),
                    "liquidity_days": parse_number(row.get("liquidity_days")),
                    "quota_access_raw": (row.get("quota_access") or "").strip(),
                    "history_months": parse_number(row.get("history_months")),
                    "min_amount": parse_number(row.get("min_amount")) or 0.0,
                    "source": (row.get("source") or "").strip(),
                    "data_date": (row.get("data_date") or "").strip(),
                }
            )
    return rows


def score_rows(
    rows: list[dict[str, Any]],
    min_history: float,
    max_drawdown: float,
    max_liquidity: float | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    passed: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for row in rows:
        reasons: list[str] = []
        tier = evidence_tier(
            row["history_months"],
            row["return_1m"],
            row["return_3m"],
            row["return_6m"],
            row["return_1y"],
            row["declared_evidence_tier"],
        )
        policy = EVIDENCE_POLICIES[tier]
        yield_used = effective_reference_yield(
            row["return_3m"],
            row["return_6m"],
            row["return_1y"],
            row["reported_reference_yield"],
            row["annualized_yield"],
        )
        row.update(
            {
                "evidence_tier": tier,
                "evidence_label": policy["label"],
                "evidence_scoring": policy["scoring"],
                "evidence_automatic": policy["automatic"],
                "evidence_single_cap_pct": policy["single_cap_pct"],
                "evidence_aggregate_cap_pct": policy["aggregate_cap_pct"],
                "reference_yield_pct": yield_used,
                "yield_used_pct": yield_used,
            }
        )
        if row["risk"] not in {"R2", "PR2"}:
            reasons.append(f"风险等级不是 R2/PR2（{row['risk_raw'] or '空'}）")
        if row["term_days"] is None or row["term_days"] < 0:
            reasons.append("期限缺失或为负")
        if not policy["scoring"]:
            reasons.append(f"{policy['label']}不进入自动评分")
        if yield_used is None:
            reasons.append("参考年化缺失")
        elif yield_used <= 0:
            reasons.append("年化收益不为正")
        if row["max_drawdown_pct"] is None:
            reasons.append("最大回撤缺失")
        elif row["max_drawdown_pct"] > max_drawdown:
            reasons.append(f"最大回撤 {row['max_drawdown_pct']:.2f}% 超过阈值 {max_drawdown:.2f}%")
        if row["history_months"] is None:
            reasons.append("历史长度缺失")
        elif row["history_months"] < min_history:
            reasons.append(f"历史 {row['history_months']:.0f} 个月少于 {min_history:.0f} 个月")
        if row["fee_bps"] is None:
            reasons.append("费率缺失")
        if row["liquidity_days"] is None:
            reasons.append("到账天数缺失")
        elif max_liquidity is not None and row["liquidity_days"] > max_liquidity:
            reasons.append(
                f"到账 T+{row['liquidity_days']:.0f} 超过上限 T+{max_liquidity:.0f}"
            )

        if reasons:
            excluded.append({**row, "reasons": reasons})
        else:
            passed.append(row)

    if not passed:
        return passed, excluded, warnings

    for row in passed:
        row["bucket"] = bucket_for(float(row["term_days"]), row["name"])

    all_yields = [float(row["yield_used_pct"]) for row in passed]
    if all_yields and max(all_yields) > 5.0:
        warnings.append(
            f"最高年化 {max(all_yields):.2f}% 对 R2 偏高，需核查底层、杠杆、估值口径和是否用了短期冲高数据。"
        )

    for bucket in BUCKET_ORDER:
        bucket_rows = [row for row in passed if row["bucket"] == bucket]
        if not bucket_rows:
            continue
        for row in bucket_rows:
            drawdown = float(row["max_drawdown_pct"])
            stability = clamp01(1.0 - drawdown / 0.5)

            liquidity_days = float(row["liquidity_days"])
            liquidity = clamp01(1.0 - liquidity_days / 10.0)

            # Absolute anchor avoids turning a 5bp difference into a 20-point swing.
            yield_score = clamp01(float(row["yield_used_pct"]) / 4.0)

            fee_bps = float(row["fee_bps"])
            fees = clamp01(1.0 - fee_bps / 50.0)

            access_key, access_score = normalize_access(row["quota_access_raw"])
            execution = access_score

            total = (
                WEIGHTS["stability"] * stability
                + WEIGHTS["liquidity"] * liquidity
                + WEIGHTS["yield"] * yield_score
                + WEIGHTS["fees"] * fees
                + WEIGHTS["execution"] * execution
            )
            row["scores"] = {
                "stability": stability,
                "liquidity": liquidity,
                "yield": yield_score,
                "fees": fees,
                "execution": execution,
            }
            row["access"] = access_key
            row["total_score"] = round(total, 1)

    passed.sort(
        key=lambda row: (
            BUCKET_ORDER[row["bucket"]],
            -float(row["total_score"]),
            float(row["term_days"]),
            float(row["yield_used_pct"]),
        )
    )
    short_history = [
        row for row in passed if row["evidence_tier"] in {"six_month", "three_month"}
    ]
    if short_history:
        warnings.append(
            f"{len(short_history)} 只产品使用不完整历史评分；自动配置须执行"
            "单只 10%、同类合计 20% 上限，并明确展示缺失周期。"
        )
    return passed, excluded, warnings


def render_markdown(
    passed: list[dict[str, Any]],
    excluded: list[dict[str, Any]],
    warnings: list[str],
    min_history: float,
    max_drawdown: float,
    max_liquidity: float | None,
    show_excluded: bool,
) -> str:
    lines: list[str] = []
    lines.append("# R2 产品评分")
    lines.append("")
    lines.append(
        f"筛选条件：R2/PR2；历史 ≥{min_history:.0f} 个月；最大回撤 ≤{max_drawdown:.2f}%；"
        + (f"到账 ≤T+{max_liquidity:.0f}。" if max_liquidity is not None else "到账天数不限。")
    )
    lines.append("")
    if passed:
        lines.append("## 排名")
        lines.append("")
        lines.append("| # | 桶 | 产品 | 发行方 | 期限 | 数据档位 | 参考年化 | 最大回撤 | 费率 | 到账 | 额度 | 历史 | 数据日期 | 评分 |")
        lines.append("|---:|---|---|---|---:|---|---:|---:|---:|---|---|---:|---|---:|")
        for index, row in enumerate(passed, start=1):
            lines.append(
                f"| {index} | {BUCKET_LABELS[row['bucket']]} | {row['name']} | {row['issuer']} | {row['term_days']:.0f}天 | "
                f"{row['evidence_label']} | {row['yield_used_pct']:.2f}% | {row['max_drawdown_pct']:.2f}% | "
                f"{row['fee_bps'] or 0:.0f}bp | T+{row['liquidity_days'] or 0:.0f} | "
                f"{row['quota_access_raw'] or '未知'} | {row['history_months']:.0f}月 | "
                f"{row.get('data_date') or '—'} | "
                f"{row['total_score']:.1f} |"
            )
        lines.append("")
        lines.append(
            "评分权重：稳定性 30、流动性 25、收益 20、费用 15、执行 10。收益率只占 20 分；"
            "评分只在同一期限桶内比较。缺 1Y 和仅 3M 档必须披露数据缺口，"
            "配置时执行单只 10%、同类合计 20% 上限；仅 1M 不进入自动评分。"
        )
    else:
        lines.append("没有产品通过硬性筛选。")
    if show_excluded and excluded:
        lines.append("")
        lines.append("## 排除")
        lines.append("")
        for row in excluded:
            lines.append(f"- **{row['name']}**：{'；'.join(row['reasons'])}")
    if warnings:
        lines.append("")
        lines.append("## 警告")
        lines.append("")
        for warning in warnings:
            lines.append(f"- {warning}")
    lines.append("")
    lines.append(
        "> 评分是决策辅助，不是买入建议。购买前重新核对产品说明书、风险等级、费率、额度和赎回规则。"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="R2 产品硬性筛选与评分")
    parser.add_argument("--input", type=Path, required=True, help="产品池 CSV")
    parser.add_argument("--min-history", type=float, default=3, help="最少历史月数，默认 3")
    parser.add_argument("--max-drawdown", type=float, default=0.5, help="最大回撤阈值（%），默认 0.5")
    parser.add_argument("--max-liquidity", type=float, default=None, help="最大到账天数 T+n")
    parser.add_argument("--show-excluded", action="store_true", help="显示被排除的产品与原因")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"输入文件不存在: {args.input}", file=sys.stderr)
        return 2
    try:
        rows = load_rows(args.input)
        passed, excluded, warnings = score_rows(
            rows,
            min_history=args.min_history,
            max_drawdown=args.max_drawdown,
            max_liquidity=args.max_liquidity,
        )
    except (OSError, ValueError) as exc:
        print(f"读取失败: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(
            json.dumps(
                {
                    "criteria": {
                        "min_history_months": args.min_history,
                        "max_drawdown_pct": args.max_drawdown,
                        "max_liquidity_days": args.max_liquidity,
                        "evidence_policies": EVIDENCE_POLICIES,
                    },
                    "weights": WEIGHTS,
                    "ranked": passed,
                    "excluded": excluded,
                    "warnings": warnings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(
            render_markdown(
                passed,
                excluded,
                warnings,
                args.min_history,
                args.max_drawdown,
                args.max_liquidity,
                args.show_excluded,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
