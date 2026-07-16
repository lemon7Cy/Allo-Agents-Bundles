#!/usr/bin/env python3
"""Resolve shorthand or misspelled DFCode department/project names."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable


DIMENSION_KEYS = {
    "department": ("department", "department_name", "name", "label"),
    "project": ("project", "project_name", "name", "label"),
}
GENERIC_SUFFIXES = (
    "事业部门",
    "事业中心",
    "项目中心",
    "项目部门",
    "事业部",
    "项目部",
    "项目组",
    "工作组",
    "办公室",
    "部门",
    "中心",
    "项目",
    "小组",
    "团队",
    "部",
    "组",
)


def normalize_dimension_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).casefold().strip()
    normalized = re.sub(r"[\s\-_/\\·,，.。:：()（）\[\]【】]+", "", normalized)
    previous = None
    while normalized and normalized != previous:
        previous = normalized
        for suffix in GENERIC_SUFFIXES:
            if normalized.endswith(suffix) and len(normalized) > len(suffix):
                normalized = normalized[: -len(suffix)]
                break
    return normalized


def _candidate_name(candidate: Any, dimension: str) -> str:
    if isinstance(candidate, str):
        return candidate
    if not isinstance(candidate, dict):
        return ""
    for key in DIMENSION_KEYS[dimension]:
        value = candidate.get(key)
        if value:
            return str(value)
    return ""


def _score(query: str, candidate: str) -> tuple[float, str]:
    raw_query = unicodedata.normalize("NFKC", query).casefold().strip()
    raw_candidate = unicodedata.normalize("NFKC", candidate).casefold().strip()
    query_norm = normalize_dimension_name(query)
    candidate_norm = normalize_dimension_name(candidate)
    if not query_norm or not candidate_norm:
        return 0.0, "none"
    if raw_query == raw_candidate:
        return 1.0, "exact"
    if query_norm == candidate_norm:
        return 0.98, "normalized"
    if query_norm in candidate_norm or candidate_norm in query_norm:
        shorter = min(len(query_norm), len(candidate_norm))
        longer = max(len(query_norm), len(candidate_norm))
        return 0.90 + (0.06 * shorter / longer), "substring"
    ratio = SequenceMatcher(None, query_norm, candidate_norm).ratio()
    return ratio, "typo" if ratio >= 0.72 else "weak"


def _rank_candidates(
    query: str,
    candidates: Iterable[Any],
    dimension: str,
    threshold: float,
) -> list[dict[str, Any]]:
    ranked = []
    seen = set()
    for candidate in candidates:
        name = _candidate_name(candidate, dimension)
        if not name or name in seen:
            continue
        seen.add(name)
        score, reason = _score(query, name)
        if score >= threshold:
            ranked.append(
                {
                    "dimension": dimension,
                    "name": name,
                    "score": round(score, 4),
                    "reason": reason,
                    "source": candidate,
                }
            )
    ranked.sort(key=lambda item: (-item["score"], len(item["name"]), item["name"]))
    return ranked


def resolve_dimension(
    query: str,
    candidates: Iterable[Any],
    dimension: str = "department",
    *,
    threshold: float = 0.72,
    ambiguity_delta: float = 0.04,
) -> dict[str, Any]:
    if dimension not in DIMENSION_KEYS:
        raise ValueError(f"unsupported dimension: {dimension}")

    ranked = _rank_candidates(query, candidates, dimension, threshold)

    result: dict[str, Any] = {
        "dimension": dimension,
        "query": query,
        "normalized_query": normalize_dimension_name(query),
        "status": "unmatched",
        "selected": None,
        "candidates": ranked[:5],
    }
    if not ranked:
        return result

    best = ranked[0]
    close = [
        item for item in ranked if best["score"] - item["score"] <= ambiguity_delta
    ]
    if len(close) > 1 and best["reason"] != "exact":
        result["status"] = "ambiguous"
        result["candidates"] = close[:5]
        return result

    result["status"] = "matched"
    result["selected"] = best
    return result


def resolve_auto(
    query: str,
    departments: Iterable[Any],
    projects: Iterable[Any],
    *,
    threshold: float = 0.72,
    ambiguity_delta: float = 0.04,
) -> dict[str, Any]:
    ranked = [
        *_rank_candidates(query, departments, "department", threshold),
        *_rank_candidates(query, projects, "project", threshold),
    ]
    ranked.sort(
        key=lambda item: (
            -item["score"],
            len(item["name"]),
            item["dimension"],
            item["name"],
        )
    )
    result: dict[str, Any] = {
        "requested_dimension": "auto",
        "dimension": None,
        "query": query,
        "normalized_query": normalize_dimension_name(query),
        "status": "unmatched",
        "selected": None,
        "candidates": ranked[:5],
    }
    if not ranked:
        return result

    best = ranked[0]
    close = [
        item for item in ranked if best["score"] - item["score"] <= ambiguity_delta
    ]
    if len(close) > 1 and best["reason"] != "exact":
        result["status"] = "ambiguous"
        result["candidates"] = close[:5]
        return result

    result["status"] = "matched"
    result["dimension"] = best["dimension"]
    result["selected"] = best
    return result


def _load_candidate_data(path: str) -> Any:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data


def _load_candidates(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    for key in ("candidates", "departments", "projects", "items", "data"):
        if isinstance(data.get(key), list):
            return data[key]
    raise ValueError(
        "candidate JSON must be a list or contain candidates/departments/projects/items/data"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("candidates_json")
    parser.add_argument(
        "--dimension", choices=["auto", *sorted(DIMENSION_KEYS)], default="auto"
    )
    args = parser.parse_args()
    data = _load_candidate_data(args.candidates_json)
    if args.dimension == "auto":
        if not isinstance(data, dict):
            parser.error(
                "auto mode requires JSON containing departments and projects lists"
            )
        result = resolve_auto(
            args.query,
            data.get("departments") or [],
            data.get("projects") or [],
        )
    else:
        result = resolve_dimension(args.query, _load_candidates(data), args.dimension)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return (
        2
        if result["status"] == "ambiguous"
        else 1
        if result["status"] == "unmatched"
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
