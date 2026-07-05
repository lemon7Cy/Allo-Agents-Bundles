---
name: report-presentation-review
description: Evaluate a student's course-report presentation / defense video (讲解/答辩录像) as an OBJECTIVE oral corroboration of the six-dimension evaluation, and compare it against the written report as a factual coverage check. Read this skill WHENEVER the teacher gives a report讲解/答辩录像 — either as a local .mp4 to submit, OR as an already-processed video job_id — and asks to 评价讲解/答辩、看讲解讲得怎么样、讲解和书面报告对不对得上/覆盖了哪些要点. It maps the video to the orally-assessable 六维 (创新性/数据分析深度/结论合理性) and, given the written report, reports which written points the oral explanation covered / ran thin on / did not mention — as plain facts. Stay objective and constructive; never accuse or infer 代写/作弊/真实性; every claim carries a timestamp; delivery dimensions stay N/A when evidence is thin.
version: "2.0.0"
author: allo-official
required_env: []
optional_env: []
---

# Course-Report Presentation / Defense Review (讲解答辩视频评价)

## Why this exists (the point in the 明学慧评 context)

明学慧评 evaluates the **written report** across the frozen 六维 (创新性/数据分析深度/完整性/文献引用/结论合理性/格式规范性) plus the 初稿→终稿 increment. The presentation/defense video adds an **objective oral corroboration**: it shows how the student explained the work out loud, which helps the teacher judge the *orally-assessable* dimensions with more evidence.

This skill's job is a **讲解答辩评价 + 客观覆盖对照** that folds into the overall evaluation — stated positively and factually:
- **口头佐证六维**: the video corroborates the *orally-assessable* dimensions (创新性 / 数据分析深度 / 结论合理性) with timestamped evidence. 文献引用 / 格式规范性 are written-only — the video does not judge them.
- **报告↔讲解覆盖对照** (objective, reference only): for each key report point, did the oral explanation **cover it / touch it briefly / not mention it** — reported as plain facts for the teacher, **not** as a judgment about the student. Frame gaps constructively (e.g. "建议在答辩中补充说明 X"), never as 代写/作弊/真实性存疑.
- **诚实**: 表达/肢体/流畅性维度现由骨架/姿态通道(`pose_delivery`)量化评估——有骨架数据就给 level+证据(手势活动度/静止占比),真无数据才标 N/A;不瞎打分,每条结论带时间戳。

> Tone rule: this is a **constructive, objective** review. Do **not** produce anti-cheating / ghostwriting / authenticity language. If the oral explanation is thinner than the report, describe it factually and suggest what to clarify — do not speculate about who wrote the report.

## Hard rules (same discipline as the general av skill)

- **Remote service only, no local fallback.** This is a thin client for the Allo video service. Never run local ffmpeg/whisper/OCR to substitute a result. Before anything, health-check:
  ```bash
  bash scripts/media_understanding.sh health
  ```
  If it does not return `status:ok` (exit `6`), STOP and tell the user the service is unavailable — do not fabricate a transcript/score.
- **Async job API.** Upload only creates a `job_id`; poll `GET /api/jobs/{id}` until `done`/`failed`, then fetch results. Never re-upload on a foreground/600s timeout — resume with the same `job_id`.
- **Large files.** Course-report videos are typically 100 MB–5 GB / 10–30 min. Upload takes time; the job runs async. If a tool call is killed at ~600s while the job is still processing, **check the job and keep waiting with the same job_id** — never re-upload.
- **Evidence-grounded, no hallucination.** Every highlight / problem / coverage finding must tie to a returned timestamp + evidence type (`asr`/`ocr`/`visual`/`summary`). If you can't back a claim with returned evidence, drop it.

## Workflow (course-report defense) — keep it to ~2-3 tool calls, then ANSWER IN CHAT

> ⚠️ **Do NOT over-run tools.** `course-eval` already fetches and grounds on the
> timeline + summary + presentation-evaluation **server-side** and returns the
> whole structured result in ONE call. **Never separately call `timeline`,
> `summary`, or `presentation` for this workflow** — the raw `timeline` is huge,
> gets truncated, and a long tool chain makes the run stall with no answer. One
> `health` + (reuse job_id) + one `course-eval` is the entire data step.

1. **Health check** once. Stop on failure.
2. **Get a `job_id` — reuse before re-uploading.**
   - **If the teacher already gives you a `job_id`**, **do NOT upload anything** — the result is cached. Go straight to step 3. (One optional sanity check: `bash scripts/media_understanding.sh job JOB_ID`.)
   - **Only if there is no `job_id`**, submit the local file and wait:
     ```bash
     bash scripts/media_understanding.sh analyze /absolute/path/to/讲解视频.mp4 auto
     ```
     On a foreground timeout, resume: `bash scripts/media_understanding.sh wait JOB_ID forever 5`.
3. **Run course-eval ONCE, passing the written report** — this is the whole data call:
   ```bash
   bash scripts/media_understanding.sh course-eval JOB_ID /absolute/path/to/report.txt
   ```
   (Omit the file to skip the coverage comparison and only get the video-side evaluation.)
4. **ALWAYS write the evaluation as a visible chat reply — this is the deliverable.**
   - Fold the `course-eval` result into the 讲解答辩评价段 (see Output) and **output the full text directly in the conversation.** The teacher must see it in chat.
   - Saving a `讲解答辩评价.md` file via `write_file` + `present_files` is **optional and secondary**. **Never end your turn with only a file and no chat text** — that shows up as "执行完成但没有输出" and is a failure. If you save a file, still give the summary in chat.
   - If a step is slow, first say one line ("已读到 job_id、视频 done,正在评价…") so the user isn't left staring at a blank run.
   - Never present the raw JSON as the deliverable.

## What `course-eval` returns (and how to use each field)

- `oral_assessable_dimensions[]` — for 创新性 / 数据分析深度 / 结论合理性: `level` (强/中/弱/证据不足) + `comment` + timestamped `evidence` + **`key_frames`**. **Use these to corroborate the written six-dimension scores** with oral evidence. If the report scores a dimension high but the oral level is 弱/证据不足, note it factually as "口头证据偏少,建议答辩补充".
- **`key_frames`** (per dimension) — each has `timecode`, `why`, and a **`frame_path`**: an actual video frame that `course-eval` has already **saved as an image file** under `$ALLO_OUTPUTS_DIR/关键帧证据/`. **`course-eval` also writes a READY-TO-USE PDF section to `$ALLO_OUTPUTS_DIR/关键帧证据/gallery_block.json`** (a `{"heading":"关键帧证据","blocks":[{gallery of ALL key frames}]}` object). **When you export the PDF, read that file and splice the whole object into your `report.json` `sections` verbatim (place it right before the radar).** Do NOT hand-pick a single frame and do NOT skip it — the 关键帧证据 section with EVERY returned frame is a required part of a video-based evaluation PDF. (`_gallery_block_path` in the course-eval output points at it.)
- `report_video_consistency` (only when you passed the report) — **objective coverage, reference only**:
  - `overall`: aligned / partial / weak — describe as coverage 完整度, not a verdict.
  - `findings[]`: per report point → `oral_status` (covered / thin / absent) + evidence + note. Report these as plain facts.
  - ⚠️ **Ignore any `authenticity_flag` / `authenticity_note` fields** the service may still return — do **not** surface them, do **not** translate them into 代写/作弊/真实性 language. They are deprecated; this review is objective and constructive only.
- `written_only_dimensions[]` — 文献引用 / 格式规范性: explicitly "视频不评,以书面六维为准". Keep this honest boundary in the report.
- `delivery_dimensions` — when `status == "pose_estimated"`, the **表达/肢体/流畅性** dimension IS assessed by a **skeleton/pose channel (yolov8-pose)**: use its `level` (强/中/弱) and `note`/`metrics` (骨架锁定主讲人后的手势活动度、躯干移动量、抬手占比、静止占比) as REAL quantified evidence — do NOT call it "证据不足". `pose_delivery` holds the raw metrics. Only when there is no pose data (status `evidence_limited`) fall back to a cautious "证据有限未评分".
- `highlights[]` / `problems[]` — timestamped 讲解闪光点/薄弱处 (frame problems as improvement suggestions).
- `warnings[]` — ASR/OCR quality caveats; surface them (don't score fluency down just because ASR looks broken).

## Output (讲解答辩评价段 — fold into the teacher's evaluation)

```
## 讲解答辩评价(视频)
- 处理概览:job_id、时长、证据通道(ASR/OCR/画面/摘要计数)
- 口头可考察维度:创新性/数据分析深度/结论合理性 —— 各 level + 时间戳证据 + 与书面分是否一致
- 报告↔讲解覆盖对照(客观参考):overall + 逐条 findings(报告要点→讲解 covered/thin/absent),缺的以“建议答辩补充说明 X”表述
- 闪光点 / 建议:各带 [mm:ss]
- **表达/肢体/流畅性**:有 `pose_delivery`(骨架通道)时给 level(强/中/弱)+ 骨架证据(如「82% 时间近静止、手势极少 → 弱」),**不再标 N/A**;仅当无 pose 数据才「证据有限未评分」。文献引用/格式规范性为书面维度,视频不评
```

Then in the teacher's **overall** judgment, use the video as extra **objective evidence** for the orally-assessable dimensions and as a **constructive coverage reference** — e.g. "讲解充分复述了核心方法(强佐证)" or "线性插值这一步讲解中未展开,建议答辩补充". Keep it about the work and how to improve it.

## Boundaries

- Do not turn this into a delivery/表演 talent show — the value is content understanding + report coverage, not gestures/eye-contact scores.
- **Never** produce 代写/作弊/真实性/ghostwriting language or accuse the student. Thin coverage → describe factually + suggest what to clarify.
- The six-dimension rubric (`../incremental-evaluation/rubric.md`) stays the frozen benchmark; the video is an objective corroboration layer, not a 7th dimension.
- `AV_UNDERSTANDING_BASE_URL` overrides the service base URL if needed (default is the Allo video service). No credential is required.
