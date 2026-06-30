---
name: incremental-evaluation
description: Read this skill when the user wants to "review a course report," "score on the six dimensions," "compare the first draft and final draft," or "generate an incremental evaluation / radar chart." It turns the six-dimension evaluation from "just talk" into something "visualized and verifiable" — you (the LLM) score each draft on the six dimensions per the rubric and write the justification, while the script draws the radar chart and computes the increments. The core is incremental evaluation: it looks at the real improvement from first draft → final draft (sidestepping "was this written by AI").
version: "1.0.0"
author: allo-official
---

# Six-Dimension Incremental Evaluation (the reviewer's killer feature)

## What this skill solves
The pain point of evaluating course reports is "you can't tell a student's real level vs. AI ghostwriting." What this skill scores is **not the absolute quality of any single draft, but the "increment" from first draft → final draft** — a large increment backed by an evidence chain means the student genuinely learned and improved while collaborating with AI; a hollow increment or mere polishing means the understanding didn't deepen. This is exactly the incremental evaluation philosophy of 明学慧评.

## Division of responsibility (hard rules)
- **You (the LLM) make the judgment**: read the drafts, score **each draft** 0–100 on the six-dimension rubric below, and write one sentence of **justification** per dimension. Judgments must be grounded — distinguish "supported by evidence," "reasonable inference," and "pending teacher confirmation"; do not fabricate when material is missing.
- **The script handles visualization**: the radar chart + increment table are produced by `scripts/render_eval.py`; **do not draw charts yourself with text**.
- **Teacher authority**: you only provide a reference evaluation; you do not replace the teacher's official grade.

## Six-dimension rubric (metric library)
The six dimensions = **创新性、数据分析深度、完整性、文献引用、结论合理性、格式规范性**.
**Before scoring you must read `rubric.md` in this skill's directory** — it has the 0–100 band anchors for each dimension (weak/medium/strong, taken from real samples), plus **6 deep-read hard-deduction items** (data authenticity ↔ conclusion consistency, citation closure, figure-number continuity, cross-section numerical self-consistency, relative vs. absolute metrics, correctness of the evaluation baseline) and difficulty-tiering rules. **Scoring off the top of your head without reading the rubric is not allowed.**

## Workflow

### 1. Get the drafts
Read the first draft and final draft from the user's uploads / workspace (`$ALLO_UPLOADS_DIR` / `$ALLO_WORKSPACE_PATH`). It also works with only one draft (produces a single-draft profile only, no increment).

### 2. Six-dimension scoring (you do this)
**First read `rubric.md` to pin down the bands**, then **deep-read across modalities** (formulas / figures / code / tables all must be examined, not just the body text) and go through those 6 hard-deduction items one by one. Then score the **first draft** and the **final draft** separately, written as a JSON (scores 0–100), with `evidence` giving one sentence of justification per dimension (must cite specific content/data from the draft, no vague generalities):

```json
{
  "title": "<课题名>",
  "dimensions": ["创新性", "数据分析深度", "完整性", "文献引用", "结论合理性", "格式规范性"],
  "series": {"初稿": [60, 55, 70, 50, 65, 80], "终稿": [78, 82, 85, 72, 80, 88]},
  "evidence": {
    "数据分析深度": "终稿新增了分组对比与显著性说明,从'贴图'变为'有分析';初稿仅罗列均值。"
  }
}
```

Write it into the workspace, e.g. `scores.json` (leave no extra files in the conversation; a temp directory is fine too).

### 3. Render chart + increment table (the script does this)
```bash
python3 scripts/render_eval.py --scores scores.json
```
The script will: ① print the **six-dimension increment table** (初稿/终稿/Δ + total); ② generate a **radar chart** in `$ALLO_OUTPUTS_DIR` (初稿 vs 终稿 overlaid); ③ automatically degrade when matplotlib / a Chinese font is missing (the table still prints, the chart is skipped or uses the D1–D6 abbreviations), never erroring out and interrupting.

Dependency: `matplotlib` (see requirements.txt); the table still works without it.

### 4. Give the evaluation (you do this)
Based on the increment table + radar chart, produce:
- **Increment highlights**: which dimensions improved the most + the corresponding growth evidence (cite specific changes in the final draft).
- **Remaining risks**: which dimensions are still weak, and what the final draft still lacks.
- **Reference comments for the teacher** + **3–5 questions to ask the student** (to verify genuine understanding rather than AI ghostwriting).

## Optional: AI baseline comparison (a stronger "do they really understand" test)
In addition to "初稿 vs 终稿," you can add a third series 「AI独立解法」 — have the agent independently produce a version of the same topic and compare it against the "student + AI final draft." If the student's final draft **exceeds** the AI's independent solution on some dimensions, that is strong evidence of genuine student understanding. Usage: just add one more entry `"AI独立解法": [...]` to `series`, and the script will draw it into the radar chart as well.

## Example
Under `examples/` there is a synthetic sample (topic + first draft + final draft + sample-scores.json), which you can run directly:
```bash
python3 scripts/render_eval.py --scores examples/sample-scores.json --title "示例:城市共享单车调度课程报告"
```
Use it to quickly validate the workflow and show the teacher the result.
