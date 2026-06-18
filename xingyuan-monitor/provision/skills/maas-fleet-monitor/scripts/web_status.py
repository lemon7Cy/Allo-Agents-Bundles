#!/usr/bin/env python3
"""Read the MaaS Monitor customer-facing Web API and print a safe summary.

This project version is intentionally read-only and uses the public Basic Auth
Web dashboard/API only.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


BASE_URL = os.getenv("MAAS_MONITOR_WEB_URL", "http://221.0.79.251:39091").rstrip("/")
USERNAME = os.getenv("MAAS_MONITOR_WEB_USERNAME", "maas")
PASSWORD = os.getenv("MAAS_MONITOR_WEB_PASSWORD", "")


def default_report_root() -> Path:
    outputs = Path("/mnt/user-data/outputs")
    if outputs.exists():
        return outputs / "maas-monitor-reports"
    workspace = os.getenv("ALLO_WORKSPACE_PATH")
    if workspace:
        return Path(workspace).expanduser() / ".allo" / "maas-monitor-reports"
    return Path.cwd() / ".allo" / "maas-monitor-reports"


def run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{os.getpid()}"


REPORT_ROOT = Path(
    os.getenv("MAAS_MONITOR_REPORT_DIR") or default_report_root()
).expanduser()
REPORT_RUN_ID = os.getenv("MAAS_MONITOR_REPORT_RUN_ID") or run_id()
REPORT_DIR = REPORT_ROOT / "runs" / REPORT_RUN_ID
LATEST_DIR = REPORT_ROOT / "latest"


def markdown_path(path: str) -> str:
    resolved = Path(path).expanduser().resolve(strict=False)
    user_data = Path("/mnt/user-data").resolve(strict=False)
    try:
        relative = resolved.relative_to(user_data)
        return f"/mnt/user-data/{relative.as_posix()}"
    except ValueError:
        return str(path)


def image_markdown(path: str, alt: str) -> str:
    if os.getenv("MAAS_MONITOR_EMBED_IMAGES", "0") == "1":
        try:
            image_path = Path(path).expanduser()
            if image_path.exists() and image_path.is_file():
                encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
                return f"![{alt}](data:image/png;base64,{encoded})"
        except Exception:
            pass
    return f"![{alt}]({markdown_path(path)})"


def request_json(path: str, password: str) -> dict:
    token = base64.b64encode(f"{USERNAME}:{password}".encode()).decode()
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers={"Authorization": f"Basic {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode())


def compact_number(value: object) -> str:
    value = raw_number(value)
    if abs(value) >= 100_000_000:
        return f"{value / 100_000_000:.2f}亿"
    if abs(value) >= 10_000:
        return f"{value / 10_000:.2f}万"
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.2f}"


def raw_number(value: object) -> float:
    try:
        if value is None:
            return 0.0
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def safe_text(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def write_svg(name: str, content: str) -> str:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def write_png(name: str, image: Image.Image) -> str:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / name
    image.save(path, format="PNG")
    return str(path)


def load_font(size: int, bold: bool = False) -> Any:
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc"
        if bold
        else "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size, index=0)
        except Exception:
            continue
    return ImageFont.load_default()


def text_width(draw: ImageDraw.ImageDraw, text: str, font: Any) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return int(bbox[2] - bbox[0])


def draw_vertical_gradient(
    image: Image.Image, top_color: str, bottom_color: str
) -> None:
    draw = ImageDraw.Draw(image)
    top = tuple(int(top_color[i : i + 2], 16) for i in (1, 3, 5))
    bottom = tuple(int(bottom_color[i : i + 2], 16) for i in (1, 3, 5))
    width, height = image.size
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
        draw.line((0, y, width, y), fill=color)


def fit_text(text: str, max_chars: int) -> str:
    text = str(text or "")
    return text if len(text) <= max_chars else text[: max(0, max_chars - 1)] + "…"


def metric_card(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    label: str,
    value: str,
    note: str,
    accent: str,
) -> None:
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=24, fill="#ffffff", outline="#d7e5ef", width=1)
    draw.rounded_rectangle((x1 + 18, y1 + 18, x1 + 26, y2 - 18), radius=4, fill=accent)
    draw.text((x1 + 42, y1 + 22), label, fill="#5b7083", font=load_font(16))
    draw.text((x1 + 42, y1 + 55), value, fill="#102f45", font=load_font(30, bold=True))
    draw.text((x1 + 42, y2 - 34), note, fill="#71869a", font=load_font(13))


def overview_png(
    today: dict,
    week: dict,
    models: list[dict],
    timeline: list[dict],
    width: int = 1200,
    height: int = 720,
) -> Image.Image:
    image = Image.new("RGB", (width, height), "#eef6f8")
    draw_vertical_gradient(image, "#eaf7f3", "#f7fbff")
    draw = ImageDraw.Draw(image)
    title_font = load_font(34, bold=True)
    sub_font = load_font(16)
    label_font = load_font(15)
    value_font = load_font(18, bold=True)

    draw.rounded_rectangle(
        (26, 22, width - 26, height - 24),
        radius=34,
        fill="#ffffff",
        outline="#cfe1ea",
        width=1,
    )
    draw.text((56, 48), "MaaS 今日用量驾驶舱", fill="#0b2f43", font=title_font)
    draw.text(
        (58, 92),
        "公网 MaaS 健康运行 · 用量核心集中在 gpt-5.5 · 内网 Agent 明细未接入",
        fill="#587084",
        font=sub_font,
    )
    draw.rounded_rectangle((925, 48, 1120, 90), radius=21, fill="#0f766e")
    draw.text(
        (955, 59), "PUBLIC HEALTHY", fill="#ecfeff", font=load_font(15, bold=True)
    )

    metric_card(
        draw,
        (58, 130, 332, 250),
        "今日 Token",
        str(today.get("tokens_display") or "-"),
        "实时累计",
        "#0f766e",
    )
    metric_card(
        draw,
        (352, 130, 626, 250),
        "今日请求",
        f"{today.get('requests_display') or '-'} 次",
        "公网请求量",
        "#2563eb",
    )
    metric_card(
        draw,
        (646, 130, 920, 250),
        "今日费用",
        str(today.get("cost_display") or "-"),
        "成本估算",
        "#f97316",
    )
    metric_card(
        draw,
        (940, 130, 1142, 250),
        "近 7 天",
        str(week.get("tokens_display") or "-"),
        "Token",
        "#7c3aed",
    )

    # Top model spotlight
    draw.rounded_rectangle(
        (58, 284, 552, 630), radius=28, fill="#f8fbfc", outline="#d7e5ef"
    )
    draw.text((86, 312), "Top 模型", fill="#587084", font=label_font)
    draw.text(
        (86, 352),
        fit_text(today.get("top_model") or "-", 22),
        fill="#102f45",
        font=load_font(36, bold=True),
    )
    draw.text(
        (86, 404),
        f"{today.get('top_model_tokens_display') or '-'} Token",
        fill="#0f766e",
        font=load_font(24, bold=True),
    )
    draw.text(
        (86, 446),
        f"占比约 {today.get('top_model_share_percent') or 0}%",
        fill="#587084",
        font=load_font(18),
    )
    draw.text(
        (86, 494),
        f"峰值时段：{today.get('peak_period') or '-'} · {today.get('peak_tokens_display') or '-'} Token",
        fill="#f97316",
        font=load_font(17, bold=True),
    )

    # Compact model bars
    rows = models[:5]
    max_value = max([raw_number(row.get("total_tokens")) for row in rows] + [1])
    draw.rounded_rectangle(
        (590, 284, 1142, 630), radius=28, fill="#f8fbfc", outline="#d7e5ef"
    )
    draw.text((620, 312), "模型用量排行", fill="#102f45", font=load_font(22, bold=True))
    palette = ["#0f766e", "#2563eb", "#f97316", "#db2777", "#64748b"]
    for idx, row in enumerate(rows):
        y = 358 + idx * 48
        model = fit_text(row.get("model") or "-", 18)
        value = raw_number(row.get("total_tokens"))
        share_w = int(value / max_value * 260)
        draw.text((620, y), model, fill="#30495d", font=load_font(15))
        draw.rounded_rectangle(
            (790, y - 2, 790 + share_w, y + 22),
            radius=9,
            fill=palette[idx % len(palette)],
        )
        draw.text(
            (1070 - text_width(draw, compact_number(value), value_font), y - 1),
            compact_number(value),
            fill="#102f45",
            font=value_font,
        )

    # Footer trend hint
    if timeline:
        peak = max(
            timeline, key=lambda row: raw_number(row.get("total_tokens")), default={}
        )
        draw.text(
            (58, 662),
            f"今日峰值：{peak.get('label') or '-'} · {compact_number(peak.get('total_tokens'))} Token",
            fill="#587084",
            font=load_font(15),
        )
    draw.text(
        (856, 662),
        "数据来源：MaaS Monitor Agent/Web API",
        fill="#8aa0af",
        font=load_font(13),
    )
    return image


def bar_chart_png(
    title: str,
    rows: list[dict],
    value_key: str,
    label_key: str,
    unit: str,
    width: int = 900,
    height: int = 520,
) -> Image.Image:
    rows = rows[:7]
    max_value = max([raw_number(row.get(value_key)) for row in rows] + [1])
    image = Image.new("RGB", (width, height), "#eef6f8")
    draw_vertical_gradient(image, "#eef8f4", "#f7fbff")
    draw = ImageDraw.Draw(image)
    title_font = load_font(26, bold=True)
    label_font = load_font(15)
    value_font = load_font(15, bold=True)
    note_font = load_font(12)
    draw.rounded_rectangle(
        (18, 18, width - 18, height - 18),
        radius=26,
        fill="#ffffff",
        outline="#d1e2ec",
        width=1,
    )
    draw.text((42, 38), title, fill="#0b2f43", font=title_font)
    draw.text(
        (42, 72),
        "按 Token 统计 · 数值右对齐，避免遮挡柱形",
        fill="#6b8192",
        font=note_font,
    )
    top, left, bar_h, gap = 112, 230, 28, 22
    plot_w = width - left - 245
    palette = [
        "#0f766e",
        "#2563eb",
        "#f97316",
        "#7c3aed",
        "#db2777",
        "#64748b",
        "#16a34a",
        "#b45309",
    ]
    for idx, row in enumerate(rows):
        y = top + idx * (bar_h + gap)
        value = raw_number(row.get(value_key))
        bar_w = max(4, int(value / max_value * plot_w))
        label = fit_text(row.get(label_key) or "-", 22)
        value_label = f"{compact_number(value)} {unit}".strip()
        requests = raw_number(row.get("requests"))
        hint = (
            f"{value_label} / {compact_number(requests)} 请求"
            if requests
            else value_label
        )
        draw.text((42, y + 4), label, fill="#30495d", font=label_font)
        draw.rounded_rectangle(
            (left, y, left + plot_w, y + bar_h), radius=10, fill="#edf4f7"
        )
        draw.rounded_rectangle(
            (left, y, left + bar_w, y + bar_h),
            radius=9,
            fill=palette[idx % len(palette)],
        )
        draw.text(
            (width - 54 - text_width(draw, hint, value_font), y + 4),
            hint,
            fill="#0b2f43",
            font=value_font,
        )
    return image


def line_chart_png(
    title: str,
    rows: list[dict],
    value_key: str,
    unit: str,
    width: int = 900,
    height: int = 360,
) -> Image.Image:
    max_value = max([raw_number(row.get(value_key)) for row in rows] + [1])
    image = Image.new("RGB", (width, height), "#eef6f8")
    draw_vertical_gradient(image, "#eef8f4", "#f7fbff")
    draw = ImageDraw.Draw(image)
    title_font = load_font(24, bold=True)
    label_font = load_font(12)
    note_font = load_font(13)
    draw.rounded_rectangle(
        (18, 18, width - 18, height - 18),
        radius=26,
        fill="#ffffff",
        outline="#d1e2ec",
        width=1,
    )
    draw.text((42, 42), title, fill="#0b2f43", font=title_font)
    left, right, top, bottom = 72, 42, 92, 58
    plot_w = width - left - right
    plot_h = height - top - bottom
    for i in range(4):
        gy = top + int(plot_h * i / 3)
        draw.line((left, gy, width - right, gy), fill="#e8f0f4", width=1)
    draw.line(
        (left, top + plot_h, width - right, top + plot_h), fill="#d1e2ec", width=2
    )
    points = []
    for idx, row in enumerate(rows):
        x = left + (plot_w / 2 if len(rows) <= 1 else idx / (len(rows) - 1) * plot_w)
        y = top + plot_h - raw_number(row.get(value_key)) / max_value * plot_h
        points.append((int(x), int(y), row))
    if len(points) >= 2:
        draw.line(
            [(x, y) for x, y, _ in points], fill="#0f766e", width=5, joint="curve"
        )
    peak = max(rows, key=lambda row: raw_number(row.get(value_key)), default=None)
    label_step = max(1, len(rows) // 6)
    for idx, (x, y, row) in enumerate(points):
        is_peak = row is peak
        radius = 6 if is_peak else 4
        color = "#f97316" if is_peak else "#0f766e"
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
        if idx % label_step == 0 or idx == len(points) - 1:
            label = str(row.get("label") or "")
            draw.text(
                (x - text_width(draw, label, label_font) // 2, height - 32),
                label,
                fill="#64748b",
                font=label_font,
            )
    if peak:
        peak_text = f"峰值 {peak.get('label')}: {compact_number(raw_number(peak.get(value_key)))} {unit}"
        draw.text(
            (width - 36 - text_width(draw, peak_text, note_font), 46),
            peak_text,
            fill="#f97316",
            font=note_font,
        )
    return image


def bar_chart_svg(
    title: str,
    rows: list[dict],
    value_key: str,
    label_key: str,
    unit: str,
    width: int = 900,
    height: int = 430,
) -> str:
    rows = rows[:8]
    max_value = max([raw_number(row.get(value_key)) for row in rows] + [1])
    top = 70
    left = 190
    bar_h = 28
    gap = 16
    plot_w = width - left - 70
    palette = [
        "#0f766e",
        "#2563eb",
        "#f97316",
        "#7c3aed",
        "#db2777",
        "#64748b",
        "#16a34a",
        "#b45309",
    ]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" rx="22" fill="#f8fafc"/>',
        '<rect x="18" y="18" width="864" height="394" rx="18" fill="#ffffff" stroke="#dbe7ef"/>',
        f'<text x="36" y="48" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#123447">{safe_text(title)}</text>',
    ]
    for idx, row in enumerate(rows):
        y = top + idx * (bar_h + gap)
        value = raw_number(row.get(value_key))
        bar_w = max(4, value / max_value * plot_w)
        color = palette[idx % len(palette)]
        label = safe_text(row.get(label_key))
        value_label = f"{compact_number(value)} {unit}".strip()
        requests = raw_number(row.get("requests"))
        hint = (
            f"{value_label} / {compact_number(requests)} 请求"
            if requests
            else value_label
        )
        parts.extend(
            [
                f'<text x="36" y="{y + 20}" font-family="Arial, sans-serif" font-size="14" fill="#334155">{label}</text>',
                f'<rect x="{left}" y="{y}" width="{bar_w:.1f}" height="{bar_h}" rx="9" fill="{color}" opacity="0.9"/>',
                f'<text x="{left + bar_w + 10:.1f}" y="{y + 20}" font-family="Arial, sans-serif" font-size="13" fill="#123447">{safe_text(hint)}</text>',
            ]
        )
    parts.append("</svg>")
    return "\n".join(parts)


def line_chart_svg(
    title: str,
    rows: list[dict],
    value_key: str,
    unit: str,
    width: int = 900,
    height: int = 360,
) -> str:
    max_value = max([raw_number(row.get(value_key)) for row in rows] + [1])
    left, right, top, bottom = 62, 28, 70, 56
    plot_w = width - left - right
    plot_h = height - top - bottom
    points = []
    for idx, row in enumerate(rows):
        x = left + (plot_w / 2 if len(rows) <= 1 else idx / (len(rows) - 1) * plot_w)
        y = top + plot_h - raw_number(row.get(value_key)) / max_value * plot_h
        points.append((x, y, row))
    path = " ".join(
        ("M" if idx == 0 else "L") + f" {x:.1f} {y:.1f}"
        for idx, (x, y, _) in enumerate(points)
    )
    peak = max(rows, key=lambda row: raw_number(row.get(value_key)), default=None)
    label_step = max(1, len(rows) // 6)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" rx="22" fill="#f8fafc"/>',
        '<rect x="18" y="18" width="864" height="324" rx="18" fill="#ffffff" stroke="#dbe7ef"/>',
        f'<text x="36" y="48" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#123447">{safe_text(title)}</text>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{width - right}" y2="{top + plot_h}" stroke="#dbe7ef"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#dbe7ef"/>',
        f'<path d="{path}" fill="none" stroke="#0f766e" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>',
    ]
    for idx, (x, y, row) in enumerate(points):
        is_peak = row is peak
        radius = 5 if is_peak else 3
        color = "#f97316" if is_peak else "#0f766e"
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{color}"><title>{safe_text(row.get("label"))}: {safe_text(compact_number(raw_number(row.get(value_key))))} {safe_text(unit)}</title></circle>'
        )
        if idx % label_step == 0 or idx == len(points) - 1:
            parts.append(
                f'<text x="{x:.1f}" y="{height - 24}" font-family="Arial, sans-serif" font-size="12" fill="#64748b" text-anchor="middle">{safe_text(row.get("label"))}</text>'
            )
    if peak:
        parts.append(
            f'<text x="{width - 36}" y="48" font-family="Arial, sans-serif" font-size="13" fill="#f97316" text-anchor="end">峰值 {safe_text(peak.get("label"))}: {safe_text(compact_number(raw_number(peak.get(value_key))))} {safe_text(unit)}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def generate_report_assets(target: dict, today: dict, week: dict) -> dict:
    timelines = target.get("token_timeline", {}) or {}
    today_rows = timelines.get("day_hourly") or []
    week_rows = timelines.get("week_daily") or []
    day_models = target.get("token_usage", {}).get("day") or []
    assets = {}
    assets["overview_chart"] = write_png(
        "maas_today_overview.png",
        overview_png(today, week, day_models, today_rows),
    )
    assets["model_usage_chart"] = write_png(
        "model_usage_today.png",
        bar_chart_png(
            "今日模型 Token 用量对比", day_models, "total_tokens", "model", "Token"
        ),
    )
    assets["today_trend_chart"] = write_png(
        "trend_today.png",
        line_chart_png("今日 Token 使用趋势", today_rows, "total_tokens", "Token"),
    )
    assets["week_trend_chart"] = write_png(
        "trend_week.png",
        line_chart_png("近 7 天 Token 使用趋势", week_rows, "total_tokens", "Token"),
    )
    return assets


def write_report_files(summary: dict) -> dict:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)
    markdown = markdown_report(summary)
    markdown_path_value = REPORT_DIR / "summary.md"
    json_path_value = REPORT_DIR / "data.json"
    markdown_path_value.write_text(markdown, encoding="utf-8")
    json_path_value.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for source in [
        *summary.get("charts", {}).values(),
        str(markdown_path_value),
        str(json_path_value),
    ]:
        if source:
            src = Path(source)
            if src.exists() and src.is_file():
                shutil.copy2(src, LATEST_DIR / src.name)
    return {
        "run_id": REPORT_RUN_ID,
        "run_dir": str(REPORT_DIR),
        "run_dir_ref": markdown_path(str(REPORT_DIR)),
        "latest_dir": str(LATEST_DIR),
        "latest_dir_ref": markdown_path(str(LATEST_DIR)),
        "summary_markdown": str(markdown_path_value),
        "summary_markdown_ref": markdown_path(str(markdown_path_value)),
        "data_json": str(json_path_value),
        "data_json_ref": markdown_path(str(json_path_value)),
    }


def summarize(instances: list[dict]) -> dict:
    public = next((item for item in instances if item.get("id") == "public-maas"), None)
    internal = next(
        (item for item in instances if item.get("id") == "internal-maas"), None
    )
    target = public or (instances[0] if instances else {})
    timeline = target.get("token_timeline", {}).get("day_hourly") or []
    week_timeline = target.get("token_timeline", {}).get("week_daily") or []
    models = target.get("token_usage", {}).get("day") or []
    total_tokens = sum(float(row.get("total_tokens") or 0) for row in timeline) or sum(
        float(row.get("total_tokens") or 0) for row in models
    )
    total_requests = sum(float(row.get("requests") or 0) for row in timeline) or sum(
        float(row.get("requests") or 0) for row in models
    )
    total_cost = sum(float(row.get("cost") or 0) for row in timeline) or sum(
        float(row.get("cost") or 0) for row in models
    )
    peak = max(
        timeline, key=lambda row: float(row.get("total_tokens") or 0), default=None
    )
    top_model = models[0] if models else None
    top_model_tokens = raw_number(top_model.get("total_tokens")) if top_model else 0
    top_model_share = (
        round(top_model_tokens / total_tokens * 100, 1) if total_tokens else 0
    )
    today_summary = {
        "instance": target.get("id"),
        "tokens": total_tokens,
        "tokens_display": compact_number(total_tokens),
        "requests": total_requests,
        "requests_display": compact_number(total_requests),
        "cost": round(total_cost, 2),
        "cost_display": compact_number(total_cost),
        "peak_period": peak.get("label") if peak else None,
        "peak_tokens_display": compact_number(peak.get("total_tokens"))
        if peak
        else None,
        "top_model": top_model.get("model") if top_model else None,
        "top_model_tokens_display": compact_number(top_model.get("total_tokens"))
        if top_model
        else None,
        "top_model_share_percent": top_model_share,
    }
    week_summary = {
        "tokens": sum(raw_number(row.get("total_tokens")) for row in week_timeline),
        "tokens_display": compact_number(
            sum(raw_number(row.get("total_tokens")) for row in week_timeline)
        ),
        "requests": sum(raw_number(row.get("requests")) for row in week_timeline),
        "requests_display": compact_number(
            sum(raw_number(row.get("requests")) for row in week_timeline)
        ),
        "cost": round(sum(raw_number(row.get("cost")) for row in week_timeline), 2),
    }
    assets = generate_report_assets(target, today_summary, week_summary)
    agent_metrics = build_agent_metrics(today_summary)
    return {
        "dashboard_url": f"{BASE_URL}/?v=metric1",
        "instances": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "status": item.get("status"),
                "lastCheckedAt": item.get("lastCheckedAt"),
            }
            for item in instances
        ],
        "today": today_summary,
        "week": week_summary,
        "charts": assets,
        "metrics": agent_metrics["metrics"],
        "metrics_line": agent_metrics["metrics_line"],
        "coverage_note": "internal-maas 尚未接入 Agent，详细模型/Token/账号/Pool 数据可能不可用。"
        if internal
        else None,
    }


def build_agent_metrics(today: dict) -> dict:
    """Structured metrics + a ready-to-use 指标 line for the Xingyuan monitor agent.

    The monitor agent appends ``metrics_line`` to its monitor_card reply so the
    observation memory can extract stable, comparable metrics for trend analysis
    (see the agent bundle SOUL "指标行" convention). Keys are intentionally stable
    English identifiers so the same metric aligns across days.
    """
    metrics = {
        "token_total": {"value": today.get("tokens"), "unit": "token", "label": "今日 Token 总量"},
        "requests": {"value": today.get("requests"), "unit": "次", "label": "今日请求数"},
        "cost": {"value": today.get("cost"), "unit": None, "label": "今日费用"},
        "top_model": {"value": today.get("top_model"), "unit": None, "label": "Top 模型"},
    }
    parts = []
    if today.get("tokens") is not None:
        parts.append(f"token_total={today['tokens']} token")
    if today.get("requests") is not None:
        parts.append(f"requests={today['requests']}")
    if today.get("cost") is not None:
        parts.append(f"cost={today['cost']}")
    if today.get("top_model"):
        parts.append(f"top_model={today['top_model']}")
    metrics_line = ("指标：" + "; ".join(parts)) if parts else ""
    return {"metrics": metrics, "metrics_line": metrics_line}


def markdown_report(summary: dict) -> str:
    today = summary.get("today", {})
    week = summary.get("week", {})
    charts = summary.get("charts", {})
    files = summary.get("files", {})
    lines = [
        f"当前公网 MaaS 运行健康，今日用量主要集中在 {today.get('top_model') or 'Top 模型'}。",
        "",
        image_markdown(charts.get("overview_chart") or "", "MaaS 今日用量驾驶舱"),
        "",
        image_markdown(
            charts.get("model_usage_chart") or "", "今日模型 Token 用量对比"
        ),
        "",
        image_markdown(charts.get("today_trend_chart") or "", "今日 Token 使用趋势"),
        "",
        image_markdown(charts.get("week_trend_chart") or "", "近 7 天 Token 使用趋势"),
        "",
        "| 指标 | 当前值 |",
        "|---|---:|",
        f"| 今日请求 | {today.get('requests_display')} 次 |",
        f"| 今日 Token | {today.get('tokens_display')} |",
        f"| 今日费用 | {today.get('cost_display')} |",
        f"| 峰值时段 | {today.get('peak_period')}，约 {today.get('peak_tokens_display')} Token |",
        f"| Top 模型 | {today.get('top_model')}，约 {today.get('top_model_tokens_display')} Token，占比约 {today.get('top_model_share_percent')}% |",
        f"| 近 7 天 Token | {week.get('tokens_display')} |",
        "",
    ]
    if summary.get("coverage_note"):
        lines.append(summary["coverage_note"])
    lines.append("如需账号、Provider Pool、错误明细，可再进入技术诊断视图查询。")
    present_paths = [
        charts.get("overview_chart"),
        charts.get("model_usage_chart"),
        charts.get("today_trend_chart"),
        charts.get("week_trend_chart"),
        files.get("summary_markdown"),
    ]
    present_paths = [path for path in present_paths if path]
    if present_paths:
        lines.extend(
            [
                "",
                "<!-- maas-monitor-present-files",
                *present_paths,
                "-->",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read MaaS Monitor Web API and print a safe report."
    )
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()
    password = PASSWORD
    if not password:
        print(
            json.dumps(
                {
                    "error": "missing_web_password",
                    "dashboard_url": f"{BASE_URL}/?v=metric1",
                    "username": USERNAME,
                },
                ensure_ascii=False,
            )
        )
        return 2
    try:
        instances_payload = request_json("/api/instances", password)
    except urllib.error.HTTPError as error:
        print(
            json.dumps(
                {
                    "error": "web_api_http_error",
                    "status": error.code,
                    "dashboard_url": f"{BASE_URL}/?v=metric1",
                },
                ensure_ascii=False,
            )
        )
        return 1
    except Exception as error:
        print(
            json.dumps(
                {
                    "error": "web_api_unreachable",
                    "message": str(error),
                    "dashboard_url": f"{BASE_URL}/?v=metric1",
                },
                ensure_ascii=False,
            )
        )
        return 1
    if not isinstance(instances_payload, list):
        print(
            json.dumps(
                {
                    "error": "unexpected_payload",
                    "dashboard_url": f"{BASE_URL}/?v=metric1",
                },
                ensure_ascii=False,
            )
        )
        return 1
    summary = summarize(instances_payload)
    files = write_report_files(summary)
    summary["files"] = files
    Path(files["summary_markdown"]).write_text(
        markdown_report(summary), encoding="utf-8"
    )
    Path(files["data_json"]).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    shutil.copy2(Path(files["summary_markdown"]), LATEST_DIR / "summary.md")
    shutil.copy2(Path(files["data_json"]), LATEST_DIR / "data.json")
    if args.format == "markdown":
        print(markdown_report(summary))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
