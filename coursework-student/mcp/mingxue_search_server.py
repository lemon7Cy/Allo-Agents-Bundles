#!/usr/bin/env python3
"""Minimal stdio MCP bridge for the Mingxue evidence-search API.

The bearer token is received only through the MCP process environment. It is
never returned to the model, logged, or exposed to a generic shell tool.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


API_URL = os.getenv("MINGXUE_SEARCH_URL", "http://221.0.79.251:18091/api/search").strip()
TOOL_NAME = "mingxue_search"
VALID_DATASETS = {"论文", "教材", "课件", "数据"}
VALID_MODES = {"answer", "research"}
MAX_TOP_K = 5
MAX_REFERENCE_SIGNALS = 5
CHUNK_TEXT_LIMIT = 2200
ASSET_TEXT_LIMIT = 1400
REFERENCE_TEXT_LIMIT = 900


def _send(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _result(request_id: Any, result: dict[str, Any]) -> None:
    _send({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id: Any, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def _tool_error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _clip(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…[已裁剪]"


def _safe_rank(value: Any, fallback: int) -> int:
    try:
        rank = int(value)
    except (TypeError, ValueError):
        return fallback
    return rank if rank > 0 else fallback


def _stable_evidence_id(prefix: str, item: dict[str, Any], fallback: int) -> str:
    raw = str(item.get("id") or item.get("chunk_id") or item.get("asset_id") or fallback)
    token = "".join(character for character in raw if character.isalnum())[:10] or str(fallback)
    return f"{prefix}-{token}"


def _markdown_quote(text: str) -> list[str]:
    return [f"> {line}" if line else ">" for line in text.splitlines()]


def _build_safe_outputs(
    *, question: str, requested_dataset: str, chunks: list[dict[str, Any]], assets: list[dict[str, Any]], reference_count: int
) -> tuple[str, str]:
    best_by_document: dict[str, dict[str, Any]] = {}
    for item in chunks:
        document = item["document"]
        existing = best_by_document.get(document)
        if existing is None or (item.get("similarity") or 0) > (existing.get("similarity") or 0):
            best_by_document[document] = item
    direct_entries = list(best_by_document.values())[:MAX_TOP_K]

    lines = [
        f"# 明学知识库证据阅读地图：{question}",
        "",
        f"> 检索库标签：{requested_dataset}。该标签只表示检索库位，不等于正式文档类型。",
        "> 本文件只保留当前检索直接返回的片段和资产；不补齐题名、作者、期刊、年份、DOI，不使用二手参考文献线索。",
        "",
        f"## 直接文档命中（{len(direct_entries)} 个）",
        "",
    ]
    for item in direct_entries:
        lines.extend(
            [
                f"### [{item['evidence_id']}] `{item['document']}`",
                "",
                f"- 检索库标签：{requested_dataset}",
                "- 正式文档类型：未提供",
                "- 作者／期刊／年份／DOI：未结构化确认；不得从文件名推断",
                f"- 命中位置类型：{item['section_type']}",
                f"- 相似度：{item['similarity']}",
                "- 当前可核原文摘录：",
            ]
        )
        lines.extend(_markdown_quote(_clip(item["content"], 900)))
        lines.extend(
            [
                "- 可支撑范围：仅限上述摘录明确陈述的内容",
                "- 局限：当前只有检索片段，不能据此证明全文内容、完整题录、文献类型或未出现的实验结论",
                "- 精读动作：在该知识库文档中定位上述原句，再由学生核对原文上下文",
                "",
            ]
        )

    if assets:
        lines.extend(["## 图表资产线索", ""])
        for item in assets[:3]:
            lines.extend(
                [
                    f"### [{item['evidence_id']}] `{item['document']}`",
                    "",
                    "- 资产原文摘录：",
                    *_markdown_quote(_clip(item["content"], 600)),
                    "- 使用边界：只把摘录中明确出现的标题／图注作为线索，查看原图后再解释趋势",
                    "",
                ]
            )

    lines.extend(
        [
            "## 缺口与下一步",
            "",
            f"- 本次接口另返回 {reference_count} 条参考文献列表信号，但自动证据图不采用这些二手线索。",
            "- 需要完整引用时，请用正式题名在学校数据库、Crossref、Google Scholar 或出版商页面核验题录与原文。",
            "- 学生应根据直接摘录回答：该证据支持什么、不能支持什么、还需要哪项数据或原文位置。",
        ]
    )
    markdown = "\n".join(lines)
    document_names = "；".join(item["document"] for item in direct_entries) or "无"
    chat_summary = (
        f"明学检索完成：当前直接命中 {len(direct_entries)} 个知识库文档（{document_names}）。"
        "题录缺失字段未补齐，参考文献列表信号未作为直接证据。已生成并呈现 `文献导读.md`。"
    )
    return markdown, chat_summary


def _sanitize_search_result(data: dict[str, Any], *, requested_dataset: str, effective_top_k: int) -> dict[str, Any]:
    chunks: list[dict[str, Any]] = []
    for index, item in enumerate(data.get("chunks") or [], start=1):
        if not isinstance(item, dict):
            continue
        rank = _safe_rank(item.get("rank"), index)
        chunks.append(
            {
                "evidence_id": _stable_evidence_id("E", item, rank),
                "classification": "direct_chunk",
                "rank": rank,
                "document": str(item.get("document") or "未提供"),
                "section_type": str(item.get("section_type") or "未提供"),
                "similarity": item.get("similarity"),
                "content": _clip(item.get("content"), 1000),
                "metadata_note": "只可使用 content 中明确出现的题名、作者、年份、期刊、DOI、章节、图表、数据集和数值；不得从 document 文件名推断。",
            }
        )

    assets: list[dict[str, Any]] = []
    for index, item in enumerate(data.get("assets") or [], start=1):
        if not isinstance(item, dict):
            continue
        rank = _safe_rank(item.get("rank"), index)
        assets.append(
            {
                "evidence_id": _stable_evidence_id("A", item, rank),
                "classification": "direct_asset",
                "rank": rank,
                "document": str(item.get("document") or "未提供"),
                "similarity": item.get("similarity"),
                "content": _clip(item.get("content"), 700),
            }
        )

    unique_documents = sorted({item["document"] for item in chunks if item["document"] != "未提供"})
    reference_count = len(data.get("reference_signals") or [])
    safe_markdown, safe_chat_summary = _build_safe_outputs(
        question=str(data.get("question") or ""),
        requested_dataset=requested_dataset,
        chunks=chunks,
        assets=assets,
        reference_count=reference_count,
    )
    return {
        "output_contract": "文献导读任务必须把 safe_markdown 原样写入 /mnt/user-data/outputs/文献导读.md，并在 present_files 后把 safe_chat_summary 原样作为最终回复；不得自行改写、扩展或补充来源。",
        "safe_chat_summary": safe_chat_summary,
        "safe_markdown": safe_markdown,
        "question": str(data.get("question") or ""),
        "requested_dataset": requested_dataset,
        "effective_top_k": effective_top_k,
        "direct_document_hit_count": len(unique_documents),
        "direct_document_hits": unique_documents,
        "chunks": chunks,
        "assets": assets,
        "reference_signal_count_withheld": reference_count,
        "provenance_contract": [
            "直接证据只能引用本响应的 E 或 A 稳定编号。",
            "参考文献列表信号已从自动合成内容中隐藏，不能计入直接文档命中。",
            "不得从文件名推断正式题名、作者、期刊、年份、DOI 或文档类型；缺失字段写未提供。",
            "不得使用历史会话、模型记忆或先前产物补齐任何来源或数值。",
        ],
    }


def _search(arguments: dict[str, Any]) -> dict[str, Any]:
    token = os.getenv("MINGXUE_API_TOKEN", "").strip()
    if not token:
        return _tool_error("明学知识库凭据未配置，请联系管理员配置后重试。不要在对话或命令中粘贴 token。")

    question = str(arguments.get("question") or "").strip()
    if not question:
        return _tool_error("question 不能为空。")

    mode = str(arguments.get("mode") or "answer").strip().lower()
    if mode not in VALID_MODES:
        return _tool_error("mode 仅支持 answer 或 research。")

    dataset = str(arguments.get("dataset") or "论文").strip()
    if dataset not in VALID_DATASETS:
        return _tool_error("dataset 仅支持 论文、教材、课件或数据。")

    try:
        top_k = int(arguments.get("top_k", 5))
    except (TypeError, ValueError):
        return _tool_error("top_k 必须是整数。")
    top_k = max(1, min(top_k, MAX_TOP_K))

    payload = {
        "question": question,
        "top_k": top_k,
        "mode": mode,
        "include_assets": bool(arguments.get("include_assets", dataset == "论文")),
        "dataset": dataset,
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            return _tool_error("明学知识库认证失败，请联系管理员检查预配置凭据。不要尝试打印或测试 token。")
        return _tool_error(f"明学知识库请求失败（HTTP {exc.code}），请稍后重试或回退到公开文献检索。")
    except (OSError, TimeoutError, json.JSONDecodeError) as exc:
        return _tool_error(f"明学知识库暂时不可用（{type(exc).__name__}），请稍后重试或回退到公开文献检索。")

    safe_data = _sanitize_search_result(data, requested_dataset=dataset, effective_top_k=top_k)
    return {
        "content": [{"type": "text", "text": json.dumps(safe_data, ensure_ascii=False)}],
        "isError": False,
    }


def _tools() -> list[dict[str, Any]]:
    return [
        {
            "name": TOOL_NAME,
            "description": (
                "检索明学知识库中的电池、储能、SOC、SOH、RUL、卡尔曼滤波、BMS 等课程证据。"
                "返回可核验的正文片段、论文图表线索和参考文献线索，用于整理阅读路径和证据清单。"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "聚焦的检索问题，避免堆叠过多关键词。"},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": MAX_TOP_K, "default": 4},
                    "mode": {"type": "string", "enum": ["answer", "research"], "default": "answer"},
                    "include_assets": {"type": "boolean", "default": True},
                    "dataset": {"type": "string", "enum": ["论文", "教材", "课件", "数据"], "default": "论文"},
                },
                "required": ["question"],
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True},
        }
    ]


def _handle(message: dict[str, Any]) -> None:
    request_id = message.get("id")
    method = message.get("method")
    if request_id is None:
        return
    if method == "initialize":
        requested = (message.get("params") or {}).get("protocolVersion")
        _result(
            request_id,
            {
                "protocolVersion": requested or "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "mingxue-kb", "version": "1.0.0"},
            },
        )
    elif method == "ping":
        _result(request_id, {})
    elif method == "tools/list":
        _result(request_id, {"tools": _tools()})
    elif method == "tools/call":
        params = message.get("params") or {}
        if params.get("name") != TOOL_NAME:
            _result(request_id, _tool_error("未知工具。"))
        else:
            _result(request_id, _search(params.get("arguments") or {}))
    else:
        _error(request_id, -32601, f"Method not found: {method}")


def main() -> int:
    for raw_line in sys.stdin:
        try:
            message = json.loads(raw_line)
            if isinstance(message, dict):
                _handle(message)
        except json.JSONDecodeError:
            _error(None, -32700, "Parse error")
        except Exception:
            _error(None, -32603, "Internal error")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
