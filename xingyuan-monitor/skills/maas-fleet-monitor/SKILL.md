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

**Default: pull JSON and render a text monitor card + markdown table — no image.** This is the portable path (no Pillow, no chart generation, works on Windows):

```bash
cd "<this skill directory>" && ./scripts/run_web_status.sh --format json
```

From the JSON, render a **monitor card** (状态 / 范围 / 信号 / 指标 / 诊断 / 建议 / 缺口) plus a compact markdown metrics table. Do **not** generate or reference chart images by default.

**Only if the user explicitly asks for an image/chart** (e.g. "给我一张用量图"), try `--format markdown` (which renders PNG charts via Pillow). If charts are unavailable (no Pillow, no shell), do **not** retry — fall back to the card + table and note in 缺口 that the image is unavailable here.

**Degrade gracefully — never loop.** If the wrapper/script cannot run at all (no shell, no Python, write permission denied — e.g. a Windows host without a usable sandbox shell):

- Do **NOT** retry repeatedly, and do **NOT** spawn subagents to brute-force it — that holds the conversation lock and blocks every following message.
- Produce the **text-only monitor card** from the user-provided data (or say the live data is unreachable), state the limitation in 缺口. One attempt, then degrade.

Fallback rules:

- Default to JSON; answer from `today`, `week`, `instances`, `charts`, `files`, and `coverage_note`.
- If Markdown was explicitly requested and returned, paste it with minimal edits.
- If it returns `missing_web_password`, tell the operator to configure `MAAS_MONITOR_WEB_PASSWORD` in runtime credentials or environment.
- If it returns `web_api_unreachable`, say the public Web dashboard/API is unreachable and include the dashboard URL for manual verification.
- If it returns `python_not_found` (the wrapper's fallback), give the text monitor card and note that Python/charting is unavailable on this host — do not keep trying.
- Never print the Basic Auth password.

Answer with:

- total Token
- request count
- cost when available
- peak period
- model breakdown — list the full `model_breakdown` (top 5 models with token + share %), not just the single top model, so usage is fully attributed (no "未归属" gap)
- healthy/degraded/limited instances
- data coverage notes

## Answer Style

- Default to a leadership-summary style for usage questions: concise, metric-first, no debugging transcript.
- Start with one conclusion sentence, then one compact metrics block, then coverage notes.
- Default to the monitor card + a compact metrics table; do not include chart images unless the user explicitly asked for one.
- Do not show intermediate command execution details, raw URLs, curl errors, or JSON fields unless the user explicitly asks how the data was queried.
- Do not include formulas or LaTeX-like fractions; write shares plainly, for example `gpt-5.5 占比约 82.8%`.
- Keep leadership summaries to 5-8 short lines. Use a table only when it improves scanning.
- Never claim account, Provider Pool, or detailed error diagnostics unless the Web payload returns them.
