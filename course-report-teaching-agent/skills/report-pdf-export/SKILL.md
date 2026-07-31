---
name: report-pdf-export
description: Export an already-finished course-report evaluation as a tidy, print-ready PDF when the teacher explicitly asks for a downloadable, printable, archivable, or handout-ready report. It supports qualitative reviews, quantitative six-dimension reviews, draft comparisons, video-only reviews, and report-plus-video reviews. Add scorecards and a radar only when a quantitative six-dimension evaluation was actually requested and completed. Write only to /mnt/user-data/outputs/ and name the file after the report or topic title, never after student names. This skill renders existing findings; it never invents scores or re-evaluates the work.
---

# Course-Report PDF Export (评价报告导出 PDF)

## Why this exists

The agent already produces evaluations as Markdown/chat text. Teachers need a
**complete, tidy, printable PDF per report** to file, hand back, or attach. This skill
is the render-only last mile: it turns an evaluation **you have already produced** into a
professional A4 PDF. It does not score or judge — it only lays out existing findings.

## When to read this skill

- When the teacher says 导出 PDF / 生成 PDF / "pdf 吧" / 完整规整一点的报告 /
  可打印、可下载、可归档或可下发的评价报告.
- After the requested evaluation has already been completed in chat or structured data.
- Do not read or invoke this skill merely because the user asked for feedback.
- One PDF per report → one render call → named after the report title.

## How to use

1. Identify the evaluation mode and assemble a `report.json` from findings already produced:
   - `qualitative`: no `scorecard`, no `radar`.
   - `quantitative_six_dimension`: exactly six canonical scores in both `scorecard` and `radar`.
   - `incremental_qualitative`: no numeric scores or radar.
   - `incremental_quantitative`: six canonical values per compared draft; include only the chart structure supported by the completed evaluation.
   - `video_only` or `report_video_qualitative`: timestamped evidence and key frames are allowed, but no written-report scorecard or radar.
   Put real, already-established content only — never fabricate scores or findings.
2. Validate `report.json` in a separate command. Do not combine validation and rendering, do not
   use a heredoc or inline Python to create/repair the document, and do not install packages:

   ```bash
   /app/backend/.venv/bin/python -m json.tool /mnt/user-data/outputs/report.json >/dev/null
   ```

   Build or repair `report.json` only with `write_file`. Inside JSON string values, prefer Chinese
   corner quotes `「」` instead of unescaped ASCII double quotes.
3. Run the renderer with the same bundled interpreter, writing to `/mnt/user-data/outputs/` so the
   file is delivered:

   ```bash
   /app/backend/.venv/bin/python /mnt/skills/agent/report-pdf-export/scripts/render_report_pdf.py \
     --data /mnt/user-data/outputs/report.json \
     --out "/mnt/user-data/outputs/锂电池SOC-SOH联合估计报告-课程报告评价.pdf" \
     --job c672ae77-...   # ONLY for a defense-video evaluation — see below
   ```

   If the bundled interpreter reports that `reportlab` or `Pillow` is unavailable, or that no
   embeddable CJK font exists, stop and report a server dependency problem. Never run `pip install`,
   never switch to the plain `python3`, and never retry by embedding the whole report in a shell
   command.

   **When the exported evaluation includes a 讲解答辩视频, ALWAYS pass `--job <job_id>`.** With it,
   the renderer fetches the video's key frames itself and guarantees the 「关键帧证据」
   gallery even if your `report.json` didn't include one — so the frames can never be lost
   to a missed step. (If your `report.json` already has the gallery, `--job` is a harmless
   no-op.) Omit `--job` for a text-only / draft-increment evaluation with no video.

   Paths copied from `gallery_block.json` may remain under `/mnt/user-data/outputs/...`; keep them
   unchanged. The renderer safely maps that virtual prefix to the current run's real output
   directory. It exits non-zero if any declared image is missing or unreadable, and a video render
   also fails if no key-frame image exists after `--job` augmentation. Do not present a PDF after a
   failed render. A successful video render prints `images=<positive count>`.

   **Filename & location — hard rules:**
   - `--out` MUST be under `/mnt/user-data/outputs/` — never an absolute host path, the
     conversation folder, `.allo/…`, or `tmp_eval/…`.
   - Name the file `报告标题-课程报告评价.pdf`, where 报告标题 is the **uploaded report's
     title** (its filename minus the extension). **Never** use student names in the
     filename. One PDF per report; do not render the same report to two names.
4. `present_files` the resulting PDF and tell the teacher in chat what was produced.

Keep this to four deterministic tool calls (write JSON → validate JSON/evidence → render → present). Do not
re-fetch the evaluation or re-run scoring — this skill only renders.

### Markdown fallback

If you only have the evaluation as Markdown (not structured), pass it directly — the
renderer parses a practical subset (`#`/`##`/`###` headings, `-`/`*` bullets, pipe
tables, `**bold**`, paragraphs):

```bash
/app/backend/.venv/bin/python /mnt/skills/agent/report-pdf-export/scripts/render_report_pdf.py --markdown eval.md --out "/mnt/user-data/outputs/不同温度下锂离子电池SOC估计-课程报告评价.pdf"
```

Prefer `--data` (JSON) when you can — it gives the tidiest, most deterministic layout.

## report.json schema

All fields optional except at least one `section`. Example values are Chinese because the
rendered PDF is user-facing.

```json
{
  "evaluation_mode": "quantitative_six_dimension",
  "title": "课程报告评价",
  "subtitle": "六维评分 + 报告与讲解一致性核验",
  "meta": [
    {"label": "学生", "value": "李思远"},
    {"label": "课程", "value": "储能系统与电池管理"},
    {"label": "评价日期", "value": "2026-07-04"}
  ],
  "sections": [
    {
      "heading": "综合结论",
      "blocks": [
        {"type": "paragraph", "text": "数据分析扎实,格式规范突出;**结论合理性偏弱**,建议加强论证。"}
      ]
    },
    {
      "heading": "六维评分",
      "blocks": [
        {"type": "scorecard", "items": [
          {"name": "创新性", "score": 78, "max": 100, "note": "思路有新意"},
          {"name": "结论合理性", "score": 65, "max": 100, "note": "由部分工况外推,建议补充依据"}
        ]}
      ]
    },
    {
      "heading": "报告↔讲解覆盖对照",
      "blocks": [
        {"type": "table", "columns": ["书面要点", "讲解覆盖", "备注"],
         "rows": [["SOC 标定", "完整复述", "覆盖"], ["线性插值", "未展开", "建议答辩补充"]]}
      ]
    },
    {
      "heading": "六维能力雷达",
      "blocks": [
        {"type": "radar", "max": 100, "caption": "蓝色为本次六维量化结果；越靠外表示该维度的本次参考分更高。",
         "dimensions": [
           {"name": "创新性", "score": 78}, {"name": "数据分析深度", "score": 88},
           {"name": "完整性", "score": 82}, {"name": "文献引用", "score": 70},
           {"name": "结论合理性", "score": 65}, {"name": "格式规范性", "score": 90}
         ]}
      ]
    }
  ],
  "footer": "元枢 · 明学慧评 · 课程报告评价"
}
```

Block `type` values: `paragraph`, `bullets` (`items`), `table` (`columns` + `rows`),
`scorecard` (`items` with `name`/`score`/`max`/`note`), `note` (a callout box),
`radar` (`dimensions` with `name`/`score`, optional `max` (default 100), `caption`,
`benchmark`), `gallery` (`images` + optional `cols`), and `image` (single). `**bold**`
works inside paragraph/bullet/table/note/caption text.

**Include a `gallery` of the video key frames when the evaluation came from a defense
video.** The video service's `course-eval` (via the `report-presentation-review` skill)
saves each key frame as an image **file** and returns, per orally-assessable dimension, a
`key_frames` list where each item has `timecode`, `why`, and a **`frame_path`** (an absolute
path to the saved .jpg, under `/mnt/user-data/outputs/关键帧证据/`). Build a 「关键帧证据」
section with a `gallery` block so the teacher SEES the frame behind each judgment:

```json
{"heading": "关键帧证据", "blocks": [
  {"type": "gallery", "cols": 2, "images": [
    {"data": "/mnt/user-data/outputs/关键帧证据/创新性_00-00_0.jpg", "caption": "**创新性** · 00:00 · 标题页展示研究主题"},
    {"data": "/mnt/user-data/outputs/关键帧证据/数据分析深度_12-35_1.jpg", "caption": "**数据分析深度** · 12:35 · 多指标评价体系"}
  ]}
]}
```

Put each `key_frames[].frame_path` into `data` (a file path OR a base64 data-URL both work);
build each `caption` from the dimension + `timecode` + `why`. `gallery` items are
`{data, caption}`; frames that fail to load are skipped. (`image` is the single-image variant.)

**Radar contract:** include a `radar` block only for an explicitly requested quantitative
six-dimension evaluation. It must be placed at the END, after all evidence, coverage, and
key-frame sections. Use exactly the same six canonical dimensions and numeric values shown
in the `scorecard`. The radar is a crisp vector chart and must not be added to qualitative or
video-only evaluations.

`benchmark` is optional. Add it only when the teacher supplied a course target or per-dimension
standard in the current request or materials. Never invent or default a passing line.

## Honesty & tone

This skill renders; it never grades. Every score, table row and coverage note must come
from an evaluation already produced by the other skills — do not add or soften anything at
render time. Keep the report **objective and constructive**: state facts, evidence, coverage,
and improvement suggestions in neutral language. The renderer applies a final visible-language
normalization pass so deprecated personal-process labels cannot leak into the PDF.
