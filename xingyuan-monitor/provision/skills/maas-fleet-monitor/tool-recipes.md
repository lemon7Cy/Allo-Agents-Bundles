# Tool Recipes

## Usage Summary

User asks:

- 今天 MaaS 使用情况怎么样？
- 本周整体用量如何？
- 当前有没有风险？

Run the read-only Web report from this skill directory:

```bash
python scripts/web_status.py --format markdown
```

Keep the three embedded PNG charts: model usage comparison, today's Token trend, and last 7 days Token trend. In ALLO, the fallback should embed charts directly in Markdown and also generate current-run files. Do not call `present_files` by default; only use the hidden `maas-monitor-present-files` paths when the user asks to download/open files. Do not search for charts or reuse old files. Do not add data-channel details unless the user asks for troubleshooting.

## Model Ranking

User asks:

- 哪个模型 Token 用量最高？
- 近 7 天模型排行？

Run `python scripts/web_status.py --format json` and read the `today`, `week`, and chart/file fields. If the Web payload lacks 30-day model ranking, mark it as a data coverage gap instead of inventing numbers.

## Error Diagnosis

User asks:

- 刚才为什么报错？
- 有没有 429、5xx、timeout？

Use the Web dashboard status fields when available. Mark 429/5xx/account/Pool drilldown as a backend/API capability gap when not returned by the Web payload.

## Account Diagnosis

User asks:

- 哪些账号不可调度？
- 上游账号有没有问题？

This project version does not include private account diagnostics. Mark account-level detail as a MaaS backend/API capability gap.

## Provider Pool Diagnosis

User asks:

- 某个 Provider Pool 是否健康？
- 为什么某个模型慢或不可用？

This project version does not include private Provider Pool diagnostics. Mark Pool-level detail as a MaaS backend/API capability gap.
