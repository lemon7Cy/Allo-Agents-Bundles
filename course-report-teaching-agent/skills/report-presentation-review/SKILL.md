---
name: report-presentation-review
description: Evaluate a student's course-report presentation / defense video (讲解/答辩录像) as part of teacher evaluation. Submit the local MP4 to the Allo video-understanding service, get ASR/OCR/timeline/summary evidence, then run the course-report evaluation — which maps the video to the orally-assessable 六维 and, given the written report, runs a report↔oral consistency check that surfaces suspected ghostwriting / shallow understanding. Read this skill when the teacher provides a report presentation/defense video (a .mp4 alongside the written report). Never fabricate; every claim carries a timestamp; delivery dimensions stay N/A when evidence is thin.
version: "1.0.0"
author: allo-official
required_env: []
optional_env:
  - AV_UNDERSTANDING_BASE_URL
---

# Course-Report Presentation / Defense Review (讲解答辩视频评价)

## Why this exists (the point in the 明学慧评 context)

The teacher already evaluates the **written report** (六维 rubric + citation check + 初稿→终稿 increment + AI baseline). The presentation/defense video adds the **strongest anti-AI signal**: a report can be AI-ghostwritten, but a student cannot fake explaining it live.

So this skill's job is **not** a standalone "video score". It produces a **讲解答辩评价 + 真实性核验层** that plugs into the teacher's overall assessment:
- **报告↔讲解一致性核验** (the killer): does the oral defense cover / contradict / run much thinner than the written report → 疑似代写 / 理解不足 signal, complementing the AI-baseline comparison.
- **口头佐证六维**: the video corroborates or challenges the *orally-assessable* dimensions (创新性 / 数据分析深度 / 结论合理性). 文献引用 / 格式规范性 are written-only — the video does not judge them.
- **诚实**: 表达/语速/肢体等表现维度证据不足就标 N/A,不瞎打分;每条结论带时间戳。

## Hard rules (same discipline as the general av skill)

- **Remote service only, no local fallback.** This is a thin client for the Allo video service. Never run local ffmpeg/whisper/OCR to substitute a result. Before anything, health-check:
  ```bash
  bash scripts/media_understanding.sh health
  ```
  If it does not return `status:ok` (exit `6`), STOP and tell the user the service is unavailable — do not fabricate a transcript/score.
- **Async job API.** Upload only creates a `job_id`; poll `GET /api/jobs/{id}` until `done`/`failed`, then fetch results. Never re-upload on a foreground/600s timeout — resume with the same `job_id`.
- **Large files.** Course-report videos are typically 100 MB–5 GB / 10–30 min. Upload takes time; the job runs async. If a tool call is killed at ~600s while the job is still processing, **check the job and keep waiting with the same job_id** — never re-upload.
- **Evidence-grounded, no hallucination.** Every highlight / problem / consistency finding must tie to a returned timestamp + evidence type (`asr`/`ocr`/`visual`/`summary`). If you can't back a claim with returned evidence, drop it.

## Workflow (course-report defense)

1. **Health check** (above). Stop on failure.
2. **Submit the video and wait** (auto soft-budget, polls until done while healthy):
   ```bash
   bash scripts/media_understanding.sh analyze /absolute/path/to/讲解视频.mp4 auto
   ```
   Capture `job_id`. On a foreground timeout, resume: `bash scripts/media_understanding.sh wait JOB_ID forever 5`.
3. **Run the course-report evaluation, passing the written report** (this is what enables the consistency check). Write the report body (the same text you evaluate in the six-dimension rubric) to a temp file, then:
   ```bash
   bash scripts/media_understanding.sh course-eval JOB_ID /absolute/path/to/report.txt
   ```
   (Omit the file to skip consistency and only get the video-side evaluation.)
4. **Integrate, don't dump.** Fold the result into the teacher's overall evaluation alongside the written 六维 / 增量 / AI 基线 — see Output below. Never present the raw JSON as the deliverable.

## What `course-eval` returns (and how to use each field)

- `oral_assessable_dimensions[]` — for 创新性 / 数据分析深度 / 结论合理性: `level` (强/中/弱/证据不足) + `comment` + timestamped `evidence`. **Use these to corroborate or challenge the written six-dimension scores**, not to replace them. If the report scores a dimension high but the oral level is 弱/证据不足, flag the gap.
- `report_video_consistency` (only when you passed the report) — **the core**:
  - `overall`: aligned / partial / weak
  - `authenticity_flag`: none / suspect_thin (讲解远薄于书面) / suspect_contradiction (讲解与书面矛盾)
  - `findings[]`: per report point → `oral_status` (covered / thin / contradicted / absent) + evidence + note
  - `authenticity_note`: always framed as **推测**, never a verdict. Combine with the AI-baseline signal; do not accuse — say "疑似代写/理解不足,建议答辩追问确认".
- `written_only_dimensions[]` — 文献引用 / 格式规范性: explicitly "视频不评,以书面六维为准". Keep this honest boundary in the report.
- `delivery_dimensions` — always `evidence_limited`; give only a cautious qualitative note, **no numeric delivery score**.
- `highlights[]` / `problems[]` — timestamped讲解闪光点/薄弱处.
- `warnings[]` — ASR/OCR quality caveats; surface them (don't score fluency down just because ASR looks broken).

## Output (讲解答辩评价段 — fold into the teacher's evaluation)

```
## 讲解答辩评价(视频)
- 处理概览:job_id、时长、证据通道(ASR/OCR/画面/摘要计数)
- 口头可考察维度:创新性/数据分析深度/结论合理性 —— 各 level + 时间戳证据 + 与书面分是否一致
- 报告↔讲解一致性核验:overall + 逐条 findings(报告要点→讲解 covered/thin/contradicted/absent)
- 真实性提示(推测):authenticity_flag + 一句“建议答辩追问 X 确认是否本人理解”
- 闪光点 / 问题点:各带 [mm:ss]
- 口径:表达/肢体维度证据有限未评分;文献引用/格式规范性为书面维度,视频不评
```

Then in the teacher's **overall** judgment, use the video as a third real-water-level signal beside 初稿→终稿 increment and the AI baseline: 书面强但讲不出 → 真实水平存疑;书面与讲解一致且能答 → 真实掌握。

## Boundaries

- Do not turn this into a delivery/表演 talent show — the value is content understanding + report consistency, not gestures/eye-contact scores.
- The six-dimension rubric (`../incremental-evaluation/rubric.md`) stays the frozen benchmark; the video is a corroboration + authenticity layer, not a 7th dimension.
- `AV_UNDERSTANDING_BASE_URL` overrides the service base URL if needed (default is the Allo video service). No credential is required.
