#!/usr/bin/env python3
"""Allocate a fully invested R2 portfolio across short/medium/long buckets.

An optional R2 cash-management sleeve can be added with --cash-pct. A target
check compares the weighted input yield with --target. The script is
deterministic planning arithmetic; it does not recommend a product or verify
live quotas, yields, or risk levels.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROFILES: dict[str, dict[str, float]] = {
    "conservative": {"cash": 0.0, "short": 0.45, "medium": 0.40, "long": 0.15},
    "balanced": {"cash": 0.0, "short": 0.40, "medium": 0.40, "long": 0.20},
    "yield": {"cash": 0.0, "short": 0.30, "medium": 0.40, "long": 0.30},
    "barbell": {"cash": 0.0, "short": 0.50, "medium": 0.0, "long": 0.50},
    "ladder": {"cash": 0.0, "short": 0.35, "medium": 0.35, "long": 0.30},
    "target3": {"cash": 0.0, "short": 0.30, "medium": 0.35, "long": 0.35},
}

BUCKET_LABELS = {
    "cash": "流动性仓（R2现金管理）",
    "short": "短期限 7–30天",
    "medium": "中期限 60–100天",
    "long": "长期限 120天+",
}

PROFILE_LABELS = {
    "conservative": "保守型",
    "balanced": "均衡型",
    "yield": "收益型",
    "barbell": "哑铃型",
    "ladder": "阶梯型",
    "target3": "3%进取型",
}


@dataclass
class Product:
    name: str
    code: str
    issuer: str
    risk_level: str
    term_days: float
    score: float
    annualized_yield: float | None
    min_amount: float
    capacity: float | None
    bucket: str
    row_number: int


def money(value: float) -> float:
    return round(value + 1e-9, 2)


def floor_unit(value: float, unit: float) -> float:
    if unit <= 0:
        return money(value)
    return money(math.floor((value + 1e-9) / unit) * unit)


def bucket_for(term_days: float, name: str = "") -> str:
    text = name.lower()
    if term_days <= 1 or any(k in text for k in ("现金", "活期", "货币", "朝朝宝")):
        return "cash"
    if term_days <= 30:
        return "short"
    if term_days <= 100:
        return "medium"
    return "long"


def load_pool(path: Path) -> tuple[list[Product], list[str]]:
    warnings: list[str] = []
    products: list[Product] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("产品池 CSV 没有表头")
        required = {"name", "risk_level", "term_days"}
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(f"产品池缺少列: {', '.join(sorted(missing))}")

        for row_number, row in enumerate(reader, start=2):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            risk = (row.get("risk_level") or "").strip().upper().replace(" ", "")
            if risk not in {"R2", "PR2"}:
                warnings.append(f"第 {row_number} 行「{name}」风险等级为 {risk or '空'}，已排除。")
                continue
            try:
                term_days = float(row.get("term_days") or 0)
            except ValueError:
                warnings.append(f"第 {row_number} 行「{name}」term_days 不是数字，已排除。")
                continue
            if term_days < 0:
                warnings.append(f"第 {row_number} 行「{name}」term_days 为负数，已排除。")
                continue
            try:
                score = float(row.get("score") or 50)
            except ValueError:
                score = 50.0
            try:
                min_amount = float(row.get("min_amount") or 0)
            except ValueError:
                min_amount = 0.0
            yield_raw = (row.get("annualized_yield") or "").strip().replace("%", "")
            try:
                annualized_yield = float(yield_raw) if yield_raw else None
            except ValueError:
                annualized_yield = None
            capacity_raw = row.get("capacity")
            try:
                capacity = float(capacity_raw) if capacity_raw not in (None, "") else None
            except ValueError:
                capacity = None
            products.append(
                Product(
                    name=name,
                    code=(row.get("code") or "").strip(),
                    issuer=(row.get("issuer") or "未知").strip() or "未知",
                    risk_level=risk,
                    term_days=term_days,
                    score=score,
                    annualized_yield=annualized_yield,
                    min_amount=max(0.0, min_amount),
                    capacity=capacity,
                    bucket=bucket_for(term_days, name),
                    row_number=row_number,
                )
            )
    return products, warnings


def allocate(
    amount: float,
    profile_name: str,
    cash_reserve: float,
    cash_pct: float,
    target: float | None,
    min_unit: float,
    max_product_pct: float,
    products: list[Product],
) -> dict[str, Any]:
    if amount <= 0:
        raise ValueError("--amount 必须大于 0")
    if cash_reserve < 0 or cash_reserve >= amount:
        raise ValueError("--cash-reserve 必须大于等于 0 且小于 --amount")
    if not (0 <= cash_pct < 1):
        raise ValueError("--cash-pct 必须在 [0, 1) 内")
    if target is not None and target < 0:
        raise ValueError("--target 不能为负")
    if target is not None and target > 20:
        raise ValueError("--target 看起来不现实，请输入 0–20 之间的年化百分比")
    if min_unit <= 0:
        raise ValueError("--min-unit 必须大于 0")
    if not (0 < max_product_pct <= 1):
        raise ValueError("--max-product-pct 必须在 (0, 1] 内")

    base = PROFILES[profile_name]
    if abs(sum(base.values()) - 1.0) > 1e-9:
        raise ValueError(f"模型 {profile_name} 的比例之和不是 100%")
    non_cash_total = sum(base[b] for b in ("short", "medium", "long"))
    if non_cash_total <= 0:
        raise ValueError(f"模型 {profile_name} 没有非现金桶")
    profile = {
        b: base[b] / non_cash_total * (1.0 - cash_pct)
        for b in ("short", "medium", "long")
    }
    profile["cash"] = cash_pct

    investable = money(amount - cash_reserve)
    bucket_targets = {
        bucket: floor_unit(investable * pct, min_unit) for bucket, pct in profile.items()
    }
    # Correct any rounding residue so the bucket targets add up to investable.
    residue = money(investable - sum(bucket_targets.values()))
    if residue > 0:
        residue_bucket = max(
            ("short", "medium", "long"), key=lambda bucket: bucket_targets[bucket]
        )
        bucket_targets[residue_bucket] = money(bucket_targets[residue_bucket] + residue)

    product_totals: dict[str, float] = {}
    allocations: list[dict[str, Any]] = []
    leftover: dict[str, float] = {}
    warnings: list[str] = []

    for bucket, bucket_target in bucket_targets.items():
        remaining = money(bucket_target)
        candidates = [p for p in products if p.bucket == bucket]
        candidates.sort(key=lambda p: (-p.score, p.term_days, p.min_amount, p.name))
        if not candidates:
            leftover[bucket] = remaining
            if remaining > 0:
                warnings.append(f"{BUCKET_LABELS[bucket]} 没有可用产品，目标金额 {remaining:,.0f} 元未分配。")
            continue

        for product in candidates:
            if remaining <= 0:
                break
            product_key = f"{product.name}|{product.code}"
            product_cap = investable * max_product_pct - product_totals.get(product_key, 0.0)
            caps = [remaining, product_cap]
            if product.capacity is not None:
                caps.append(product.capacity)
            allowable = min(caps)
            if allowable < product.min_amount:
                continue
            allocation = floor_unit(allowable, min_unit)
            if allocation < product.min_amount or allocation <= 0:
                continue
            allocations.append(
                {
                    "bucket": bucket,
                    "bucket_label": BUCKET_LABELS[bucket],
                    "name": product.name,
                    "code": product.code,
                    "issuer": product.issuer,
                    "term_days": product.term_days,
                    "annualized_yield": product.annualized_yield,
                    "amount": money(allocation),
                    "pct_of_investable": money(allocation / investable * 100),
                    "score": product.score,
                }
            )
            product_totals[product_key] = product_totals.get(product_key, 0.0) + allocation
            remaining = money(remaining - allocation)

        if remaining > 0:
            leftover[bucket] = remaining
            warnings.append(
                f"{BUCKET_LABELS[bucket]} 仍有 {remaining:,.0f} 元未分配；"
                "可能是产品不足、起购金额或单只上限导致。"
            )

    allocated_total = money(sum(item["amount"] for item in allocations))
    unallocated_total = money(investable - allocated_total)
    if unallocated_total > 0:
        warnings.append(
            f"共 {unallocated_total:,.0f} 元未分配到具体产品，建议留在短桶/流动性仓或补充候选产品。"
        )
    if cash_pct == 0:
        warnings.append(
            "本方案不留现金/流动性仓；确认应急资金在组合外，短桶承担流动性。"
        )
    else:
        warnings.append(
            f"流动性仓 {cash_pct * 100:.1f}% 使用 R2 现金管理产品；"
            "确认 T+0/T+1 快速赎回限额和到账规则。"
        )
    total_cash = money(cash_reserve + bucket_targets["cash"])
    if cash_reserve > 0 and bucket_targets["cash"] > 0:
        warnings.append(
            "组合外预留现金与 R2 流动性仓同时存在；确认两者不是同一笔钱，否则会重复计算流动性。"
        )
    if amount > 0 and total_cash / amount > 0.30:
        warnings.append(
            f"组合外预留现金 + R2 流动性仓合计 {total_cash:,.0f} 元，占总资金 {total_cash / amount * 100:.1f}%；"
            "确认这是流动性安排，而不是重复计算现金。"
        )

    target_analysis: dict[str, Any] | None = None
    if target and target > 0:
        covered = [item for item in allocations if item["annualized_yield"] is not None]
        covered_amount = money(sum(item["amount"] for item in covered))
        total_amount = money(sum(item["amount"] for item in allocations))
        weighted_yield = None
        if covered_amount > 0:
            weighted_yield = money(
                sum(item["amount"] * item["annualized_yield"] for item in covered)
                / covered_amount
            )
        required_monthly = ((1 + target / 100) ** (1 / 12) - 1) * 100
        gap_bp = money((weighted_yield - target) * 100) if weighted_yield is not None else None
        status = "未计算"
        if weighted_yield is not None:
            status = "达到输入口径" if gap_bp >= 0 else "低于目标"
        target_analysis = {
            "target_annualized_pct": target,
            "required_monthly_pct": round(required_monthly, 4),
            "weighted_annualized_pct": weighted_yield,
            "target_gap_bp": gap_bp,
            "status": status,
            "covered_amount": covered_amount,
            "allocated_amount": total_amount,
            "coverage_pct": money(covered_amount / total_amount * 100) if total_amount else 0,
            "note": "加权年化来自产品池 annualized_yield 输入，不是收益承诺。",
        }
        if weighted_yield is None:
            warnings.append("产品池未填 annualized_yield，无法做目标检查。")
        else:
            if gap_bp < 0:
                warnings.append(
                    f"组合输入年化 {weighted_yield:.2f}%，低于目标 {target:.2f}%，"
                    f"缺口 {abs(gap_bp):.0f} bp；不要用杠杆或假收益补，"
                    "先考虑更长期限/信用暴露，或降低目标。"
                )
            else:
                warnings.append(
                    f"组合输入年化 {weighted_yield:.2f}%，达到目标 {target:.2f}% 的输入口径；"
                    "仍需用实际净值和回撤验证。"
                )
            if total_amount > 0 and covered_amount / total_amount < 0.999:
                warnings.append(
                    f"只有 {covered_amount / total_amount * 100:.0f}% 的已分配金额有年化输入，"
                    "目标检查不完整。"
                )

    return {
        "assumptions": {
            "amount": money(amount),
            "cash_reserve": money(cash_reserve),
            "cash_pct": cash_pct,
            "fully_invested": cash_pct == 0 and cash_reserve == 0,
            "investable": investable,
            "profile": profile_name,
            "profile_weights": profile,
            "min_unit": min_unit,
            "max_product_pct": max_product_pct,
            "target_annualized_pct": target,
        },
        "bucket_targets": [
            {
                "bucket": bucket,
                "label": BUCKET_LABELS[bucket],
                "weight_pct": profile[bucket] * 100,
                "target_amount": bucket_target,
            }
            for bucket, bucket_target in bucket_targets.items()
        ],
        "allocations": allocations,
        "leftover": [
            {"bucket": bucket, "label": BUCKET_LABELS[bucket], "amount": amount_left}
            for bucket, amount_left in leftover.items()
            if amount_left > 0
        ],
        "totals": {
            "allocated": allocated_total,
            "unallocated": unallocated_total,
        },
        "target_analysis": target_analysis,
        "warnings": warnings,
    }


def render_markdown(result: dict[str, Any]) -> str:
    assumptions = result["assumptions"]
    lines: list[str] = []
    lines.append("# R2 配置方案")
    lines.append("")
    lines.append(
        f"- 总资金：{assumptions['amount']:,.0f} 元；"
        f"组合外预留现金：{assumptions['cash_reserve']:,.0f} 元；"
        f"可投资：{assumptions['investable']:,.0f} 元"
    )
    liquidity_text = (
        "0%（全仓 R2，短桶承担流动性）"
        if assumptions["cash_pct"] == 0
        else f"{assumptions['cash_pct'] * 100:.1f}%（R2 现金管理）"
    )
    lines.append(f"- 流动性仓：{liquidity_text}")
    lines.append(
        f"- 模型：{PROFILE_LABELS.get(assumptions['profile'], assumptions['profile'])}；"
        f"单只上限 {assumptions['max_product_pct']*100:.0f}%；"
        f"发行方仅展示；最小交易单位 {assumptions['min_unit']:,.0f} 元"
    )
    lines.append("")
    lines.append("## 桶目标")
    lines.append("")
    lines.append("| 桶 | 目标比例 | 目标金额 |")
    lines.append("|---|---:|---:|")
    for item in result["bucket_targets"]:
        lines.append(
            f"| {item['label']} | {item['weight_pct']:.1f}% | {item['target_amount']:,.0f} |"
        )
    lines.append("")
    target_analysis = result.get("target_analysis")
    if target_analysis:
        lines.append("## 目标检查")
        lines.append("")
        lines.append(
            f"- 目标年化：{target_analysis['target_annualized_pct']:.2f}%；"
            f"月目标：{target_analysis['required_monthly_pct']:.3f}%"
        )
        weighted = target_analysis["weighted_annualized_pct"]
        if weighted is None:
            lines.append("- 组合输入年化：未计算（产品池缺 annualized_yield）")
        else:
            gap = target_analysis["target_gap_bp"]
            lines.append(
                f"- 组合输入年化：{weighted:.2f}%；"
                f"缺口：{gap:+.0f} bp；状态：{target_analysis['status']}"
            )
            lines.append(
                f"- 覆盖：{target_analysis['coverage_pct']:.0f}% 的已分配金额有年化输入"
            )
        lines.append(f"- 说明：{target_analysis['note']}")
        lines.append("")
    if result["allocations"]:
        lines.append("## 产品分配")
        lines.append("")
        lines.append("| 桶 | 产品 | 发行方 | 期限 | 金额 | 占可投资 | 评分 |")
        lines.append("|---|---|---|---:|---:|---:|---:|")
        for item in result["allocations"]:
            lines.append(
                f"| {item['bucket_label']} | {item['name']} | {item['issuer']} | "
                f"{item['term_days']:.0f}天 | {item['amount']:,.0f} | "
                f"{item['pct_of_investable']:.1f}% | {item['score']:.0f} |"
            )
        lines.append("")
    lines.append("## 汇总")
    lines.append("")
    lines.append(f"- 已分配：{result['totals']['allocated']:,.0f} 元")
    lines.append(f"- 未分配：{result['totals']['unallocated']:,.0f} 元")
    if result["leftover"]:
        lines.append("")
        lines.append("未分配明细：")
        for item in result["leftover"]:
            lines.append(f"- {item['label']}：{item['amount']:,.0f} 元")
    if result["warnings"]:
        lines.append("")
        lines.append("## 警告")
        lines.append("")
        for warning in result["warnings"]:
            lines.append(f"- {warning}")
    lines.append("")
    lines.append(
        "> 这是配置算术，不是投资建议。购买前需重新核对风险等级、额度、费率、赎回规则和产品说明书。"
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="R2 四桶配置与产品分配")
    parser.add_argument("--amount", type=float, required=True, help="总资金（元）")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="balanced",
        help="配置模型，默认 balanced",
    )
    parser.add_argument(
        "--cash-reserve",
        type=float,
        default=0,
        help="组合外预留现金（元），默认 0",
    )
    parser.add_argument(
        "--cash-pct",
        type=float,
        default=0.0,
        help="R2 流动性仓比例（0-1），默认 0；0 表示全部资金进短/中/长 R2",
    )
    parser.add_argument(
        "--target",
        type=float,
        default=3.0,
        help="目标年化（%%），默认 3.0；设为 0 可关闭目标检查",
    )
    parser.add_argument("--min-unit", type=float, default=1000, help="最小交易单位（元），默认 1000")
    parser.add_argument("--max-product-pct", type=float, default=0.25, help="单只上限，默认 25%%")
    parser.add_argument("--pool", type=Path, help="产品池 CSV；不提供则只输出桶目标")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser


def force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    args = build_parser().parse_args(argv)
    products: list[Product] = []
    pool_warnings: list[str] = []
    if args.pool:
        if not args.pool.exists():
            print(f"产品池不存在: {args.pool}", file=sys.stderr)
            return 2
        try:
            products, pool_warnings = load_pool(args.pool)
        except (OSError, ValueError) as exc:
            print(f"读取产品池失败: {exc}", file=sys.stderr)
            return 2
    try:
        result = allocate(
            amount=args.amount,
            profile_name=args.profile,
            cash_reserve=args.cash_reserve,
            cash_pct=args.cash_pct,
            target=args.target,
            min_unit=args.min_unit,
            max_product_pct=args.max_product_pct,
            products=products,
        )
    except ValueError as exc:
        print(f"参数错误: {exc}", file=sys.stderr)
        return 2
    result["warnings"] = pool_warnings + result["warnings"]
    if not args.pool:
        result["warnings"].insert(0, "未提供产品池，仅输出桶目标。")
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
