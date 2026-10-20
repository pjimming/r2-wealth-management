# 招行 R2 公开数据自动化（本工作区已验证）

## 何时读这份参考

当任务需要更新招行 R2 产品快照、扫描更大的 R2 产品池、解释应用为什么选中某份 CSV，或复核 3% 目标在当前池子的可行性时，读这份参考。

这里记录的是 2026-10-19 已验证的公开接口和本工作区脚本。接口、字段或签名可能变化；每次实际更新都要重新验证，不能把本文当成永久 API 合同。

## 数据源分层

| 层级 | 来源 | 能拿到什么 | 不能替代什么 |
|---|---|---|---|
| 1 | 招行 App | 实时额度、可买状态、实际起购、赎回 T+n、订单入口 | 不能用公开接口替代 |
| 2 | 招行理财产品统一查询平台 `finprod.paas.cmbchina.com` | R2/开放/代销产品列表、1M/3M/6M/1Y、基准、固定费率、起购、下一开放日 | 实时额度、实际可买、赎回到账 |
| 3 | 招行移动端 R2 货架 `mobile.cmbchina.com` | 移动端展示年化、期限、起购标签 | 它的年化可能是“成立以来”，不能直接当 1Y |
| 4 | 招银理财官网/中国理财网 | 产品说明书、登记编码、风险等级、公告 | 实时额度和账户资格 |

## 统一查询平台接口

```text
POST https://finprod.paas.cmbchina.com/api/prod/queryProdList
appid: FinProd
content-type: application/json;charset=UTF-8
signature / timespan / x-b3-businessid: 从公开页面请求中捕获
```

查询条件（对应页面截图）：

```json
{
  "keyWords": "<产品代码或名称，可空>",
  "type": "PN",
  "isOwn": "C",
  "isPublic": "Z",
  "status": "1",
  "pageNO": 1,
  "pageSize": 50,
  "crossFinance": "Z",
  "riskLevel": "R2",
  "obligate": ""
}
```

- `type=PN`：理财
- `isOwn=C`：代销
- `isPublic=Z`：公募/私募不限
- `status=1`：开放中
- `riskLevel=R2`：只要 R2
- `crossFinance=Z`：跨境理财通不限
- `keyWords` 传产品代码可直接定位单只产品

2026-10-19 实测：该条件返回 **980 只 R2 开放代销产品**，20 页 × 50 条。

### 字段映射

| 接口字段 | 含义 |
|---|---|
| `code` / `shortName` / `name` | 产品代码 / 简称 / 全称 |
| `orgName` | 发行机构 |
| `risk` | 风险等级 |
| `statusText` | `1` = 开放中 |
| `begdat` | 下一开放日（`YYYYMMDD`） |
| `buynfq` | 起购金额 |
| `zprfDat` | 业绩数据日期 |
| `zbasPrf` | 业绩比较基准 |
| `zbasDsc` | 基准测算说明 / 底层描述 |
| `pastPerf.tqilstw4z3` 的 `A/B/C/D/F` | 1M / 3M / 6M / 1Y / 成立以来年化 |
| `zchrCst + chrmn2 + chrsal` | 托管费 + 固定管理费 + 销售服务费（百分比） |
| `zrunDat` | 成立日期 |

`E`、`J` 是额外周期（如更长区间、年初至今），不要拿来替代 1M/3M/6M/1Y。

固定费率换算：

```text
fee_bps = (zchrCst + chrmn2 + chrsal) × 100
```

这个口径不含浮动业绩报酬、申购费和赎回费；产品说明书仍要看。

### 签名捕获

不要硬编码 `signature` 或 `timespan`。做法是用 Playwright 打开 `https://finprod.paas.cmbchina.com/`，页面会自动发起 `queryProdList` 请求；从请求头捕获 `appid`、`timespan`、`signature`、`x-b3-businessid`，然后在短时间内复用到后续查询。签名失效时重新加载页面再捕获。

如果页面结构、签名或接口变化，先停下来重新验证；不要猜签名，也不要用过期签名伪造更新结果。

## 移动端 R2 货架

```text
POST https://mobile.cmbchina.com/ientrustfinance/financelist/alllist
```

请求体使用 `evlLvl: "R2"`、`prdTyp: "F"`、`ordTyp: "A"`、`buyNf: "Z"` 等字段。公开页面不需要登录；随机 `mh5aid`、`MFE_MSID2`、`x-mfe-uid`、`x-mfe-msid` 也可返回数据，`sysCode=1014` 可能只是未登录提示，仍要看 `bizResult.code=200` 和 `prdList`。

它适合做移动端展示核对，不适合作为 1Y 历史收益的唯一来源：`prdRat` 可能标注“成立以来年化”，和统一平台的 `D`（近 1 年）不是同一口径。

## 本工作区快照脚本

主脚本：`scripts/fetch-cmb-r2-all.cjs`

流程：

1. 用 Playwright 捕获统一查询平台签名。
2. 分页拉取 `riskLevel=R2`、开放中的全量代销产品。
3. 按普通可买条件筛选，生成 `cmb_r2_universe`。
4. 用 `buildProductView()` 生成短/中/长每桶前 3 只的研究观察池。
5. 写入 `data/cmb_r2_all-YYYY-MM-DD.csv`、`data/cmb_r2_universe-YYYY-MM-DD.csv`、`data/cmb_r2_selected-YYYY-MM-DD.csv`。
6. 调用 `POST http://127.0.0.1:8765/api/products/refresh`，让应用切换到最新 universe 快照。

约束：

- 不登录招行账户，不抓实时额度，不替用户下单。
- 三个 CSV 都是公开数据的本地快照；`selected` 只用于研究排序，不是买入清单或资金分配结果。
- 接口、签名或字段变化时先重新验证；失败时不要用旧数据伪装成新快照。
- 旧脚本 `scripts/fetch-cmb-r2-snapshot.cjs` 只保留兼容，不再作为默认更新路径。

定时任务：`R2产品快照每周更新`（自动化 ID `r2`），每周一 08:30。电脑和 Codex 应用需要在运行；错过时客户端下次启动可能补跑一次，但不保证。

## 快照选择与刷新

服务端 `resolveProductCsv()` 的顺序：

1. `R2_PRODUCT_CSV` 环境变量：直接使用指定路径，优先级最高。
2. 扫描 `data/cmb_r2_universe*.csv`，优先使用普通可买候选池。
3. 找不到时回退 `data/cmb_r2_products*.csv`（旧版兼容快照）。
4. 从**文件名**提取第一个 `YYYY-MM-DD`，按日期倒序；同日期按 `mtime` 倒序。
5. 仍没有候选时回退 `data/cmb_r2_universe.csv`。

“刷新快照”调用 `POST /api/products/refresh`，会重新执行上面的选择，然后 `replaceProducts()` 在一个事务里 `DELETE FROM products` 并插入新 CSV 的全部产品。它是整表替换，不是合并；失败时回滚，旧池保留。

页面上的两个日期不是文件名日期：

- `product_snapshot_date`：所有产品 `data_date` 的最大值。
- `product_history_date`：有 1Y 数据的产品里 `data_date` 的最大值。

所以文件名可以是 2026-10-19，而页面显示“快照 2026-10-18、历史 2026-10-15”，这不代表选错文件。

## 应用观察池评分

应用不是直接用 CSV 的 `score` 列，而是重新计算：

```text
observation_score = 0.45 × 3M + 0.30 × 6M + 0.25 × 1Y
```

如果 `1M < 3M - 0.5`，再扣 0.08。`selection_score` 另做两项调整：`1Y - 6M > 1` 时最多扣 0.25；成立满 18/24 个月分别加 0.015/0.03。

进入观察池的条件：

- R2/PR2
- 人民币、公募普通产品，剔除私行/私银/私享/尊享/企享/专属/私募
- `capacity !== 0`
- 状态为“开放中”，且不含“募集/新发/未开放”
- 成立满 12 个月
- 1M、3M、6M、1Y 都有数值

期限桶：`<=1` 日开、`<=30` 短、`<=100` 中、`>100` 长。研究观察池从短/中/长各取前 3 只，最多 9 只。

实际配置的 `watchlist` 不是每桶固定一只。`buildProductView` 会按本金、已确认持仓、待确认买入、期限桶目标、流动性下限、未来现金流、单只/发行方/底层策略上限和逐只额度，动态决定产品数量与目标金额；`cmb_r2_selected` 不代表最终配置。

## 2026-10-19 已验证快照

快照：`data/cmb_r2_all-2026-10-19.csv`（980 只原始）、`data/cmb_r2_universe-2026-10-19.csv`（432 只普通可买候选）、`data/cmb_r2_selected-2026-10-19.csv`（9 只研究观察池）。

候选池期限分布：

| 桶 | 数量 |
|---|---:|
| 日开 | 17 |
| 短（2–30 天） | 159 |
| 中（31–100 天） | 93 |
| 长（>100 天） | 163 |

研究观察池代码：`JX040210,JX040213,SY040201,ZX040233,XY040215,111301,GD040320,GD040242,PAPB0105`。短/中/长各 3 只。

2026-10-19 的 1Y 中位：全池约 1.73%，研究观察池约 2.72%。研究观察池仍低于 3%，且其中部分 1Y 高值可能受前期行情推动，不能把 1Y 历史输入当作未来一年收益。

30,000 元等具体金额的 target3 配置，以应用按当时本金、持仓、待确认买入、现金流、额度与集中度约束动态计算的结果为准；不要再把“每桶一只”或某份固定六只清单当成工作台规则。

## 买入日仍要核验

- R2/PR2 是否仍成立
- D/K 等份额类别和渠道是否可买
- 起购金额、费率、浮动业绩报酬、赎回费
- 赎回 T+n、最短持有期、到账日
- 当日额度、买入截止、确认日

公开接口只能帮助筛选和更新快照，不能替代 App 当天的交易规则。
