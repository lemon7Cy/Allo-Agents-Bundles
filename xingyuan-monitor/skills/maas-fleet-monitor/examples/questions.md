# MaaS Skill Smoke Test Questions

Ask these in ALLO after enabling the Skill and configuring the Web dashboard password.

## Usage Summary

```text
今天 MaaS 用量怎么样？
```

Expected command:

```text
cd /mnt/skills/custom/maas-fleet-monitor && ./.venv/bin/python scripts/web_status.py --format markdown
```

Then answer with a concise summary and embedded chart references.

## Weekly Model Ranking

```text
近7天哪个模型 Token 用量最高？
```

Expected command:

```text
cd /mnt/skills/custom/maas-fleet-monitor && ./.venv/bin/python scripts/web_status.py --format json
```

## Error / Account / Provider Pool Detail

If the Web payload lacks detailed errors, account, or Provider Pool fields, say this project version exposes only Web dashboard/API data and mark the requested drilldown as a coverage gap.
