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
QUALITY_LABELS = ("合格", "不合格", "达标", "不达标", "优秀", "良好")
BOOK_TITLE_RE = re.compile(r"《([^》]+)》")
LATIN_EXAMPLE_SOURCE_RE = re.compile(r"(?:如|例如)\s*([A-Z][A-Za-z]+(?:\s*(?:&|and)\s*[A-Z][A-Za-z]+)+)")
ALLOWED_TEXT_NUMBERS = {"0", "1", "2", "3", "4", "5", "6", "100"}
CANONICAL_DIMENSIONS = ("创新性", "数据分析深度", "完整性", "文献引用", "结论合理性", "格式规范性")
QUANTITATIVE_MODES = {"quantitative_six_dimension", "incremental_quantitative"}
QUALITATIVE_MODES = {"qualitative", "incremental_qualitative", "video_only", "report_video_qualitative"}


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


def _benchmark_issues(value: Any, path: tuple[str, ...] = ()) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(_benchmark_issues(item, path + (str(index),)))
    elif isinstance(value, dict):
        for key, item in value.items():
            next_path = path + (str(key),)
            if key == "benchmark":
                issues.append({"path": ".".join(next_path), "kind": "unverified_benchmark", "value": str(item)})
            else:
                issues.extend(_benchmark_issues(item, next_path))
    return issues


def _section_blocks(data: Any) -> list[tuple[int, int, dict[str, Any]]]:
    if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
        return []
    blocks: list[tuple[int, int, dict[str, Any]]] = []
    for section_index, section in enumerate(data["sections"]):
        if not isinstance(section, dict) or not isinstance(section.get("blocks"), list):
            continue
        for block_index, block in enumerate(section["blocks"]):
            if isinstance(block, dict):
                blocks.append((section_index, block_index, block))
    return blocks


def _named_scores(block: dict[str, Any], key: str) -> tuple[list[str], dict[str, float], list[dict[str, str]]]:
    path = f"sections.{key}"
    entries = block.get(key)
    if not isinstance(entries, list):
        return [], {}, [{"path": path, "kind": "invalid_score_structure", "value": "expected_list"}]
    names: list[str] = []
    scores: dict[str, float] = {}
    issues: list[dict[str, str]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            issues.append({"path": f"{path}.{index}", "kind": "invalid_score_entry", "value": "expected_object"})
            continue
        name = entry.get("name")
        score = entry.get("score")
        if not isinstance(name, str) or not name:
            issues.append({"path": f"{path}.{index}.name", "kind": "invalid_dimension_name", "value": str(name)})
            continue
        names.append(name)
        if name in scores:
            issues.append({"path": f"{path}.{index}.name", "kind": "duplicate_dimension", "value": name})
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            issues.append({"path": f"{path}.{index}.score", "kind": "invalid_dimension_score", "value": str(score)})
            continue
        scores[name] = float(score)
    return names, scores, issues


def _quantitative_structure_issues(data: Any) -> list[dict[str, str]]:
    if not isinstance(data, dict):
        return [{"path": "", "kind": "invalid_report_structure", "value": "expected_object"}]

    mode = data.get("evaluation_mode")
    blocks = _section_blocks(data)
    scorecards = [(si, bi, block) for si, bi, block in blocks if block.get("type") == "scorecard"]
    radars = [(si, bi, block) for si, bi, block in blocks if block.get("type") == "radar"]
    has_quantitative_blocks = bool(scorecards or radars)
    quantitative = mode in QUANTITATIVE_MODES or has_quantitative_blocks

    if mode in QUALITATIVE_MODES and has_quantitative_blocks:
        return [{"path": "evaluation_mode", "kind": "qualitative_contains_quantitative_blocks", "value": str(mode)}]
    if not quantitative:
        return []

    issues: list[dict[str, str]] = []
    if len(scorecards) != 1:
        issues.append({"path": "sections", "kind": "quantitative_scorecard_count", "value": str(len(scorecards))})
    if len(radars) != 1:
        issues.append({"path": "sections", "kind": "quantitative_radar_count", "value": str(len(radars))})
    if len(scorecards) != 1 or len(radars) != 1:
        return issues

    score_section, score_block_index, scorecard = scorecards[0]
    radar_section, radar_block_index, radar = radars[0]
    score_names, score_values, score_issues = _named_scores(scorecard, "items")
    radar_names, radar_values, radar_issues = _named_scores(radar, "dimensions")
    issues.extend(score_issues)
    issues.extend(radar_issues)

    expected = list(CANONICAL_DIMENSIONS)
    if score_names != expected:
        issues.append({"path": f"sections.{score_section}.blocks.{score_block_index}.items", "kind": "noncanonical_scorecard_dimensions", "value": "|".join(score_names)})
    if radar_names != expected:
        issues.append({"path": f"sections.{radar_section}.blocks.{radar_block_index}.dimensions", "kind": "noncanonical_radar_dimensions", "value": "|".join(radar_names)})
    if score_values and radar_values and score_values != radar_values:
        issues.append({"path": f"sections.{radar_section}.blocks.{radar_block_index}.dimensions", "kind": "scorecard_radar_mismatch", "value": "scores_differ"})

    sections = data.get("sections")
    if isinstance(sections, list):
        if radar_section != len(sections) - 1:
            issues.append({"path": f"sections.{radar_section}", "kind": "radar_section_not_last", "value": str(radar_section)})
        radar_blocks = sections[radar_section].get("blocks") if isinstance(sections[radar_section], dict) else None
        if isinstance(radar_blocks, list) and radar_block_index != len(radar_blocks) - 1:
            issues.append({"path": f"sections.{radar_section}.blocks.{radar_block_index}", "kind": "radar_block_not_last", "value": str(radar_block_index)})
    return issues


def _unsupported_named_or_quality_issues(data: Any, evidence: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for path, text in _walk_strings(data):
        if path and path[0] == "meta":
            continue
        for label in QUALITY_LABELS:
            if label in text and label not in evidence:
                issues.append({"path": ".".join(path), "kind": "unsupported_quality_label", "value": label})
        for match in BOOK_TITLE_RE.finditer(text):
            title = match.group(1).strip()
            if title and title not in evidence:
                issues.append({"path": ".".join(path), "kind": "ungrounded_named_source", "value": title})
        for match in LATIN_EXAMPLE_SOURCE_RE.finditer(text):
            source = match.group(1).strip()
            if source and source not in evidence:
                issues.append({"path": ".".join(path), "kind": "ungrounded_named_source", "value": source})
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--video-evidence")
    parser.add_argument("--rubric", default=str(Path(__file__).resolve().parent.parent / "rubric.md"))
    parser.add_argument("--allow-benchmark", action="store_true")
    args = parser.parse_args()

    try:
        data = json.loads(Path(args.data).read_text(encoding="utf-8"))
        source = Path(args.source).read_text(encoding="utf-8")
        rubric = Path(args.rubric).read_text(encoding="utf-8")
        video_evidence = Path(args.video_evidence).read_text(encoding="utf-8") if args.video_evidence else ""
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "error", "issues": [f"input_error:{type(error).__name__}"]}, ensure_ascii=False))
        return 2

    evidence = source + "\n" + rubric + ("\n" + video_evidence if video_evidence else "")
    allowed_numbers = _number_variants(evidence) | _score_numbers(data) | ALLOWED_TEXT_NUMBERS
    issues: list[dict[str, str]] = []
    if not args.allow_benchmark:
        issues.extend(_benchmark_issues(data))
    issues.extend(_quantitative_structure_issues(data))
    issues.extend(_unsupported_named_or_quality_issues(data, evidence))

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
