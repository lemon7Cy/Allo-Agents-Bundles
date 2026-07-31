#!/usr/bin/env python3
"""Render topic candidates from a constrained, evidence-aware JSON ledger."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ALLOWED_DIFFICULTY = {"low", "medium", "high"}
ALLOWED_STATUS = {
    "stated-available",
    "needs-inspection",
    "needs-derivation",
    "missing-or-external",
}
STATUS_LABELS = {
    "stated-available": "用户本轮已说明可用",
    "needs-inspection": "需读取原始材料确认",
    "needs-derivation": "需在验证后计算或构造",
    "missing-or-external": "当前缺失或需外部补充",
}
DIFFICULTY_LABELS = {"low": "低", "medium": "中", "high": "高"}
UNSUPPORTED_CLAIM = re.compile(
    r"多数(?:课程)?报告|普遍|近期文献|文献中|研究较少|研究空白|最稳|最佳|最好|最高|高分|角度最新|投入产出比最高|充足|足够|适中|必然|肯定|首选",
    re.IGNORECASE,
)
DOI_OR_CITATION = re.compile(
    r"\b10\.\d{4,9}/\S+|\bet\s+al\.|\b[A-Z][A-Za-z'’-]+\s*[,(]?\s*(?:19|20)\d{2}\b",
    re.IGNORECASE,
)
INSPECTION_SIGNAL = re.compile(
    r"真值|ground\s*truth|完整|连续|范围|覆盖|质量|分布|温度变化|计算资源|训练|测试|OCV|等效电路|模型参数|噪声协方差|充放电周期|倍率|工况|采样|缺失|异常",
    re.IGNORECASE,
)
DIRECT_OCV_STEP = re.compile(r"从(?:CSV|数据).*拟合.*OCV[-–— ]?SOC|拟合.*OCV[-–— ]?SOC.*(?:CSV|数据)", re.IGNORECASE)
UNVERIFIED_TRUTH_STEP = re.compile(r"(?:以|将)\s*`?soc_reference`?\s*(?:作为|为)\s*真值", re.IGNORECASE)
UNVERIFIED_EXTERNAL_SOURCE = re.compile(
    r"OpenStreetMap|\bOSM\b|\bGTFS\b|Citi\s*Bike|Divvy|公开数据集|开放数据|开源(?:GIS|数据)?平台|交通部门公开|文献值|教材中的?标准案例",
    re.IGNORECASE,
)


class ValidationError(ValueError):
    pass


def _text(value: object, field: str, *, max_length: int = 600) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be a non-empty string")
    result = " ".join(value.strip().split())
    if len(result) > max_length:
        raise ValidationError(f"{field} exceeds {max_length} characters")
    return result


def _safe_text(value: object, field: str, normalizations: list[str], *, fallback: str, max_length: int = 600) -> str:
    text = _text(value, field, max_length=max_length)
    if UNSUPPORTED_CLAIM.search(text) or DOI_OR_CITATION.search(text):
        normalizations.append(f"{field}: replaced unsupported ranking, prevalence, or citation claim")
        return fallback
    return text


def _safe_list(
    value: object,
    field: str,
    normalizations: list[str],
    *,
    fallback: str,
    minimum: int = 1,
    maximum: int = 6,
) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ValidationError(f"{field} must contain at least {minimum} item(s)")
    results = [
        _safe_text(item, field, normalizations, fallback=fallback, max_length=500)
        for item in value[:maximum]
    ]
    if len(value) > maximum:
        normalizations.append(f"{field}: kept the first {maximum} items")
    return results


def validate(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValidationError("input must be a JSON object")
    normalizations: list[str] = []
    course = _safe_text(payload.get("course"), "course", normalizations, fallback="课程信息待确认", max_length=160)
    interest = _safe_text(payload.get("interest"), "interest", normalizations, fallback="兴趣方向待确认", max_length=240)
    requirements = _safe_list(
        payload.get("requirements"),
        "requirements",
        normalizations,
        fallback="该要求需结合课程任务书确认。",
        maximum=8,
    )

    dataset = payload.get("dataset")
    if not isinstance(dataset, dict):
        raise ValidationError("dataset must be an object")
    inspected = dataset.get("inspected")
    if not isinstance(inspected, bool):
        raise ValidationError("dataset.inspected must be true or false")
    dataset_description = _safe_text(
        dataset.get("description"),
        "dataset.description",
        normalizations,
        fallback="数据说明待确认",
        max_length=300,
    )
    raw_fields = dataset.get("fields", [])
    if not isinstance(raw_fields, list) or not all(isinstance(field, str) and field.strip() for field in raw_fields):
        raise ValidationError("dataset.fields must be a string list")
    fields = list(dict.fromkeys(field.strip() for field in raw_fields))[:30]

    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list) or not 3 <= len(raw_candidates) <= 5:
        raise ValidationError("candidates must contain 3 to 5 items")
    candidates = []
    for index, raw in enumerate(raw_candidates, start=1):
        if not isinstance(raw, dict):
            raise ValidationError(f"candidates[{index}] must be an object")
        label = f"candidates[{index}]"
        title = _safe_text(raw.get("title"), f"{label}.title", normalizations, fallback=f"候选方向 {index}", max_length=240)
        course_fit = _safe_text(
            raw.get("course_fit"),
            f"{label}.course_fit",
            normalizations,
            fallback="需对照课程要求进一步确认匹配点。",
        )
        differentiation = _safe_text(
            raw.get("differentiation"),
            f"{label}.differentiation",
            normalizations,
            fallback="从当前数据、比较条件或评价维度中形成自己的切入点。",
        )
        difficulty = _text(raw.get("difficulty"), f"{label}.difficulty", max_length=20)
        if difficulty not in ALLOWED_DIFFICULTY:
            raise ValidationError(f"{label}.difficulty is unsupported")

        raw_data = raw.get("data_requirements")
        if not isinstance(raw_data, list) or not raw_data:
            raise ValidationError(f"{label}.data_requirements must be a non-empty list")
        data_requirements = []
        for data_index, item in enumerate(raw_data[:8], start=1):
            if not isinstance(item, dict):
                raise ValidationError(f"{label}.data_requirements[{data_index}] must be an object")
            status = _text(item.get("status"), f"{label}.data_requirements[{data_index}].status", max_length=30)
            if status not in ALLOWED_STATUS:
                raise ValidationError(f"{label}.data_requirements[{data_index}].status is unsupported")
            safe_item = _safe_text(
                item.get("item"),
                f"{label}.data_requirements[{data_index}].item",
                normalizations,
                fallback="该数据条件待确认",
                max_length=240,
            )
            safe_basis = _safe_text(
                item.get("basis"),
                f"{label}.data_requirements[{data_index}].basis",
                normalizations,
                fallback="当前材料未提供可核依据。",
                max_length=300,
            )
            if not inspected and UNVERIFIED_EXTERNAL_SOURCE.search(safe_basis):
                normalizations.append(f"{label}.data_requirements[{data_index}].basis: removed an unverified external source")
                if status == "needs-derivation":
                    safe_basis = "当前材料未提供；需在明确假设和依据后构造，并记录来源与适用范围。"
                else:
                    safe_basis = "当前材料未提供来源；需先检索并核验授权、字段、时间范围和可用性。"
            if not inspected and status == "stated-available" and INSPECTION_SIGNAL.search(f"{safe_item} {safe_basis}"):
                normalizations.append(
                    f"{label}.data_requirements[{data_index}]: downgraded an uninspected property to needs-inspection"
                )
                status = "needs-inspection"
                safe_basis = "用户仅说明了字段或行数；该性质需读取原始文件后确认。"
            data_requirements.append({"item": safe_item, "status": status, "basis": safe_basis})

        method_steps = _safe_list(
            raw.get("method_steps"),
            f"{label}.method_steps",
            normalizations,
            fallback="该步骤需结合实际材料确认。",
            maximum=6,
        )
        if not inspected:
            for step_index, step in enumerate(method_steps):
                if UNVERIFIED_EXTERNAL_SOURCE.search(step):
                    normalizations.append(f"{label}.method_steps: removed an unverified external source")
                    method_steps[step_index] = "先确定并核验可获取的数据格式、字段、授权和样本范围，再进入建模与分析。"
                elif DIRECT_OCV_STEP.search(step):
                    normalizations.append(f"{label}.method_steps: replaced direct OCV-SOC derivation from uninspected data")
                    method_steps[step_index] = (
                        "先确认数据是否包含可用于 OCV-SOC 关系识别的静置或低电流片段；否则补充外部曲线或调整该方法。"
                    )
                elif UNVERIFIED_TRUTH_STEP.search(step):
                    normalizations.append(f"{label}.method_steps: replaced unverified soc_reference ground-truth claim")
                    method_steps[step_index] = "先核对 `soc_reference` 的来源与误差，再决定它是否可作为评价基准。"

        candidates.append(
            {
                "title": title,
                "course_fit": course_fit,
                "differentiation": differentiation,
                "data_requirements": data_requirements,
                "method_steps": method_steps,
                "difficulty": difficulty,
                "difficulty_basis": _safe_list(
                    raw.get("difficulty_basis"),
                    f"{label}.difficulty_basis",
                    normalizations,
                    fallback="工作量需结合实际数据和工具条件确认。",
                    maximum=4,
                ),
                "risks": _safe_list(
                    raw.get("risks"),
                    f"{label}.risks",
                    normalizations,
                    fallback="该风险需读取原始材料后复核。",
                    maximum=4,
                ),
                "go_no_go_checks": _safe_list(
                    raw.get("go_no_go_checks"),
                    f"{label}.go_no_go_checks",
                    normalizations,
                    fallback="先核对现有材料是否满足该条件。",
                    maximum=4,
                ),
            }
        )

    return {
        "course": course,
        "interest": interest,
        "requirements": requirements,
        "dataset": {"description": dataset_description, "inspected": inspected, "fields": fields},
        "candidates": candidates,
        "normalizations": normalizations,
    }


def render(payload: dict) -> tuple[str, str]:
    def cell(value: str) -> str:
        return value.replace("|", "\\|")

    lines = ["# 课程报告选题候选", "", f"**课程**：{payload['course']}  ", f"**兴趣方向**：{payload['interest']}  "]
    dataset = payload["dataset"]
    lines.append(f"**数据说明**：{dataset['description']}  ")
    if dataset["fields"]:
        lines.append(f"**已说明字段**：{', '.join(f'`{field}`' for field in dataset['fields'])}  ")
    if not dataset["inspected"]:
        lines.extend(["", "> 当前仅依据用户本轮描述，尚未读取原始数据文件；所有分布、质量和可行性判断均需在上传后复核。"])
    lines.extend(["", "## 课程要求", ""])
    lines.extend(f"- {item}" for item in payload["requirements"])

    for index, candidate in enumerate(payload["candidates"], start=1):
        lines.extend(
            [
                "",
                f"## 候选 {index}｜{candidate['title']}",
                "",
                f"- **课程匹配**：{candidate['course_fit']}",
                f"- **差异化切入点**：{candidate['differentiation']}",
                f"- **难度**：{DIFFICULTY_LABELS[candidate['difficulty']]}",
                "",
                "### 数据与前置条件",
                "",
                "| 条件 | 当前状态 | 依据 |",
                "|---|---|---|",
            ]
        )
        for item in candidate["data_requirements"]:
            lines.append(f"| {cell(item['item'])} | {STATUS_LABELS[item['status']]} | {cell(item['basis'])} |")
        lines.extend(["", "### 方法步骤", ""])
        lines.extend(f"{step_index}. {step}" for step_index, step in enumerate(candidate["method_steps"], start=1))
        lines.extend(["", "### 工作量依据", ""])
        lines.extend(f"- {item}" for item in candidate["difficulty_basis"])
        lines.extend(["", "### 主要风险", ""])
        lines.extend(f"- {item}" for item in candidate["risks"])
        lines.extend(["", "### 进入该方向前先检查", ""])
        lines.extend(f"- [ ] {item}" for item in candidate["go_no_go_checks"])

    lines.extend(
        [
            "",
            "## 下一步选择",
            "",
            "请先选择你更愿意投入的方向，再上传原始数据或任务书核对前置条件；候选之间没有预设排名。",
            "",
        ]
    )
    titles = "；".join(candidate["title"] for candidate in payload["candidates"])
    summary = (
        f"已整理 {len(payload['candidates'])} 个候选方向：{titles}。"
        "候选没有预设排名；请先按兴趣和课程覆盖选择一到两个，再核验数据来源与前置条件。"
        "完整对比已生成到 `选题候选.md`，可直接下载。"
    )
    return "\n".join(lines), summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        payload = validate(json.loads(Path(args.input).read_text(encoding="utf-8")))
        markdown, summary = render(payload)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown, encoding="utf-8")
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "status": "ok",
                "output": args.output,
                "safe_chat_summary": summary,
                "normalizations": payload["normalizations"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
