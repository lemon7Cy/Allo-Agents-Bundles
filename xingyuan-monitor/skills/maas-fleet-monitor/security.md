# Security Rules

- Never print or reveal MaaS passwords, API keys, account credentials, cookies, or request bodies.
- Store the Web dashboard password in ALLO Desktop credentials or environment variables, not in Git-tracked files.
- Use only the public read-only Web dashboard/API for this project version.
- Public Web dashboard URL is `http://221.0.79.251:39091/?v=metric1`; it uses Basic Auth username `maas`.
- Do not use public `/api/ingest/*`; it is intentionally blocked.
- Do not modify MaaS accounts, weights, routes, database rows, or credentials from this skill.
- Treat current tools as read-only diagnostics.
- Always state visibility gaps when detailed model/account/Pool/error data is not exposed by the Web payload.
