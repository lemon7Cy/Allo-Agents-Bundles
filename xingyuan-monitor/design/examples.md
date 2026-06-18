# 星元枢算助手示例

Status: design only, not runtime-loaded in phase 1.

## Workbench-first prompts

- 看一下今天 MaaS 和 DFCode 整体有什么需要关注的地方。
- 今天哪个模型用量最高，主要来自哪些部门？
- 最近有没有错误、反馈或运营风险？
- 生成一条飞书监控摘要草稿，先不要发送。
- 把刚才的监控摘要发送到飞书。

## Expected behavior

- Use compact monitor-card output unless the user explicitly asks for a report.
- Show missing Skill, MCP, credential, or API fields as data gaps.
- Keep MaaS data retrieval inside `maas-fleet-monitor`.
- Keep Feishu card rendering/sending inside `feishu-webhook-report`.
- Represent desktop results as run, snapshot, evidence, and Feishu draft objects rather than one chat answer.
