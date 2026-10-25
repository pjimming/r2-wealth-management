# 期限调整参考年化与评分口径

本文件是 `r2-wealth-management` Skill 与钱多多工作台共同的收益证据口径。它只统一“参考年化、期限桶、证据档位和收益诊断字段”，不把应用的 `selection_score` 与 Skill 的 0–100 多因子 `total_score` 混成同一个分数。

## 适用范围

- 产品研究池、证据分层和短历史仓位上限；
- `reference_yield_pct` 与兼容字段 `weighted_yield_pct`；
- 应用内观察评分、选择评分和桶内排序；
- 持仓替换时当前产品与候选产品的参考年化比较；
- 收益归因中的产品选择估算。

Skill 的产品配置仍按稳定性、流动性、收益、费用和执行五项形成 `total_score`。应用若使用只针对收益的 `selection_score`，必须单独标明，不能把它写成 Skill 的 `total_score`。

## 期限桶

只接受非负安全整数天数：

| 桶 | 期限 | 用途 |
|---|---:|---|
| `cash` | `0` 天 | 日开现金管理；当前招行工作台仅展示 |
| `short` | `1–30` 天 | 排序及评分候选 |
| `medium` | `31–100` 天 | 排序及评分候选 |
| `long` | `101+` 天 | 排序及评分候选 |

`null`、负数、小数、非安全整数、`NaN` 和无穷值都归入 `unknown`。`unknown` 不进入产品池、排名、评分、预算、候选或提案。

“评分期限桶 short=1–30 天”与“组合流动性优先使用 7–30 天产品”是两个概念。前项决定收益窗口，后项是风险与现金流安排，不能共用同一个模糊标签。

## 参考年化

| 桶 | 1M | 3M | 6M | 1Y |
|---|---:|---:|---:|---:|
| `cash` | 70% | 30% | — | — |
| `short` | 20% | 50% | 30% | — |
| `medium` | — | 50% | 30% | 20% |
| `long` | — | 20% | 40% | 40% |

规则：

- 只使用当前桶列出的窗口；
- 缺失窗口按剩余原始权重重新归一化；
- 数值 `0` 是有效收益，不视为缺失；
- 指定窗口全部缺失时返回 `unavailable`，数值为 `null`，不得用 0 或旧字段补齐；
- `unknown` 期限返回 `unavailable / unknown_term`。

返回契约：

| 字段 | 含义 |
|---|---|
| `reference_yield_pct` | 期限调整参考年化，4 位小数 |
| `reference_yield_status` | `available` 或 `unavailable` |
| `reference_yield_reason` | `complete_history`、`partial_history`、`no_available_horizons` 或 `unknown_term` |
| `reference_available_horizons` | 实际参与的窗口标签，如 `1m`、`3m` |
| `reference_normalized_weights` | 实际使用的归一化权重 |
| `weighted_yield_pct` | 与 `reference_yield_pct` 完全一致的兼容别名 |

`weighted_yield_pct` 不再独立计算，也不得用于第二套决策。

## 证据档位与仓位上限

| 档位 | 自动配置 | 当前招行工作台仓位上限 |
|---|---:|---:|
| `full_1y` | 是 | 沿用普通单只与策略上限 |
| `six_month` | 是 | 单只 10%，本档合计 20% |
| `three_month` | 是 | 单只 10%，本档合计 20% |
| `one_month` | 否 | 仅人工观察，单只 5%，同档合计 5% |
| `no_data` | 否 | 0 |

## 评分

应用 `selection_score` 的计算顺序固定为：

```text
期限参考基准
→ 1M/3M 发散扣分
→ B 方案前视扣分
→ 历史加成
→ 最终 4 位小数舍入
```

### 1M/3M 发散

仅当 `1M` 和 `3M` 都存在且 `1M < 3M − 0.5pp` 时扣 `0.08` 评分点。等号不扣。

### 前视扣分

令 `gap = 1Y − 6M`：

- short、medium：`gap > 1pp` 时扣 `min(0.25, (gap−1)×0.15)`；
- long：`gap > 1.5pp` 时扣 `min(0.25, (gap−1.5)×0.15)`；
- short、medium、long 以外的桶不评分。

### 历史加成

- 成立满 24 个月：`+0.03`；
- 成立满 18 个月但不足 24 个月：`+0.015`；
- 其他情况：0。

### 舍入

参考年化、观察评分和选择评分都保留 4 位小数，采用绝对值半值远离 0。排序使用对外暴露的 4 位选择评分。

## cash 规则

当前招行工作台中：

- cash 可以展示 `reference_yield_pct` 和兼容字段；
- 不生成观察评分或选择评分；
- 不进入研究排名、观察名单、自动配置、新仓候选、持仓替换候选或新提案；
- 现有日开持仓只能用于当前持仓事实诊断和迁移提示。

Skill 和当前招行工作台都不再生成新的日开配置目标。组合外应急金仍独立保留，组合内流动性由 short 桶承担；日开产品只用于展示和诊断现有持仓。

## Skill 脚本字段映射

| Skill / 应用字段 | 使用方式 |
|---|---|
| `reference_yield_pct` | 统一参考年化 |
| `weighted_yield_pct` | 兼容别名 |
| `observation_score` | 应用收益观察分 |
| `selection_score` | 应用桶内选择与替换诊断 |
| `total_score` | Skill 的五因子 0–100 综合分 |
| `yield_policy_version` | `r2-term-yield-v1` |

`score_products.py` 可以同时输出 `selection_score` 作为应用兼容诊断，但默认排序仍以 `total_score` 为主。只有明确执行“与应用产品池对齐”任务时，才按 `selection_score` 复现应用桶内排序。

## 跨实现验证

黄金案例必须覆盖：

- `0 / 1 / 30 / 31 / 100 / 101` 天边界；
- `null`、负数、小数、非安全整数和非法数值；
- cash、short、medium、long 完整与部分历史；
- 全部指定窗口缺失；
- 0 元收益；
- A/B/C 前视方案和最终 B 方案；
- 正、负半值舍入；
- cash 无评分；
- `weighted_yield_pct === reference_yield_pct`。

运行跨语言校验：

```text
python scripts/verify_policy.py --app-root D:\codex\钱多多财富工作台
```

该命令只读 Skill 资产和工作区源码，不写数据库或生产接口。
