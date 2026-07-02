#!/usr/bin/env python3
"""Render a six-dimension incremental evaluation: radar chart + increment table.

The agent (LLM) does the judgment — it scores each draft on the six dimensions
and writes a scores JSON. This script is the deterministic visualization layer:
it draws an overlaid radar chart (one polygon per draft) and prints a markdown
increment table (终稿 − 初稿 per dimension + total). No judgment lives here.

Scores JSON schema (all scores 0–100):
    {
      "title": "……课题名（可选）",
      "dimensions": ["创新性", "数据分析深度", "完整性", "文献引用", "结论合理性", "格式规范性"],
      "series": {"初稿": [60, 55, 70, 50, 65, 80], "终稿": [78, 82, 85, 72, 80, 88]},
      "evidence": {"创新性": "终稿提出了……（可选，每维一句依据）"}
    }

Usage:
    python3 render_eval.py --scores scores.json [--out radar.png] [--title "…"]

Output PNG goes to $ALLO_OUTPUTS_DIR (falls back to the current dir). If
matplotlib (or a CJK font) is unavailable the chart is skipped gracefully — the
increment table (plain text) is always printed, so the evaluation never fails.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# The canonical six dimensions, shared across the 出题 / 学生 / 评审 bundles.
CANONICAL_DIMENSIONS = ["创新性", "数据分析深度", "完整性", "文献引用", "结论合理性", "格式规范性"]


def _outputs_dir() -> str:
    return os.getenv("ALLO_OUTPUTS_DIR") or os.getcwd()


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _is_ai_series(name: str) -> bool:
    return "AI" in name.upper() or "基线" in name


def _pick_pair(names: list[str]) -> tuple[str, str]:
    """The increment Δ is the STUDENT's growth: 终稿 − 初稿.

    Never let an AI-baseline series (conventionally last in the JSON) be picked
    as the "final" side — that silently turns the headline increment into
    AI基线−初稿 (real bug: 58→76 printed Δ+12 because the AI series at 70 sat
    last). Prefer explicit 初稿/终稿 names, else the first/last NON-AI series.
    """
    base = next((n for n in names if "初稿" in n), None)
    final = next((n for n in names if "终稿" in n), None)
    if base is None or final is None:
        non_ai = [n for n in names if not _is_ai_series(n)] or names
        base = base or non_ai[0]
        final = final or non_ai[-1]
    return base, final


def _print_increment_table(dims: list[str], series: dict[str, list[float]], evidence: dict[str, str]) -> None:
    names = list(series.keys())
    # The student increment Δ needs TWO student drafts. A single draft plus an
    # AI baseline is a comparison (vs-AI column), not an increment — rendering
    # Δ(终稿−终稿)=0 would be a fake column.
    non_ai_names = [n for n in names if not _is_ai_series(n)]
    has_pair = len(non_ai_names) >= 2
    base_name, final_name = _pick_pair(names) if has_pair else (names[0], names[0])
    base, final = series[base_name], series[final_name]
    ai_name = next((n for n in names if _is_ai_series(n)), None)
    ai = series[ai_name] if ai_name else None

    print("\n### 六维增量评价")
    header = "| 维度 | " + " | ".join(names)
    extra_headers = []
    if has_pair:
        extra_headers.append(f"增量Δ({final_name}−{base_name})")
    if ai is not None:
        extra_headers.append(f"vs {ai_name}({final_name}−{ai_name})")
    header += "".join(f" | {h}" for h in extra_headers) + " |"
    print(header)
    print("|" + "---|" * (len(names) + 1 + len(extra_headers)))

    def _fmt_signed(v: float) -> str:
        text = f"{v:.1f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)
        return f"+{text}" if v >= 0 else text

    for i, dim in enumerate(dims):
        cells = [str(series[n][i]) for n in names]
        if has_pair:
            cells.append(_fmt_signed(final[i] - base[i]))
        if ai is not None:
            cells.append(_fmt_signed(final[i] - ai[i]))
        print(f"| {dim} | " + " | ".join(cells) + " |")
    # totals
    cells = [f"{sum(series[n]) / len(dims):.1f}" for n in names]
    if has_pair:
        cells.append(_fmt_signed(round((sum(final) - sum(base)) / len(dims), 1)))
    if ai is not None:
        cells.append(_fmt_signed(round((sum(final) - sum(ai)) / len(dims), 1)))
    print("| **合计/均值** | " + " | ".join(cells) + " |")

    if evidence:
        print("\n**逐维依据**")
        for dim in dims:
            if dim in evidence and evidence[dim]:
                print(f"- {dim}：{evidence[dim]}")


def _pick_cjk_font():
    """Return a matplotlib font name that can render CJK, or None."""
    try:
        from matplotlib import font_manager
    except Exception:
        return None
    candidates = ["PingFang SC", "Hiragino Sans GB", "Heiti SC", "STHeiti", "Songti SC",
                  "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Zen Hei"]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            return name
    return None


def _xml_esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render_radar_svg(dims: list[str], series: dict[str, list[float]], title: str, out_path: str) -> str:
    """Zero-dependency SVG radar — fallback when matplotlib is absent.

    SVG text uses the VIEWER's fonts, so CJK labels render in any browser /
    IM preview without font probing; works on a bare customer machine."""
    import math
    width = height = 640
    cx, cy, radius = width / 2, height / 2 + 14, 198.0
    n = len(dims)
    colors = ["#64748B", "#2563EB", "#F59E0B", "#10B981", "#EF4444"]

    def pt(i: int, r: float) -> tuple[float, float]:
        ang = -math.pi / 2 + 2 * math.pi * i / n
        return (cx + r * math.cos(ang), cy + r * math.sin(ang))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height + 44}" viewBox="0 0 {width} {height + 44}" font-family="PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{cx}" y="34" text-anchor="middle" font-size="18" fill="#0F172A">{_xml_esc(title)}</text>',
    ]
    for frac in (0.2, 0.4, 0.6, 0.8, 1.0):
        ring = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, radius * frac) for i in range(n)))
        parts.append(f'<polygon points="{ring}" fill="none" stroke="#E2E8F0" stroke-width="1"/>')
        parts.append(f'<text x="{cx + 4:.1f}" y="{cy - radius * frac - 3:.1f}" font-size="9" fill="#94A3B8">{int(frac * 100)}</text>')
    for i, dim in enumerate(dims):
        ax, ay = pt(i, radius)
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{ax:.1f}" y2="{ay:.1f}" stroke="#E2E8F0" stroke-width="1"/>')
        lx, ly = pt(i, radius + 26)
        anchor = "middle" if abs(lx - cx) < 30 else ("start" if lx > cx else "end")
        parts.append(f'<text x="{lx:.1f}" y="{ly + 4:.1f}" text-anchor="{anchor}" font-size="13" fill="#334155">{_xml_esc(dim)}</text>')
    for k, (name, values) in enumerate(series.items()):
        color = colors[k % len(colors)]
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, radius * max(0.0, min(100.0, float(v))) / 100.0) for i, v in enumerate(values)))
        dash = ' stroke-dasharray="6,4"' if "AI" in name else ""
        parts.append(f'<polygon points="{pts}" fill="{color}" fill-opacity="0.10" stroke="{color}" stroke-width="2"{dash}/>')
    for k, name in enumerate(series):
        color = colors[k % len(colors)]
        x, y = 24 + k * 180, height + 22
        parts.append(f'<rect x="{x}" y="{y - 10}" width="12" height="12" fill="{color}" fill-opacity="0.6"/>')
        parts.append(f'<text x="{x + 18}" y="{y}" font-size="12" fill="#334155">{_xml_esc(name)}</text>')
    parts.append("</svg>")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return out_path


def _render_radar(dims: list[str], series: dict[str, list[float]], title: str, out_path: str) -> str | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception as exc:  # matplotlib not installed → zero-dependency SVG fallback
        svg_path = os.path.splitext(out_path)[0] + ".svg"
        try:
            saved = _render_radar_svg(dims, series, title, svg_path)
            print(f"\n(matplotlib 不可用:{exc};已用内置 SVG 渲染雷达图,浏览器/预览可直接打开)")
            return saved
        except Exception as svg_exc:
            print(f"\n(雷达图已跳过:matplotlib 不可用且 SVG 兜底失败 {svg_exc};增量表如上)")
            return None

    cjk = _pick_cjk_font()
    if cjk:
        plt.rcParams["font.sans-serif"] = [cjk]
        plt.rcParams["axes.unicode_minus"] = False
        labels = dims
        legend_note = ""
    else:
        # No CJK font → use D1..D6 on the axes, keep Chinese in the table/legend note.
        labels = [f"D{i + 1}" for i in range(len(dims))]
        legend_note = "  ".join(f"D{i + 1}={d}" for i, d in enumerate(dims))

    n = len(dims)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(6.4, 6.4), subplot_kw=dict(polar=True))
    for name, values in series.items():
        vals = list(values) + values[:1]
        ax.plot(angles, vals, linewidth=2, label=name)
        ax.fill(angles, vals, alpha=0.12)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylim(0, 100)
    ax.set_title(title, fontsize=14, pad=18)
    ax.legend(loc="upper right", bbox_to_anchor=(1.18, 1.12))
    fig.tight_layout()
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)

    if legend_note:
        print(f"\n(图中坐标轴用 D1–D6 缩写,因系统无中文字体:{legend_note})")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="六维增量评价:雷达图 + 增量表")
    parser.add_argument("--scores", required=True, help="评分 JSON 路径")
    parser.add_argument("--out", default=None, help="输出 PNG 文件名(默认 outputs 目录下 incremental-eval.png)")
    parser.add_argument("--title", default=None, help="图表标题")
    args = parser.parse_args()

    data = _load(args.scores)
    dims = data.get("dimensions") or CANONICAL_DIMENSIONS
    series = data.get("series") or {}
    evidence = data.get("evidence") or {}
    title = args.title or data.get("title") or "课程报告六维增量评价"

    if not series:
        print("错误:scores JSON 缺少 series(至少一份草稿的六维评分)", file=sys.stderr)
        return 1
    for name, vals in series.items():
        if len(vals) != len(dims):
            print(f"错误:草稿「{name}」的评分个数({len(vals)})与维度数({len(dims)})不一致", file=sys.stderr)
            return 1

    _print_increment_table(dims, series, evidence)

    out_path = args.out or os.path.join(_outputs_dir(), "incremental-eval.png")
    saved = _render_radar(dims, series, title, out_path)
    if saved:
        print(f"\n雷达图已生成:{saved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
