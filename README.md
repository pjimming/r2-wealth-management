# R2 Wealth Management

`r2-wealth-management` 是一套面向中国银行 R2/PR2 理财的本地决策支持技能，覆盖产品筛选、期限桶配置、额度核验、买入检查、持仓复核、切换测算和周期复盘。

当前目录既是 Codex 实际加载的技能目录，也是该技能唯一的 Git 工作树。不要再在 `D:\codex\r2-wealth-management` 或其他路径维护镜像。

## 权威路径

```text
C:\Users\Administrator\.codex\skills\r2-wealth-management
```

远程仓库：

```text
https://github.com/pjimming/r2-wealth-management.git
```

默认分支：`main`

## 能力范围

- 仅处理已确认属于 R2/PR2 的银行理财产品。
- 按短期、中期、长期期限桶建立全仓配置，可按需启用小额 R2 现金管理仓。
- 在买入前核对风险等级、期限、赎回规则、费用、起购金额和额度状态。
- 对已确认持仓执行同期限候选比较，并计入赎回费、申购费和切换等待期。
- 跟踪目标差距、负收益天数、最大回撤、额度和流程执行情况。
- 发行方名称、金额和占比仅用于识别与展示，不作为筛选、分配、买入或持有上限。

本技能不登录银行账户、不查询实时额度、不代替用户下单、赎回或转账，也不构成投资建议。

## 目录结构

```text
.
├─ SKILL.md                 # Codex 技能入口与完整政策
├─ agents/openai.yaml       # 技能显示信息与隐式调用配置
├─ references/              # 筛选、配置、执行、数据源和风险说明
├─ assets/                  # 产品池、日志、复盘和单品备忘录模板
└─ scripts/                 # 标准库 Python 计算工具
```

## 快速使用

在 Codex 中显式调用：

```text
$r2-wealth-management 帮我检查当前 R2 配置，并给出下周需要复核的事项。
```

常用脚本：

```powershell
$skill = "C:\Users\Administrator\.codex\skills\r2-wealth-management"

python -B "$skill\scripts\score_products.py" --input "$skill\assets\product_pool_template.csv" --show-excluded
python -B "$skill\scripts\allocate.py" --amount 540000 --profile target3 --target 3.0 --pool "$skill\assets\product_pool_template.csv"
python -B "$skill\scripts\switch_calc.py" --amount 100000 --current-yield 3.0 --remaining-days 90 --idle-days 3 --new-yield 3.5
python -B "$skill\scripts\review.py" --input "$skill\assets\daily_log_template.csv" --target 3.0
```

脚本只使用 Python 标准库。运行时使用 `-B`，避免在工作树中生成 `__pycache__`。

## 主要脚本

| 脚本 | 用途 |
| --- | --- |
| `scripts/score_products.py` | 对产品池执行硬筛选和加权评分 |
| `scripts/allocate.py` | 按期限桶和目标生成产品金额，检查单只上限、额度与起购金额 |
| `scripts/switch_calc.py` | 计算切换费用、等待期和盈亏平衡年化 |
| `scripts/review.py` | 计算收益、年化、回撤、目标差距和月度评级 |

发行方字段可以进入输入、分配输出和展示报告，但 `allocate.py` 不再提供发行方比例上限参数。

## 修改与验证

1. 先读取 `SKILL.md`；如果改动规则或流程，同步更新相关 `references/`、`assets/` 和脚本。
2. 修改技能行为时更新 `SKILL.md` 中的 `metadata.version`。
3. 至少运行受影响脚本，并确认参数说明、JSON 输出和 Markdown 输出正常。
4. 检查工作树中没有 `__pycache__/`、`.pyc` 或真实账户导出等中间文件。
5. 只在当前权威目录提交和推送，不再复制到 D 盘维护第二个工作树。

```powershell
git status --short
git diff --check
git add SKILL.md README.md agents assets references scripts .gitignore
git commit -m "Update R2 wealth management skill"
git push origin main
```

## 数据与合规边界

- 公开快照中的额度和开放状态可能过期，买入前必须以银行 App、产品说明书和当日公告为准。
- R2/PR2 不等于保本，历史收益不代表未来收益。
- 不保存银行登录凭证、验证码、密码、身份证件或完整账户截图。
- 真实账户数据只用于用户授权的本地分析；提交前必须移除个人金额、产品持仓和截图。
