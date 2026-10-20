---
name: r2-wealth-management
description: "Operate a fully invested R2 bank wealth-management workflow with a 3%+ annualized target when feasible: screen, size, buy quota-limited issues, redeem or switch, ladder terms, and review. Use for Chinese bank R2/PR2, 招行/招银理财 quota timing, and cash-management plans. Not for stocks, funds, or guaranteed returns."
metadata:
  version: "1.4.0"
  short-description: R2 bank wealth-management operating system
---

# R2 Wealth Management

Turn the public "R2 + quota timing + daily P&L" playbook into a repeatable operating process. The method is inspired by public creator posts, not affiliated with any bank or creator. It is decision support, not investment advice. R2 products are not principal-protected, and past returns do not predict future returns.

## Operating stance

- Only consider products documented as R2/PR2 by the issuer or distributor. If the risk level is missing or ambiguous, exclude it until verified.
- Treat annualized 3%+ as the default stretch target, not a promise. Check feasibility against the current R2 pool; if 3% requires leverage or risk outside the user's limits, say so and show the gap.
- Run a fully invested R2 sleeve by default when the user confirms emergency cash is held outside. No idle cash: default cash reserve is 0 and the liquidity bucket is 0%; the short bucket is the liquidity source. If the user wants a T+0/T+1 parking product, use `--cash-pct` for a small R2 cash-management sleeve.
- No leverage, no borrowing, and no credit-card or consumer-loan funding. No all-in position in one product.
- A quota opening is not a buy signal. Buy only if the product still passes the screen and fits the bucket.
- Prefer issuer documents over social-media posts. Record the data date and source for every material number.
- The user makes the final buy and sell decision. Present tradeoffs and checklists; never promise a return.

## Workflow

### 0. Set the mandate

Establish or infer:

- investable amount and the emergency reserve held outside the plan; default the R2 sleeve to 0% cash;
- whether to keep a 0–15% R2 cash-management sleeve; default 0% (fully invested);
- target annualized return: default 3.0% (required monthly ≈0.247%); whether it is a stretch or a hard requirement;
- cash needs in 0–3, 3–6, and 6–12 months;
- maximum acceptable drawdown and tolerance for negative days;
- time available for quota monitoring;
- bank, app, and account constraints;
- whether the user wants a model portfolio, a product review, or a redemption decision.

If key inputs are missing, state assumptions and give a conditional plan instead of blocking.

### 1. Build the product pool

Read [product screening](references/product-screening.md). For CMB products, also read [data sources](references/data-sources.md) and [CMB automation](references/cmb-automation.md), and re-verify every quota, rate, and product code there. Use the public unified query platform to screen the broader R2 open/agency pool, not only the existing core CSV; then verify the shortlisted codes in the App. For each candidate record the product code, issuer, distributor, risk level, term, open/closed rules, purchase and redemption cutoffs, confirmation and arrival days, valuation method, benchmark and underlying assets, fees by share class, minimum amount, quota window, recent 1M/3M/6M/1Y annualized return, maximum drawdown, and data date.

Exclude anything that cannot be verified as R2, has unclear redemption terms, or depends on a quota story that cannot be checked.

### 2. Screen and score

Apply hard filters first:

- R2/PR2 verified;
- redemption available before the user's cash need;
- no leverage or complex payoff;
- fee and share class understood;
- at least three months of history for scored ranking; new products go to a separate checklist and are capped at 10%.

Then score with the [scorecard](references/product-screening.md#评分卡). Default weights are stability 30, liquidity 25, yield 20, fees 15, and execution 10. Yield is deliberately not dominant.

Before allocating, run a target feasibility check with [the 3% target guide](references/return-target.md): compare the best available R2 products' recent 3M/6M/1Y annualized returns and benchmark-implied yields with 3%. If the pool cannot support 3% within the user's drawdown and liquidity limits, mark the gap and do not fill it with leverage, fake yield, or unsuitable products.

Check 3M/6M/1Y together. A 1Y figure above the product's benchmark range can be historical, not forward; do not select it on 1Y alone.

### 3. Allocate by term bucket

Read [allocation models](references/allocation-models.md). The default is fully invested: 0% cash and 0% liquidity sleeve. Use three working buckets, plus an optional R2 cash-management sleeve:

- **liquidity sleeve (optional):** 0–15%, T+0/T+1 R2 cash management only; still an R2 product, not idle cash;
- **short:** 7–30 days;
- **medium:** 60–100 days;
- **long:** 120–180 days or longer.

Fully invested models:

| Model | Liquidity sleeve | Short | Medium | Long |
|---|---:|---:|---:|---:|
| Conservative | 0% | 45% | 40% | 15% |
| Balanced | 0% | 40% | 40% | 20% |
| Yield | 0% | 30% | 40% | 30% |
| Barbell | 0% | 50% | 0% | 50% |
| Ladder | 0% | 35% | 35% | 30% |
| 3% target | 0% | 30% | 35% | 35% |

When the liquidity sleeve is 0%, keep at least 30% in short 7–30 day or T+1 redeemable products. Never put more than 25–30% in one product. For a multi-bank mandate, keep each issuer at 40–50%; for a single-bank mandate such as CMB-only, the issuer cap can be 100%, but cap product series/underlying strategy and keep the single-product limit. If the emergency reserve is not outside the plan, stop and fix that before investing. `--cash-pct 0.10` moves 10% into an R2 cash-management product and scales the other three buckets down proportionally.

For a 3%+ target, start with `--profile target3`, `yield`, or `barbell` only if the horizon and drawdown budget allow it. Longer duration or credit-selected R2 may raise the yield ceiling, but it also raises volatility and lock-up risk. If the current long R2 products are still below 3%, do not pretend the model reaches the target.

As of 2026-10-19, the CMB ordinary candidate pool has 432 products (17 daily-open, 159 short, 93 medium, 163 long); its 1Y median is about 1.73%. A constrained target3 backtest can show a 1Y historical input around 2.9%, while 3M/6M run-rate is around 2.5%/1.9%. Report the 1Y and 3M/6M figures separately, and never turn the 1Y figure into a 3% forward return. See [CMB automation](references/cmb-automation.md) for the current snapshot and dynamic-allocation rules.

### 4. Execute the buy

Read [the execution playbook](references/execution-playbook.md). Confirm:

- the product is still R2 and still within its quota window;
- the purchase cutoff and confirmation date;
- the settlement path from the funding source;
- the fee and share class;
- the fallback product if the quota is missed.

For quota-limited products, prepare the order before the window, refresh at the stated time, and use the app's documented "additional purchase" path only if it is available to the account. If the quota is missed, do not chase a worse substitute just to stay invested. Keep the money in the short bucket or the optional R2 liquidity sleeve and wait for the next verified window.

### 5. Hold and monitor

Daily, record principal, daily P&L, liquidity balance (0 if fully invested), action, and quota notes. Weekly, check for negative-day clusters, benchmark drift, manager or fee changes, and redemption gates. Do not sell on one noisy day.

### 6. Sell, redeem, or switch

Read [sell and switch rules](references/execution-playbook.md#卖出与切换). Valid reasons:

- cash need or maturity;
- the product no longer fits the bucket;
- verified deterioration in risk, liquidity, fees, or mandate;
- a switch that clears the break-even test after fees and idle days;
- rebalancing back to the target model.

Do not redeem early solely because another product's headline yield is higher. Run `scripts/switch_calc.py` to compare holding versus switching after fees and settlement.

### 6b. Holding-by-holding replacement review

Run this review at least monthly, and whenever a holding enters its maturity or redemption-open window. The question is not "is there a higher headline yield?" but "after redemption, settlement idle days and fees, does switching improve the same-horizon outcome enough to justify the operational risk?"

For every confirmed lot:

1. **Match the current lot to the latest snapshot.** Use the product code, not the display name. Record the snapshot date. If the current product is missing from the snapshot, mark current yield and current rules as unavailable; do not substitute a similar product.
2. **Build a like-for-like candidate set.** Same R2/PR2 risk level, same term bucket, term close to the lot's remaining horizon, purchase minimum not above the remaining principal, and no private/closed product. Show no more than six candidates.
3. **Compare reference yield, not the 1Y headline.** Use `0.5 × 3M + 0.3 × 6M + 0.2 × 1Y` annualized, renormalised when a field is missing. Always show 3M/6M/1Y separately and the data date. A 1Y figure above the benchmark range is history, not a forward return.
4. **Use the same-horizon comparison.** For a fixed-term lot, use the remaining days to maturity. For a daily-open lot, use an explicit comparison horizon (default 30 days). If a candidate's term is shorter than the lot's remaining horizon, compare only over the candidate term and flag that reinvestment after it matures is uncertain; such a candidate cannot be a clean "replace". If the candidate term is longer, compare over the candidate term on the same horizon and disclose the extra lock-up.
5. **Charge the switch path properly.** Record redemption confirmation T+N, arrival T+N, redemption fee, purchase fee and expected idle days. Default idle days = redemption T+N + arrival T+N + 1 (buy confirmation) only when both T+N values are verified; otherwise use an explicit estimate and mark it unverified. Run `scripts/switch_calc.py` or the app's equivalent `r2-holding-review-v1` calculation; do not hand-wave the break-even.
6. **Apply the decision thresholds.** A candidate can be labelled **建议替换** only when all of the following hold:
   - reference-yield edge ≥ 0.15pp;
   - post-fee, post-idle gain ≥ max(10 CNY, 0.10% of remaining principal);
   - candidate yield > break-even yield + 0.05pp;
   - the candidate term is not materially shorter than the comparison horizon;
   - risk, liquidity and concentration do not worsen.
   If the economics pass but quota or redemption rules are unverified, keep the label but add "执行前核对" and do not treat it as an executable order. If only some conditions pass, use **观察**; otherwise **继续持有**.
7. **Gate the label on actual redeemability.** A fixed-term or holding-period lot that is still inside its lock-up cannot be switched now, even if the candidate economics look better. In that case the holding verdict must be **继续持有（锁定期）**, the candidate may be shown as **到期后可替换**, and the decision log entry must use action `观察` with `planned_action=replace_at_maturity`; do not write a `切换` action or imply an executable redemption. Only after the maturity/open date, or for a daily-open product with verified redemption, can the label become **建议替换** and action become `切换`.
8. **Record the decision before acting.** Write the replacement decision to the decision log with action `切换` (or `赎回`) only when redeemable now; otherwise use `观察` for the maturity plan. Include evidence date, verification date, the current and candidate codes, snapshot date, comparison horizon, idle days, fee drag, break-even yield, expected difference, and the explicit reason. A decision without an evidence date and a later verification date is incomplete.
9. **Set reminders.** Alert at 14 days and 3 days before maturity; alert at 3 days before a verified redemption-open date. For daily-open products without a fixed maturity, review monthly. Never use the public `next_open_date` (usually a purchase-opening date) as if it were a redemption date.

Output for each lot: current product and remaining principal, remaining term / comparison horizon, current reference yield and 3M/6M/1Y, verified redemption path or data gap, top candidates with fee and quota status, break-even, expected post-fee difference, one of the three verdicts, the reason, and the next verification date.

### 7. Review

Use [review templates](references/review.md) and `scripts/review.py`. Review daily in one minute, monthly in ten minutes, and quarterly in thirty minutes. Track return, annualized return, target gap, negative-day ratio, maximum drawdown, idle-cash drag (normally 0 in fully invested mode), fee drag, quota hit rate, concentration, and whether the process was followed. If rolling 3M/6M/1Y annualized stays below 3%, review duration, credit, fees, and whether the target is feasible for the current R2 pool.

## Data acquisition

The skill does not log into the user's account or place orders. For CMB, use [data sources](references/data-sources.md) and [CMB automation](references/cmb-automation.md) to update the public product pool; live quota, redemption terms, and actual purchasability still require the App on purchase day. CMB Wealth Management announcements and China Wealth remain the sources for documents and registration codes. Social posts are leads only. Recheck quota, rate, fees, and redemption rules on the purchase day.

## Output contract

When the user asks for a plan, return:

1. assumptions and constraints, including whether the plan is fully invested or includes an R2 liquidity sleeve, where the emergency reserve sits, and whether 3%+ is a stretch or a hard requirement;
2. a product shortlist with pass/fail reasons;
3. a bucket allocation table with amounts and percentages;
4. the target math: required monthly return, current weighted annualized input, 1Y historical input and 3M/6M run-rate separately, target gap, and feasibility;
5. a buy checklist with dates, cutoffs, and fallbacks;
6. a sell and switch checklist;
7. a review schedule and the exact fields to log;
8. risks and what would change the plan.

When the user asks about one product, return a one-page memo: what it is, what it owns, liquidity, fees, return evidence, fit with the user's buckets, and buy/hold/sell conditions. Do not invent missing data.

When the user asks whether to keep or replace an existing holding, return a holding review memo:

1. the lot and remaining principal, snapshot date, and whether the current product is still in the pool;
2. remaining term or daily-open comparison horizon, current reference yield and 3M/6M/1Y;
3. verified redemption path (T+N, fees, idle days) or the exact data gaps;
4. like-for-like candidates with 3M/6M/1Y, fee, quota status, break-even and post-fee difference;
5. one of **继续持有 / 观察 / 建议替换**, with the threshold arithmetic shown;
6. the decision-log entry fields (evidence date, verification date, reason) and the next reminder date.

## Tools

- `scripts/allocate.py` — fully invested R2 bucket and product allocation; optional R2 liquidity sleeve via `--cash-pct`; target check via `--target`.
- `scripts/score_products.py` — hard filters and weighted ranking from a CSV.
- `scripts/switch_calc.py` — break-even yield for a switch after fees and idle days.
- `scripts/review.py` — monthly metrics, target gap, and grading from a daily CSV.
- `assets/product_pool_template.csv` — product-pool schema and sample rows.
- `assets/daily_log_template.csv` — daily P&L log schema.
- `assets/monthly_review_template.md` — monthly review worksheet.
- `assets/product_memo_template.md` — one-page single-product memo.

Run scripts with the environment's Python. They use only the standard library and need Python 3.9+. Treat outputs as calculations, not recommendations.

`allocate.py` reads the pool's `score` column. Run `score_products.py` first and copy each `total_score` into that column, or enter your own 0–100 score. Missing scores default to 50.

Example invocations:

```bash
python scripts/score_products.py --input assets/product_pool_template.csv --show-excluded
python scripts/allocate.py --amount 540000 --profile balanced --target 3.0 --pool assets/product_pool_template.csv
python scripts/allocate.py --amount 540000 --profile balanced --target 3.0 --cash-pct 0.10 --pool assets/product_pool_template.csv
python scripts/switch_calc.py --amount 100000 --current-yield 3.0 --remaining-days 90 --idle-days 3 --new-yield 3.5
python scripts/review.py --input assets/daily_log_template.csv --target 3.0
```

## References

- [Product screening](references/product-screening.md)
- [Allocation models](references/allocation-models.md)
- [Execution playbook](references/execution-playbook.md)
- [Review templates](references/review.md)
- [Risk and compliance](references/risk-and-compliance.md)
- [Data sources](references/data-sources.md)
- [CMB automation](references/cmb-automation.md)
- [3% target guide](references/return-target.md)
