#!/usr/bin/env python3
"""Render a public-web literature guide from a constrained evidence ledger."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote

ALLOWED_DESIGNS = {
    "correlational",
    "cross-sectional",
    "questionnaire",
    "observational",
    "experimental",
    "mixed-methods",
    "qualitative",
    "systematic-review",
    "other",
}
ALLOWED_ROLES = {"background", "method", "contrast", "gap"}
ALLOWED_READING_FOCUS = {"摘要", "方法", "结果", "讨论", "局限"}
NON_CAUSAL_DESIGNS = {
    "correlational",
    "cross-sectional",
    "questionnaire",
    "observational",
    "mixed-methods",
    "qualitative",
    "systematic-review",
    "other",
}
CAUSAL_OVERCLAIM = re.compile(
    r"导致|证明|证实|因果|影响|损伤|损害|受损|缺陷|群体后果|引发|揭示|机制|路径|黏性|心流|即时满足|实证基础|神经证据|实验证据|行为证据|被引|研究者推论|认知资源|表明|提示|会提升|会增加|会降低|会减少|→|⇒|\bcaus(?:e|es|ed|ing)\b|\bleads?\s+to\b|\bimpact(?:s|ed|ing)?\b|\bdamag(?:e|es|ed|ing)\b|\bmechanisms?\b|\bpathways?\b",
    re.IGNORECASE,
)
CORRELATION_SIGNAL = re.compile(r"相关|关联|关系|r\s*=|p\s*=|问卷|量表|得分|横断面", re.IGNORECASE)
UNVERIFIED_COMMENTARY = re.compile(r"(?:\(|（)[^\n)）]*(?:包含|预印本|本科生|高中生|政策建议|非研究论文)[^\n)）]*(?:\)|）)")
CJK_TEXT = re.compile(r"[\u4e00-\u9fff]")
OBSERVATION_SIGNAL = re.compile(
    r"DOI|发表于|收录|作者|样本|参与者|问卷|量表|访谈|任务|EEG|脑电|采用|使用|方法|分析|记录|收集|报告|显示|发现|相关|关联|关系|r\s*=|p\s*=|得分|概率|高于|低于|未支持|未发现|未观察|不显著|显著|学校",
    re.IGNORECASE,
)
DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)

DESIGN_LABELS = {
    "correlational": "相关性研究",
    "cross-sectional": "横断面研究",
    "questionnaire": "问卷研究",
    "observational": "观察性研究",
    "experimental": "实验研究",
    "mixed-methods": "混合方法研究",
    "qualitative": "质性研究",
    "systematic-review": "系统综述",
    "other": "研究设计待进一步核对",
}
ROLE_LABELS = {
    "background": "背景证据",
    "method": "方法借鉴",
    "contrast": "对照材料",
    "gap": "缺口定位",
}
CAUTIONS = {
    "correlational": "只能说明变量在该样本中相关，不能据此推出因果关系或推荐算法造成了注意力变化。",
    "cross-sectional": "只能说明同一时间点的关联，不能判断时间顺序或因果关系。",
    "questionnaire": "依赖自报/量表结果，不能据此推出客观认知损伤或推荐算法的因果效应。",
    "observational": "没有随机分配或受控操纵，不能据此推出因果关系。",
    "experimental": "只支持页面明确描述的样本、任务和操纵；不能自动外推为平台推荐算法的长期因果效应。",
    "mixed-methods": "可说明该样本中的用户假设与观察规律，不等同于平台算法内部的实际运行机制。",
    "qualitative": "可说明受访者经验与解释，不等同于总体规律或平台算法内部机制。",
    "systematic-review": "结论受纳入研究设计与偏倚限制；若原研究多为观察性研究，综述也不自动成为因果证据。",
    "other": "只按官方页面明确显示的内容使用，不补写因果解释或研究设计细节。",
}
QUESTION_PROMPTS = {
    "correlational": "这项关联还需要哪些纵向或实验性证据，才能支持方向或因果判断？",
    "cross-sectional": "还需要哪些纵向证据，才能判断时间顺序并排除反向解释？",
    "questionnaire": "如何用行为任务、日志或其他客观指标复核这项问卷结果？",
    "observational": "哪些混杂因素需要控制，才能缩小其他解释的范围？",
    "experimental": "该样本、任务与操纵能否外推到你的研究对象和真实平台情境？",
    "mixed-methods": "如何把用户假设、观察规律与平台内部算法逻辑分开表述？",
    "qualitative": "还需要哪些样本或量化证据，才能判断这些经验是否具有更广泛适用性？",
    "systematic-review": "纳入研究的设计、样本与偏倚如何限制这篇综述的结论？",
    "other": "还需要核对哪些方法与样本信息，才能确定这条材料可支持的结论范围？",
}


class ValidationError(ValueError):
    pass


def _required_text(value: object, field: str, *, max_length: int = 800) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be a non-empty string")
    text = value.strip()
    if len(text) > max_length:
        raise ValidationError(f"{field} exceeds {max_length} characters")
    return text


def _optional_text(value: object, field: str, *, max_length: int = 300) -> str | None:
    if value is None or value == "":
        return None
    return _required_text(value, field, max_length=max_length)


def _optional_year(value: object, field: str) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    text = _required_text(value, field, max_length=20)
    if not re.fullmatch(r"\d{4}", text):
        raise ValidationError(f"{field} must be a four-digit year or null")
    return text


def _optional_doi(value: object, field: str) -> str | None:
    text = _optional_text(value, field, max_length=200)
    if text is None:
        return None
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/"):
        if text.lower().startswith(prefix):
            text = text[len(prefix) :]
            break
    if not DOI_PATTERN.fullmatch(text):
        raise ValidationError(f"{field} must be a full DOI beginning with 10. or null; do not use an article number or URL suffix")
    return text


def _validate_payload(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValidationError("input must be a JSON object")

    topic = _required_text(payload.get("topic"), "topic", max_length=200)
    course = _optional_text(payload.get("course"), "course", max_length=120)
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= 5:
        raise ValidationError("items must contain 1 to 5 verified sources")

    validation_errors: list[str] = []
    items: list[dict] = []
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            raise ValidationError(f"items[{index}] must be an object")
        title = _required_text(raw.get("title"), f"items[{index}].title", max_length=500)
        item_label = f"items[{index}] '{title}'"
        design = _required_text(raw.get("study_design"), f"items[{index}].study_design", max_length=40)
        if design not in ALLOWED_DESIGNS:
            raise ValidationError(f"items[{index}].study_design is unsupported")
        role = _required_text(raw.get("topic_role"), f"items[{index}].topic_role", max_length=30)
        if role not in ALLOWED_ROLES:
            raise ValidationError(f"items[{index}].topic_role is unsupported")

        facts = raw.get("official_page_facts")
        if not isinstance(facts, list):
            raise ValidationError(f"{item_label}.official_page_facts must be a list")
        if not 1 <= len(facts) <= 4:
            validation_errors.append(f"{item_label} has {len(facts)} official_page_facts; keep 1 to 4")
        clean_facts = [_required_text(fact, f"items[{index}].official_page_facts", max_length=500) for fact in facts]
        for fact in clean_facts:
            if not CJK_TEXT.search(fact):
                validation_errors.append(f"{item_label} facts must be written as neutral Simplified Chinese observations: {fact}")
            else:
                if CAUSAL_OVERCLAIM.search(fact):
                    validation_errors.append(f"{item_label} uses causal/interpretive wording; rewrite it as a direct page observation or association: {fact}")
                if not OBSERVATION_SIGNAL.search(fact):
                    validation_errors.append(f"{item_label} needs a direct observation verb such as 报告/显示/发现/记录/收集: {fact}")
        if design == "experimental" and any(CORRELATION_SIGNAL.search(fact) for fact in clean_facts):
            design = "correlational"

        focus = raw.get("reading_focus")
        if not isinstance(focus, list) or not focus:
            raise ValidationError(f"items[{index}].reading_focus must be a non-empty list")
        clean_focus = []
        for part in focus:
            part_text = _required_text(part, f"items[{index}].reading_focus", max_length=20)
            if part_text not in ALLOWED_READING_FOCUS:
                raise ValidationError(f"items[{index}].reading_focus must use generic labels only")
            if part_text not in clean_focus:
                clean_focus.append(part_text)

        try:
            doi = _optional_doi(raw.get("doi"), f"items[{index}].doi")
        except ValidationError as exc:
            validation_errors.append(f"{item_label}: {exc}")
            doi = None
        official_url = _required_text(raw.get("official_url"), f"items[{index}].official_url", max_length=1000)
        if doi and doi.casefold() not in unquote(official_url).casefold():
            validation_errors.append(
                f"{item_label} DOI must appear literally in official_url; use a DOI resolver/publisher URL containing it or set DOI to null"
            )

        items.append(
            {
                "title": title,
                "first_author": _optional_text(raw.get("first_author"), f"items[{index}].first_author", max_length=120),
                "year": _optional_year(raw.get("year"), f"items[{index}].year"),
                "venue": _optional_text(raw.get("venue"), f"items[{index}].venue", max_length=200),
                "doi": doi,
                "official_url": official_url,
                "study_design": design,
                "topic_role": role,
                "official_page_facts": clean_facts,
                "reading_focus": clean_focus,
            }
        )

    raw_unverified = payload.get("unverified", [])
    if not isinstance(raw_unverified, list) or len(raw_unverified) > 10:
        raise ValidationError("unverified must be a list with at most 10 items")
    unverified: list[dict] = []
    for index, raw in enumerate(raw_unverified, start=1):
        if not isinstance(raw, dict):
            raise ValidationError(f"unverified[{index}] must be an object")
        title = _required_text(raw.get("title"), f"unverified[{index}].title", max_length=500)
        if UNVERIFIED_COMMENTARY.search(title):
            validation_errors.append(f"unverified[{index}].title contains commentary; keep only the exact visible title")
        unverified.append(
            {
                "title": title,
                "url_or_query": _required_text(raw.get("url_or_query"), f"unverified[{index}].url_or_query", max_length=1000),
            }
        )

    if validation_errors:
        raise ValidationError(" | ".join(validation_errors))
    return {"topic": topic, "course": course, "items": items, "unverified": unverified}


def _bibliography(item: dict) -> str:
    author = f"{item['first_author']} et al." if item["first_author"] else "作者列表待核"
    parts = [author]
    if item["venue"]:
        parts.append(item["venue"])
    if item["year"]:
        parts.append(item["year"])
    if item["doi"]:
        parts.append(f"DOI: {item['doi']}")
    return " ｜ ".join(parts)


def render(payload: dict) -> tuple[str, str]:
    lines = [f"# 文献导读：{payload['topic']}", ""]
    if payload["course"]:
        lines.extend([f"**课程/学科**：{payload['course']}", ""])
    lines.extend(
        [
            "> 核验口径：核心条目只使用本轮已打开的官方页面。作者统一使用首位作者 et al. 或标记待核；相关性与因果性分开；搜索结果只作为未核实线索。",
            "",
            "## 核心文献阅读地图",
            "",
        ]
    )

    for index, item in enumerate(payload["items"], start=1):
        lines.extend(
            [
                f"### {index}. 《{item['title']}》",
                "",
                f"- **书目信息**：{_bibliography(item)}",
                f"- **核验状态**：已打开官方页面（{item['official_url']}）",
                f"- **证据类型**：{DESIGN_LABELS[item['study_design']]}",
                f"- **与你选题的关系**：{ROLE_LABELS[item['topic_role']]}",
                "- **官方页面明确显示**：",
            ]
        )
        lines.extend(f"  - {fact}" for fact in item["official_page_facts"])
        lines.extend(
            [
                f"- **不能据此推出**：{CAUTIONS[item['study_design']]}",
                f"- **建议精读**：{' / '.join(item['reading_focus'])}",
            ]
        )
        lines.append(f"- **待检验问题**：{QUESTION_PROMPTS[item['study_design']]}")
        lines.append("")

    designs = "、".join(dict.fromkeys(DESIGN_LABELS[item["study_design"]] for item in payload["items"]))
    lines.extend(
        [
            "## 文献版图小结",
            "",
            f"本组材料覆盖：{designs}。它们可以分别用于建立背景、借鉴方法、形成对照或定位缺口，但不能仅凭排列顺序拼成“算法 → 认知损伤”的因果链。写作时请把每个结论限定在对应官方页面明确显示的证据范围内。",
            "",
        ]
    )

    if payload["unverified"]:
        lines.extend(["## 检索线索（当前未核实）", "", "| 题名或可见片段 | URL / 检索式 | 状态 |", "|---|---|---|"])
        for item in payload["unverified"]:
            lines.append(f"| {item['title']} | {item['url_or_query']} | 未核实 |")
        lines.append("")

    lines.extend(["---", "", "*本文件用于整理阅读路径与证据边界，便于继续查读和完成报告。*", ""])
    summary = (
        f"已生成并呈现 `文献导读.md`：共 {len(payload['items'])} 条本轮已打开官方页面的核心文献。"
        "文件已把作者截断、相关性与因果性、研究设计限制和未核实线索分开标注；请按每条的证据边界使用。"
    )
    return "\n".join(lines), summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    try:
        payload = _validate_payload(json.loads(input_path.read_text(encoding="utf-8")))
        markdown, summary = render(payload)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False))
        return 2

    print(json.dumps({"status": "ok", "output": str(output_path), "safe_chat_summary": summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
