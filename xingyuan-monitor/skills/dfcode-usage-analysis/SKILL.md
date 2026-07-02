---
name: dfcode-usage-analysis
description: Methodology for usage analysis via the DFCode enterprise MCP — department/employee token usage, period-over-period comparison, same-time-window "today vs yesterday" intraday comparison, root-cause breakdown of "why did it rise/fall", and per-user usage-decline alerts answered at user granularity. When the user asks "部门用量" "谁用得多" "今天用量有没有上升/下降" "今天和昨天比" "这几天为什么下降/上升" "对比两个周期", or (in a 飞书 group, @-mentioning the bot) asks "谁在掉量" "用户用量下降" "掉量预警/用量下降提醒", read this skill first.
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
- **"Today's partial accumulation" vs "yesterday's FULL day"** — window length AND date both moved. This can even **flip the sign** of the conclusion (real incident: naive read −31.9% "明显下降" while the same-window truth was **+4.8% up**). See §3b — the same-window comparison is **your job, one call away; never hand "按同一时间点再复核" back to the user.**

## 3b. Intraday Iron Rule: "today vs yesterday" MUST be same-time-window (你算,不是用户算)

Whenever the comparison involves **the current, incomplete day** ("今天用量升了还是降了?" "今日 vs 昨日" — or any period whose right edge is today), the naive day-aggregate comparison is **forbidden as a conclusion**. Do the same-window comparison yourself:

1. **ONE call gets everything**: `query_usage {from: <yesterday>, to: <today>, groupBy: "hour_day"}` → hour×date rows (2 days ≈ 30 rows / ~4KB, far under budget).
2. **Pipe the rows into the engine — never hand-compute** (§8's rule applies here too):
   ```bash
   echo '{"items": <hour_day items>, "cutoff_hour": <current hour, e.g. 16>}' \
     | python3 skills/dfcode-usage-analysis/scripts/usage_cube.py --intraday --md
   ```
   The engine returns: **same-window Δ%** (both days cut at `cutoff_hour`), baseline full day (reference), **projected full-day for today** (pace-based, labeled 推测), and the naive partial-vs-full % explicitly labeled 禁止口径. Omit `cutoff_hour` and it derives one from today's last active hour (deterministic).
3. **Headline = the same-window number.** Yesterday's full day is context; the projection answers "那今天全天大概会怎样"; the naive number may appear **only** as "⚠️ 若按整日口径会误读为 −X%" — never as the conclusion.
4. **Per-model / per-person drill-down (also same-window, ≤3 extra calls)**: for the top movers, `query_usage {model: <m>, from, to, groupBy: "hour_day"}` (or `userId: <id>`), tag rows with `"model"`, feed the combined items to the same `--intraday` run → the digest lists per-series same-window deltas. Identify *candidate* movers from a cheap day-aggregate first, but **verify and report them same-window**.
5. **Baseline sanity** (engine flags these in `gaps`): if yesterday was a weekend/holiday and the question is about workday pace, use the previous workday or same weekday last week as `baseline`; a Monday-vs-Sunday comparison is another dirty comparison.
6. If hourly data is unavailable for the range (tool error/empty), fall back to declaring the limitation **and still give the pace-based estimate** (today ÷ elapsed-fraction) labeled as rough — but never present partial-vs-full as the finding.

### 3b.1 "今日用量" overview questions — 分部门 + 谁在降/升 are MANDATORY, not optional

A bare total (or a top-users list) is an incomplete answer to "今日 DFCode 用量怎么样/升了还是降了". The reader is a manager: they need **which departments** and **which people** moved. Required composition (~4 calls, within budget):

1. `query_usage {from: 昨日, to: 今日, groupBy: "hour_day"}` → org same-window headline (§3b).
2. `query_usage {from: 昨日, to: 昨日, groupBy: "user"}` + `query_usage {from: 今日, to: 今日, groupBy: "user"}` → per-user totals (aggregates, 2 calls).
3. Map user → department (`query_departments` or `query_roster`, 1 call); **drop unassigned people entirely** (§1).
4. Feed everything into ONE engine run — hourly rows as `items`, per-user rows as `users`:
   ```json
   {"items": [...hour_day...], "cutoff_hour": 16,
    "users": [{"name": "张三", "department": "智能视迅", "baseline_tokens": 52800000, "today_tokens": 16050000}, ...]}
   ```
   The engine scales each user's yesterday-full-day by the org pace ratio into an **expected-by-now** figure and compares today's actual against THAT (labeled 估算 — per-person hourly would blow the query budget), then rolls up per department and classifies drop / rise / silent_today / new.
5. **Mandatory answer structure** (in this order):
   ```
   结论:总量同窗 Δ±X%(均截至 HH:00)…
   分部门(期望 vs 实际,估算):<每部门一行,降幅大的在前>
   📉 明显下降:<人·部门:期望→实际(Δ-X% / 今日未使用)>
   📈 明显上升:<人·部门:…>(有新增用户也点出)
   口径:同窗;分部门/个人=昨日整日×进度比的估算;仅已分配部门。
   缺口:<engine gaps 原样带出>
   ```
   Never answer with only the total or only a "谁用得多" ranking; never present the drop list computed as "today-partial vs yesterday-full" per person (that marks everyone as fake-dropping).

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
| Cross-dimension aggregation | `query_usage` (`groupBy`: model/project/user/day/**hour**/agent + crosses `user_model`/`model_day`/`user_day`/**`hour_day`**/`model_hour`; filters: `from`/`to`/`userId`/`model`/`project`) |
| **Same-window "today vs yesterday" (§3b)** | `query_usage {from,to, groupBy:"hour_day"}` → pipe to `usage_cube.py --intraday`; drill a mover with `model:`/`userId:` filter + same groupBy |

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

## 8. Deep Usage Analysis · Data-Model SOP (the engine computes; you only interpret)

When asked for a **multi-dimensional deep analysis** (e.g.: "分析某部门本月工作日整体用量趋势,挑出谁持续增长/谁突然下降,各人模型使用也要趋势分析,对比粒度要一致") or a **recent-days drop** question ("最近两天用量下来了"), **do NOT compute trends, percentages, deltas, slopes, or growth/decline classification in your head/context.** The LLM does arithmetic badly and in-context computation is non-reproducible and blows up the context window. Instead, pull AGGREGATE data, normalize it into a fact cube, and hand the cube to a deterministic engine that does ALL the arithmetic. **Your only job is interpretation** (root cause / 推测 / 建议 / narrative) of the engine's digest.

### 8.1 The fact cube (data model — recall this first)

One cube is the single source of truth; every view derives from it, so 口径 is consistent by construction:

- **dimensions**: `employee` × `department` × `date (YYYY-MM-DD)` × `model`
- **measures**: `tokens`, `requests`
- **derived (engine adds these — never compute yourself)**: `is_workday`, week bucket, weekly totals, deltas, slopes, model share, classification.

### 8.2 Fixed, aggregate-only query plan (obey the «Query Budget Iron Rule» — ≤ 8 calls, NO raw entries)

Lock scope first: **department, period, weekdays-only?, scope (default token)**. Then use a FIXED plan that returns AGGREGATES only — never raw paginated entries:

1. **One `query_departments` call** (filter = that department, range = that period, with `daily trends` + `WoW growth` + `model breakdown` + `top employees per dept`) → gives, in one shot: ① department daily totals ② per-person period comparison within the dept ③ model distribution.
2. If a **person × date × model** cross-tab is available as an aggregate (e.g. `query_usage` cross-dimension that returns sums, not rows), use it to fill per-person/per-model series. **Only if it returns aggregates** — never request raw entries.
3. **Cap any per-person drill** (`query_employee_detail` / `query_employee_portal_stats`) to the **few standouts** the engine flags afterward (≤ 3 growth + ≤ 3 decline). Never loop over everyone — that is the blow-up red line.

### 8.3 Normalize MCP results → the engine's `records`, then RUN the engine

Flatten whatever the MCP returned into the cube's `records` list and pipe it into the engine. **Do the arithmetic in the engine, not in context.**

```bash
python3 skills/dfcode-usage-analysis/scripts/usage_cube.py --md   # reads JSON on STDIN, prints a markdown digest
# (drop --md to get the full JSON instead)
```

STDIN JSON contract:

```json
{
  "records": [{"employee": "...", "department": "...", "date": "YYYY-MM-DD", "model": "...", "tokens": 0, "requests": 0}],
  "period": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
  "workdays_only": true,
  "holidays": ["YYYY-MM-DD"],
  "extra_workdays": ["YYYY-MM-DD"],
  "recent_days": 5,
  "thresholds": {"growth_pct": 50, "drop_pct": 50, "silent_days": 5}
}
```

The engine returns (and the `--md` digest summarizes): `scope`, `dept_daily`, `dept_weekly`, `overall` (first/last week, `delta_pct`, `trend`, `inflection_weeks`), `model_share`, `per_person` (with `first_tokens`/`last_tokens`/`delta_pct`/`slope`/`top_model`/`class`/`model_trend`), `growth`, `decline`, `recent_days_view`, `week_over_week` (本周 vs 上周同工作日), `gaps`.

- **Workday rule (engine enforces it)**: a date is a workday if (Mon–Fri AND not in `holidays`) OR (in `extra_workdays`). Pass known `holidays`/`extra_workdays` so 调休/节假日 are corrected; if you can't, the engine notes the approximation in `gaps`.
- **Classification (engine, deterministic)**: growth = `delta_pct ≥ growth_pct AND slope > 0`; decline = `delta_pct ≤ -drop_pct` OR 由活转静 (was active then last `silent_days` workdays ~0); else steady.
- **DO NOT** re-derive any of these numbers in context. If a number looks off, fix the `records` you fed in or the thresholds — don't hand-compute.

### 8.4 Recent-days questions ("最近两天用量下来了")

Set `recent_days` to the window in question (e.g. `2`) and read `recent_days_view`: it compares the **last N workdays vs the preceding N workdays** (`dept_recent_vs_prior_pct`) and lists `per_person_drops` (prior_avg → recent_avg, drop_pct, last_active_date). This directly answers "谁最近掉量了". No in-context math.

> ⚠️ **If the range's right edge is TODAY (an incomplete day), exclude today from the day-granularity cube** — a partial day pollutes every daily/weekly view as a fake drop. Answer the "today" part separately via §3b's same-window intraday comparison, and say so in the 口径 line.

### 8.4b Department "用量降低了" (incl. mid/partial week) → read `week_over_week`, NOT just the month aggregate

A monthly/period aggregate can read **+X% (up)** while a department is actually **dropping this week**, and the rolling `recent_days_view` block straddles week boundaries and is easily polluted by one odd low workday (e.g. a near-zero Friday), so it too can read "up". For "某部门用量降低了 / 视讯部门掉量了" questions the **authoritative signal is `week_over_week`**: it pairs each current-week workday with the **same weekday of the previous week** (本周一/二 ↔ 上周一/二), so a partial-week slide is caught cleanly even before the week is over. Read `dept_wow_pct`, the per-weekday `by_weekday` pairs, and `per_person_drops`.

> ⚠️ **Headline the disagreement.** When the month says up but week-over-week says down, THAT is the story — e.g. "月环比 +262%(涨),但**本周工作日同比上周 −36%(降)** —— 月度把近周下降盖住了". Reporting only the month "+X%" and missing the recent workday drop is exactly the mistake that makes the conclusion wrong. Conversely, if `week_over_week` is roughly flat/up while a raw day looks low, it's likely a weekend/holiday artifact — don't cry decline.

### 8.5 The AI's job = interpretation ONLY

From the engine digest, write: **root cause**, **推测** (always mark inferences as 推测), **建议**, and the narrative. Rule out false declines (Section 4/7.3: roster rotation / departure / quota / model retirement / holidays) and label causes. **Never re-derive trends, %, deltas, slopes, or the growth/decline split** — those are the engine's, and they must stay reproducible.

### 8.6 Structured output (keep these Chinese labels)

```
结论:<部门> 本月工作日用量 <升/降 X%>,主因 <…>。口径:仅工作日、token 计、本月(引擎口径)。

整体趋势:<按周一句话 + 关键拐点(取自 overall.inflection_weeks)>

📈 持续增长(N 人):
- <姓名>:<周期首 token> → <周期末 token>（Δ+X%，slope>0），模型:<top_model + model_trend>
📉 突然下降(M 人):
- <姓名>:<最后活跃工作日> 后骤降/由活转静,疑因 <真降 / 换人 / 配额 / 请假>（推测），模型:<…>

最近 N 工作日(如问及):部门 Δ<±X%>;个人掉量:<姓名 prior→recent (Δ-X%)>
本周 vs 上周(同工作日,部门掉量问题必看):部门同工作日 Δ<±X%>(本周 <日/日> vs 上周同星期几);若与月环比方向相反,务必点出"月涨但近周工作日在降"
粒度声明:本节所有数字取自确定性引擎(同口径:仅工作日、token、本周期、同一批人),未在上下文重算。
缺口:<engine gaps 原样带出 + 数据不全/某人离岗待确认 等>
```

> Self-check: **total MCP calls ~5–8** (1 aggregate + optional cross-dim + ≤ 3+3 standouts). If you catch yourself looping `query_department_employee_detail` over everyone, or doing arithmetic in your head, **stop** — return to 8.2's aggregate plan and let `usage_cube.py` do the math.
