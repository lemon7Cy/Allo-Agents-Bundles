---
name: report-presentation-review
description: "Evaluate a student's course-report presentation or defense video as objective oral and coverage evidence. Read this skill whenever the teacher gives a local video, an already-processed video job_id, or an App-generated video_understanding_jobs handoff and asks to evaluate the presentation or compare it with a written report. A video-only review never creates written six-dimension scores or a radar. With a report, scoring remains optional and must come only from an explicitly requested written-report evaluation. An App handoff job_id is authoritative: never upload that video again."
---

# Course-Report Presentation / Defense Review (讲解答辩视频评价)

## Authorship request: fixed short-circuit

Before accepting a video job or inspecting any material, detect requests to infer authorship, ghostwriting, cheating, suspicious patterns, consistency strength, or "背诵/本人理解" from a report or video. For those requests, return Mandatory Gate A from the agent SOUL verbatim. Do not call the video service, inspect files, provide hypothetical examples, or continue into the workflow below.

## Why this exists (the point in the 明学慧评 context)

明学慧评 can review the **written report** qualitatively or, when explicitly requested, quantitatively across the 六维 (创新性/数据分析深度/完整性/文献引用/结论合理性/格式规范性). The presentation/defense video adds **objective oral and coverage evidence**: it shows how the work was explained out loud and which written points were covered.

This skill's job is a **讲解答辩评价 + 客观覆盖对照** that folds into the overall evaluation — stated positively and factually:
- **口头可考察内容**: organize timestamped evidence around 创新性 / 数据分析深度 / 结论合理性 when those labels fit the task. 文献引用 / 格式规范性 are written-only — the video does not judge them or create written-report scores.
- **报告↔讲解覆盖对照** (objective, reference only): for each key report point, did the oral explanation **cover it / touch it briefly / not mention it** — reported as plain facts for the teacher. Frame gaps constructively (e.g. "建议在答辩中补充说明 X") and keep every visible sentence focused on material evidence and next actions.
- **诚实**: 表达/肢体/流畅性维度由骨架/姿态通道量化,**由 render `--job` 权威注入,agent 不写这行**;口头维度不瞎打分,每条结论带时间戳。

> Tone rule: this is a **constructive, objective** review. Do **not** produce anti-cheating / ghostwriting / authenticity language. If the oral explanation is thinner than the report, describe it factually and suggest what to clarify — do not speculate about who wrote the report.

## Hard rules (same discipline as the general av skill)

- **Authorship requests are not a video-analysis mode.** Return Mandatory Gate A from the agent SOUL verbatim and add nothing else.
- **App handoff wins; never upload twice.** Before looking at attachment paths, scan the human message for a `<video_understanding_jobs>` block. Its JSON array contains the videos that the App has already uploaded and finalized. For every item with a non-empty `job_id`:
  - Treat that `job_id` as the only authoritative video input, even if the same message also shows an `.mp4` attachment or local path.
  - Never call `upload`, `submit`, `analyze`, `POST /api/videos`, or any other upload command for that video. Never ask the user to choose the file again.
  - Query/wait with that same `job_id`, then run `course-eval` once.
  - If several jobs are present, process each `job_id` exactly once and keep filename-to-job mapping from the envelope.
- **Malformed App handoff is a zero-tool hard stop.** If `<video_understanding_jobs>` is invalid JSON, is not an array, or contains no non-empty `job_id`, do not inspect files, health-check, list/query jobs, print script usage, inspect caches, or call any other tool. Reply only: `App 视频任务信息不完整，缺少有效 job_id。请在 App 中重试本次上传或恢复任务；收到新的 handoff 后我会继续。为避免重复传输大文件，我不会在 Agent 侧重新上传。`
- **Never inspect runtime configuration or credentials.** Do not run `env`, `printenv`, `set`, `export -p`, inspect `/proc/*/environ`, grep environment variables, or print/echo/test any token, key, secret, service URL, or credential-related variable. Determine video-service availability only through the provided script's normal `health` result after a valid video input has been established.
- **Remote service only, no local fallback.** This is a thin client for the Allo video service. Never run local ffmpeg/whisper/OCR to substitute a result. After resolving a valid video input, health-check:
  ```bash
  bash /mnt/skills/agent/report-presentation-review/scripts/media_understanding.sh health
  ```
  If it does not return `status:ok` (exit `6`), STOP and tell the user the service is unavailable — do not fabricate a transcript/score.
- **Async job API.** Upload only creates a `job_id`; poll `GET /api/jobs/{id}` until `done`/`failed`, then fetch results. Never re-upload on a foreground/600s timeout — resume with the same `job_id`.
- **Large files.** Course-report videos are typically 100 MB–5 GB / 10–30 min. Upload takes time; the job runs async. If a tool call is killed at ~600s while the job is still processing, **check the job and keep waiting with the same job_id** — never re-upload.
- **Evidence-grounded, no hallucination.** Every highlight / problem / coverage finding must tie to a returned timestamp in the structured result. If you can't back a claim with returned evidence, drop it. Evidence source fields are internal and must not appear in the customer-facing answer.

## Workflow (course-report defense) — keep it to ~2-3 tool calls, then ANSWER IN CHAT

> **Do NOT over-run tools.** `course-eval` already fetches and grounds on the
> timeline + summary + presentation-evaluation **server-side** and returns the
> whole structured result in ONE call. **Never separately call `timeline`,
> `summary`, or `presentation` for this workflow** — the raw `timeline` is huge,
> gets truncated, and a long tool chain makes the run stall with no answer. One
> `health` + (reuse job_id) + one `course-eval` is the entire data step.
>
> **不要自己写 Python 脚本来编排评价/提取/渲染**(如 `build_kalman_eval.py`、
> `extract_pdf.py`、把路径写进临时文件再读之类)。**评价就用 `media_understanding.sh
> course-eval`,提取报告就用现成 markitdown 一行,渲染就用 `render_report_pdf.py`。**
> 自己造脚本 = 反复试错 → 撞迭代上限 → 「执行完成但无输出」。整条流程 ≤3 步工具调用:
> `course-eval` → (读 `gallery_block.json`)→ `render_report_pdf.py --job`。发现自己在写脚本
> 编排,立刻停手,回到这三步。路径带空格就用双引号 `"..."`,别用临时文件绕。

1. **Resolve the video input without tools.** First inspect `<video_understanding_jobs>`. Parse its JSON array and collect every non-empty `job_id`. If parsing fails or none exists, return the fixed malformed-handoff reply above and stop with zero tool calls.
2. **Health check** once, but only after step 1 produced a valid App `job_id`, the teacher supplied a plain `job_id`, or a local video path exists. Stop on failure.
3. **Get a `job_id` — App handoff first, then explicit ID, upload last.**
   - **For a valid `<video_understanding_jobs>` block**, reuse every supplied `job_id`; the App has already completed the resumable upload and created the remote job. Do not inspect the attachment path as an upload candidate and do not run `analyze`. If its status is not yet `done`, use `bash /mnt/skills/agent/report-presentation-review/scripts/media_understanding.sh wait JOB_ID forever 5`.
   - **Otherwise, if the teacher already gives you a plain `job_id`**, **do NOT upload anything** — the result is cached. Go straight to step 4. (One optional sanity check: `bash /mnt/skills/agent/report-presentation-review/scripts/media_understanding.sh job JOB_ID`.)
   - **Only if there is no `job_id`**, submit the local file and wait:
     ```bash
     bash /mnt/skills/agent/report-presentation-review/scripts/media_understanding.sh analyze /absolute/path/to/讲解视频.mp4 auto
     ```
     On a foreground timeout, resume: `bash /mnt/skills/agent/report-presentation-review/scripts/media_understanding.sh wait JOB_ID forever 5`.
4. **Run course-eval ONCE, passing the written report** — this is the whole data call:
   ```bash
   bash /mnt/skills/agent/report-presentation-review/scripts/media_understanding.sh course-eval JOB_ID /absolute/path/to/report.txt
   ```
   (Omit the file to skip the coverage comparison and only get the video-side evaluation.)
   - If the report + video result will be validated or exported as a PDF, redirect this authoritative result to `/mnt/user-data/tmp/course-eval.json` and pass that file to the report evidence validator with `--video-evidence`. This grounds video timestamps and generated key-frame paths while leaving written-report scores grounded only in the report and rubric.
   - For the **report + video qualitative branch**, use the same single call but redirect its JSON to the private temporary evidence file, then read that file before drafting:
     ```bash
     bash /mnt/skills/agent/report-presentation-review/scripts/media_understanding.sh course-eval JOB_ID /absolute/path/to/report.txt > /mnt/user-data/tmp/course-eval.json
     ```
   - **Video-only branch:** if no written report was supplied, do not read `gallery_block.json`, do not read the incremental-evaluation skill, and do not create/present a file or render a PDF unless the teacher explicitly requested a downloadable artifact. Reply in chat with the full substantive review: organization, central message, supporting material, timestamped content evidence, and concrete improvement actions. Explicitly state briefly that written-report dimensions are not evaluated. Unless the teacher explicitly requested grading, remove every `level` field and do not turn `强/中/弱` into an overall grade. Omit expression/body-language/fluency entirely; do not explain which internal channel owns it.
   - **Report + video qualitative branch:** when a written report is supplied but the teacher did not explicitly request scoring, quantification, a radar, or a downloadable artifact, keep the joint review qualitative and chat-first. Do not read the numeric incremental-evaluation rubric, create `scores.json`, present a file, or render a PDF. Save the single `course-eval` result to `/mnt/user-data/tmp/course-eval.json`; write the proposed visible answer to `/mnt/user-data/tmp/joint-review-draft.md`. The report supplies written evidence; the video supplies timestamped oral/coverage evidence only. The default deliverable contains the written findings, video evidence, coverage comparison, and count-free improvement directions; omit separate student-self-check and teacher-follow-up sections unless the user explicitly requests them. Before replying, delete or rewrite every sentence containing `job_id`, `任务号`, `已复用`, `至少`, `不少于`, `若干`, `多项`, `多个`, `多处`, `几项`, `几处`, `一系列`, `一张`, `一条`, `各补`, `各增加`, `各添加`, `必须`, `严重`, `最薄弱`, `✅`, `❌`, or `⚠️`, plus every visible path, service/model/channel name, internal field, tool command, renderer instruction, and status glyph. Never summarize listed gaps with a vague quantity phrase: introduce them with `当前结论主要受以下证据缺口影响：` and name the actual gaps. Use plain text such as `已覆盖 / 简要涉及 / 未覆盖` in tables. Do not invent a timebox, number of slides/figures/sources, or singular target; ask which evidence type or which material should be prioritized instead. An observed number may be quoted as evidence, but never turn it into a required count/threshold. Delete any unsupported external benchmark or remembered literature comparison, including `行业文献中常见...` and `已有大量文献...`; do not introduce an external dataset, method, paper, or standard unless it appears in current materials or a current-run source. Run the bundled qualitative validator; on failure rewrite once and validate once more. If it still fails, stop with a brief evidence-boundary message. On success, read the validated draft and copy it verbatim into chat with no additions. Never present the temporary draft or evidence JSON.
5. **ALWAYS write the evaluation as a visible chat reply — this is the deliverable.**
   - Fold the `course-eval` result into the 讲解答辩评价段 (see Output) and **output the full text directly in the conversation.** The teacher must see it in chat.
   - Saving a `讲解答辩评价.md` file via `write_file` + `present_files` is **optional and secondary**. **Never end your turn with only a file and no chat text** — that shows up as "执行完成但没有输出" and is a failure. If you save a file, still give the summary in chat.
   - If a step is slow, first say one line ("已读到 job_id、视频 done,正在评价…") so the user isn't left staring at a blank run.
   - Never present the raw JSON as the deliverable.

## What `course-eval` returns (and how to use each field)

- **`report_input_check` (INPUT GUARD — check this FIRST when you passed a report).** If
  `is_likely_report == false`, the uploaded "report" is NOT the course report — usually a
  previous **课程报告评价** uploaded by mistake (filenames differ by only `-课程报告评价`),
  or an unrelated/too-short doc. **STOP immediately**: tell the user per its `note`, ask them
  to upload the correct 配套课程报告, and do NOT score or export a PDF. Never confidently
  evaluate the wrong document.
- `oral_assessable_dimensions[]` — for 创新性 / 数据分析深度 / 结论合理性: `level` (强/中/弱/证据不足) + `comment` + timestamped `evidence` + **`key_frames`**. Use these as oral evidence alongside the written review. If a quantitative written score exists and the oral evidence is 弱/证据不足, note it factually as "口头证据偏少,建议答辩补充"; do not change the written score.
- **`key_frames`** (per dimension) — each has `timecode`, `why`, and a **`frame_path`**: an actual video frame that `course-eval` has already **saved as an image file** under `$ALLO_OUTPUTS_DIR/关键帧证据/`. **`course-eval` also writes a READY-TO-USE PDF section to `$ALLO_OUTPUTS_DIR/关键帧证据/gallery_block.json`** (a `{"heading":"关键帧证据","blocks":[{gallery of ALL key frames}]}` object). When the user explicitly requests a PDF, read that file and splice the whole object into `report.json` verbatim. Place it before the radar if a quantitative radar exists; otherwise it may be the final evidence section. Do NOT hand-pick a single frame and do NOT skip it.
- `report_video_consistency` (only when you passed the report) — **objective coverage, reference only**:
  - `overall`: aligned / partial / weak — describe as coverage 完整度, not a verdict.
  - `findings[]`: per report point → `oral_status` (covered / thin / absent) + evidence + note. Report these as plain facts.
  - **Ignore any `authenticity_flag` / `authenticity_note` fields** the service may still return — do **not** surface them, do **not** translate them into 代写/作弊/真实性 language. They are deprecated; this review is objective and constructive only.
- `written_only_dimensions[]` — 文献引用 / 格式规范性: explicitly "视频不评,以书面六维为准". Keep this honest boundary in the report.
- `delivery_dimensions` / `pose_delivery` — the **表达/肢体/流畅性** dimension is owned by a skeleton/pose channel. **You do NOT write this line.** When you export the PDF, pass `--job <job_id>` to `render_report_pdf.py` and the renderer injects the authoritative 表达/肢体/流畅性 (level + 骨架证据) itself. Do NOT write "证据不足/未评分/未检测到肢体" for delivery — that is stale and the renderer will strip it.
- `highlights[]` / `problems[]` — timestamped 讲解闪光点/薄弱处 (frame problems as improvement suggestions).
- `warnings[]` — surface only a user-relevant limitation that materially affects the content judgment. Do not expose channel names, counts, implementation details, or use them to judge fluency.

## Customer-facing output contract

```
## 讲解答辩评价(视频)
- 讲解结构与中心信息:按时间顺序概括,保留必要时间戳
- 支撑材料与论证:只写视频中可观察到的公式、图表、代码、对比和口头解释
- 口头可考察内容:创新性/数据分析深度/结论合理性相关的时间戳证据；默认不显示 level 或总评等级
- 报告↔讲解覆盖对照(客观参考):overall + 逐条 findings(报告要点→讲解 covered/thin/absent),缺的以“建议答辩补充说明 X”表述
- 闪光点 / 建议:各带 [mm:ss]
- 无书面报告时只加一句边界说明:书面报告维度需结合报告材料另行评价
```

Never expose or explain `job_id`, service/model names, `source`, ASR/OCR/visual counts,
processing steps, key-frame file paths, gallery JSON, renderer flags, pose/skeleton fields,
or any other runtime implementation. Do not use overall score/grade language, `优/良/中/弱`
levels, or phrases such as `致命弱点` unless the teacher explicitly asked for grading and
provided the grading rule. Improvement actions must not invent required counts, target values,
comparison baselines, parameter changes, or hypothetical percentages. Phrase unsupplied choices
as teacher/student decisions or symbolic experiments. In a video-only answer, digits may appear
only in timestamps, the observed video duration, and measurements explicitly returned by the
current video result. Do not prescribe a number of slides/examples/metrics/experiments/minutes,
and do not use circled-number or status glyphs. Do not name an external method, feature, dataset,
or source merely as a suggestion unless it appeared in the current video result or teacher materials.
Apply the same recommendation and internal-identifier hygiene to a qualitative report + video
answer. Report-observed numbers remain evidence, but `至少/不少于/各...篇/各...张/补...项`,
invented acceptance thresholds, and remembered `典型/行业/通常` benchmarks are forbidden.
After the full qualitative joint answer is drafted, scan the actual visible text literally. It must
contain zero `job_id`, `任务号`, `已复用`, `至少`, `不少于`, `若干`, `多项`, `多个`, `多处`,
`几项`, `几处`, `一系列`, `一张`, `一条`, `各补`, `各增加`, or `各添加` when prescribing
revision work. Never summarize listed evidence gaps with a vague quantity phrase; introduce the list with
`当前结论主要受以下证据缺口影响：`. Remove internal-status parentheticals;
rewrite actions without counts, such as `补充能够呈现差异的对比图表` and
`为关键技术模块补充可核验引文`. This scan happens last and overrides wording copied from the
video service or an earlier draft.

Then in the teacher's **overall** judgment, use the video as extra **objective evidence** for the orally-assessable dimensions and as a **constructive coverage reference** — e.g. "讲解充分复述了核心方法(强佐证)" or "线性插值这一步讲解中未展开,建议答辩补充". Keep it about the work and how to improve it.

## Boundaries

- Do not turn this into a delivery/表演 talent show — the value is content understanding + report coverage, not gestures/eye-contact scores.
- Keep visible wording neutral and constructive. Thin coverage → describe factually + suggest what to clarify; do not repeat personal-process labels from the request or service response.
- Do not label delivery as memorized, spontaneous, "in their own words", or proof of personal understanding. Those are not reliably established from a recording. Report only observable content, organization, support, coverage, and timestamps.
- Do not output warning signs, suspicion levels, authorship likelihoods, consistency strength as a proxy for authorship, or recommendations to "flag" a student. Coverage gaps become neutral follow-up questions only.
- The six-dimension rubric (`../incremental-evaluation/rubric.md`) governs only an explicitly requested written-report quantitative evaluation; the video is an objective evidence layer, not a seventh dimension and not a reason to force scoring.
- **若做六维量化，六维分数评的是「书面报告」，视频只是口头佐证，绝不因视频拉高分数。** 若报告某维在书面上薄弱(如某实验章节正文为空、无数据表),该维就维持书面证据对应的结果——即使视频里口头或画面演示了该实验也不例外。视频里多出来的内容写进「讲解答辩评价」和「教师追问建议」。视频与书面出现落差时,如实并列陈述,让老师自己判断。
- `AV_UNDERSTANDING_BASE_URL` overrides the service base URL if needed (default is the Allo video service). No credential is required.
