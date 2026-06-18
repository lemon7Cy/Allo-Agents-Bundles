# MaaS Fleet Monitor Skill for ALLO

This project version lets ALLO query MaaS through the public read-only Web dashboard/API.

## Requirements

1. The MaaS monitor central service must be running on the public MaaS server.
2. The runtime should provide `MAAS_MONITOR_WEB_PASSWORD` through ALLO credentials or environment variables.
3. The Web dashboard is available at `http://221.0.79.251:39091/?v=metric1` with Basic Auth username `maas`.

## Web Fallback

Run the read-only Web report from this skill directory:

```bash
python scripts/web_status.py --format markdown
```

The script returns a ready-to-paste Markdown report with fresh PNG image references:

- overview dashboard
- model usage comparison
- today's Token trend
- last 7 days Token trend

Use `python scripts/web_status.py --format json` only when raw structured data is needed for debugging or downstream processing.

In ALLO, each script run writes images and `summary.md` under a unique `maas-monitor-reports/runs/{run_id}` directory when artifacts are available. The report stdout stays short so the bash tool does not truncate image data. The hidden file list is only for optional download/open requests. Do not call `present_files` by default. If the user asks for files, present only the paths listed in that same command's hidden `maas-monitor-present-files` comment. Do not discover or reuse older images from the workspace, and do not rely on a fixed user-specific path.

The script uses:

- `MAAS_MONITOR_WEB_URL`, default `http://221.0.79.251:39091`
- `MAAS_MONITOR_WEB_USERNAME`, default `maas`
- `MAAS_MONITOR_WEB_PASSWORD`, optional Basic Auth password

Never print or commit the password.

## Desktop Runtime Note

In ALLO desktop mode, skills are commonly loaded from the global custom skills directory:

```text
~/.allo/skills/custom
```

If this repository `skills/public` folder is not visible in the desktop app, copy this folder to:

```text
~/.allo/skills/custom/maas-fleet-monitor
```
