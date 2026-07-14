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
- `provision/` may ship installable Skill/MCP sources for one-click setup.
- `design/` is documentation only unless Allo explicitly implements a loader for a file.

> **v2 (self-contained, per-agent isolated):** bundles may instead ship capabilities
> at the root under `skills/` and `mcp/`, which load **only for that agent** and are
> not shared with the general assistant or other agents. See
> [PROTOCOL-v2.md](PROTOCOL-v2.md) for the complete development contract.

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

- `course-report-teaching-agent` - 教学助手，面向课程报告评审、修订、评价与教学反思。
- `coursework-student` - 课程报告助手（学生端），提供选题、文献、写作和自评支架。
- `xingyuan-monitor` - 星元枢算助手，聚合 MaaS、DFCode MCP 和飞书监控上报能力。
