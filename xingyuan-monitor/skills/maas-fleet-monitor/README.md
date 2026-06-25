# MaaS Fleet Monitor Skill for ALLO

This project version lets ALLO query MaaS through the public read-only Web dashboard/API.

## Requirements

1. The MaaS monitor central service must be running on the public MaaS server.
2. Runtime credentials or environment variables must provide `MAAS_MONITOR_WEB_PASSWORD`.
3. The Web dashboard is available at `http://221.0.79.251:39091/?v=metric1` with Basic Auth username `maas`.

## Web Report

Run the read-only Web report from this skill directory:

```bash
cd /mnt/skills/custom/maas-fleet-monitor && ./.venv/bin/python scripts/web_status.py --format markdown
```

Use JSON only for debugging or downstream structured processing:

```bash
cd /mnt/skills/custom/maas-fleet-monitor && ./.venv/bin/python scripts/web_status.py --format json
```

The script writes images and `summary.md` under a unique `maas-monitor-reports/runs/{run_id}` directory when artifacts are available. Do not reuse old chart files.

Never print or commit the password.

## Desktop Runtime Note

Desktop skills are commonly loaded from:

```text
~/.allo/skills/custom
```
