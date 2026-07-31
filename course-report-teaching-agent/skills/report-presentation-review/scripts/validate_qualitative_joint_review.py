#!/usr/bin/env python3
"""Fail closed when a qualitative report-video review exceeds current evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?%?")
TIMECODE_RE = re.compile(r"\[\d{1,2}:\d{2}(?:\s*[–—-]\s*\d{1,2}:\d{2})?\]")
LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-_+./][A-Za-z0-9]+)*")

BANNED_LITERALS = (
    "job_id", "任务号", "已复用", "/mnt/", "course-eval", "oral_assessable_dimensions",
    "至少", "不少于", "若干", "多项", "多个", "多处", "几项", "几处", "一系列",
    "一张", "一条", "各补", "各增加", "各添加", "必须", "严重", "最薄弱",
    "偏高", "偏低", "过高", "过低",
    "✅", "❌", "⚠️", "covered", "thin", "absent", "partial",
)
QUALITATIVE_ONLY_LITERALS = ("评分", "得分", "雷达", "PDF", "导出")
UNSUPPORTED_EXTERNAL_PATTERNS = (
    re.compile(r"(?:行业|领域|工程)(?:内|中|常用|通常|普遍|标准|目标|阈值|水平)"),
    re.compile(r"(?:典型|通常|一般|公认|普遍|常见)(?:的|认为|要求|达到|目标|标准|阈值|水平|方法|方案|文献)?"),
    re.compile(r"(?:已有|现有)(?:大量|广泛|成熟|相关)?(?:研究|文献|工作|方法|方案|使用)"),
)
ALLOWED_STRUCTURAL_NUMBERS = {str(value) for value in range(7)} | {"100"}


def _read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _normalise_number(token: str) -> str:
    suffix = "%" if token.endswith("%") else ""
    raw = token[:-1] if suffix else token
    try:
        value = float(raw)
    except ValueError:
        return token
    if value.is_integer():
        raw = str(int(value))
    else:
        raw = (f"{value:.8f}").rstrip("0").rstrip(".")
    return raw + suffix


def _number_variants(text: str) -> set[str]:
    variants: set[str] = set()
    for match in NUMBER_RE.finditer(text):
        token = _normalise_number(match.group())
        variants.add(token)
        suffix = "%" if token.endswith("%") else ""
        raw = token[:-1] if suffix else token
        try:
            value = float(raw)
        except ValueError:
            continue
        variants.add(f"{round(value):.0f}{suffix}")
        variants.add(f"{value:.1f}".rstrip("0").rstrip(".") + suffix)
        variants.add(f"{value:.2f}".rstrip("0").rstrip(".") + suffix)
    return variants


def _latin_tokens(text: str) -> set[str]:
    return {match.group().casefold() for match in LATIN_TOKEN_RE.finditer(text) if len(match.group()) > 1}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--video-evidence", required=True)
    args = parser.parse_args()

    try:
        draft = _read_text(args.draft)
        source = Path(args.source).read_text(encoding="utf-8")
        video = Path(args.video_evidence).read_text(encoding="utf-8")
        json.loads(video)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "error", "issues": [f"input_error:{type(error).__name__}"]}, ensure_ascii=False))
        return 2

    evidence = source + "\n" + video
    allowed_numbers = _number_variants(evidence) | ALLOWED_STRUCTURAL_NUMBERS
    evidence_tokens = _latin_tokens(evidence)
    issues: list[dict[str, str]] = []

    for literal in BANNED_LITERALS + QUALITATIVE_ONLY_LITERALS:
        if literal.casefold() in draft.casefold():
            issues.append({"kind": "banned_literal", "value": literal})

    for pattern in UNSUPPORTED_EXTERNAL_PATTERNS:
        for match in pattern.finditer(draft):
            issues.append({"kind": "unsupported_external_assertion", "value": match.group()})

    without_timecodes = TIMECODE_RE.sub("", draft)
    for match in NUMBER_RE.finditer(without_timecodes):
        token = _normalise_number(match.group())
        if token not in allowed_numbers:
            issues.append({"kind": "ungrounded_number", "value": token})

    for token in sorted(_latin_tokens(draft) - evidence_tokens):
        issues.append({"kind": "ungrounded_latin_term", "value": token})

    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for issue in issues:
        key = (issue["kind"], issue["value"])
        if key not in seen:
            seen.add(key)
            unique.append(issue)

    status = "ok" if not unique else "error"
    print(json.dumps({"status": status, "issues": unique}, ensure_ascii=False, indent=2))
    return 0 if status == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
