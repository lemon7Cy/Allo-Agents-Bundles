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


def _print_increment_table(dims: list[str], series: dict[str, list[float]], evidence: dict[str, str]) -> None:
    names = list(series.keys())
    has_pair = len(names) >= 2
    base_name, final_name = (names[0], names[-1]) if has_pair else (names[0], names[0])
    base, final = series[base_name], series[final_name]

    print("\n### 六维增量评价")
    header = "| 维度 | " + " | ".join(names)
    if has_pair:
        header += " | 增量(Δ) |"
    else:
        header += " |"
    print(header)
    print("|" + "---|" * (len(names) + (2 if has_pair else 1)))
    for i, dim in enumerate(dims):
        row = f"| {dim} | " + " | ".join(str(series[n][i]) for n in names)
        if has_pair:
            delta = final[i] - base[i]
            row += f" | {'+' if delta >= 0 else ''}{delta} |"
        else:
            row += " |"
        print(row)
    # totals
    total_row = "| **合计/均值** | " + " | ".join(f"{sum(series[n]) / len(dims):.1f}" for n in names)
    if has_pair:
        total_delta = (sum(final) - sum(base)) / len(dims)
        total_row += f" | {'+' if total_delta >= 0 else ''}{total_delta:.1f} |"
    else:
        total_row += " |"
    print(total_row)

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


def _render_radar(dims: list[str], series: dict[str, list[float]], title: str, out_path: str) -> str | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception as exc:  # matplotlib not installed → degrade
        print(f"\n(雷达图已跳过：{exc};增量表如上,可 `pip install matplotlib` 后重渲染)")
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
