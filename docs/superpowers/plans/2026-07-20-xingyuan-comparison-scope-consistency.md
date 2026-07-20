# Xingyuan Comparison Scope Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent Xingyuan from calculating or reporting comparisons whose department, population, metric, timezone, or cutoff differs across periods.

**Architecture:** Add a self-contained deterministic comparison engine to the DFCode usage skill. The engine filters all periods through one roster snapshot, validates comparison metadata before aggregation, and emits the only allowed scope statement. Strengthen the agent and skill contracts so the model must use this engine rather than temporary hand-built dictionaries.

**Tech Stack:** Python 3 standard library, `unittest`, Markdown Agent Bundle contracts.

---

### Task 1: Add incident regression tests

**Files:**
- Create: `tests/test_xingyuan_scope_comparison.py`
- Create: `tests/fixtures/xingyuan_scope_incident.json`

- [ ] Write tests that import `xingyuan-monitor/skills/dfcode-usage-analysis/scripts/compare_scope.py` and assert fixed-scope totals, exclusions, ID-based joins, missing-row zero fill, and generated scope statements.
- [ ] Add tests that expect `ScopeValidationError` for organization-versus-department scope, cutoff, and metric mismatches.
- [ ] Run `python3 -m unittest tests.test_xingyuan_scope_comparison -v` and confirm failure because the script does not exist.

### Task 2: Implement deterministic comparison engine

**Files:**
- Create: `xingyuan-monitor/skills/dfcode-usage-analysis/scripts/compare_scope.py`

- [ ] Implement `analyze(payload)` with stable-user-ID roster joins, normalized department/status filtering, period metadata validation, totals, deltas, contributor ranking, exclusion counters, and generated scope statement.
- [ ] Implement a JSON-file CLI that writes structured JSON to stdout and returns non-zero with a bounded error on invalid input.
- [ ] Run `python3 -m unittest tests.test_xingyuan_scope_comparison -v` and confirm all tests pass.

### Task 3: Strengthen agent and methodology contracts

**Files:**
- Modify: `xingyuan-monitor/SOUL.md`
- Modify: `xingyuan-monitor/skills/dfcode-usage-analysis/SKILL.md`
- Create: `tests/test_xingyuan_scope_contract.py`

- [ ] Write contract tests requiring fixed roster snapshots, deterministic engine use, no manually assembled trend dictionaries, and hard failure on inconsistent scope.
- [ ] Run the contract test and confirm it fails against the current documents.
- [ ] Add the hard execution rules, exact engine invocation, normalized input contract, and rejected-input response template.
- [ ] Run both Xingyuan test modules and confirm they pass.

### Task 4: Verify and deliver canonical bundle

**Files:**
- Modify: `xingyuan-monitor/config.yaml`
- Modify: `docs/superpowers/specs/2026-07-20-xingyuan-comparison-scope-consistency-design.md`
- Modify: `docs/superpowers/plans/2026-07-20-xingyuan-comparison-scope-consistency.md`

- [ ] Increment `content_revision` so deployed clients detect the bundle update.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_*.py' -v`, `python3 -m py_compile xingyuan-monitor/skills/dfcode-usage-analysis/scripts/compare_scope.py`, and `git diff --check`.
- [ ] Review the branch diff against `origin/main` and ensure it contains only Xingyuan scope-consistency files and design/plan documentation.
- [ ] Commit, push to the configured fork if upstream is read-only, and open a PR to `wbz0429/Allo-Agents-Bundles:main`.

### Task 5: Synchronize Allo web vendored bundle

**Files:**
- Modify: `agent-configs/agents/xingyuan-monitor/SOUL.md`
- Modify: `agent-configs/agents/xingyuan-monitor/skills/dfcode-usage-analysis/SKILL.md`
- Create: `agent-configs/agents/xingyuan-monitor/skills/dfcode-usage-analysis/scripts/compare_scope.py`
- Modify: `agent-configs/agents/xingyuan-monitor/config.yaml`
- Create: `backend/tests/test_xingyuan_scope_comparison.py`

- [ ] Create a clean branch from the latest `origin/feat/web-multitenant`.
- [ ] Copy the reviewed canonical files and adapt the tests to the Allo repository path.
- [ ] Run the targeted backend tests and bundle validation available on the web branch.
- [ ] Commit, push, and open a PR with base `feat/web-multitenant`, linking the canonical bundle PR.
