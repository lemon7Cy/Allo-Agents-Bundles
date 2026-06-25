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

Access mode: public read-only Web dashboard/API at `http://221.0.79.251:39091/?v=metric1` with Basic Auth.

Do not reveal `MAAS_MONITOR_WEB_PASSWORD`, API keys, passwords, credentials, cookies, or request bodies in any answer.

## Public Web Dashboard

Dashboard URL:

```text
http://221.0.79.251:39091/?v=metric1
```

Login guidance:

- Username: `maas`
- Password must be provided through ALLO Desktop credentials or environment variable `MAAS_MONITOR_WEB_PASSWORD`.
- Never print or paste the password in chat.

Important boundaries:

- This project version does not require a private MaaS MCP deployment.
- The public Web URL is not an MCP endpoint.
- Public `/api/ingest/*` is intentionally blocked.
- This skill is read-only and must not modify MaaS accounts, weights, routes, database rows, or credentials.

## Data Coverage

- Public Web dashboard/API exposes customer-facing usage, health, model ranking, timelines, and generated chart artifacts.
- Account, Provider Pool, and detailed error drilldown are capability gaps unless the Web payload explicitly returns them.
- `internal-maas` may have limited visibility; clearly state gaps when detailed Token/model/account/Pool data is unavailable.
- Historical 30-day Token data before around 2026-06-06 may be incomplete because some old rows have request/cost data but zero token fields.

## Recipes

### Overall Usage

For questions like:

- 今天 MaaS 用量怎么样？
- 本周整体消耗如何？
- 当前有没有风险？
- 给领导一个 MaaS 摘要。

**Always run through the wrapper, from this skill's own directory** (the path shown in this skill's `<location>`). The wrapper auto-selects `.venv/bin/python` or `python3` and degrades gracefully if neither exists. Do **not** call `python scripts/web_status.py` directly and do **not** hardcode a `.venv` path.

```bash
cd "<this skill directory>" && ./scripts/run_web_status.sh --format markdown
```

Raw structured data: `./scripts/run_web_status.sh --format json`.

**Degrade gracefully — never loop.** If the wrapper/script cannot run (no shell, no Python, write permission denied — e.g. a Windows host without a usable sandbox shell):

- Do **NOT** retry repeatedly, and do **NOT** spawn subagents to brute-force chart generation — that holds the conversation lock and blocks every following message.
- Instead produce a **text-only monitor card** (状态 / 范围 / 信号 / 指标 / 诊断 / 建议 / 缺口) from the Web API JSON (or the user-provided data), and state in 缺口 that image/chart generation is unavailable in this environment. One attempt, then degrade.

Fallback rules:

- If Markdown is returned, paste it with minimal edits and keep the image references.
- If JSON is returned, answer from `today`, `week`, `instances`, `charts`, `files`, and `coverage_note`.
- If it returns `missing_web_password`, tell the operator to configure `MAAS_MONITOR_WEB_PASSWORD` in runtime credentials or environment.
- If it returns `web_api_unreachable`, say the public Web dashboard/API is unreachable and include the dashboard URL for manual verification.
- If it returns `python_not_found` (the wrapper's fallback), give the text monitor card and note that Python/charting is unavailable on this host — do not keep trying.
- Never print the Basic Auth password.

Answer with:

- total Token
- request count
- cost when available
- peak period
- top model
- healthy/degraded/limited instances
- data coverage notes

## Answer Style

- Default to a leadership-summary style for usage questions: concise, metric-first, no debugging transcript.
- Start with one conclusion sentence, then one compact metrics block, then coverage notes.
- For usage/status questions, include charts before the metrics table whenever chart paths are available.
- Do not show intermediate command execution details, raw URLs, curl errors, or JSON fields unless the user explicitly asks how the data was queried.
- Do not include formulas or LaTeX-like fractions; write shares plainly, for example `gpt-5.5 占比约 82.8%`.
- Keep leadership summaries to 5-8 short lines. Use a table only when it improves scanning.
- Never claim account, Provider Pool, or detailed error diagnostics unless the Web payload returns them.
