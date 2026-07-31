#!/usr/bin/env python3
"""Evaluate prediction columns without inventing an acceptance criterion."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


def _result(status: str, safe_chat_summary: str, **extra: object) -> None:
    print(
        json.dumps(
            {"status": status, "safe_chat_summary": safe_chat_summary, **extra},
            ensure_ascii=False,
            indent=2,
        )
    )


def _format_number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--reference-column", required=True)
    parser.add_argument("--prediction-column", required=True)
    parser.add_argument("--time-column")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_file():
        _result("error", f"当前无法读取 `{path.name}`。请确认文件已成功上传后重试。")
        return 1

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as error:
        _result("error", f"当前无法解析 `{path.name}`：{type(error).__name__}。请另存为 UTF-8 CSV 后重试。")
        return 1

    required = [args.reference_column, args.prediction_column]
    missing_columns = [name for name in required if name not in fieldnames]
    if missing_columns:
        available = "、".join(f"`{name}`" for name in fieldnames) or "无可识别列"
        missing = "、".join(f"`{name}`" for name in missing_columns)
        _result(
            "needs_input",
            f"`{path.name}` 中没有找到 {missing}。当前列为：{available}。请确认哪一列是参考值、哪一列是模型输出。",
            columns=fieldnames,
        )
        return 0

    valid: list[dict[str, object]] = []
    invalid_rows: list[int] = []
    for row_number, row in enumerate(rows, start=2):
        try:
            reference = float(row[args.reference_column])
            prediction = float(row[args.prediction_column])
        except (TypeError, ValueError):
            invalid_rows.append(row_number)
            continue
        if not math.isfinite(reference) or not math.isfinite(prediction):
            invalid_rows.append(row_number)
            continue
        valid.append(
            {
                "row_number": row_number,
                "reference": reference,
                "prediction": prediction,
                "time": row.get(args.time_column) if args.time_column and args.time_column in fieldnames else None,
            }
        )

    if not valid:
        _result(
            "needs_input",
            f"`{path.name}` 的 `{args.reference_column}` 与 `{args.prediction_column}` 没有可共同计算的数值行。请检查缺失值、文本或单位格式。",
            total_rows=len(rows),
            invalid_rows=invalid_rows,
        )
        return 0

    signed_errors = [float(item["prediction"]) - float(item["reference"]) for item in valid]
    absolute_errors = [abs(value) for value in signed_errors]
    mae = sum(absolute_errors) / len(absolute_errors)
    rmse = math.sqrt(sum(value * value for value in signed_errors) / len(signed_errors))
    mean_signed_error = sum(signed_errors) / len(signed_errors)
    max_index = max(range(len(absolute_errors)), key=absolute_errors.__getitem__)
    max_item = valid[max_index]
    lower_count = sum(value < 0 for value in signed_errors)
    higher_count = sum(value > 0 for value in signed_errors)
    equal_count = len(signed_errors) - lower_count - higher_count

    location = f"CSV 第 {max_item['row_number']} 行"
    if max_item["time"] not in (None, ""):
        location += f"，`{args.time_column}`={max_item['time']}"

    invalid_note = ""
    if invalid_rows:
        invalid_note = f"；另有 {len(invalid_rows)} 行因参考值或预测值不是有限数值而未参与计算"

    summary = (
        f"已读取 `{path.name}`：共 {len(rows)} 行，使用 `{args.reference_column}` 作为暂定参考列、"
        f"`{args.prediction_column}` 作为预测列，{len(valid)} 行参与计算{invalid_note}。\n\n"
        "当前文件中观察到：\n"
        f"- MAE：{_format_number(mae)}\n"
        f"- RMSE：{_format_number(rmse)}\n"
        f"- 最大绝对误差：{_format_number(absolute_errors[max_index])}（{location}）\n"
        f"- 平均有符号误差（预测值 − 参考值）：{_format_number(mean_signed_error)}\n"
        f"- 预测低于 / 高于 / 等于参考值的行数：{lower_count} / {higher_count} / {equal_count}\n\n"
        f"结论边界：在这份文件中，以 `{args.reference_column}` 作为暂定参考时可以得到以上指标；"
        "这些结果只描述当前样本，尚不足以判定模型整体是否有效、准确或达到要求。\n\n"
        "完成判定前请补充：\n"
        f"1. `{args.reference_column}` 的获得方法、误差和校准依据；\n"
        "2. 课程或项目明确采用的验收指标、阈值或对照基线；\n"
        "3. 当前样本是否覆盖独立测试集以及需要代表的温度、工况、个体或时间范围。"
    )

    _result(
        "ok",
        summary,
        file=path.name,
        columns=fieldnames,
        total_rows=len(rows),
        valid_rows=len(valid),
        invalid_rows=invalid_rows,
        metrics={
            "mae": mae,
            "rmse": rmse,
            "max_absolute_error": absolute_errors[max_index],
            "mean_signed_error_prediction_minus_reference": mean_signed_error,
            "prediction_lower_count": lower_count,
            "prediction_higher_count": higher_count,
            "prediction_equal_count": equal_count,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
