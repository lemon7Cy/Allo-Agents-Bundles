# Allo Agent Bundles

This repository stores external Agent Bundles for Allo. Allo loads bundles from
the directory pointed to by `ALLO_BUNDLES_ROOT` without requiring every business
agent to live in the main Allo repository.

## Local Usage

```bash
export ALLO_BUNDLES_ROOT=/Users/steven/allo-agent-bundles
cd /Users/steven/Allo
make desktop-dev
```

Each direct child directory is one Agent Bundle:

```text
<agent-name>/
  config.yaml
  SOUL.md
  capabilities.yaml
  provision/
  design/
```

## Bundle Contract

- `config.yaml` defines runtime identity, model defaults, dashboard routing, and access policy.
- `SOUL.md` defines persona, behavior, output style, and safety boundaries.
- `capabilities.yaml` declares Skill/MCP dependencies, entry prompts, and dashboard metadata.
- `provision/` may ship installable Skill/MCP sources for one-click setup (v1 layout).
- `design/` is documentation only unless Allo explicitly implements a loader for a file.

> **v2 (self-contained, per-agent isolated):** bundles may instead ship capabilities
> at the root under `skills/` and `mcp/`, which load **only for that agent** (no
> global install, not shared with the general assistant or other agents). See
> [PROTOCOL-v2.md](PROTOCOL-v2.md) for the v1↔v2 comparison and the loading model.
> `xingyuan-monitor` in this PR is migrated to v2.

## Access Fields

Bundles may declare lightweight visibility policy in `config.yaml`:

```yaml
access: org        # public | org | role
roles: [admin]    # used only when access=role
dashboard: full   # full | minimal | none
workspace_type: dashboard  # dashboard | workbench
```

Desktop mode is single-user and shows installed bundles locally. Server mode filters API results by the configured policy.

## Current Bundles

- `xingyuan-monitor` - 星元枢算助手, a monitoring Agent Bundle that aggregates MaaS, DFCode MCP, and notification/reporting capabilities.
