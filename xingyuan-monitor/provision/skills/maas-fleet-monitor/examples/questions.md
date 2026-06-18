# MaaS Skill Smoke Test Questions

Ask these in ALLO after enabling the Skill and configuring the Web dashboard password.

## Usage Summary

```text
今天 MaaS 用量怎么样？
```

Expected command:

```text
python scripts/web_status.py --format markdown
```

Then paste the returned Markdown report with embedded images. Do not call `present_files` unless the user asks to download/open the generated files; if needed, use only the files listed in that same command's hidden `maas-monitor-present-files` comment.

Expected answer style:

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

Avoid long execution explanations, data-channel sections, raw endpoint dumps, curl errors, duplicate conclusions, formula blocks, and old chart files.

## Weekly Model Ranking

```text
近7天哪个模型 Token 用量最高？
```

Expected command:

```text
python scripts/web_status.py --format json
```

## Error Risk

```text
现在 MaaS 有没有错误或风险？
```

Expected command:

```text
python scripts/web_status.py --format json
```

If the Web payload lacks detailed errors, mark error drilldown as a backend/API capability gap.

## Account Diagnosis

```text
哪些上游账号现在不可调度？
```

Expected answer:

```text
当前项目版仅接入 MaaS Web dashboard/API，账号级诊断属于后端/API 能力缺口。
```

## Provider Pool Diagnosis

```text
Provider Pool 现在有没有异常？
```

Expected answer:

```text
当前项目版仅接入 MaaS Web dashboard/API，Provider Pool 诊断属于后端/API 能力缺口。
```

## Internal MaaS Coverage

```text
内网 MaaS 为什么没有 Token 明细？
```

Expected answer:

```text
internal-maas 尚未部署 Agent，所以只有健康状态，暂无 Token、模型、账号、Pool 明细。
```
