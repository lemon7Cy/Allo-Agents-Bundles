---
name: maas-fleet-monitor
description: Query MaaS usage, health, model ranking, current risks, and the customer-facing MaaS Web dashboard through the public read-only Web dashboard/API.
optional_env:
  - MAAS_MONITOR_WEB_PASSWORD
credentials:
  - key: MAAS_MONITOR_WEB_PASSWORD
    label: MaaS Monitor Web Password
    description: Basic Auth password for the public read-only MaaS Web dashboard. Keep it secret and never print it in chat.
    required: false
    secret: true
---

# MaaS Fleet Monitor Skill

Use this skill when the user asks about MaaS usage, health, costs, model ranking, operational risk, or the customer-facing MaaS Web dashboard.

Access mode: Public Web dashboard/API for customer-facing read-only status at `http://221.0.79.251:39091/?v=metric1` with Basic Auth.

Do not reveal `MAAS_MONITOR_WEB_PASSWORD`, API keys, passwords, credentials, cookies, or request bodies in any answer.

## Public Web Dashboard

Use the Web dashboard path when the user is a customer, non-technical stakeholder, sales/support colleague, or anyone asking to open/view/share the MaaS dashboard.

Dashboard URL:

```text
http://221.0.79.251:39091/?v=metric1
```

Login guidance:

- Username: `maas`
- Password is stored on the monitor server at `/home/songjin/maas-monitor/.web-basic-auth`.
- Never print or paste the password in chat.

Important boundaries:

- The public Web URL is not an MCP endpoint.
- Do not configure ALLO MCP to `http://221.0.79.251:39091/mcp`; it is intentionally blocked and should return `403`.
- Public `/api/ingest/*` is intentionally blocked.

## Data Coverage

- `public-maas`: full Agent data is available, including usage, timeline, models, Provider Pools, accounts, errors, and costs.
- `internal-maas`: currently limited visibility only. Detailed Token/model/account/Pool data is unavailable until an internal Agent is deployed.
- Historical 30-day Token data before around 2026-06-06 may be incomplete because some old `usage_logs` rows have request/cost data but zero token fields. When answering 30-day Token questions, mention that request volume and cost can be more reliable for older history.

## Recipes

### Overall Usage

For questions like:

- 今天 MaaS 用量怎么样？
- 本周整体消耗如何？
- 当前有没有风险？
- 给领导一个 MaaS 摘要。

Default to a visual report, even when the user only asks generally. Run the read-only Web API chart report first:

```bash
python scripts/web_status.py --format markdown
```

Paste the returned Markdown directly so the user sees the dashboard image references. Do not answer usage-summary questions with text-only metrics unless the chart script fails.

The script prints a ready-to-paste Markdown report with fresh PNG image references for model comparison, today's Token trend, and last 7 days Token trend. It keeps stdout short so tool output is not truncated. Each run writes files to a unique `maas-monitor-reports/runs/{run_id}` directory and refreshes `maas-monitor-reports/latest` as a convenience copy. Paste the report directly. Do not add command logs, transport details, raw endpoint URLs, or curl errors.

Fallback rules:

- If `scripts/web_status.py --format markdown` returns Markdown, paste that Markdown as the answer with minimal edits and keep the four image reference lines. It should include an overview dashboard image, model ranking image, today's trend image, and 7-day trend image.
- After running `scripts/web_status.py --format markdown`, do not call `present_files` by default because the Markdown already embeds the charts inline. Only call `present_files` if the user explicitly asks to download/open the generated files. If presenting files, use only the paths listed in that same command's hidden `maas-monitor-present-files` comment. These current-run paths are the only authoritative files for the current answer. Never present files discovered by searching the workspace, never reuse files from a previous answer, and never substitute files from `latest` unless they are explicitly listed in the current command output.
- If `scripts/web_status.py` returns a JSON summary, answer from that JSON and include chart image paths if present. Prefer the current run's `files.run_dir` and `charts` paths from the same JSON payload; do not infer paths from a fixed location.
- If it returns `missing_web_password`, provide the dashboard URL and username, then tell the operator to set `MAAS_MONITOR_WEB_PASSWORD` in the runtime credential store or environment.
- If it returns `web_api_unreachable`, say the public Web dashboard/API is unreachable and include the URL for manual verification.
- Never print the Basic Auth password.

Answer with:

- total Token
- request count
- cost
- peak period
- top model
- healthy/degraded/limited instances
- data coverage notes

### Model Ranking

For questions like:

- 今天哪个模型用得最多？
- 近7天 Top 5 模型是什么？
- gpt-5.5 用量怎么样？

Run `python scripts/web_status.py --format json` and answer from the returned `today`, `week`, and chart/file fields. If the question asks for 30 days, add the historical Token completeness warning.

### Error Diagnosis

For questions like:

- 刚才为什么报错？
- 现在有没有异常？
- 哪个账号或 Pool 出问题？

This Web-only project version does not perform account or Provider Pool deep diagnostics. Return the Web dashboard status and mark account/Pool/error drilldown as a MaaS backend/API capability gap.

### Specific Instance

For public MaaS only:

```json
{"instance_id":"public-maas"}
```

For internal MaaS:

```json
{"instance_id":"internal-maas"}
```

When discussing `internal-maas`, clearly say detailed Agent metrics are not available yet.

## 星元监控 Agent 适配（观测记忆与趋势）

当本 skill 被「星元枢算」监控 Agent 调用时，除正常的可视化报告/摘要外，请遵循：

- 用监控卡片风格回复（状态 / 范围 / 信号 / 诊断 / 建议 / 缺口），不要默认长日报。
- 在卡片**末尾附上一行机器可读指标**，直接取自 `scripts/web_status.py --format json` 输出里的
  `metrics_line` 字段，形如：

  ```text
  指标：token_total=12400000 token; requests=2439; cost=917.55; top_model=gpt-5.5
  ```

  系统会据此把本次观测的结构化指标记入星元的观测记忆，用于"较昨日/上次 +X%"的趋势对比。
- 指标 key（`token_total` / `requests` / `cost` / `top_model` 等）必须保持稳定，跨天同名，否则趋势无法对齐；不要改名或本地化 key。
- 数据不可用时（如 `internal-maas` limited、`missing_web_password`、`web_api_unreachable`），照常给出
  `状态：数据不足` + 明确的`缺口`，并**省略指标行**，绝不为凑指标而编造数值。

## Answer Style

- Default to a leadership-summary style for usage questions: concise, metric-first, no debugging transcript.
- Start with one conclusion sentence, then one compact metrics block, then coverage notes.
- For usage/status questions, include charts before the metrics table whenever chart paths are available.
- Do not show intermediate command execution details, raw URLs, curl errors, or JSON fields unless the user explicitly asks how the data was queried.
- Never include a default section titled `数据通道说明`, `Web fallback`, or similar. These are troubleshooting details, not usage-report content.
- Do not include formulas or LaTeX-like fractions. If calculating a share, write it plainly, for example `gpt-5.5 占比约 82.8%`.
- Avoid repeating the same conclusion at both the top and bottom. Use either a top conclusion or a final one-liner, not both.
- Keep leadership summaries to 5-8 short lines. Use a table only when it improves scanning.
- For technical diagnostics, include likely affected Pool/account/model when available.
- Never claim that internal MaaS has detailed usage data unless the tool returns it.
- Never perform remediation, credential changes, database writes, scheduling changes, or service restarts. This skill is read-only.

Recommended leadership usage format:

```text
当前公网 MaaS 运行健康，今日用量主要集中在 gpt-5.5。

<embedded PNG: MaaS 今日用量驾驶舱>

<embedded PNG: 今日模型 Token 用量对比>

<embedded PNG: 今日 Token 使用趋势>

<embedded PNG: 近 7 天 Token 使用趋势>

| 指标 | 当前值 |
|---|---:|
| 今日请求 | 2,068 次 |
| 今日 Token | 2,581.98 万 |
| 今日费用 | 885.34 |
| 峰值时段 | 17:00，约 436.77 万 Token |
| Top 模型 | gpt-5.5，约 2,137.48 万 Token，占比约 82.8% |

内网 MaaS 当前为 limited：尚未接入完整 Agent，因此暂无模型、账号、Pool、Token 明细。
如需账号、Provider Pool、错误明细，可再进入技术诊断视图查询。
```

For account, Provider Pool, or error drilldown that the Web payload does not expose, add only one short capability caveat at the end:

```text
如需账号、Provider Pool、错误明细，可再进入技术诊断视图查询。
```

## Example Answer

用户：今天 MaaS 用量怎么样？

After running `python scripts/web_status.py --format markdown`, answer like the returned visual report. Do not replace it with a text-only sentence.

```text
当前公网 MaaS 运行健康，今日请求 2,439 次，消耗 3,067.23 万 Token，费用约 917.55；峰值出现在 12:00，Top 模型是 gpt-5.5。内网 MaaS 当前为 limited，尚未接入完整 Agent，因此暂无详细 Token、模型、账号或 Pool 数据。
```
