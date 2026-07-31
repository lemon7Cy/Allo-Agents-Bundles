#!/usr/bin/env python3
"""Validate that a customer-visible course review uses production-ready language."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


BLOCKED_TERMS = (
    "job_id",
    "任务号",
    "已复用",
    "/mnt/",
    "course-eval",
    "MVP",
    "同一把尺子",
    "我的进度",
    "P0",
    "P1",
    "P2",
    "rubic.md",
    "rubric.md",
    "自查锚点",
    "弱档",
    "中档",
    "强档",
    "至少",
    "不少于",
    "若干",
    "多项",
    "多个",
    "多处",
    "几项",
    "几处",
    "一系列",
    "一张",
    "一条",
    "各补",
    "各增加",
    "各添加",
    "必须",
    "严重",
    "最薄弱",
    "完全套模板",
    "直接暴露",
    "几乎为零",
    "断链",
    "✅",
    "❌",
    "⚠️",
)
HYPOTHETICAL_VALUE_RE = re.compile(
    r"(?:如|例如|比如)[^。；\n]{0,48}(?:x0|x₀|初值|阈值|容许误差|分钟|篇|张|项)[^。；\n]{0,24}\d",
    re.IGNORECASE,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft", required=True)
    args = parser.parse_args()

    try:
        text = Path(args.draft).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(json.dumps({"status": "error", "issues": [f"input_error:{type(error).__name__}"]}, ensure_ascii=False))
        return 2

    issues: list[dict[str, str]] = []
    for term in BLOCKED_TERMS:
        if term in text:
            issues.append({"kind": "blocked_visible_term", "value": term})
    for match in HYPOTHETICAL_VALUE_RE.finditer(text):
        issues.append({"kind": "invented_hypothetical_value", "value": match.group()})

    status = "ok" if not issues else "error"
    print(json.dumps({"status": status, "issues": issues}, ensure_ascii=False, indent=2))
    return 0 if status == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
