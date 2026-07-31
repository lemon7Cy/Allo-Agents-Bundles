#!/usr/bin/env python3
"""Register public-literature fetch URLs and reject duplicate candidates."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

DEFAULT_REGISTRY = Path("/mnt/user-data/tmp/public_literature_fetch_registry.json")
DOI_PATTERN = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)


def _normalized_url(raw_url: str) -> str:
    url = raw_url.strip()
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        raise ValueError("url must be an absolute http(s) URL")
    if parts.username or parts.password:
        raise ValueError("url must not contain credentials")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))


def _candidate_key(url: str) -> str:
    parts = urlsplit(unquote(url))
    path = parts.path
    lowered = path.casefold()
    for marker in ("/doi/full/", "/doi/abs/", "/doi/pdf/", "/doi/epdf/", "/doi/"):
        position = lowered.find(marker)
        if position >= 0:
            candidate = path[position + len(marker) :].strip("/")
            if DOI_PATTERN.fullmatch(candidate):
                return f"doi:{candidate.casefold()}"
    if parts.netloc.casefold() in {"doi.org", "dx.doi.org"}:
        candidate = path.strip("/")
        if DOI_PATTERN.fullmatch(candidate):
            return f"doi:{candidate.casefold()}"
    match = DOI_PATTERN.search(path)
    if match:
        candidate = match.group(0)
        for suffix in ("/full", "/abs", "/pdf", "/epdf", "/abstract"):
            if candidate.casefold().endswith(suffix):
                candidate = candidate[: -len(suffix)]
                break
        return f"doi:{candidate.casefold()}"
    return f"url:{url.casefold()}"


def _load(path: Path) -> dict:
    if not path.is_file():
        return {"urls": [], "candidate_keys": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("fetch registry must be a JSON object")
    urls = payload.get("urls", [])
    candidate_keys = payload.get("candidate_keys", [])
    if not isinstance(urls, list) or not isinstance(candidate_keys, list):
        raise TypeError("fetch registry lists are invalid")
    return {"urls": urls, "candidate_keys": candidate_keys}


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--reset", action="store_true")
    group.add_argument("--url")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    args = parser.parse_args()

    args.registry.parent.mkdir(parents=True, exist_ok=True)
    if args.reset:
        payload = {"urls": [], "candidate_keys": []}
        args.registry.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"status": "ok", "registry": str(args.registry)}, ensure_ascii=False))
        return 0

    try:
        url = _normalized_url(args.url)
        candidate_key = _candidate_key(url)
        payload = _load(args.registry)
        if url in payload["urls"]:
            raise ValueError("duplicate URL; do not call web_fetch again")
        if candidate_key in payload["candidate_keys"]:
            raise ValueError("duplicate DOI/title candidate; use the first opened page or choose another paper")
        payload["urls"].append(url)
        payload["candidate_keys"].append(candidate_key)
        args.registry.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except (OSError, TypeError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False))
        return 2

    print(json.dumps({"status": "ok", "url": url, "candidate_key": candidate_key}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
