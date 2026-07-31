#!/usr/bin/env python3
"""Reject common unsupported claims before a course evaluation is rendered."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?%?")
EXTERNAL_ASSERTION_PATTERNS = (
    re.compile(r"(?:行业|领域|工程)(?:内|中|常用|通常|普遍|标准|目标|阈值)"),
    re.compile(r"(?:通常|一般|公认)(?:要求|认为|达到|目标|标准|阈值)"),
    re.compile(r"(?:至少|不少于|不低于|≥|>=)\s*\d+\s*(?:篇|处|条|个)"),
)
REMEMBERED_DATASET_TERMS = ("NASA", "PCoE")
ALLOWED_TEXT_NUMBERS = {"0", "1", "2", "3", "4", "5", "6", "100"}


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


def _walk_strings(value: Any, path: tuple[str, ...] = ()):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_strings(item, path + (str(index),))
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_strings(item, path + (str(key),))


def _score_numbers(value: Any) -> set[str]:
    allowed: set[str] = set()
    if isinstance(value, list):
        for item in value:
            allowed.update(_score_numbers(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in {"score", "max"} and isinstance(item, (int, float)):
                allowed.add(_normalise_number(str(item)))
            else:
                allowed.update(_score_numbers(item))
    return allowed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--rubric", required=True)
    args = parser.parse_args()

    try:
        data = json.loads(Path(args.data).read_text(encoding="utf-8"))
        source = Path(args.source).read_text(encoding="utf-8")
        rubric = Path(args.rubric).read_text(encoding="utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "error", "issues": [f"input_error:{type(error).__name__}"]}, ensure_ascii=False))
        return 2

    evidence = source + "\n" + rubric
    allowed_numbers = _number_variants(evidence) | _score_numbers(data) | ALLOWED_TEXT_NUMBERS
    issues: list[dict[str, str]] = []

    for path, text in _walk_strings(data):
        if path and path[0] == "meta":
            continue
        for match in NUMBER_RE.finditer(text):
            token = _normalise_number(match.group())
            if token not in allowed_numbers:
                issues.append({"path": ".".join(path), "kind": "ungrounded_number", "value": token})
        for pattern in EXTERNAL_ASSERTION_PATTERNS:
            for match in pattern.finditer(text):
                phrase = match.group()
                if phrase not in evidence:
                    issues.append({"path": ".".join(path), "kind": "unsupported_external_assertion", "value": phrase})
        for term in REMEMBERED_DATASET_TERMS:
            if term in text and term not in evidence:
                issues.append({"path": ".".join(path), "kind": "ungrounded_dataset", "value": term})

    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in issues:
        key = (issue["path"], issue["kind"], issue["value"])
        if key not in seen:
            seen.add(key)
            unique.append(issue)

    status = "ok" if not unique else "error"
    print(json.dumps({"status": status, "issues": unique}, ensure_ascii=False, indent=2))
    return 0 if status == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
