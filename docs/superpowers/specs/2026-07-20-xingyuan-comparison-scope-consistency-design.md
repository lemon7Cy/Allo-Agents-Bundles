# Xingyuan Comparison Scope Consistency Design

## Problem

Xingyuan generated a weekly request-count comparison that claimed all three Mondays used the same `智能视迅` department scope. The underlying MCP calls returned organization-wide user aggregates, and a per-run script manually copied selected rows into dictionaries without actually filtering by department. The current-period dictionary included unassigned users and users from other departments, so the totals, rankings, percentage change, and diagnosis were invalid.

The installed methodology already says to exclude unassigned personnel, preserve comparison granularity, and use deterministic analysis. The failure occurred because the agent bypassed that workflow and performed an ad-hoc calculation with no machine-verifiable scope metadata.

## Goals

- Guarantee that every period in a comparison uses the same object scope, population rule, metric, and cutoff window.
- Exclude `未设置`, empty, placeholder, non-staff, and out-of-department users before aggregation or ranking.
- Prevent the agent from presenting manually assembled dictionaries or free-form calculations as validated comparisons.
- Make the final scope declaration derive from validated input metadata rather than model-authored prose.
- Reject inconsistent inputs instead of producing a partial or misleading report.

## Non-Goals

- Change DFCode source data or MCP transport behavior.
- Add write operations or production mutations.
- Redesign unrelated MaaS monitoring or Feishu card rendering.
- Infer historical department membership from usage rows alone.
- Rank token usage when the user explicitly asks for request-count analysis; the selected metric must remain fixed across periods.

## Ownership And Delivery

The canonical implementation belongs in `Allo-Agents-Bundles/xingyuan-monitor` and targets `Allo-Agents-Bundles/main`.

The deployed Allo web branch also carries a vendored Xingyuan bundle under `agent-configs/agents/xingyuan-monitor`. After the canonical bundle change is reviewed, a separate synchronization change should target `Allo/feat/web-multitenant`. No unrelated desktop, MaaS-login, or skill-marketplace branch should be used.

## Design

### 1. Agent Execution Contract

`SOUL.md` will define a hard comparison contract:

1. Resolve the requested object scope before querying or calculating.
2. Build one roster snapshot that maps stable user IDs to normalized department and employment status.
3. Apply that same snapshot and target scope to every comparison period.
4. Keep metric, group-by dimension, timezone, date semantics, and intraday cutoff fixed.
5. Pass normalized facts to the bundled deterministic comparison engine.
6. If scope metadata cannot be verified, report `数据不足` and do not calculate a percentage change.

The agent must not:

- Label organization-wide results as department-only results.
- Manually copy MCP rows into temporary Python dictionaries for trend calculation.
- Reuse an earlier period result unless its scope metadata exactly matches the current comparison.
- Write its own scope declaration or claim `同口径` without engine validation.
- Rank unassigned or out-of-scope users, even when their request or token count is high.

### 2. Methodology Skill

`skills/dfcode-usage-analysis/SKILL.md` will specify a deterministic comparison workflow for both token and request-count questions.

The normalized input must include:

```json
{
  "comparison": {
    "metric": "requests",
    "scope_type": "department",
    "scope_value": "智能视迅",
    "timezone": "Asia/Shanghai",
    "cutoff_hour": 18,
    "population_mode": "fixed_roster_snapshot",
    "group_by": "user",
    "date_semantics": "calendar_date_inclusive"
  },
  "roster": [
    {
      "user_id": "user_x",
      "name": "张三",
      "department": "智能视迅",
      "employment_status": "active"
    }
  ],
  "periods": [
    {
      "label": "2026-07-13",
      "from": "2026-07-13",
      "to": "2026-07-13",
      "metric": "requests",
      "scope_type": "department",
      "scope_value": "智能视迅",
      "timezone": "Asia/Shanghai",
      "cutoff_hour": 18,
      "population_mode": "fixed_roster_snapshot",
      "group_by": "user",
      "date_semantics": "calendar_date_inclusive",
      "rows": [
        {"user_id": "user_x", "requests": 120}
      ]
    }
  ]
}
```

Names are display fields only. Membership and joins use stable user IDs. The roster snapshot is authoritative for all periods in the comparison. If the user explicitly asks for historical organizational membership and no historical roster is available, the report must disclose that limitation rather than infer it.

### 3. Deterministic Engine

The bundle will include or extend a deterministic comparison command in the `dfcode-usage-analysis` skill scripts. The engine will:

- Normalize department values and reject unassigned placeholders such as `未设置` and `maas-migration-smoke`.
- Select the fixed population once from the supplied roster and requested scope.
- Join every period by stable user ID.
- Treat an in-scope user absent from a period as zero for that period.
- Ignore and count out-of-scope rows without allowing them into totals or rankings.
- Validate that metric, scope type, scope value, timezone, cutoff hour, population mode, `group_by=user`, and `date_semantics=calendar_date_inclusive` are identical across all periods.
- Require ISO `from`/`to` dates with `from <= to` and identical inclusive duration across all periods.
- Require periods in strictly increasing, non-overlapping chronological order with unique period labels; reject reversed, duplicate, or overlapping windows rather than sorting them.
- Require requests values are nonnegative integers (excluding booleans); tokens values are nonnegative finite integers or floats.
- Preserve arbitrary-size integer totals and deltas exactly. Arbitrary-size integer token values are inherently finite and must never pass through float conversion or `math.isfinite`; only token floats require a finiteness check.
- Internally, token values are normalized to Decimal: integers use `Decimal(value)` and floats use `Decimal(str(value))`. Aggregation, contributor deltas, and percentage calculations remain Decimal until serialization. The base contract is `integral Decimal -> JSON integer` and `non-integral Decimal -> finite plain decimal string`; the integral form applies only when safely serializable under Python's integer digit limit, otherwise plain decimal string. Output uses no exponent, `Infinity`, or `NaN`.
- CLI input uses a `json.load` parse_int hook that returns `int` for reasonably sized numeric literals and `Decimal` for literals over the active Python integer digit limit. It must not change the global integer digit limit. Metadata integers therefore remain `int`, while oversized request literals are rejected by request validation.
- Emit every nonzero-baseline percentage as a finite decimal string rounded to two decimal places; zero baseline remains null. JSON output must never contain `Infinity`, `-Infinity`, or `NaN`.
- Calculate totals, deltas, percentages, and per-user contributors only after validation.
- Emit structured JSON containing validated scope metadata, excluded-row counts, totals, rankings, and a generated scope statement.

Any mismatch is a hard validation error. The engine must not silently coerce a department period and an organization-wide period into one comparison.

### 4. Scope Statement

The report scope line must come directly from engine output. Example:

```text
口径：请求次数；部门=智能视迅；固定人员集合=23人；三个周一均截至18:00；已排除未分配及跨部门人员。
```

The agent may shorten surrounding prose but must not alter the metric, department, population size, cutoff, or exclusions in this statement.

Organization scope statements must not claim cross-department exclusion because departments are part of the organization population. Department scope statements may state that cross-department personnel were excluded.

### 5. Failure Behavior

When validation fails, the engine returns a non-zero exit code and a bounded actionable error identifying the mismatched field and periods. The agent responds with:

```text
状态：数据不足
诊断：当前周期口径不一致，已停止计算环比。
缺口：需要使用同一范围、同一固定人员集合和同一截止时间重新取数。
```

It must not include a percentage change, ranking, or causal diagnosis based on rejected input.

## Test Strategy

### Engine Tests

- Reject a previous-period `智能视迅` scope combined with a current-period organization-wide scope.
- Reject periods with different cutoff hours.
- Reject periods using different metrics, such as tokens versus requests.
- Exclude `未设置`, empty departments, placeholder departments, non-staff users, and users from another department.
- Join by user ID even when display names collide or change.
- Treat missing in-scope rows as zero.
- Produce correct totals and contributors for three fixed-scope Monday windows.
- Generate the scope statement from validated metadata.

### Bundle Contract Tests

- Assert that `SOUL.md` forbids manual ad-hoc trend dictionaries and requires deterministic validation.
- Assert that `SKILL.md` documents fixed roster snapshots and hard failure on scope mismatch.
- Assert that the deterministic script is provisioned in the self-contained bundle.

### Incident Regression Fixture

Add a fixture modeled on the production incident:

- `智能视迅` users appear in all three periods.
- Current-period rows also contain `未设置`, `系统部`, and `配电部` users.
- The validated result excludes those rows and never ranks them.
- A falsely declared department-only current period with organization-wide scope metadata is rejected before calculation.

## Rollout And Verification

1. Merge the canonical bundle PR into `Allo-Agents-Bundles/main`.
2. Synchronize the reviewed files to `Allo/feat/web-multitenant` in a separate PR.
3. Run bundle validation and deterministic engine tests in both repositories.
4. Deploy the web bundle through the normal `feat/web-multitenant` process.
5. Replay the incident query in a non-destructive production thread and inspect tool calls, engine input, output scope statement, and exclusions.
6. Confirm that no temporary manually assembled trend script is created for the replay.

## Acceptance Criteria

- A department-versus-organization comparison cannot produce a percentage or ranking.
- The same roster snapshot and cutoff apply to every period.
- Unassigned and cross-department users cannot appear in totals, rankings, or contributor lists.
- The output scope statement is generated by validated code.
- The original three-Monday incident fixture passes with correct exclusions.
- Canonical and Allo web vendored copies are delivered through their correct repositories and base branches.
