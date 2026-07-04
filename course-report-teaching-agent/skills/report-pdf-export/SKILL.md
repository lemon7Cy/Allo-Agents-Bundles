---
name: report-pdf-export
description: Export a finished course-report evaluation as a tidy, print-ready PDF — one file per student. Read this skill WHENEVER the teacher, after an evaluation has been produced (六维评分 / 增量评价 / 讲解答辩一致性核验), asks for a 完整规整的报告、导出 PDF、"各自一份 PDF"、"pdf 吧"、可打印/可下发的评价报告. You build a small JSON from the evaluation you already produced and run the renderer; it lays out title, student meta, sections, score tables and consistency tables into a clean A4 PDF. Chinese fonts are handled automatically (embeds an OS CJK font, falls back to a built-in one). One student per call → one PDF per student. Do NOT invent scores or findings here — only render what the evaluation already established.
version: "1.0.0"
author: allo-official
required_env: []
optional_env: []
---

# Course-Report PDF Export (评价报告导出 PDF)

## Why this exists

The agent already produces evaluations as Markdown/chat text. Teachers often need a
**complete, tidy, printable PDF per student** to file, hand back, or attach. This skill
is the render-only last mile: it turns an evaluation **you have already produced** into a
professional A4 PDF. It does not score or judge — it only lays out existing findings.

## When to read this skill

- The teacher says 导出 PDF / 生成 PDF / "pdf 吧" / 各自一份(报告)/ 完整规整一点的报告 / 可打印的评价报告.
- After a 六维评分, 初终稿增量评价 ([[incremental-evaluation]]), or 讲解答辩一致性核验
  ([[report-presentation-review]]) — when the teacher wants the result as a file.
- Multiple students → call once per student → one PDF each.

## How to use

1. Assemble a `report.json` from the evaluation you already produced (schema below).
   Put real, already-established content only — never fabricate scores or findings.
2. Run the renderer, writing to `/mnt/user-data/outputs/` so the file is delivered:

   ```bash
   python3 /mnt/skills/.../report-pdf-export/scripts/render_report_pdf.py \
     --data report.json \
     --out "/mnt/user-data/outputs/李思远-课程报告评价.pdf"
   ```

   Use the student's name in the filename so each student's PDF is distinct.
3. `present_files` the resulting PDF(s) and tell the teacher in chat what was produced.

Keep this to ~2 tool calls per student (write JSON → render). Do not re-fetch the
evaluation or re-run scoring — this skill only renders.

### Markdown fallback

If you only have the evaluation as Markdown (not structured), pass it directly — the
renderer parses a practical subset (`#`/`##`/`###` headings, `-`/`*` bullets, pipe
tables, `**bold**`, paragraphs):

```bash
python3 .../render_report_pdf.py --markdown eval.md --out "/mnt/user-data/outputs/张三-课程报告评价.pdf"
```

Prefer `--data` (JSON) when you can — it gives the tidiest, most deterministic layout.

## report.json schema

All fields optional except at least one `section`. Example values are Chinese because the
rendered PDF is user-facing.

```json
{
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
        {"type": "radar", "max": 100, "benchmark": 80, "caption": "蓝色为本次得分,灰色虚线为达标标准线;越靠外该维度越强。",
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
`scorecard` (`items` with `name`/`score`/`max`/`note`), `note` (a callout box), and
`radar` (`dimensions` with `name`/`score`, optional `max` (default 100), `caption`, and
`benchmark`). `**bold**` works inside paragraph/bullet/table/note text.

**Always include a `radar` block for a six-dimension evaluation, placed at the END**
(after the scoring table), so the report reads 综合结论 → 六维评分表 → (覆盖对照) → 能力雷达图.
This is the 能力雷达图量化评分 look. Use the same six scores you show in the `scorecard`.
The radar is drawn as a crisp vector chart (no image files); it needs at least 3 dimensions.

**Set a standard line with `benchmark`** so each dimension shows how far it reaches against
a target (like a game character's radar). `benchmark` is either one number (a uniform
达标线, e.g. `80`) or a list of per-dimension targets aligned with `dimensions`. It renders
as a gray dashed reference polygon behind the blue score polygon. Default the uniform
达标线 to the course's passing/good standard (e.g. 80) unless the teacher gives specific
per-dimension targets.

## Honesty & tone

This skill renders; it never grades. Every score, table row and coverage note must come
from an evaluation already produced by the other skills — do not add or soften anything at
render time. Keep the report **objective and constructive**: state facts and improvement
suggestions; **never** render 代写/作弊/真实性 accusations.
