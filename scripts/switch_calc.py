#!/usr/bin/env python3
"""Compare holding an R2 product with switching to another one.

Compound-return calculation after fees and idle days. The current product is
assumed to be held to its maturity/open date; the early-redemption fee applies
only to the switch path. It does not forecast returns or verify either product.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any


def money(value: float) -> float:
    return round(value + 1e-9, 2)


def calculate(
    amount: float,
    current_yield_pct: float,
    remaining_days: float,
    redemption_fee_bps: float,
    idle_days: float,
    new_yield_pct: float,
    purchase_fee_bps: float,
) -> dict[str, Any]:
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("--amount 必须大于 0")
    if not math.isfinite(remaining_days) or remaining_days < 0:
        raise ValueError("--remaining-days 不能为负")
    if not math.isfinite(idle_days) or idle_days < 0:
        raise ValueError("--idle-days 不能为负")
    if (
        not math.isfinite(redemption_fee_bps)
        or not math.isfinite(purchase_fee_bps)
        or redemption_fee_bps < 0
        or purchase_fee_bps < 0
    ):
        raise ValueError("费率不能为负")
    if (
        not math.isfinite(current_yield_pct)
        or not math.isfinite(new_yield_pct)
        or current_yield_pct <= -100
        or new_yield_pct <= -100
    ):
        raise ValueError("参考年化必须大于 -100%")

    current_yield = current_yield_pct / 100.0
    new_yield = new_yield_pct / 100.0
    new_days = max(0.0, remaining_days - idle_days)

    current_gross = amount * (
        (1.0 + current_yield) ** (remaining_days / 365.0) - 1.0
    )
    redemption_fee = amount * redemption_fee_bps / 10_000.0
    current_net = current_gross

    new_gross = amount * (
        (1.0 + new_yield) ** (new_days / 365.0) - 1.0
    )
    purchase_fee = amount * purchase_fee_bps / 10_000.0
    # The redemption fee is paid only on the switch path. Holding the current
    # product to its maturity/open date does not trigger an early-redemption fee.
    new_net = new_gross - redemption_fee - purchase_fee

    difference = new_net - current_net
    break_even_yield_pct: float | None
    required_growth = (
        1.0
        + (current_net + redemption_fee + purchase_fee) / amount
        if new_days > 0
        else None
    )
    if required_growth is not None and required_growth > 0:
        break_even_yield_pct = (
            required_growth ** (365.0 / new_days) - 1.0
        ) * 100.0
    else:
        break_even_yield_pct = None

    idle_cost = amount * (
        (1.0 + new_yield) ** (remaining_days / 365.0)
        - (1.0 + new_yield) ** (new_days / 365.0)
    )
    fee_drag = redemption_fee + purchase_fee
    warnings: list[str] = []
    if new_days <= 0:
        warnings.append("空档天数大于等于剩余天数，切换没有计息时间。")
    if remaining_days > 0 and idle_days / remaining_days >= 0.5:
        warnings.append("空档天数占剩余期限一半以上，切换成本很高。")
    if break_even_yield_pct is not None and break_even_yield_pct > 5.0:
        warnings.append(
            f"盈亏平衡年化 {break_even_yield_pct:.2f}% 对 R2 偏高，切换大概率不划算或数据有误。"
        )
    if fee_drag > max(0.0, difference):
        warnings.append("费用已吃掉大部分或全部收益差。")

    if new_days <= 0:
        verdict = "不要切换：没有计息时间。"
    elif difference > 0 and break_even_yield_pct is not None and new_yield_pct > break_even_yield_pct:
        verdict = "收益上值得切换；仍需复核风险、流动性和额度。"
    else:
        verdict = "收益上不值得切换；除非有风险、流动性或配置上的明确理由。"

    return {
        "inputs": {
            "amount": money(amount),
            "current_yield_pct": current_yield_pct,
            "remaining_days": remaining_days,
            "redemption_fee_bps": redemption_fee_bps,
            "idle_days": idle_days,
            "new_yield_pct": new_yield_pct,
            "purchase_fee_bps": purchase_fee_bps,
        },
        "results": {
            "new_days": new_days,
            "current_gross": money(current_gross),
            "redemption_fee": money(redemption_fee),
            "current_net": money(current_net),
            "new_gross": money(new_gross),
            "purchase_fee": money(purchase_fee),
            "new_net": money(new_net),
            "difference": money(difference),
            "break_even_yield_pct": (
                round(break_even_yield_pct, 4) if break_even_yield_pct is not None else None
            ),
            "idle_cost": money(idle_cost),
            "fee_drag": money(fee_drag),
        },
        "verdict": verdict,
        "warnings": warnings,
        "note": (
            "复利计算：费率按初始金额一次性计算，不按扣费后本金二次计息；"
            "假设旧产品继续持有至到期/开放日，不产生提前赎回费，赎回费只在切换路径扣除。"
            "未计税费、净值波动和产品间风险差异。"
        ),
    }


def render_markdown(result: dict[str, Any]) -> str:
    inputs = result["inputs"]
    results = result["results"]
    lines = [
        "# R2 切换测算",
        "",
        f"- 金额：{inputs['amount']:,.0f} 元",
        f"- 旧产品：年化 {inputs['current_yield_pct']:.2f}%，剩余 {inputs['remaining_days']:.0f} 天，"
        f"赎回费 {inputs['redemption_fee_bps']:.0f}bp",
        f"- 新产品：年化 {inputs['new_yield_pct']:.2f}%，申购费 {inputs['purchase_fee_bps']:.0f}bp，"
        f"空档 {inputs['idle_days']:.0f} 天",
        "",
        "## 结果",
        "",
        "| 项目 | 金额 |",
        "|---|---:|",
        f"| 旧产品继续持有（不提前赎回） | {results['current_net']:,.2f} 元 |",
        f"| 切换至新产品（扣赎回费 + 申购费） | {results['new_net']:,.2f} 元 |",
        f"| 切换差额 | {results['difference']:,.2f} 元 |",
        f"| 空档少计收益（按新收益率估，已体现在新产品计息天数中） | {results['idle_cost']:,.2f} 元 |",
        f"| 赎回费（切换时） | {results['redemption_fee']:,.2f} 元 |",
        f"| 申购费 | {results['purchase_fee']:,.2f} 元 |",
        f"| 费用合计 | {results['fee_drag']:,.2f} 元 |",
    ]
    if results["break_even_yield_pct"] is not None:
        lines.append(f"| 盈亏平衡年化 | {results['break_even_yield_pct']:.2f}% |")
    lines.append("")
    lines.append("## 结论")
    lines.append("")
    lines.append(result["verdict"])
    if result["warnings"]:
        lines.append("")
        lines.append("## 警告")
        lines.append("")
        for warning in result["warnings"]:
            lines.append(f"- {warning}")
    lines.append("")
    lines.append(f"> {result['note']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="R2 持有 vs 切换测算")
    parser.add_argument("--amount", type=float, required=True, help="切换金额（元）")
    parser.add_argument("--current-yield", type=float, required=True, help="旧产品年化（%）")
    parser.add_argument(
        "--remaining-days",
        type=float,
        required=True,
        help="旧产品距到期/开放日的剩余天数（假设继续持有至该时点）",
    )
    parser.add_argument(
        "--redemption-fee-bps",
        type=float,
        default=0,
        help="切换时旧产品的提前赎回费（bp；继续持有不扣）",
    )
    parser.add_argument("--idle-days", type=float, default=2, help="赎回至新产品起息的空档天数")
    parser.add_argument("--new-yield", type=float, required=True, help="新产品年化（%）")
    parser.add_argument(
        "--purchase-fee-bps",
        type=float,
        default=0,
        help="新产品申购费（bp）",
    )
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)

    try:
        result = calculate(
            amount=args.amount,
            current_yield_pct=args.current_yield,
            remaining_days=args.remaining_days,
            redemption_fee_bps=args.redemption_fee_bps,
            idle_days=args.idle_days,
            new_yield_pct=args.new_yield,
            purchase_fee_bps=args.purchase_fee_bps,
        )
    except ValueError as exc:
        print(f"参数错误: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
