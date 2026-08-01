#!/usr/bin/env python3
"""Render a practical Markdown subset to a real PDF or Word DOCX file."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape


@dataclass
class Block:
    kind: str
    text: str = ""
    level: int = 0
    items: list[str] = field(default_factory=list)
    ordered: bool = False
    rows: list[list[str]] = field(default_factory=list)


_TABLE_SEPARATOR = re.compile(r"^:?-{3,}:?$")
_DOCX_PRIMARY_FONT = "PingFang SC"
_DOCX_FALLBACK_FONT = "Microsoft YaHei"
_INLINE_REPLACEMENTS = {
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "--",
    "\u2212": "-",
}
_WINDOWS_FONT_ROOT = os.environ.get("WINDIR") or os.path.join("C:" + os.sep, "Windows")
_CJK_FONTS = [
    (os.path.join(_WINDOWS_FONT_ROOT, "Fonts", "msyh.ttc"), 0, os.path.join(_WINDOWS_FONT_ROOT, "Fonts", "msyhbd.ttc"), 0),
    (os.path.join(_WINDOWS_FONT_ROOT, "Fonts", "msyh.ttf"), 0, os.path.join(_WINDOWS_FONT_ROOT, "Fonts", "msyhbd.ttf"), 0),
    (os.path.join(_WINDOWS_FONT_ROOT, "Fonts", "simsun.ttc"), 0, os.path.join(_WINDOWS_FONT_ROOT, "Fonts", "simhei.ttf"), 0),
    ("/System/Library/Fonts/Supplemental/Songti.ttc", 0, "/System/Library/Fonts/Supplemental/Songti.ttc", 1),
    ("/System/Library/Fonts/PingFang.ttc", 0, "/System/Library/Fonts/PingFang.ttc", 0),
    ("/System/Library/Fonts/STHeiti Medium.ttc", 0, "/System/Library/Fonts/STHeiti Medium.ttc", 0),
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0, "/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 2, "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 2),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf", 0, "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.otf", 0),
    ("/usr/share/fonts/truetype/arphic/uming.ttc", 0, "/usr/share/fonts/truetype/arphic/uming.ttc", 0),
    ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0, "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0),
    ("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf", 0, "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf", 0),
]


def _split_table_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [part.replace("\\|", "|").strip() for part in re.split(r"(?<!\\)\|", line)]


def _is_table_separator(line: str) -> bool:
    cells = _split_table_row(line)
    return bool(cells) and all(_TABLE_SEPARATOR.fullmatch(cell.replace(" ", "")) for cell in cells)


def parse_markdown(source: str) -> list[Block]:
    lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[Block] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(Block("paragraph", text=" ".join(part.strip() for part in paragraph).strip()))
            paragraph.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            language = stripped[3:].strip()
            code: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code.append(lines[index])
                index += 1
            blocks.append(Block("code", text="\n".join(code), level=1 if language else 0))
            index += 1
            continue

        if index + 1 < len(lines) and "|" in line and _is_table_separator(lines[index + 1]):
            flush_paragraph()
            rows = [_split_table_row(line)]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                rows.append(_split_table_row(lines[index]))
                index += 1
            blocks.append(Block("table", rows=rows))
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            blocks.append(Block("heading", text=heading.group(2).strip(), level=len(heading.group(1))))
            index += 1
            continue

        unordered = re.match(r"^\s*[-+*]\s+(.+)$", line)
        ordered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if unordered or ordered:
            flush_paragraph()
            is_ordered = ordered is not None
            items: list[str] = []
            while index < len(lines):
                current = re.match(r"^\s*\d+[.)]\s+(.+)$", lines[index]) if is_ordered else re.match(r"^\s*[-+*]\s+(.+)$", lines[index])
                if not current:
                    break
                items.append(current.group(1).strip())
                index += 1
            blocks.append(Block("list", items=items, ordered=is_ordered))
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote.append(lines[index].strip()[1:].strip())
                index += 1
            blocks.append(Block("quote", text=" ".join(quote)))
            continue

        if re.fullmatch(r"(?:-{3,}|\*{3,}|_{3,})", stripped):
            flush_paragraph()
            blocks.append(Block("rule"))
            index += 1
            continue

        if not stripped:
            flush_paragraph()
            index += 1
            continue

        paragraph.append(line)
        index += 1

    flush_paragraph()
    return blocks


def _normalize_inline(text: str) -> str:
    for source, replacement in _INLINE_REPLACEMENTS.items():
        text = text.replace(source, replacement)
    text = re.sub(r"!\[([^]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    return text


def _inline_parts(text: str) -> list[tuple[str, bool, bool, bool]]:
    text = _normalize_inline(text)
    pattern = re.compile(r"(\*\*.+?\*\*|`[^`]+`|(?<!\*)\*[^*]+\*(?!\*))")
    parts: list[tuple[str, bool, bool, bool]] = []
    cursor = 0
    for match in pattern.finditer(text):
        if match.start() > cursor:
            parts.append((text[cursor : match.start()], False, False, False))
        token = match.group(0)
        if token.startswith("**"):
            parts.append((token[2:-2], True, False, False))
        elif token.startswith("`"):
            parts.append((token[1:-1], False, False, True))
        else:
            parts.append((token[1:-1], False, True, False))
        cursor = match.end()
    if cursor < len(text):
        parts.append((text[cursor:], False, False, False))
    return parts or [(text, False, False, False)]


def _pdf_markup(text: str) -> str:
    rendered: list[str] = []
    for value, bold, italic, code in _inline_parts(text):
        value = escape(value)
        if code:
            value = f'<font color="#334155">{value}</font>'
        if bold:
            value = f"<b>{value}</b>"
        if italic:
            value = f"<i>{value}</i>"
        rendered.append(value)
    return "".join(rendered).replace("\n", "<br/>")


def _register_pdf_fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for regular_path, regular_index, bold_path, bold_index in _CJK_FONTS:
        if not os.path.exists(regular_path):
            continue
        try:
            pdfmetrics.registerFont(TTFont("DocumentCJK", regular_path, subfontIndex=regular_index))
        except Exception:
            continue
        bold_name = "DocumentCJK"
        if os.path.exists(bold_path):
            try:
                pdfmetrics.registerFont(TTFont("DocumentCJK-Bold", bold_path, subfontIndex=bold_index))
                bold_name = "DocumentCJK-Bold"
            except Exception:
                pass
        pdfmetrics.registerFontFamily("DocumentCJK", normal="DocumentCJK", bold=bold_name, italic="DocumentCJK", boldItalic=bold_name)
        return "DocumentCJK", bold_name
    raise RuntimeError("no embeddable CJK font found")


def render_pdf(blocks: list[Block], output: Path, title: str | None) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise RuntimeError("reportlab is required for PDF export") from exc

    regular, bold = _register_pdf_fonts()
    ink = colors.HexColor("#172033")
    muted = colors.HexColor("#64748B")
    accent = colors.HexColor("#2E74B5")
    accent_dark = colors.HexColor("#1F4D78")
    rule = colors.HexColor("#DCE3EC")
    styles = {
        "title": ParagraphStyle("title", fontName=bold, fontSize=20, leading=28, alignment=TA_CENTER, textColor=ink, spaceAfter=12),
        "h1": ParagraphStyle("h1", fontName=bold, fontSize=16, leading=20, textColor=accent, spaceBefore=18, spaceAfter=10, keepWithNext=True),
        "h2": ParagraphStyle("h2", fontName=bold, fontSize=13, leading=17, textColor=accent, spaceBefore=14, spaceAfter=7, keepWithNext=True),
        "h3": ParagraphStyle("h3", fontName=bold, fontSize=12, leading=15, textColor=accent_dark, spaceBefore=10, spaceAfter=5, keepWithNext=True),
        "body": ParagraphStyle("body", fontName=regular, fontSize=11, leading=13.75, alignment=TA_LEFT, textColor=ink, spaceAfter=6),
        "list": ParagraphStyle("list", fontName=regular, fontSize=11, leading=13.75, leftIndent=27, firstLineIndent=-13.5, textColor=ink, spaceAfter=4),
        "quote": ParagraphStyle("quote", fontName=regular, fontSize=10, leading=16, leftIndent=10, rightIndent=8, textColor=muted),
        "code": ParagraphStyle("code", fontName=regular, fontSize=9.5, leading=15, leftIndent=8, rightIndent=8, textColor=colors.HexColor("#334155"), backColor=colors.HexColor("#F3F6FA"), borderPadding=7, spaceAfter=7),
        "cell": ParagraphStyle("cell", fontName=regular, fontSize=9, leading=13, textColor=ink),
        "cellhead": ParagraphStyle("cellhead", fontName=bold, fontSize=9, leading=13, textColor=ink),
    }
    doc = SimpleDocTemplate(
        str(output),
        pagesize=LETTER,
        rightMargin=25.4 * mm,
        leftMargin=25.4 * mm,
        topMargin=25.4 * mm,
        bottomMargin=25.4 * mm,
        title=title or "Allo 文档",
        author="Allo 教育助手",
    )
    story = []
    if title:
        story.extend([Paragraph(_pdf_markup(title), styles["title"]), HRFlowable(width="100%", thickness=0.7, color=rule), Spacer(1, 7)])
    for block in blocks:
        if block.kind == "heading":
            style = styles["h1" if block.level <= 1 else "h2" if block.level == 2 else "h3"]
            story.append(Paragraph(_pdf_markup(block.text), style))
        elif block.kind == "paragraph":
            story.append(Paragraph(_pdf_markup(block.text), styles["body"]))
        elif block.kind == "list":
            for position, item in enumerate(block.items, 1):
                marker = f"{position}." if block.ordered else "•"
                story.append(Paragraph(f"{marker} {_pdf_markup(item)}", styles["list"]))
        elif block.kind == "quote":
            quote = Table([[Paragraph(_pdf_markup(block.text), styles["quote"])]], colWidths=[doc.width])
            quote.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F6F8FB")), ("LINEBEFORE", (0, 0), (0, -1), 3, accent), ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
            story.extend([quote, Spacer(1, 7)])
        elif block.kind == "code":
            story.append(Paragraph(_pdf_markup(block.text), styles["code"]))
        elif block.kind == "rule":
            story.extend([Spacer(1, 3), HRFlowable(width="100%", thickness=0.6, color=rule), Spacer(1, 5)])
        elif block.kind == "table" and block.rows:
            width = max(len(row) for row in block.rows)
            rows = [row + [""] * (width - len(row)) for row in block.rows]
            pdf_rows = []
            for row_index, row in enumerate(rows):
                style = styles["cellhead"] if row_index == 0 else styles["cell"]
                pdf_rows.append([Paragraph(_pdf_markup(cell), style) for cell in row])
            widths_dxa = _table_widths(rows)
            table = Table(pdf_rows, colWidths=[doc.width * column_width / 9360 for column_width in widths_dxa], repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF5")), ("BOX", (0, 0), (-1, -1), 0.6, rule), ("INNERGRID", (0, 0), (-1, -1), 0.35, rule), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
            story.extend([table, Spacer(1, 8)])
    if not story:
        raise RuntimeError("document has no renderable content")
    doc.build(story)


def _w_run(text: str, *, bold: bool = False, italic: bool = False, code: bool = False) -> str:
    properties = [
        f'<w:rFonts w:ascii="{_DOCX_PRIMARY_FONT}" w:hAnsi="{_DOCX_PRIMARY_FONT}" w:eastAsia="{_DOCX_PRIMARY_FONT}"/>',
        '<w:lang w:val="zh-CN" w:eastAsia="zh-CN"/>',
    ]
    if bold:
        properties.append("<w:b/>")
    if italic:
        properties.append("<w:i/>")
    if code:
        properties.extend(['<w:color w:val="334155"/>', '<w:shd w:val="clear" w:fill="F3F6FA"/>'])
    content: list[str] = []
    for index, line in enumerate(text.split("\n")):
        if index:
            content.append("<w:br/>")
        content.append(f'<w:t xml:space="preserve">{escape(line)}</w:t>')
    return f'<w:r><w:rPr>{"".join(properties)}</w:rPr>{"".join(content)}</w:r>'


def _w_paragraph(text: str, *, style: str | None = None, num_id: int | None = None, quote: bool = False, code: bool = False) -> str:
    paragraph_properties: list[str] = []
    if style:
        paragraph_properties.append(f'<w:pStyle w:val="{style}"/>')
    if num_id is not None:
        paragraph_properties.append(f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num_id}"/></w:numPr>')
    if quote:
        paragraph_properties.extend(['<w:ind w:left="360" w:right="240"/>', '<w:pBdr><w:left w:val="single" w:sz="18" w:space="8" w:color="2563EB"/></w:pBdr>', '<w:shd w:val="clear" w:fill="F6F8FB"/>'])
    if code:
        paragraph_properties.extend(['<w:ind w:left="240" w:right="240"/>', '<w:shd w:val="clear" w:fill="F3F6FA"/>'])
    runs: list[str] = []
    for value, bold, italic, inline_code in _inline_parts(text):
        runs.append(_w_run(value, bold=bold, italic=italic, code=code or inline_code))
    return f'<w:p><w:pPr>{"".join(paragraph_properties)}</w:pPr>{"".join(runs)}</w:p>'


def _table_widths(rows: list[list[str]], total: int = 9360) -> list[int]:
    width = max(len(row) for row in rows)
    weights: list[int] = []
    for column in range(width):
        longest = max((len(row[column]) if column < len(row) else 0) for row in rows)
        weights.append(max(6, min(longest, 48)))
    minimum = max(1, min(900, total // width))
    remaining = max(0, total - minimum * width)
    weight_total = sum(weights) or width
    widths = [minimum + remaining * weight // weight_total for weight in weights]
    widths[-1] += total - sum(widths)
    return widths


def _w_table(rows: list[list[str]]) -> str:
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    column_widths = _table_widths(normalized)
    table_rows: list[str] = []
    for row_index, row in enumerate(normalized):
        cells: list[str] = []
        for column_index, cell in enumerate(row):
            shade = '<w:shd w:val="clear" w:fill="E8EEF5"/>' if row_index == 0 else ""
            cell_text = _w_paragraph(cell, style="TableHeader" if row_index == 0 else "TableBody")
            cells.append(f'<w:tc><w:tcPr><w:tcW w:w="{column_widths[column_index]}" w:type="dxa"/><w:vAlign w:val="center"/>{shade}</w:tcPr>{cell_text}</w:tc>')
        table_rows.append(f'<w:tr>{"".join(cells)}</w:tr>')
    borders = "".join(f'<w:{edge} w:val="single" w:sz="4" w:space="0" w:color="DCE3EC"/>' for edge in ("top", "left", "bottom", "right", "insideH", "insideV"))
    grid = "".join(f'<w:gridCol w:w="{column_width}"/>' for column_width in column_widths)
    return f'<w:tbl><w:tblPr><w:tblW w:w="9360" w:type="dxa"/><w:tblInd w:w="120" w:type="dxa"/><w:tblLayout w:type="fixed"/><w:tblBorders>{borders}</w:tblBorders><w:tblCellMar><w:top w:w="80" w:type="dxa"/><w:left w:w="120" w:type="dxa"/><w:bottom w:w="80" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>{grid}</w:tblGrid>{"".join(table_rows)}</w:tbl>'


def render_docx(blocks: list[Block], output: Path, title: str | None) -> None:
    body: list[str] = []
    if title:
        body.append(_w_paragraph(title, style="Title"))
    for block in blocks:
        if block.kind == "heading":
            body.append(_w_paragraph(block.text, style=f"Heading{min(block.level, 3)}"))
        elif block.kind == "paragraph":
            body.append(_w_paragraph(block.text, style="BodyText"))
        elif block.kind == "list":
            for item in block.items:
                body.append(_w_paragraph(item, style="BodyText", num_id=2 if block.ordered else 1))
        elif block.kind == "quote":
            body.append(_w_paragraph(block.text, style="BodyText", quote=True))
        elif block.kind == "code":
            body.append(_w_paragraph(block.text, style="Code", code=True))
        elif block.kind == "rule":
            body.append('<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="4" w:space="1" w:color="DCE3EC"/></w:pBdr></w:pPr></w:p>')
        elif block.kind == "table" and block.rows:
            body.append(_w_table(block.rows))
    if not body:
        raise RuntimeError("document has no renderable content")

    document_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{"".join(body)}<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>'''
    styles_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{_DOCX_PRIMARY_FONT}" w:hAnsi="{_DOCX_PRIMARY_FONT}" w:eastAsia="{_DOCX_PRIMARY_FONT}"/><w:lang w:val="zh-CN" w:eastAsia="zh-CN"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="300" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/><w:spacing w:before="120" w:after="300"/></w:pPr><w:rPr><w:b/><w:sz w:val="40"/><w:szCs w:val="40"/><w:color w:val="172033"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="360" w:after="200"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/><w:szCs w:val="32"/><w:color w:val="2E74B5"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="280" w:after="140"/></w:pPr><w:rPr><w:b/><w:sz w:val="26"/><w:szCs w:val="26"/><w:color w:val="2E74B5"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="200" w:after="100"/></w:pPr><w:rPr><w:b/><w:sz w:val="24"/><w:szCs w:val="24"/><w:color w:val="1F4D78"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="BodyText"><w:name w:val="Body Text"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="120" w:line="300" w:lineRule="auto"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="120" w:line="300" w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="19"/><w:szCs w:val="19"/><w:color w:val="334155"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="TableHeader"><w:name w:val="Table Header"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="19"/><w:szCs w:val="19"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="TableBody"><w:name w:val="Table Body"/><w:basedOn w:val="Normal"/><w:rPr><w:sz w:val="19"/><w:szCs w:val="19"/></w:rPr></w:style>
</w:styles>'''
    numbering_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="singleLevel"/><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/><w:lvlJc w:val="left"/><w:pPr><w:tabs><w:tab w:val="num" w:pos="540"/></w:tabs><w:ind w:left="540" w:hanging="270"/><w:spacing w:after="80" w:line="300" w:lineRule="auto"/></w:pPr><w:rPr><w:rFonts w:ascii="{_DOCX_PRIMARY_FONT}" w:hAnsi="{_DOCX_PRIMARY_FONT}" w:eastAsia="{_DOCX_PRIMARY_FONT}"/><w:lang w:val="zh-CN" w:eastAsia="zh-CN"/></w:rPr></w:lvl></w:abstractNum><w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="singleLevel"/><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/><w:lvlJc w:val="left"/><w:pPr><w:tabs><w:tab w:val="num" w:pos="540"/></w:tabs><w:ind w:left="540" w:hanging="270"/><w:spacing w:after="80" w:line="300" w:lineRule="auto"/></w:pPr><w:rPr><w:rFonts w:ascii="{_DOCX_PRIMARY_FONT}" w:hAnsi="{_DOCX_PRIMARY_FONT}" w:eastAsia="{_DOCX_PRIMARY_FONT}"/><w:lang w:val="zh-CN" w:eastAsia="zh-CN"/></w:rPr></w:lvl></w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num><w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num></w:numbering>'''
    font_table_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:fonts xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:font w:name="{_DOCX_PRIMARY_FONT}"><w:altName w:val="{_DOCX_FALLBACK_FONT}"/><w:family w:val="swiss"/><w:charset w:val="86"/></w:font></w:fonts>'''
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/><Override PartName="/word/fontTable.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>'''
    relationships = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>'''
    document_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/fontTable" Target="fontTable.xml"/></Relationships>'''
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    core = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>{escape(title or "Allo 文档")}</dc:title><dc:creator>Allo 教育助手</dc:creator><cp:lastModifiedBy>Allo 教育助手</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>'''
    app = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Allo 教育助手</Application><AppVersion>1.0</AppVersion></Properties>'''
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/styles.xml", styles_xml)
        archive.writestr("word/numbering.xml", numbering_xml)
        archive.writestr("word/fontTable.xml", font_table_xml)
        archive.writestr("word/_rels/document.xml.rels", document_rels)
        archive.writestr("docProps/core.xml", core)
        archive.writestr("docProps/app.xml", app)


def _validate_output(output: Path, output_format: str) -> None:
    if not output.is_file() or output.stat().st_size < 256:
        raise RuntimeError("rendered file is missing or empty")
    if output_format == "pdf":
        if output.read_bytes()[:5] != b"%PDF-":
            raise RuntimeError("rendered file is not a valid PDF")
        return
    if not zipfile.is_zipfile(output):
        raise RuntimeError("rendered file is not a valid DOCX package")
    with zipfile.ZipFile(output) as archive:
        required_parts = {"[Content_Types].xml", "word/document.xml", "word/styles.xml", "word/numbering.xml", "word/fontTable.xml"}
        missing = required_parts.difference(archive.namelist())
        if missing:
            raise RuntimeError(f"DOCX package is missing required parts: {sorted(missing)}")


def _allowed_output(output: Path) -> None:
    root = Path(os.getenv("ALLO_OUTPUTS_DIR", "/mnt/user-data/outputs")).resolve()
    resolved = output.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"output must stay under {root}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Markdown to PDF or Word DOCX")
    parser.add_argument("--input", required=True, help="Completed Markdown source")
    parser.add_argument("--out", required=True, help="Final .pdf or .docx path under ALLO_OUTPUTS_DIR")
    parser.add_argument("--title", help="Optional document title")
    args = parser.parse_args()

    source_path = Path(args.input)
    output_path = Path(args.out)
    try:
        if not source_path.is_file():
            raise RuntimeError(f"input file not found: {source_path}")
        output_format = output_path.suffix.lower().lstrip(".")
        if output_format not in {"pdf", "docx"}:
            raise RuntimeError("output extension must be .pdf or .docx")
        _allowed_output(output_path)
        source = source_path.read_text(encoding="utf-8")
        blocks = parse_markdown(source)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = output_path.with_name(f".{output_path.stem}.{os.getpid()}.tmp{output_path.suffix}")
        try:
            if output_format == "pdf":
                render_pdf(blocks, temporary_path, args.title)
            else:
                render_docx(blocks, temporary_path, args.title)
            _validate_output(temporary_path, output_format)
            os.replace(temporary_path, output_path)
        finally:
            temporary_path.unlink(missing_ok=True)
        print(json.dumps({"status": "ok", "format": output_format, "path": str(output_path), "bytes": output_path.stat().st_size}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
