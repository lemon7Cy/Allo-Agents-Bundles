---
name: report-writing
description: Create editable coursework paper/report drafts and help revise them with evidence-aware writing, outlines, analysis plans, source boundaries, and six-dimension feedback. Read this skill when a student asks to write a first draft, complete or revise a report/chapter/section, check a draft, or plan the analysis. When PDF, Word, or DOCX is explicitly requested, pair this skill with document-export in the same turn.
---

# Coursework Drafting and Revision

Deliver a useful first version at the level requested, then help the student improve it with materials, data, and verified sources. Never replace missing evidence with plausible-sounding facts.

## 0. Explicit PDF / Word handoff (Highest Priority)

When the request explicitly says PDF, Word, DOCX, printable, or editable Word document, read `/mnt/skills/agent/document-export/SKILL.md` before attempting any conversion. This gate overrides the normal Markdown-only delivery in the workflow below.

1. Write the completed Markdown source to `/mnt/user-data/tmp/<clear-name>.md`, not to `outputs`, unless the user also requested Markdown.
2. Run the bundled `document-export` command exactly as a top-level shell command, with `--input` pointing to the temporary Markdown and `--out` pointing to the requested `.pdf` or `.docx` under `/mnt/user-data/outputs/`.
3. Do not probe for Pandoc or `python-docx`, run `pip install`, create a conversion script, or place a literal `/mnt/user-data/outputs/...` path inside custom Python. Those routes can create a transient file that appears in one shell but is unavailable to the artifact download service.
4. Present the requested file only after the renderer reports `status=ok` and a separate top-level existence check succeeds. If the renderer fails, provide the completed content without claiming that the requested file exists.

## 0. Complete first-draft workflow

When the user asks for a paper/report first draft, a complete draft, or body text for a chapter or section:

1. Read the user's supplied topic, course requirements, files, constraints, and requested output format. Do not require preliminary answers when the existing request is enough to begin.
2. If the user asks for verifiable literature or citations, use `literature-review` and include only sources verified in the current run. If verification cannot be completed, keep the reference entry or supporting claim visibly marked `待核实`; never invent bibliographic fields.
3. Write actual connected prose for the requested sections. A complete first draft normally includes the title, abstract, keywords, introduction/problem statement, related work or conceptual basis, research questions, research design, data and analysis plan, expected contribution, conclusion boundary, and references or a verification list. Adapt this structure to the user's request instead of forcing every heading.
4. When the user has not supplied data or results, write methods and analysis in proposed/future tense. Use explicit placeholders such as `[待补：样本来源]`, `[待补：量表或指标定义]`, and `[待数据分析后填写]`. Do not manufacture a completed experiment or positive conclusion.
5. With no explicit PDF/Word request, save the complete draft to `/mnt/user-data/outputs/<课题简称>-论文初稿.md` with `write_file`, then call `present_files`. Do this even when the user only says “写个初稿” and does not separately ask for a file. With an explicit PDF/Word request, follow the handoff gate above instead.
6. Reply with a concise completion summary, name the file, and state which evidence fields still need the user's material. Do not expose `/mnt/...` paths or internal tool names. Do not end with only an outline or questions.

## 0. Six-Dimension Quality Standard (the unified rubric for checking drafts)
The six dimensions = **创新性、数据分析深度、完整性、文献引用、结论合理性、格式规范性**. Student self-check is qualitative by default: point out evidence, gaps, and priorities without forcing numeric scores or a radar.
**Before checking a draft, first read `rubric.md` in this same directory** — it holds the 0–100 score-band anchors (weak/medium/strong) for each dimension plus a **"critical-flaw checklist"** (data-source↔conclusion fit, citation closure, continuous figure numbering, numerical self-consistency, relative vs. absolute, evaluation baseline) that helps the student **find gaps by comparison**. This yardstick is **exactly identical** to the teacher-side review: the spots a student fixes by self-checking against it are exactly the spots the teacher's review will award points for.

## 0.5 Uploaded prediction CSV: deterministic evidence gate

When the user uploads a CSV and asks whether a model/result is effective, accurate, qualified, or good, first identify the exact reference and prediction columns from the file. Then run:

```bash
python3 /mnt/skills/agent/report-writing/scripts/evaluate_prediction_csv.py \
  --file /mnt/user-data/uploads/<file.csv> \
  --reference-column '<reference column>' \
  --prediction-column '<prediction column>' \
  --time-column '<optional time column>'
```

Omit `--time-column` when no time column exists. Never install a dependency, calculate aggregate metrics mentally, add an acceptance threshold, infer a root cause, or replace the script's boundary with a stronger conclusion. Parse the JSON. For `status=ok` or `status=needs_input`, return `safe_chat_summary` verbatim as the whole answer. For `status=error`, return its `safe_chat_summary` and ask the user to re-upload or correct the CSV; do not claim a numeric result.

## 1. Writing and analysis support
When the student asks how to write or analyze a specific part:
- Match the requested depth. Provide connected draft prose when they ask for prose; provide an outline or sentence skeleton only when they ask for a framework.
- For data-analysis work, clarify what method can answer the research question, how to validate it, and what assumptions and limitations must be reported. Give readable example code when useful.
- Distinguish observed facts, proposed methods, expected contribution, and pending evidence in both chat and files.

## 2. Revision phase
When the student submits a draft (already uploaded; read it with `read_file`):
- Go through the **six dimensions** item by item and point out specifically which paragraph/sentence has what problem, why, and which direction to revise toward. When the user asks you to revise the text, provide the revised passage as well as a short explanation of the material change.
- Distinguish "critical flaws" (broken logic, fake citations, conclusions overreaching the evidence) from "could be optimized."
- Finally, give a **revision-priority list** (what to fix first).
- Close the feedback loop. For every high-priority item include the evidence location, why it blocks the learning goal, the student's next action, and how the student can self-check the revision. Avoid vague praise or criticism about the person.
- In visible output, call these `关键问题`, `随后完善`, and `可选优化`. Never expose `P0/P1/P2`, internal test labels, or the phrase `硬伤`.
- Keep critique neutral and material-focused. After drafting the complete visible response, scan it literally and rewrite every occurrence of `至少`, `不少于`, `若干`, `多项`, `多个`, `多处`, `几项`, `几处`, `一系列`, `一张`, `一条`, `各补`, `各增加`, `各添加`, `必须`, `严重`, `最薄弱`, `完全套模板`, `直接暴露`, `几乎为零`, or `断链`, including occurrences in questions, headings, tables, and quotations. Do not prescribe a fixed figure/source/experiment count or an unsupplied parameter value; name the missing evidence type and leave the concrete condition to the student or teacher.
- Judge completeness against the supplied task/rubric. If no word count, required section list, or reference count was supplied, do not invent one; describe only the observable missing reasoning, evidence, or structure.
- Do not name remembered textbooks, authors, papers, datasets, standards, or prescribe a fixed reference count during draft feedback. Use only sources visible in the draft/current tools; otherwise ask for the course-designated material or suggest a generic source type to verify.
- Before returning the review, write the complete visible draft to `/mnt/user-data/tmp/visible-review-draft.md` and run `python3 /mnt/skills/agent/report-writing/scripts/validate_visible_review.py --draft /mnt/user-data/tmp/visible-review-draft.md`. Rewrite once if blocked, validate once more, and on success copy the validated draft verbatim with no extra text. If the second validation is still blocked, return only a brief evidence-boundary message.

## 3. Output template (revision)
```
初稿六维诊断:
- 创新性:<具体问题/亮点> → 建议方向
- 数据分析深度:…
- 完整性:…
- 文献引用:…（来源可核实性也查）
- 结论合理性:…
- 格式规范性:…

修改优先级:1)<优先处理> 2)<随后完善> 3)<可选优化>
（请按修改任务补齐材料和表达；需要某段的提纲/思路可继续展开）
```
