#!/usr/bin/env python3
"""Render one student's course-report evaluation into a tidy, print-ready PDF.

Pure-Python (reportlab) so it runs inside the Allo desktop sandbox with no native
deps. Chinese is handled by EMBEDDING an OS CJK font (subsetted, so the PDF stays
small and every viewer shows identical glyphs); if none is found it falls back to
reportlab's built-in STSong-Light CID font plus symbol sanitising.

Two input shapes:
  --data report.json     structured report (preferred — deterministic, tidy layout)
  --markdown report.md   a pragmatic Markdown subset (headings / bullets / tables /
                         **bold** / paragraphs) for when you only have Markdown.

Usage:
  python3 render_report_pdf.py --data report.json --out /mnt/user-data/outputs/张三-课程报告评价.pdf
  python3 render_report_pdf.py --markdown report.md --out out.pdf --title "课程报告评价"

report.json schema (all fields optional except at least one section):
  {
    "title": "课程报告评价",
    "subtitle": "报告与讲解一致性核验",
    "meta": [{"label": "学生", "value": "张三"}, {"label": "日期", "value": "2026-07-04"}],
    "sections": [
      {"heading": "综合结论", "blocks": [
        {"type": "paragraph", "text": "..."},
        {"type": "bullets", "items": ["...", "..."]},
        {"type": "table", "columns": ["维度", "得分", "说明"], "rows": [["创新性", "82", "..."]]},
        {"type": "scorecard", "items": [{"name": "创新性", "score": 82, "max": 100, "note": "..."}]},
        {"type": "note", "text": "提示框里的一段话"}
      ]}
    ],
    "footer": "元枢 · 课程报告评价"
  }
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as RLImage
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Minimal ink palette so the report reads as tidy, not decorated.
INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#6b7280")
ACCENT = colors.HexColor("#2563eb")
RULE = colors.HexColor("#d7dbe0")
HEAD_BG = colors.HexColor("#eef2f7")
NOTE_BG = colors.HexColor("#f4f7fb")

# OS CJK font candidates, deploy target (Windows) first. subfontIndex picks a face
# inside a .ttc collection. (regular_path, subfont, bold_path, bold_subfont)
_CJK_CANDIDATES = [
    ("C:/Windows/Fonts/msyh.ttc", 0, "C:/Windows/Fonts/msyhbd.ttc", 0),
    ("C:/Windows/Fonts/msyh.ttf", 0, "C:/Windows/Fonts/msyhbd.ttf", 0),
    ("C:/Windows/Fonts/simsun.ttc", 0, "C:/Windows/Fonts/simhei.ttf", 0),
    ("C:/Windows/Fonts/simhei.ttf", 0, "C:/Windows/Fonts/simhei.ttf", 0),
    ("/System/Library/Fonts/Supplemental/Songti.ttc", 0, "/System/Library/Fonts/Supplemental/Songti.ttc", 1),
    ("/System/Library/Fonts/PingFang.ttc", 0, "/System/Library/Fonts/PingFang.ttc", 0),
    ("/System/Library/Fonts/STHeiti Medium.ttc", 0, "/System/Library/Fonts/STHeiti Medium.ttc", 0),
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0, "/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0, "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
    ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0, "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0),
]

# Glyphs that even good CJK fonts sometimes lack → normalise to safe equivalents so
# a report never shows a blank box or a wrong glyph.
_SYMBOL_FIXES = {
    "↔": "–",  # ↔ -> – (en dash)
    "⇄": "–",  # ⇄
    "✓": "√",  # ✓ -> √ (widely present)
    "✔": "√",  # ✔
    "✗": "x",       # ✗
    "✘": "x",       # ✘
}


def _register_fonts() -> tuple[str, str]:
    """Register a CJK font family and return (regular_name, bold_name).

    Prefers embedding an OS font (correct glyphs, subsetted, small); falls back to
    the built-in STSong-Light CID font (no file, relies on the viewer's CJK font).
    """
    for reg_path, reg_idx, bold_path, bold_idx in _CJK_CANDIDATES:
        if not os.path.exists(reg_path):
            continue
        try:
            pdfmetrics.registerFont(TTFont("ReportCJK", reg_path, subfontIndex=reg_idx))
        except Exception:
            continue
        bold_name = "ReportCJK"
        if os.path.exists(bold_path):
            try:
                pdfmetrics.registerFont(TTFont("ReportCJK-Bold", bold_path, subfontIndex=bold_idx))
                bold_name = "ReportCJK-Bold"
            except Exception:
                bold_name = "ReportCJK"
        pdfmetrics.registerFontFamily("ReportCJK", normal="ReportCJK", bold=bold_name, italic="ReportCJK", boldItalic=bold_name)
        return "ReportCJK", bold_name

    # Fallback: built-in CID font (Simplified Chinese). No bold face available.
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    pdfmetrics.registerFontFamily("STSong-Light", normal="STSong-Light", bold="STSong-Light", italic="STSong-Light", boldItalic="STSong-Light")
    return "STSong-Light", "STSong-Light"


def _clean(text: object) -> str:
    s = "" if text is None else str(text)
    for bad, good in _SYMBOL_FIXES.items():
        if bad in s:
            s = s.replace(bad, good)
    return s


def _markup(text: object) -> str:
    """Escape XML then re-enable **bold** for reportlab Paragraph mini-markup."""
    s = _clean(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    parts = s.split("**")
    if len(parts) >= 3:
        out = []
        for i, part in enumerate(parts):
            out.append(f"<b>{part}</b>" if i % 2 == 1 else part)
        s = "".join(out)
    return s


def _styles(regular: str, bold: str) -> dict[str, ParagraphStyle]:
    base = dict(fontName=regular, textColor=INK, alignment=TA_LEFT)
    return {
        "title": ParagraphStyle("title", fontName=bold, fontSize=20, leading=26, textColor=INK, spaceAfter=2),
        "subtitle": ParagraphStyle("subtitle", fontName=regular, fontSize=11, leading=16, textColor=MUTED, spaceAfter=6),
        "heading": ParagraphStyle("heading", fontName=bold, fontSize=13.5, leading=20, textColor=INK, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("body", fontSize=10.5, leading=17, spaceAfter=5, **base),
        "bullet": ParagraphStyle("bullet", fontSize=10.5, leading=16, leftIndent=12, bulletIndent=2, spaceAfter=2, **base),
        "note": ParagraphStyle("note", fontSize=10, leading=16, textColor=colors.HexColor("#334155"), fontName=regular),
        "cell": ParagraphStyle("cell", fontSize=9.5, leading=14, fontName=regular, textColor=INK),
        "cellhead": ParagraphStyle("cellhead", fontSize=9.5, leading=14, fontName=bold, textColor=INK),
        "meta": ParagraphStyle("meta", fontSize=10, leading=15, fontName=regular, textColor=colors.HexColor("#374151")),
        "caption": ParagraphStyle("caption", fontSize=9, leading=13, fontName=regular, textColor=MUTED, alignment=1, spaceAfter=4),
        "_font": regular,
    }


def _table(columns: list, rows: list, st: dict, avail_width: float) -> Table:
    header = [Paragraph(_markup(c), st["cellhead"]) for c in columns]
    body = [[Paragraph(_markup(c), st["cell"]) for c in row] for row in rows]
    ncols = max(1, len(columns))
    table = Table([header, *body], colWidths=[avail_width / ncols] * ncols, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
                ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor("#edf0f3")),
                ("BOX", (0, 0), (-1, -1), 0.6, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _scorecard(items: list, st: dict, avail_width: float) -> Table:
    columns = ["维度", "得分", "说明"]
    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        score = it.get("score")
        mx = it.get("max", 100)
        score_txt = "—" if score is None else (f"{score} / {mx}" if mx else str(score))
        rows.append([it.get("name", ""), score_txt, it.get("note", "")])
    return _table(columns, rows, st, avail_width)


def _note_box(text: str, st: dict, avail_width: float) -> Table:
    box = Table([[Paragraph(_markup(text), st["note"])]], colWidths=[avail_width], hAlign="LEFT")
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NOTE_BG),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#c7d7ee")),
                ("LINEBEFORE", (0, 0), (0, -1), 2.5, ACCENT),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return box


def _radar_dims(block: dict) -> tuple[list[str], list[float]]:
    """Pull (names, scores) from a radar block. Accepts `dimensions` or `items`,
    each an entry with `name` + `score` (aligned with the scorecard shape)."""
    entries = block.get("dimensions") or block.get("items") or []
    names: list[str] = []
    scores: list[float] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            scores.append(float(entry.get("score")))
        except (TypeError, ValueError):
            continue
        names.append(_clean(entry.get("name", "")))
    return names, scores


def _radar_benchmark_values(benchmark: object, n: int) -> list[float] | None:
    """Normalise a radar `benchmark` (one number → uniform 达标线, or a per-axis list)
    into n values, or None when absent/invalid."""
    if benchmark is None:
        return None
    if isinstance(benchmark, bool):
        return None
    if isinstance(benchmark, (int, float)):
        return [float(benchmark)] * n
    if isinstance(benchmark, (list, tuple)):
        values: list[float] = []
        for i in range(n):
            try:
                values.append(float(benchmark[i]))
            except (TypeError, ValueError, IndexError):
                return None
        return values
    return None


def _radar_drawing(names: list[str], scores: list[float], maxv: float, font: str, benchmark: object = None, size: float = 360.0) -> Drawing:
    """Hand-drawn six-axis (or n-axis) radar: grid rings + spokes + optional gray
    dashed benchmark (标准线) + blue score polygon + CJK labels/values. Pure reportlab
    vector — no matplotlib, no raster image."""
    n = len(names)
    d = Drawing(size, size)
    cx = cy = size / 2.0
    radius = size * 0.30
    maxv = maxv if maxv and maxv > 0 else 100.0

    def ang(i: int) -> float:  # start at top (12 o'clock), go clockwise
        return math.pi / 2 - i * 2 * math.pi / n

    grid = colors.HexColor("#d7dbe0")
    for frac in (0.25, 0.5, 0.75, 1.0):
        ring: list[float] = []
        for i in range(n):
            ring += [cx + radius * frac * math.cos(ang(i)), cy + radius * frac * math.sin(ang(i))]
        d.add(Polygon(ring, strokeColor=grid, strokeWidth=0.5, fillColor=None))
    for i in range(n):
        d.add(Line(cx, cy, cx + radius * math.cos(ang(i)), cy + radius * math.sin(ang(i)), strokeColor=grid, strokeWidth=0.5))

    # Standard/达标线 (drawn behind the score polygon): gray dashed reference.
    bench_values = _radar_benchmark_values(benchmark, n)
    if bench_values is not None:
        bpoly: list[float] = []
        for i, bval in enumerate(bench_values):
            rr = radius * max(0.0, min(1.0, bval / maxv))
            bpoly += [cx + rr * math.cos(ang(i)), cy + rr * math.sin(ang(i))]
        d.add(Polygon(bpoly, strokeColor=colors.HexColor("#9aa4b2"), strokeWidth=1.0, fillColor=None, strokeDashArray=[3, 2]))

    poly: list[float] = []
    for i, score in enumerate(scores):
        rr = radius * max(0.0, min(1.0, score / maxv))
        poly += [cx + rr * math.cos(ang(i)), cy + rr * math.sin(ang(i))]
    d.add(Polygon(poly, strokeColor=ACCENT, strokeWidth=1.5, fillColor=colors.Color(0.145, 0.388, 0.922, alpha=0.22)))
    for i in range(0, len(poly), 2):
        d.add(Circle(poly[i], poly[i + 1], 2.2, fillColor=ACCENT, strokeColor=None))

    for i, (name, score) in enumerate(zip(names, scores)):
        lx = cx + (radius + 18) * math.cos(ang(i))
        ly = cy + (radius + 18) * math.sin(ang(i))
        cos = math.cos(ang(i))
        anchor = "middle" if abs(cos) < 0.3 else ("start" if cos > 0 else "end")
        d.add(String(lx, ly - 3, name, fontName=font, fontSize=10, fillColor=INK, textAnchor=anchor))
        d.add(String(lx, ly - 14, _clean(int(score) if float(score).is_integer() else score), fontName=font, fontSize=8.5, fillColor=ACCENT, textAnchor=anchor))
    return d


def _decode_image(data: str):
    """Turn a base64 string or `data:image/...;base64,...` URL into a BytesIO."""
    import base64
    import io

    raw = (data or "").strip()
    if raw.startswith("data:"):
        raw = raw.split(",", 1)[-1]
    try:
        return io.BytesIO(base64.b64decode(raw))
    except Exception:
        return None


def _image_flowable(data: str, max_w: float, max_h: float):
    """A reportlab Image scaled to fit within (max_w, max_h), preserving aspect.
    `data` may be a file path, a base64 data-URL, or raw base64."""
    import os as _os

    raw = (data or "").strip()
    if not raw:
        return None
    # A local file path (the key-frame images saved by course-eval) takes priority.
    src = raw if (not raw.startswith("data:") and _os.path.exists(raw)) else _decode_image(raw)
    if src is None:
        return None
    try:
        from reportlab.lib.utils import ImageReader

        iw, ih = ImageReader(src).getSize()
        if hasattr(src, "seek"):
            src.seek(0)
        if iw <= 0 or ih <= 0:
            return None
        scale = min(max_w / iw, max_h / ih)
        return RLImage(src, width=iw * scale, height=ih * scale)
    except Exception:
        return None


def _gallery(images: list, st: dict, avail_width: float, cols: int = 2) -> list:
    """A grid of key-frame thumbnails, each with a caption. `images` items are
    {data|thumbnail, caption}. Skips any that fail to decode."""
    cols = max(1, min(int(cols or 2), 3))
    cell_w = avail_width / cols
    cells: list = []
    for item in images:
        if not isinstance(item, dict):
            continue
        img = _image_flowable(item.get("data") or item.get("thumbnail") or "", cell_w - 12, 150)
        if img is None:
            continue
        img.hAlign = "CENTER"
        caption = Paragraph(_markup(item.get("caption", "")), st["caption"]) if item.get("caption") else Spacer(1, 0)
        cells.append((img, caption))
    if not cells:
        return []
    rows = [cells[i : i + cols] for i in range(0, len(cells), cols)]
    for row in rows:
        while len(row) < cols:
            row.append(None)

    def _cell(entry):
        # Each grid cell is a 1-col, 2-row table so the image sits above its caption.
        if entry is None:
            return ""
        img, caption = entry
        return Table([[img], [caption]], colWidths=[cell_w - 8])

    grid = [[_cell(entry) for entry in row] for row in rows]
    table = Table(grid, colWidths=[cell_w] * cols, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return [table, Spacer(1, 4)]


def _render_block(block: dict, st: dict, avail_width: float) -> list:
    btype = block.get("type", "paragraph")
    if btype == "gallery":
        return _gallery(block.get("images", []), st, avail_width, block.get("cols", 2))
    if btype == "image":
        img = _image_flowable(block.get("data") or block.get("thumbnail") or "", avail_width * 0.6, 220)
        if img is None:
            return []
        img.hAlign = "CENTER"
        out: list = [img]
        if block.get("caption"):
            out.append(Paragraph(_markup(block["caption"]), st["caption"]))
        out.append(Spacer(1, 6))
        return out
    if btype == "paragraph":
        return [Paragraph(_markup(block.get("text", "")), st["body"])]
    if btype == "bullets":
        return [Paragraph(_markup(item), st["bullet"], bulletText="•") for item in block.get("items", [])]
    if btype == "table":
        return [_table(block.get("columns", []), block.get("rows", []), st, avail_width), Spacer(1, 5)]
    if btype == "scorecard":
        return [_scorecard(block.get("items", []), st, avail_width), Spacer(1, 5)]
    if btype == "note":
        return [_note_box(block.get("text", ""), st, avail_width), Spacer(1, 5)]
    if btype == "radar":
        names, scores = _radar_dims(block)
        if len(names) < 3:  # a radar needs at least 3 axes to be meaningful
            return []
        try:
            maxv = float(block.get("max", 100))
        except (TypeError, ValueError):
            maxv = 100.0
        drawing = _radar_drawing(names, scores, maxv, st["_font"], benchmark=block.get("benchmark"))
        drawing.hAlign = "CENTER"
        out: list = [drawing]
        if block.get("caption"):
            out.append(Paragraph(_markup(block["caption"]), st["caption"]))
        out.append(Spacer(1, 6))
        return out
    # Unknown block: degrade to a paragraph of whatever text it carries.
    return [Paragraph(_markup(block.get("text", "")), st["body"])]


def _build_story(data: dict, st: dict, avail_width: float) -> list:
    story: list = []
    title = _clean(data.get("title") or "课程报告评价")
    story.append(Paragraph(_markup(title), st["title"]))
    if data.get("subtitle"):
        story.append(Paragraph(_markup(data["subtitle"]), st["subtitle"]))
    story.append(Spacer(1, 2))
    story.append(_accent_rule(avail_width))

    meta = [m for m in data.get("meta", []) if isinstance(m, dict) and (m.get("value") not in (None, ""))]
    if meta:
        rows = [[Paragraph(f"<b>{_markup(m.get('label', ''))}</b>", st["meta"]), Paragraph(_markup(m.get("value", "")), st["meta"])] for m in meta]
        meta_table = Table(rows, colWidths=[28 * mm, avail_width - 28 * mm], hAlign="LEFT")
        meta_table.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1), ("LEFTPADDING", (0, 0), (0, -1), 0)]))
        story.append(Spacer(1, 6))
        story.append(meta_table)

    for section in data.get("sections", []):
        if not isinstance(section, dict):
            continue
        head = [Paragraph(_markup(section.get("heading", "")), st["heading"])] if section.get("heading") else []
        blocks: list = []
        for block in section.get("blocks", []):
            if isinstance(block, dict):
                blocks.extend(_render_block(block, st, avail_width))
        # Keep a heading with the start of its section so it never dangles alone.
        story.append(KeepTogether(head + blocks[:1]) if head else (blocks[0] if blocks else Spacer(1, 0)))
        story.extend(blocks[1:])
    return story


def _accent_rule(width: float) -> Table:
    rule = Table([[""]], colWidths=[width], rowHeights=[2])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), ACCENT), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return rule


# ------------------------------------------------------------------ markdown fallback


def _markdown_to_data(md: str, title: str | None) -> dict:
    """Pragmatic Markdown subset -> report data. Handles #/##/### headings, - / *
    bullets, pipe tables, and paragraphs. Not a full CommonMark parser."""
    lines = md.replace("\r\n", "\n").split("\n")
    doc_title = title
    sections: list = []
    current = {"heading": "", "blocks": []}
    para: list[str] = []
    bullets: list[str] = []
    table_rows: list[list[str]] = []

    def flush_para():
        nonlocal para
        if para:
            current["blocks"].append({"type": "paragraph", "text": " ".join(para).strip()})
            para = []

    def flush_bullets():
        nonlocal bullets
        if bullets:
            current["blocks"].append({"type": "bullets", "items": bullets})
            bullets = []

    def flush_table():
        nonlocal table_rows
        rows = [r for r in table_rows if not all(set(c.strip()) <= {"-", ":", " "} for c in r)]
        if rows:
            current["blocks"].append({"type": "table", "columns": rows[0], "rows": rows[1:]})
        table_rows = []

    def flush_all():
        flush_para()
        flush_bullets()
        flush_table()

    def push_section():
        if current["heading"] or current["blocks"]:
            sections.append({"heading": current["heading"], "blocks": current["blocks"]})

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_para()
            flush_bullets()
            table_rows.append([c.strip() for c in stripped.strip("|").split("|")])
            continue
        else:
            flush_table()
        if stripped.startswith("# "):
            flush_all()
            if doc_title is None:
                doc_title = stripped[2:].strip()
            else:
                push_section()
                current = {"heading": stripped[2:].strip(), "blocks": []}
            continue
        if stripped.startswith("## ") or stripped.startswith("### "):
            flush_all()
            push_section()
            current = {"heading": stripped.lstrip("#").strip(), "blocks": []}
            continue
        if stripped.startswith(("- ", "* ")):
            flush_para()
            bullets.append(stripped[2:].strip())
            continue
        if not stripped:
            flush_para()
            flush_bullets()
            continue
        flush_bullets()
        para.append(stripped)

    flush_all()
    push_section()
    return {"title": doc_title or "课程报告评价", "sections": sections}


def _fetch_course_eval(job_id: str):
    """Fetch the (cached, no-report) course-eval for a video job. Returns the dict or None."""
    import json as _json
    import urllib.request

    base = os.environ.get("AV_UNDERSTANDING_BASE_URL", "http://221.0.79.252:8090").rstrip("/")
    try:
        req = urllib.request.Request(
            f"{base}/api/jobs/{job_id}/course-report-evaluation",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            return _json.load(resp)
    except Exception:
        return None


def _gallery_from_eval(ev: dict, out_dir: str):
    """Build a ready 「关键帧证据」 gallery section from a course-eval dict (saving base64
    thumbnails to files under out_dir/关键帧证据/). Returns the section dict or None."""
    import base64 as _b64

    kf_dir = os.path.join(out_dir, "关键帧证据")
    try:
        os.makedirs(kf_dir, exist_ok=True)
    except OSError:
        return None
    images: list = []
    saved = 0
    for dim in ev.get("oral_assessable_dimensions") or []:
        if not isinstance(dim, dict):
            continue
        name = str(dim.get("dimension") or "维度")
        for kf in dim.get("key_frames") or []:
            if not isinstance(kf, dict):
                continue
            raw_tc = str(kf.get("timecode") or "")
            why = str(kf.get("why") or "").strip()
            caption = f"**{name}** · {raw_tc}" + (f" · {why}" if why else "")
            fp = kf.get("frame_path")
            thumb = kf.get("thumbnail") or ""
            if fp and os.path.exists(fp):
                images.append({"data": fp, "caption": caption})
            elif isinstance(thumb, str) and thumb.startswith("data:"):
                try:
                    p = os.path.join(kf_dir, f"{name}_{raw_tc.replace(':', '-') or '帧'}_{saved}.jpg")
                    with open(p, "wb") as fh:
                        fh.write(_b64.b64decode(thumb.split(",", 1)[-1]))
                    images.append({"data": p, "caption": caption})
                    saved += 1
                except Exception:
                    pass
    if not images:
        return None
    return {"heading": "关键帧证据", "blocks": [{"type": "gallery", "cols": 2, "images": images}]}


def _ensure_pose_delivery(data: dict, ev: dict) -> None:
    """Render-level GUARANTEE for the 表达/肢体/流畅性 dimension: when the eval has a
    pose_delivery (skeleton channel), drop any wrong "证据有限未评分 / 未检测到肢体" delivery
    line the agent wrote (weaker models ignore the pose data and fall back to N/A), and
    inject the authoritative pose-backed assessment. Model-independent."""
    import re

    pose = ev.get("pose_delivery") or {}
    level = pose.get("delivery_level")
    if not level:
        return
    authoritative = f"**表达/肢体/流畅性:{level}** —— {str(pose.get('evidence') or '').strip()}"
    sections = data.get("sections") or []
    subj = re.compile(r"(表达|肢体|姿态|姿体|流畅|delivery)", re.I)
    lvl = re.compile(r"[强中弱]")
    # a REAL pose assessment carries actual skeleton numbers — not just the word "骨架"
    metric = re.compile(r"(静止|手势活动|移动量|归一化|锁定主讲)")
    # a placeholder/deferral/N-A line about delivery (must be replaced, must NOT count as done)
    placeholder = re.compile(r"(未评分|证据有限|证据不足|N\s*/?\s*A|未检测|无法评估|不作评分|不予评分|不单独|不撰写|权威注入|--job|由骨架[^,。]{0,8}(注入|量化))", re.I)

    def _is_real(t: str) -> bool:
        return bool(subj.search(t) and lvl.search(t) and metric.search(t))

    def _is_placeholder(t: str) -> bool:
        return bool(subj.search(t) and placeholder.search(t) and not metric.search(t))

    already = False
    for s in sections:
        new_blocks = []
        for b in s.get("blocks") or []:
            bt = b.get("type")
            if bt == "bullets":
                kept = []
                for it in b.get("items") or []:
                    t = str(it)
                    if _is_real(t):
                        already = True
                        kept.append(it)
                    elif _is_placeholder(t):
                        continue  # drop the deferral / N-A delivery bullet
                    else:
                        kept.append(it)
                b["items"] = kept
                new_blocks.append(b)
            elif bt in ("paragraph", "note"):
                t = str(b.get("text") or "")
                if _is_real(t):
                    already = True
                    new_blocks.append(b)
                elif _is_placeholder(t) and len(t) < 240:
                    continue  # drop a short delivery deferral / N-A block entirely
                else:
                    new_blocks.append(b)
            else:
                new_blocks.append(b)
        s["blocks"] = new_blocks
    if already:
        return  # a real pose assessment is already present

    target = next((s for s in sections if any(w in str(s.get("heading", "")) for w in ("讲解", "答辩"))), None)
    if target:
        bl = next((b for b in target.get("blocks") or [] if b.get("type") == "bullets"), None)
        if bl is not None:
            bl.setdefault("items", []).append(authoritative)
            return
    idx = next((i for i, s in enumerate(sections) if any(b.get("type") == "radar" for b in (s.get("blocks") or []))), len(sections))
    sections.insert(idx, {"heading": "表达/肢体/流畅性(骨架量化)", "blocks": [{"type": "note", "text": authoritative}]})
    data["sections"] = sections


def _augment_from_job(data: dict, job_id: str, out_dir: str) -> None:
    """Render-level guarantees for a video evaluation (fetch the eval once): ensure the
    关键帧证据 gallery AND the pose-backed 表达/肢体/流畅性 dimension both appear, regardless
    of what the (possibly weaker) agent model produced."""
    ev = _fetch_course_eval(job_id)
    if not ev:
        return
    sections = data.get("sections") or []
    if not any(b.get("type") in ("gallery", "image") for s in sections for b in (s.get("blocks") or [])):
        gallery = _gallery_from_eval(ev, out_dir)
        if gallery:
            idx = next((i for i, s in enumerate(sections) if any(b.get("type") == "radar" for b in (s.get("blocks") or []))), len(sections))
            sections.insert(idx, gallery)
            data["sections"] = sections
    _ensure_pose_delivery(data, ev)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a course-report evaluation to a tidy PDF (one student per file).")
    parser.add_argument("--data", help="Path to a structured report JSON file.")
    parser.add_argument("--markdown", help="Path to a Markdown file (fallback input).")
    parser.add_argument("--out", required=True, help="Output PDF path (e.g. /mnt/user-data/outputs/张三-课程报告评价.pdf).")
    parser.add_argument("--title", help="Report title (overrides / supplies the title).")
    parser.add_argument("--footer", help="Footer text shown on every page.")
    parser.add_argument("--job", help="Video job_id. When given, render guarantees a 关键帧证据 gallery by fetching the key frames itself if the report JSON has none.")
    args = parser.parse_args()

    if not args.data and not args.markdown:
        print("error: provide --data <report.json> or --markdown <report.md>", file=sys.stderr)
        return 2

    try:
        if args.data:
            with open(args.data, encoding="utf-8") as f:
                data = json.load(f)
            if args.title:
                data["title"] = args.title
        else:
            with open(args.markdown, encoding="utf-8") as f:
                data = _markdown_to_data(f.read(), args.title)
    except FileNotFoundError as exc:
        print(f"error: input file not found: {exc.filename}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: --data is not valid JSON: {exc}", file=sys.stderr)
        return 2

    if not data.get("sections"):
        print("error: nothing to render (no sections found in the input).", file=sys.stderr)
        return 2

    regular, bold = _register_fonts()
    st = _styles(regular, bold)

    out_path = os.path.abspath(os.path.expanduser(args.out))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    # Render-level guarantees for a video evaluation, regardless of the agent's model:
    # the 关键帧证据 gallery AND the pose-backed 表达/肢体/流畅性 dimension.
    if args.job:
        try:
            _augment_from_job(data, args.job, os.path.dirname(out_path))
        except Exception:
            pass  # never let the render-level nets break rendering

    left = right = 20 * mm
    top = 18 * mm
    bottom = 20 * mm
    avail_width = A4[0] - left - right
    footer_text = _clean(args.footer or data.get("footer") or "元枢 · 课程报告评价")

    def _decorate(canvas, doc):
        canvas.saveState()
        canvas.setFont(regular, 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(left, 11 * mm, footer_text)
        canvas.drawRightString(A4[0] - right, 11 * mm, f"第 {doc.page} 页")
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.4)
        canvas.line(left, 14 * mm, A4[0] - right, 14 * mm)
        canvas.restoreState()

    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=left,
        rightMargin=right,
        topMargin=top,
        bottomMargin=bottom,
        title=_clean(data.get("title") or "课程报告评价"),
    )
    story = _build_story(data, st, avail_width)
    try:
        doc.build(story, onFirstPage=_decorate, onLaterPages=_decorate)
    except Exception as exc:  # never crash the agent's turn on a layout error
        print(f"error: failed to build PDF: {exc}", file=sys.stderr)
        return 1

    print(f"PDF written: {out_path} ({os.path.getsize(out_path)} bytes, font={regular})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
