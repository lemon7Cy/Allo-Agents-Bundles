---
name: incremental-evaluation
description: 'Compare a course-report first draft and final draft, or run an explicitly requested quantitative six-dimension evaluation. Default to a qualitative, evidence-based comparison without scores. Produce six numeric scores and a radar chart only when the teacher explicitly asks for scoring, quantification, or a radar, or supplies a rubric that requires numeric scores.'
---

# Draft-to-Final Incremental Evaluation

## What this skill solves

This skill compares **observable changes from first draft to final draft**. A strong increment is backed by concrete changes in decisions, evidence, methods, analysis, citation closure, boundaries, and reflection. A language-only change is reported as expression improvement, not automatically as deeper learning. The teacher retains the final judgment.

## Choose the mode first

### Qualitative comparison (default)

Use this when the user asks to compare, review, diagnose, or comment without explicitly requesting numeric scores.

- Read both drafts across text, formulas, figures, code, and tables.
- Compare the six canonical dimensions when relevant: 创新性、数据分析深度、完整性、文献引用、结论合理性、格式规范性.
- For each dimension, state the initial evidence, final evidence, observable change, and remaining gap.
- Do **not** create numeric scores, a scorecard, a benchmark, `scores.json`, or a radar chart.
- A single-draft review is also qualitative by default.

### Quantitative six-dimension comparison (explicit request only)

Use this only when the user explicitly asks to score, quantify, compare scores, or generate a radar chart, or when a supplied course rubric requires numeric scores.

- Read `rubric.md` before scoring. Scoring from memory or from example numbers is not allowed.
- Score each provided draft from 0–100 on all six canonical dimensions and give material-specific evidence for every score.
- The script handles the increment table and radar; do not draw a text chart yourself.
- The same six values must be used in the score table, `scores.json`, and any PDF radar.
- A benchmark is allowed only when the teacher supplied a course target in the current request or materials.

## Evidence boundary

- Use only the uploaded drafts, `rubric.md`, and current-run tool results as factual support.
- Do not convert RMSE into a different metric, invent an acceptance threshold, prescribe a fixed reference count, or name a remembered dataset.
- Apply the same boundary to examples, suggested experiments, self-checks, and teacher follow-up questions. Use source-provided values or symbolic wording; never invent a concrete initial value, range, comparison count, or target merely to make a question sound specific.
- Treat filenames only as identifiers. Determine whether a revision is language-only or substantive from the actual content comparison, never from words in the filename.
- Immediately before replying, scan the final draft-comparison text itself. Remove every numeric literal/range not present in the uploaded drafts or requested rubric, including numbers hidden inside suggested experiments and teacher questions. Replace them with symbolic wording such as `更换初值`, `调整停止条件`, or `增加对照条件`. Do not use checkbox/status glyphs such as `✓`, `✗`, `✅`, `❌`, or `⚠️`.
- When no acceptance criterion is available, report the observed result and ask for the course/project baseline.
- Every high-priority issue must remain closed-loop: `material evidence → student action → student self-check → teacher verification`.
- Video evidence may add timestamped oral corroboration and a coverage comparison, but it must never raise a written-report score.

## Workflow

### 1. Read and verify the drafts

Use the files from `$ALLO_UPLOADS_DIR` or `$ALLO_WORKSPACE_PATH`. Prefer an upload-provided same-basename Markdown companion instead of reconverting a PDF. Confirm which file is the first draft and which is the final draft.

### 2. Produce the qualitative comparison

Return:

- Increment overview.
- Dimension comparison: initial evidence, final evidence, observable change, remaining gap.
- Changes that are substantive versus language-only.
- Remaining priorities in closed-loop format.
- Teacher follow-up questions and student reflection prompts.

Stop here unless quantitative comparison was explicitly requested.

### 3. Quantitative branch only

After reading `rubric.md`, write a temporary `scores.json`:

```json
{
  "title": "<课题名>",
  "dimensions": ["创新性", "数据分析深度", "完整性", "文献引用", "结论合理性", "格式规范性"],
  "series": {"初稿": [60, 55, 70, 50, 65, 80], "终稿": [78, 82, 85, 72, 80, 88]},
  "evidence": {
    "数据分析深度": "终稿新增了分组对比及其解释；初稿只列出了均值。"
  }
}
```

The numbers above are schema examples, not scoring standards. Derive all real values from the current drafts and `rubric.md`.

Render the quantitative comparison:

```bash
python3 scripts/render_eval.py --scores scores.json
```

The script prints the six-dimension increment table and writes the radar chart to `$ALLO_OUTPUTS_DIR`. If matplotlib or a Chinese font is unavailable, keep the table and report the chart dependency issue; do not invent a replacement chart.

### 4. Optional PDF export

Do not export a PDF by default. If the user explicitly asks for a downloadable or printable evaluation, use `report-pdf-export` after the evaluation is complete. For a quantitative PDF, the scorecard and radar must use identical six-dimension values and the radar must be the final section. For a qualitative PDF, omit both scorecard and radar.

Before rendering a report-based PDF, run `scripts/validate_evaluation_evidence.py` with `python3` against the JSON and source report Markdown. The validator loads the adjacent bundled `rubric.md` itself, so do not pass a second `/mnt/skills/agent/...` rubric path. Fix a failed validation from current evidence; never bypass it, install packages, or continue to rendering after a blocked/failed validation.
