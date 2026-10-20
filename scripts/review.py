#!/usr/bin/env python3
"""Compute R2 daily-log metrics and a monthly review report."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any


def parse_date(value: str) -> date:
    text = (value or "").strip().replace("/", "-")
    parts = text.split("-")
    if len(parts) == 3:
        text = f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    return date.fromisoformat(text)


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_log(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    grouped: dict[date, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV 没有表头")
        required = {"date", "principal", "daily_pnl"}
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV 缺少列: {', '.join(sorted(missing))}")

        for row_number, row in enumerate(reader, start=2):
            try:
                day = parse_date(row.get("date") or "")
            except (ValueError, TypeError):
                warnings.append(f"第 {row_number} 行日期无效，已跳过：{row.get('date')!r}")
                continue
            principal = parse_float(row.get("principal"))
            daily_pnl = parse_float(row.get("daily_pnl"))
            if principal is None or daily_pnl is None:
                warnings.append(f"第 {row_number} 行本金或收益缺失，已跳过。")
                continue
            if principal <= 0:
                warnings.append(f"第 {row_number} 行本金不为正，已跳过。")
                continue
            cash_balance = parse_float(row.get("cash_balance"))
            action = (row.get("action") or "").strip()
            notes = (row.get("notes") or "").strip()

            if day not in grouped:
                grouped[day] = {
                    "date": day,
                    "principal": principal,
                    "daily_pnl": daily_pnl,
                    "cash_balance": cash_balance,
                    "action": action,
                    "notes": notes,
                    "rows": 1,
                }
            else:
                item = grouped[day]
                item["daily_pnl"] += daily_pnl
                item["principal"] = principal
                if cash_balance is not None:
                    item["cash_balance"] = cash_balance
                if action:
                    item["action"] = f"{item['action']}；{action}".strip("；")
                if notes:
                    item["notes"] = f"{item['notes']}；{notes}".strip("；")
                item["rows"] += 1
                warnings.append(f"{day} 有多行记录，已合并。")

    records = [grouped[key] for key in sorted(grouped)]
    return records, warnings


def grade(month_return_pct: float, thresholds: tuple[float, float, float, float]) -> str:
    pass_threshold, good, excellent, outstanding = thresholds
    if month_return_pct >= outstanding:
        return "卓越"
    if month_return_pct >= excellent:
        return "优秀"
    if month_return_pct >= good:
        return "良好"
    if month_return_pct >= pass_threshold:
        return "及格"
    return "不及格"


def compute(
    records: list[dict[str, Any]],
    thresholds: tuple[float, float, float, float],
    target_annualized: float | None,
) -> dict[str, Any]:
    if not records:
        raise ValueError("没有有效记录")

    first_day = records[0]["date"]
    last_day = records[-1]["date"]
    calendar_days = (last_day - first_day).days + 1
    if calendar_days <= 0:
        raise ValueError("日期范围无效")

    principals = [float(item["principal"]) for item in records]
    pnls = [float(item["daily_pnl"]) for item in records]
    avg_principal = sum(principals) / len(principals)
    total_pnl = sum(pnls)

    daily_returns: list[float] = []
    cumulative = 1.0
    curve: list[float] = []
    for item in records:
        daily_return = float(item["daily_pnl"]) / float(item["principal"])
        daily_returns.append(daily_return)
        cumulative *= 1.0 + daily_return
        curve.append(cumulative)

    period_return = cumulative - 1.0
    annualized = None
    if cumulative > 0:
        annualized = cumulative ** (365.0 / calendar_days) - 1.0
    annualized_pct = annualized * 100.0 if annualized is not None else None
    required_monthly_pct = None
    target_gap_pct = None
    target_status = "未设置"
    if target_annualized is not None and target_annualized > 0:
        required_monthly_pct = ((1 + target_annualized / 100.0) ** (1 / 12) - 1) * 100.0
        if annualized_pct is not None:
            target_gap_pct = annualized_pct - target_annualized
            if calendar_days < 28:
                target_status = "样本不足"
            else:
                target_status = "达到" if target_gap_pct >= 0 else "低于目标"

    peak = 1.0
    max_drawdown = 0.0
    for value in curve:
        peak = max(peak, value)
        drawdown = value / peak - 1.0
        max_drawdown = min(max_drawdown, drawdown)

    negative_days = sum(1 for value in daily_returns if value < 0)
    cash_values = [
        float(item["cash_balance"]) / float(item["principal"])
        for item in records
        if item.get("cash_balance") is not None
    ]
    cash_drag = sum(cash_values) / len(cash_values) if cash_values else None

    actions = [
        item["action"]
        for item in records
        if item.get("action") and item["action"] not in {"无操作", "none", "hold", "持有"}
    ]

    monthly_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        monthly_groups[item["date"].strftime("%Y-%m")].append(item)

    monthly: list[dict[str, Any]] = []
    for month_key in sorted(monthly_groups):
        items = monthly_groups[month_key]
        month_pnl = sum(float(item["daily_pnl"]) for item in items)
        month_avg_principal = sum(float(item["principal"]) for item in items) / len(items)
        month_return = month_pnl / month_avg_principal if month_avg_principal else 0.0
        month_days = (items[-1]["date"] - items[0]["date"]).days + 1
        month_annualized = None
        if month_days >= 7 and (1.0 + month_return) > 0:
            month_annualized = (1.0 + month_return) ** (365.0 / month_days) - 1.0
        monthly.append(
            {
                "month": month_key,
                "days": len(items),
                "avg_principal": month_avg_principal,
                "pnl": month_pnl,
                "return_pct": month_return * 100.0,
                "annualized_pct": month_annualized * 100.0 if month_annualized is not None else None,
                "target_gap_pct": (
                    month_annualized * 100.0 - target_annualized
                    if month_annualized is not None
                    and target_annualized is not None
                    and target_annualized > 0
                    else None
                ),
                "target_status": (
                    "样本不足"
                    if month_annualized is not None
                    and target_annualized is not None
                    and target_annualized > 0
                    and (month_days < 28 or len(items) < 20)
                    else "达到"
                    if month_annualized is not None
                    and target_annualized is not None
                    and target_annualized > 0
                    and month_annualized * 100.0 >= target_annualized
                    else "低于目标"
                    if month_annualized is not None
                    and target_annualized is not None
                    and target_annualized > 0
                    else "未设置"
                ),
                "grade": (
                    "样本不足"
                    if month_days < 28 or len(items) < 20
                    else grade(month_return * 100.0, thresholds)
                ),
            }
        )

    warnings: list[str] = []
    if calendar_days < 28:
        warnings.append("样本不足一个完整月，年化收益噪音很大，仅作参考。")
    if negative_days / len(records) > 0.30:
        warnings.append("负收益天数超过 30%，检查久期、信用暴露和产品稳定性。")
    if max_drawdown < -0.003:
        warnings.append("最大回撤超过 0.30%，超出保守型 R2 的常见体验，需复核产品。")
    if cash_drag is not None and cash_drag > 0.20:
        warnings.append("闲置资金拖累超过 20%，确认是否为了流动性，还是资金没有按计划配置。")
    if cash_drag is None:
        warnings.append("没有流动性仓余额数据，无法计算闲置资金拖累。")
    if max(principals) / min(principals) > 1.10:
        warnings.append("本金变化超过 10%，区间收益率的可比性下降。")
    if target_gap_pct is not None and calendar_days < 28:
        warnings.append("样本不足一个完整月，目标差距和年化仅作参考。")
    elif target_gap_pct is not None and target_gap_pct < 0:
        warnings.append(
            f"区间年化 {annualized_pct:.2f}%，低于目标 {target_annualized:.2f}%，"
            f"缺口 {abs(target_gap_pct):.2f} 个百分点；不要用杠杆或假收益补。"
        )

    return {
        "period": {
            "start": first_day.isoformat(),
            "end": last_day.isoformat(),
            "calendar_days": calendar_days,
            "records": len(records),
        },
        "summary": {
            "total_pnl": total_pnl,
            "avg_principal": avg_principal,
            "return_pct": period_return * 100.0,
            "annualized_pct": annualized_pct,
            "target_annualized_pct": target_annualized,
            "required_monthly_pct": required_monthly_pct,
            "target_gap_pct": target_gap_pct,
            "target_status": target_status,
            "max_drawdown_pct": max_drawdown * 100.0,
            "negative_days": negative_days,
            "negative_day_ratio_pct": negative_days / len(records) * 100.0,
            "best_day": max(pnls),
            "worst_day": min(pnls),
            "cash_drag_pct": cash_drag * 100.0 if cash_drag is not None else None,
            "action_count": len(actions),
        },
        "monthly": monthly,
        "warnings": warnings,
        "note": "评级阈值是公开笔记中的个人参考，不是行业标准或收益承诺。",
    }


def render_markdown(result: dict[str, Any]) -> str:
    period = result["period"]
    summary = result["summary"]
    lines = [
        "# R2 复盘",
        "",
        f"- 区间：{period['start']} 至 {period['end']}（{period['calendar_days']} 天，{period['records']} 条记录）",
        "",
        "## 总览",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| 总收益 | {summary['total_pnl']:,.2f} 元 |",
        f"| 平均本金 | {summary['avg_principal']:,.0f} 元 |",
        f"| 区间收益率 | {summary['return_pct']:.3f}% |",
    ]
    if summary["annualized_pct"] is not None:
        lines.append(f"| 年化收益率（参考） | {summary['annualized_pct']:.2f}% |")
    if summary["target_annualized_pct"] is not None and summary["target_annualized_pct"] > 0:
        lines.append(f"| 目标年化 | {summary['target_annualized_pct']:.2f}% |")
        lines.append(f"| 月目标 | {summary['required_monthly_pct']:.3f}% |")
        if summary["target_gap_pct"] is not None:
            lines.append(
                f"| 目标差距 | {summary['target_gap_pct']:+.2f} 个百分点（{summary['target_status']}） |"
            )
    lines.extend(
        [
            f"| 最大回撤 | {summary['max_drawdown_pct']:.3f}% |",
            f"| 负收益天数 | {summary['negative_days']} 天（{summary['negative_day_ratio_pct']:.1f}%） |",
            f"| 最好/最差单日 | {summary['best_day']:,.2f} / {summary['worst_day']:,.2f} 元 |",
        ]
    )
    if summary["cash_drag_pct"] is not None:
        lines.append(f"| 闲置资金拖累 | {summary['cash_drag_pct']:.1f}% |")
    lines.append(f"| 操作次数 | {summary['action_count']} |")
    lines.append("")
    lines.append("## 月度")
    lines.append("")
    lines.append("| 月份 | 天数 | 平均本金 | 月收益 | 月收益率 | 年化（参考） | 目标差距 | 评级 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for item in result["monthly"]:
        annualized = (
            f"{item['annualized_pct']:.2f}%" if item["annualized_pct"] is not None else "—"
        )
        target_gap = (
            f"{item['target_gap_pct']:+.2f}pp"
            if item["target_gap_pct"] is not None
            else "—"
        )
        lines.append(
            f"| {item['month']} | {item['days']} | {item['avg_principal']:,.0f} | "
            f"{item['pnl']:,.2f} | {item['return_pct']:.3f}% | {annualized} | "
            f"{target_gap} | {item['grade']} |"
        )
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
    parser = argparse.ArgumentParser(description="R2 每日收益记录复盘")
    parser.add_argument("--input", type=Path, required=True, help="每日记录 CSV")
    parser.add_argument(
        "--grade-thresholds",
        default="0.16,0.20,0.25,0.30",
        help="月度评级阈值（%），依次为及格/良好/优秀/卓越",
    )
    parser.add_argument(
        "--target",
        type=float,
        default=3.0,
        help="目标年化（%），默认 3.0；设为 0 可关闭目标检查",
    )
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)

    if args.target < 0 or args.target > 20:
        print("--target 需要在 0–20 之间", file=sys.stderr)
        return 2
    try:
        thresholds = tuple(float(part.strip()) for part in args.grade_thresholds.split(","))
        if len(thresholds) != 4:
            raise ValueError("评级阈值需要 4 个数")
    except ValueError as exc:
        print(f"评级阈值错误: {exc}", file=sys.stderr)
        return 2
    if not args.input.exists():
        print(f"输入文件不存在: {args.input}", file=sys.stderr)
        return 2

    try:
        records, load_warnings = load_log(args.input)
        result = compute(records, thresholds, args.target)  # type: ignore[arg-type]
    except (OSError, ValueError) as exc:
        print(f"复盘失败: {exc}", file=sys.stderr)
        return 2
    result["warnings"] = load_warnings + result["warnings"]

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
