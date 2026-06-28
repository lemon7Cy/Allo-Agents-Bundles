# Tool Recipes

## Usage Summary

User asks:

- 今天 MaaS 使用情况怎么样？
- 本周整体用量如何？
- 当前有没有风险？

Run from this skill directory:

```bash
./scripts/run_web_status.sh --format json
```

Keep the embedded chart references and the compact metrics. Do not add data-channel details unless the user asks for troubleshooting.

## Model Ranking

Run:

```bash
./scripts/run_web_status.sh --format json
```

Answer from the returned `today`, `week`, and chart/file fields. If the Web payload lacks a requested window or model drilldown, mark it as a coverage gap.

## Error, Account, And Provider Pool Diagnosis

This project version does not include private account, Provider Pool, or detailed error drilldown. Use the Web dashboard status fields when available and mark missing detail as a MaaS backend/API capability gap.
