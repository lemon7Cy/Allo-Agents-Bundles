#!/usr/bin/env python3
"""Verify a supplied scholarly citation without turning search failure into nonexistence."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from typing import Any

USER_AGENT = "AlloEducationCitationVerifier/1.0 (mailto:admin@allo.local)"


def _normalize(value: str) -> str:
    return "".join(re.findall(r"[0-9a-z\u3400-\u9fff]+", value.casefold()))


def _similarity(left: str, right: str) -> float:
    a, b = _normalize(left), _normalize(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _get_json(url: str) -> tuple[int | None, dict[str, Any] | None, str | None]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.load(response), None
    except urllib.error.HTTPError as error:
        return error.code, None, None
    except (OSError, TimeoutError, json.JSONDecodeError) as error:
        return None, None, type(error).__name__


def _metadata(message: dict[str, Any]) -> dict[str, Any]:
    title = (message.get("title") or [""])[0]
    authors = []
    for author in message.get("author") or []:
        name = " ".join(part for part in (author.get("given"), author.get("family")) if part)
        if name:
            authors.append(name)
    issued = ((message.get("issued") or {}).get("date-parts") or [[]])[0]
    return {
        "title": title,
        "authors": authors,
        "venue": (message.get("container-title") or [""])[0],
        "year": issued[0] if issued else None,
        "volume": message.get("volume"),
        "issue": message.get("issue"),
        "page": message.get("page") or message.get("article-number"),
        "doi": message.get("DOI"),
        "url": message.get("URL"),
    }


def _safe_response(status: str, metadata: dict[str, Any] | None = None) -> str:
    if status == "verified_match" and metadata:
        authors = "、".join(metadata.get("authors") or []) or "未提供"
        return (
            "核验状态：已核实匹配。\n"
            f"题名：{metadata.get('title') or '未提供'}\n"
            f"作者：{authors}\n"
            f"出处：{metadata.get('venue') or '未提供'}；年份：{metadata.get('year') or '未提供'}；"
            f"卷：{metadata.get('volume') or '未提供'}；期：{metadata.get('issue') or '未提供'}；页码/文章号：{metadata.get('page') or '未提供'}\n"
            f"DOI：{metadata.get('doi') or '未提供'}\n"
            "仅可按以上当前 Crossref 元数据引用；未提供字段不要补猜。"
        )
    if status == "metadata_conflict":
        return (
            "核验状态：元数据冲突。给定 DOI 与题名/作者信息未能对应到同一条 Crossref 记录，"
            "因此不能补全卷期页码，也不要把它写入参考文献；请回到出版商页面或学校数据库核对原始出处。"
        )
    return (
        "核验状态：当前无法核实。Crossref 未返回与给定 DOI/题名匹配的记录；这不能证明论文不存在，"
        "但在核实前不要写入参考文献，也不能补全卷期页码。建议通过出版商页面、学校数据库或 Crossref 再核。"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--doi", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--author", default="")
    parser.add_argument("--venue", default="")
    parser.add_argument("--year", default="")
    args = parser.parse_args()

    doi = args.doi.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    candidate: dict[str, Any] | None = None
    evidence: dict[str, Any] = {"doi_lookup": None, "title_search": None}

    if doi:
        status_code, payload, error = _get_json(
            "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
        )
        evidence["doi_lookup"] = {"http_status": status_code, "error": error}
        if status_code == 200 and payload:
            candidate = _metadata(payload.get("message") or {})

    if candidate is None and args.title.strip():
        query = urllib.parse.urlencode({"query.title": args.title.strip(), "rows": 3, "select": "DOI,title,author,container-title,issued,volume,issue,page,URL"})
        status_code, payload, error = _get_json("https://api.crossref.org/works?" + query)
        items = ((payload or {}).get("message") or {}).get("items") or []
        scored = [(_similarity(args.title, (item.get("title") or [""])[0]), item) for item in items]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        evidence["title_search"] = {
            "http_status": status_code,
            "error": error,
            "best_similarity": scored[0][0] if scored else 0.0,
        }
        if scored and scored[0][0] >= 0.90:
            candidate = _metadata(scored[0][1])

    result_status = "unable_to_verify"
    if candidate is not None:
        title_match = not args.title.strip() or _similarity(args.title, candidate.get("title") or "") >= 0.72
        doi_match = not doi or _normalize(doi) == _normalize(candidate.get("doi") or "")
        venue_match = not args.venue.strip() or _similarity(args.venue, candidate.get("venue") or "") >= 0.55
        year_match = not args.year.strip() or str(candidate.get("year") or "") == args.year.strip()
        result_status = "verified_match" if title_match and doi_match and venue_match and year_match else "metadata_conflict"

    output = {
        "status": result_status,
        "safe_response": _safe_response(result_status, candidate),
        "matched_metadata": candidate,
        "evidence": evidence,
        "rule": "Only verified_match may be added to a reference list. unable_to_verify is not proof of nonexistence.",
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
