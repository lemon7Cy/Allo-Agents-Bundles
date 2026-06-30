---
name: dfcode-usage-analysis
description: Methodology for usage analysis via the DFCode enterprise MCP — department/employee token usage, period-over-period comparison, root-cause breakdown of "why did it rise/fall", and per-user usage-decline alerts answered at user granularity. When the user asks "部门用量" "谁用得多" "这几天为什么下降/上升" "对比两个周期", or (in a 飞书 group, @-mentioning the bot) asks "谁在掉量" "用户用量下降" "掉量预警/用量下降提醒", read this skill first.
---

# DFCode Usage Analysis Methodology

When the user asks about an enterprise's/department's/employee's **usage, ranking, trend, comparison, or "why did it change"**, analyze using this methodology. Data comes from the DFCode enterprise MCP (`query_departments` / `query_employee_detail` / `query_roster` / `query_dashboard`, etc.).

**Goal: give the reader the conclusion at a glance, not a giant table they have to dig the answer out of themselves.**

## ⚠️ Query Budget Iron Rule (top priority — break it and you blow up the whole session into an error)

The dfcode tools can return a **huge** amount of data in a single call; a few calls pile up enough context to blow it up and the whole session throws "internal error" (this actually happened: pulling per-employee detail for everyone → 1.45MB / ~430k tokens in a single turn → the model refused to answer). Therefore:

- **Aggregate first**: start with `query_departments` (one call already carries daily trends / WoW growth / model breakdown / top employees per dept) to get the global picture; **don't immediately pull person by person**.
- **Strictly cap per-person queries**: call `query_employee_detail` / `query_department_employee_detail` **only for the 3–5 key people you filtered out**, **never loop over everyone** (per-employee over everyone = guaranteed blowup, that's exactly what crashed last time).
- **No raw / full detail**: for trends use daily trends (already aggregated by day), not paginated raw entries.
- **Total tool calls per analysis ≤ 8**; if that isn't enough it means you're brute-forcing detail — stop and switch to aggregation instead of continuing person by person.
- Rule of thumb: keep any single tool result under ~15k tokens.

## 0. First Principle: conclusion first, evidence after

- **Answer the user's question in the very first line/sentence** (up or down, why, who's the main driver), then give the supporting data.
- Don't dump a Top-5 table first and make the user read it themselves. **The table is evidence; the conclusion comes first.**

## 1. Data Scope (most important — get it wrong and everything's wrong)

- **People with no assigned department = not company personnel; exclude outright.** In reports, **don't count, don't rank, don't show them, and don't suggest "confirming their department assignment"** — they're noise, treat them as nonexistent.
- **Only count people with an assigned department.** Determine assignment via `query_roster` (by department/status) or the department dimension of `query_departments`; drop anyone with `department=null` / no department / non-staff (编外) status.
- Default to **aggregating by department**; drill down to individuals only when needed (and only within assigned departments).
- At the end of the conclusion, declare the scope in one line, e.g.: `口径:仅已分配部门(已排除未分配人员)。用量以 token 计。`
- ⚠️ Don't list someone or suggest assigning them just because an unassigned person has high usage — **high usage but unassigned = still excluded**; at most summarize it in the gaps section with one line "另有未分配人员用量未纳入", without naming names.

## 2. Metric Definition: usage = tokens, not request count

- **Rankings, comparisons, and "high-usage users" are always based on token consumption.**
- **Request count ≠ usage.** Many requests but low tokens = high-frequency small requests (possibly scripts/polling/autocomplete scenarios), **not a high-usage user**.
- Mention request count only as a supporting signal when explaining "call patterns", **never as the basis for usage ranking**, and by default don't highlight it in the conclusion.
- If someone has high request count but very low tokens, **proactively flag** this as "高频低耗" (high-frequency, low-consumption), correcting the misjudgment that "they're a high-usage user".

## 3. Comparison Methodology: control variables (a pitfall the team lead hit hard)

Before any comparison, **first ask: which variable am I holding fixed?** Only two clean comparisons are allowed, **never mix dimensions**:

- **Vertical (lock the object, vary time)**: how the same department / same person / same model changes across different time periods. E.g., 智能视迅 department this month vs. last month tokens.
- **Horizontal (lock time, compare objects)**: the relative levels among different departments / people / models within the same time period. E.g., this month's token ranking across departments.

**Forbidden dirty comparisons (move one thing and you've moved two variables — instantly seen through):**
- Putting "period A's #1" side by side with "period B's #1" — they're often **different people** (object and time both changed), meaningless.
- Comparing "a department's total" against "one person's usage" — **inconsistent granularity**.
- Mixing scopes: token vs. request count, including vs. excluding non-staff (编外), different-length time windows.

**To see "people over time"**, **take the union of the two periods' populations and list, per person**, `token(A) → token(B) → Δ` (object fixed = each person; the only variable that moves is time). Use `query_departments`'s daily trends / WoW growth / top employees per dept.

## 4. Root-Cause Breakdown: directly answer "why did it rise/fall"

When a department's usage changes, answer along this chain:

1. **Conclusion first**: department tokens rose/fell X% period-over-period (from A to B), main driver is ___.
2. **Break down to person/model**: compare the same department across two periods, find **the few people with the largest token change / which model migrated**.
3. **Distinguish two cases** (this is exactly what the team lead wants to know):
   - **Roster rotation (主力轮换)**: the department total is basically stable, just a different set of active people → make clear "不是真下降,是 X 换成了 Y" (not a real decline — X was replaced by Y).
   - **Real decline (真实下降)**: the total substantively decreased → find out **who stopped/reduced** (use `query_employee_detail` to check their daily trend as corroboration), and whether it's accompanied by **quota changes, model retirement, or departure**.
4. **Falsifiable**: if data is missing, say it's missing (e.g., period too short, a day's data incomplete); don't fabricate causation.

## 5. Tool Quick Reference

| What you want to do | Which tool |
|---|---|
| Department usage / comparison / trend / WoW / in-department top | `query_departments` (with range filters / daily trends / WoW / top employees per dept) |
| Single-person deep dive (overview, daily trend, model distribution, detail) | `query_employee_detail` / `query_department_employee_detail` |
| Department assignment / non-staff (编外) determination / filter by status | `query_roster` |
| Global overview (today/7d/month, active headcount, model distribution) | `query_dashboard` |
| Cross-dimension aggregation | `query_usage` |

## 6. Output Template (department usage comparison questions)

```
结论:<部门> 近 <周期> token 环比 <涨/跌 X%>,主因是 <主力轮换 / 谁降了 / 谁升了>。

变化拆解(同部门,同口径):
- <人/模型A>:<tokenA> → <tokenB>（Δ<±X>）
- <人/模型B>:...
（只列 token 变化最大的 3-5 项;请求次数如异常另起一行点出"高频低耗"）

判断:<主力轮换 / 真实下降>，依据 <…>。
口径:仅已分配部门，排除未分配/编外人员；用量以 token 计。
缺口:<数据不全/周期过短等，如有>
```

## 7. User Usage-Decline Alerts (when asked, answer at user granularity)

Scenario: after 星元 is connected to the 飞书 bot, someone in a group **@-mentions the bot** asking "谁的用量在掉 / 用户用量下降 / 掉量预警". This is **answer-only-when-asked** (no irregular proactive push), but answer at **individual-user granularity** — point out who's dropping, by how much, and whether it looks like real churn. The reply is sent straight back to the @-ing group by the 飞书 channel (no extra reporting needed; only use `feishu-webhook-report` when the user explicitly asks to send it to **a different group**).

### 7.1 How to locate "the people who are dropping" (two steps, saves MCP calls)
1. **Batch-filter candidates**: use `query_departments` (WoW growth / daily trends / top employees per dept) or `query_dashboard` to get per-person/per-department "recent period vs. prior period" tokens in one call, circle the people with clear period-over-period decline, **don't pull person by person**.
2. **Confirm per person**: for candidates, use `query_employee_portal_stats` (single-person daily trend + 365-day activity heatmap) / `query_employee_detail` to check the daily trend and confirm whether it's a "sustained/significant decline" or a single-day fluctuation.

### 7.2 Two types of decline, viewed separately (don't only watch big users)
There are two kinds of decline, **with different focuses, and both must be reported** — scope follows Sections 1 and 2 (only assigned departments, usage = tokens):

**A · Usage impact (用量影响 — a big user dropped, large token impact)**
- **Period-over-period plunge**: this period's tokens fell ≥ 50% vs. last period.
- **Sustained slide**: monotonic decline over ≥ 3 consecutive periods / N days.

**B · Activation/conversion (活跃转化 — usage is small or even tiny, but "never got going / stopped using")** — this affects activity and retention conversion, **must not be missed just because tokens are small**.
- **Active-to-silent (由活转静)**: previously had steady usage, tokens approaching 0 in the last 7 days (don't look at decline %, look at "are they still using it").
- **New user / low-base silence**: historical usage was already very low or near-zero, and no tokens for ≥ 7 consecutive days — the base is too small to compute a meaningful decline %, so **judge by "did they get going" and list them anyway** (especially recently onboarded / key promotion targets).

> ⚠️ **Key: don't drop a user from the list just because their absolute tokens are small.** Big users go through A (usage impact), small/new users go through B (activation/conversion). Both thresholds are adjustable.

### 7.3 First rule out "false declines" (key — don't misjudge as churn)
Before answering, use the tools to rule these out, otherwise the conclusion will be instantly seen through:
- **Roster rotation** (Section 4): department total stable, just a change of active people → not an individual decline.
- **Departure/non-staff/transfer**: `query_roster` / `query_user_detail` (roster status) → just annotate those who left or transferred; not an alert.
- **Quota/model changes**: `query_user_detail` (MAAS quota), `query_maas_models` / `query_model_endpoints` (model retirement) → declines caused by quota cuts / a commonly-used model being retired must be **labeled with the cause**; it's not the user choosing to stop.
- **Leave/holidays/weekends**: if the period is too short or spans a holiday, use the 365-day heatmap to check seasonality; don't treat time off as churn.

### 7.4 Severity grading (A and B graded separately)
| Level | A Usage impact (用量影响) | B Activation/conversion (活跃转化) |
|---|---|---|
| 🔴 Alert (预警) | High-usage user plunges ≥ 50% / active-to-silent, false declines already excluded | Newly onboarded / key promotion target silent ≥ 7 days |
| 🟡 Watch (关注) | Sustained small slide / below threshold → recheck next period | Low-base user silent (not a key target) → list them, recheck next period |
| ⚪ Not counted (不算) | Hit a false decline (rotation/departure/quota/holiday) | Genuinely normal (one-off trial, already departed, etc.) |

### 7.5 Reply format (conclusion first, fits 飞书 cards)
```
结论:近 <周期>，用量影响类 <N> 人明显下降,活跃转化类 <K> 人静默/未激活。口径:仅已分配部门,token 计,已排除离岗/配额/节假日等假下降。

🔴 用量影响 · 骤降/由活转静:
- <姓名/工号·部门>:<上周期 token> → <本周期 token>（Δ-X%），疑因 <真降 / 未知>，建议 <跟进动作>。

🟡 活跃转化 · 静默/未激活(低基数也算):
- <姓名·部门>:历史仅 <总量 token>，<最后使用日> 后静默 → 疑似没用起来,建议确认登录/权限/使用场景。

缺口:<数据不全 / 周期过短 / 某人离岗待确认 等>
```

### 7.6 Triggers and default behavior
- When the group @-mentions the bot asking "谁在掉量 / 用户用量下降 / 掉量预警 / 用量下降提醒" → run this flow, **answer at user granularity**.
- **Answer only when asked**; the reply goes back to the current group by default (the 飞书 channel handles this automatically), **no proactive scheduled push**.

## 8. Deep Usage Analysis · Standard Operating Procedure (SOP)

When asked for a **multi-dimensional deep analysis** (e.g.: "分析某部门本月工作日整体用量趋势,挑出谁持续增长/谁突然下降,各人模型使用也要趋势分析,对比粒度要一致"), **follow this procedure strictly** — efficient, consistent granularity, and holding to the «Query Budget Iron Rule» without blowing up.

**Step 1 · Lock scope + one aggregate call for the base (key call-saver)**
- First confirm four things: **department, period, whether to look at weekdays only, and scope (default token)**.
- **One** `query_departments` call (filter=that department, range=that period, with `daily trends` + `WoW growth` + `model breakdown` + `top employees per dept`) → get in one shot: ① department daily totals ② per-person period comparison within the department ③ model distribution. **Don't replace this step with a per-person loop.**
- **Weekdays only**: **drop Saturdays and Sundays** (and known holidays) from the daily trends before computing, to keep weekend noise out of the trend.

**Step 2 · Overall trend (整体趋势, conclusion first)**
- Use the "weekdays-only" daily trends to give the department's trajectory this month: rising / flat / falling + period-over-period X% + key inflection point (which day it started changing). The first sentence is the conclusion.

**Step 3 · Per-person classification (vertical: lock the person, watch time)**
- Using each person's period series from Step 1, classify into two groups by "weekday token over time" (reuse Section 7's signals + rule out false declines):
  - **Sustained growth (持续增长)**: the weekday series is basically monotonically rising / positive slope.
  - **Sudden drop (突然下降)**: a sharp drop starting from some weekday / active-to-silent (由活转静).
- List only the people the classification needs; don't spread out over everyone.

**Step 4 · Model trend for key people (hard cap 3–5 people)**
- Only for the **few fastest-growing + fastest-dropping people (≤ 3 each)** picked in Step 3, call `query_employee_detail` (`daily trend` + `model distribution`) → see **how their model usage changes over time** (switched models? a model rising/stopping?).
- **Never** do this step for everyone (that's the blowup red line).

**Step 5 · Granularity-consistency check (per Section 3, mandatory)**
- Lock all comparisons to **the same period, the same "weekdays-only" scope, the same token metric, the same set of people**;
- Vertical = lock the person and watch time; horizontal = lock time and compare people; **never mix dimensions**.

**Step 6 · Structured output**
```
结论:<部门> 本月工作日用量 <升/降 X%>,主因 <…>。口径:仅工作日、token 计、本月。

整体趋势:<按周/按天一句话 + 关键拐点>

📈 持续增长(N 人):
- <姓名>:<周期首 token> → <周期末 token>（Δ+X%），模型:<主用模型 + 变化趋势>
📉 突然下降(M 人):
- <姓名>:<最后活跃工作日> 后骤降/静默,疑因 <真降 / 换人 / 配额 / 请假>，模型:<…>

粒度声明:本节所有对比同口径(仅工作日、token、本月、同一批人)。
缺口:<数据不全 / 某人离岗待确认 等,如有>
```

> Self-check: this procedure's **total tool calls should be ~5–8** (1 aggregate + 3–5 key people). If you find yourself looping over employees one by one on `query_department_employee_detail`, **stop immediately** and return to Step 1's aggregate approach.
