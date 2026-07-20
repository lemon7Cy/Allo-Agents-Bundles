#!/usr/bin/env python3
import json
import math
import sys
from datetime import date
from decimal import Decimal, DecimalException, localcontext
from pathlib import Path


VALIDATION_FIELDS = (
    "metric",
    "scope_type",
    "scope_value",
    "timezone",
    "cutoff_hour",
    "population_mode",
    "group_by",
    "date_semantics",
)
UNASSIGNED_DEPARTMENTS = {"未设置", "未分配", "无部门", "none", "null"}
PLACEHOLDER_DEPARTMENTS = {"maas-migration-smoke", "placeholder", "test", "测试"}
STAFF_STATUSES = {"active", "staff", "employee", "employed", "在职", "正式员工"}
METRIC_LABELS = {"requests": "请求次数", "tokens": "Token 用量"}


class ScopeValidationError(ValueError):
    pass


def _integer_digit_limit():
    getter = getattr(sys, "get_int_max_str_digits", None)
    return getter() if getter is not None else 0


def _int_is_safely_serializable(value):
    limit = _integer_digit_limit()
    return limit == 0 or abs(value) < 10**limit


def _parse_json_integer(literal):
    digits = literal.lstrip("-")
    limit = _integer_digit_limit()
    try:
        if limit and len(digits) > limit:
            return Decimal(literal)
        return int(literal)
    except (DecimalException, ValueError, OverflowError) as exc:
        raise ScopeValidationError("invalid JSON integer") from exc


def _normalize_text(value):
    return " ".join(str(value or "").strip().split())


def _normalize_department(value):
    return _normalize_text(value)


def _string(value, context, allow_empty=False):
    if not isinstance(value, str):
        raise ScopeValidationError("%s must be a string" % context)
    normalized = _normalize_text(value)
    if not allow_empty and not normalized:
        raise ScopeValidationError("%s is required" % context)
    return normalized


def _normalized_metadata(source):
    if not isinstance(source, dict):
        raise ScopeValidationError("comparison metadata must be an object")
    return {
        "metric": _string(source.get("metric"), "metric").lower(),
        "scope_type": _string(source.get("scope_type"), "scope_type").lower(),
        "scope_value": _string(source.get("scope_value"), "scope_value"),
        "timezone": _string(source.get("timezone"), "timezone"),
        "cutoff_hour": source.get("cutoff_hour"),
        "population_mode": _string(
            source.get("population_mode"), "population_mode"
        ).lower(),
        "group_by": _string(source.get("group_by"), "group_by").lower(),
        "date_semantics": _string(
            source.get("date_semantics"), "date_semantics"
        ).lower(),
    }


def _iso_date(value, context):
    if not isinstance(value, str):
        raise ScopeValidationError("%s must be an ISO date (YYYY-MM-DD)" % context)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ScopeValidationError(
            "%s must be an ISO date (YYYY-MM-DD)" % context
        ) from exc
    if parsed.isoformat() != value:
        raise ScopeValidationError("%s must be an ISO date (YYYY-MM-DD)" % context)
    return parsed


def _validate_comparison(comparison, periods):
    expected = _normalized_metadata(comparison)
    if expected["cutoff_hour"] is None:
        raise ScopeValidationError("comparison.cutoff_hour is required")
    if expected["scope_type"] not in {"department", "organization"}:
        raise ScopeValidationError("scope_type must be department or organization")
    if expected["metric"] not in METRIC_LABELS:
        raise ScopeValidationError("metric must be requests or tokens")
    if expected["population_mode"] != "fixed_roster_snapshot":
        raise ScopeValidationError("population_mode must be fixed_roster_snapshot")
    if expected["group_by"] != "user":
        raise ScopeValidationError("group_by must be user")
    if expected["date_semantics"] != "calendar_date_inclusive":
        raise ScopeValidationError("date_semantics must be calendar_date_inclusive")
    if (
        isinstance(expected["cutoff_hour"], bool)
        or not isinstance(expected["cutoff_hour"], int)
        or not 0 <= expected["cutoff_hour"] <= 23
    ):
        raise ScopeValidationError("cutoff_hour must be an integer from 0 to 23")
    if not periods:
        raise ScopeValidationError("periods must contain at least one period")

    inclusive_duration = None
    labels = set()
    previous_start = None
    previous_end = None
    for index, period in enumerate(periods):
        if not isinstance(period, dict):
            raise ScopeValidationError("period %d must be an object" % (index + 1))
        label = _string(period.get("label"), "period label")
        if label in labels:
            raise ScopeValidationError("duplicate period label: %s" % label)
        labels.add(label)
        actual = _normalized_metadata(period)
        for field in VALIDATION_FIELDS:
            if actual[field] != expected[field]:
                label = _normalize_text(period.get("label")) or "period %d" % (
                    index + 1
                )
                raise ScopeValidationError(
                    "%s mismatch for %s: expected %r, got %r"
                    % (field, label, expected[field], actual[field])
                )
        start = _iso_date(period.get("from"), "period %d from" % (index + 1))
        end = _iso_date(period.get("to"), "period %d to" % (index + 1))
        if start > end:
            raise ScopeValidationError(
                "period %d from must be on or before to" % (index + 1)
            )
        if previous_start is not None and start <= previous_start:
            raise ScopeValidationError(
                "periods must be in strictly increasing chronological order"
            )
        if previous_end is not None and start <= previous_end:
            raise ScopeValidationError("periods must not overlap")
        duration = (end - start).days + 1
        if inclusive_duration is None:
            inclusive_duration = duration
        elif duration != inclusive_duration:
            raise ScopeValidationError(
                "period %d inclusive duration mismatch: expected %d days, got %d"
                % (index + 1, inclusive_duration, duration)
            )
        previous_start = start
        previous_end = end
    return expected


def _department_category(department):
    if not department:
        return "empty_department"
    lowered = department.casefold()
    if lowered in {value.casefold() for value in UNASSIGNED_DEPARTMENTS}:
        return "placeholder_department"
    if lowered in {value.casefold() for value in PLACEHOLDER_DEPARTMENTS}:
        return "placeholder_department"
    return None


def _select_population(roster, metadata):
    selected = {}
    exclusions = {
        "empty_department": 0,
        "non_staff": 0,
        "out_of_scope": 0,
        "placeholder_department": 0,
    }
    target = metadata["scope_value"]
    seen_user_ids = set()
    normalized_members = []
    for index, member in enumerate(roster):
        if not isinstance(member, dict):
            raise ScopeValidationError(
                "roster member %d must be an object" % (index + 1)
            )
        user_id = _string(member.get("user_id"), "roster user_id")
        _string(member.get("name", ""), "roster name", allow_empty=True)
        _string(member.get("department"), "roster department", allow_empty=True)
        _string(member.get("employment_status"), "roster employment_status")
        if user_id in seen_user_ids:
            raise ScopeValidationError("duplicate roster user_id: %s" % user_id)
        seen_user_ids.add(user_id)
        normalized_members.append((member, user_id))

    for member, user_id in normalized_members:
        department = _string(
            member.get("department"), "roster department", allow_empty=True
        )
        category = _department_category(department)
        if category:
            exclusions[category] += 1
            continue
        status = _string(
            member.get("employment_status"), "roster employment_status"
        ).casefold()
        if status not in {value.casefold() for value in STAFF_STATUSES}:
            exclusions["non_staff"] += 1
            continue
        if metadata["scope_type"] == "department" and department != target:
            exclusions["out_of_scope"] += 1
            continue
        selected[user_id] = {
            "user_id": user_id,
            "name": _string(member.get("name", ""), "roster name", allow_empty=True)
            or user_id,
            "department": department,
        }
    if not selected:
        raise ScopeValidationError("fixed roster snapshot contains no in-scope staff")
    return selected, exclusions


def _metric_value(value, metric, context):
    if metric == "requests":
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ScopeValidationError(
                "%s requests must be a nonnegative integer" % context
            )
        if not _int_is_safely_serializable(value):
            raise ScopeValidationError(
                "%s requests must be a nonnegative integer; value exceeds JSON digit limit"
                % context
            )
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ScopeValidationError(
            "%s tokens must be a nonnegative finite number" % context
        )
    if isinstance(value, Decimal):
        if not value.is_finite() or value < 0:
            raise ScopeValidationError(
                "%s tokens must be a nonnegative finite number" % context
            )
        return value
    if isinstance(value, int):
        if value < 0:
            raise ScopeValidationError(
                "%s tokens must be a nonnegative finite number" % context
            )
        return Decimal(value)
    if not math.isfinite(value) or value < 0:
        raise ScopeValidationError(
            "%s tokens must be a nonnegative finite number" % context
        )
    return Decimal(str(value))


def _decimal_precision(values):
    decimals = [value for value in values if isinstance(value, Decimal)]
    if not decimals:
        return 30
    integer_digits = max(max(value.adjusted() + 1, 1) for value in decimals)
    fractional_digits = max(
        max(-int(value.as_tuple().exponent), 0) for value in decimals
    )
    return max(integer_digits + fractional_digits + 10, 30)


def _sum_metric(values, metric):
    if metric == "requests":
        return sum(values)
    with localcontext() as context:
        context.prec = _decimal_precision(values)
        return sum(values, Decimal(0))


def _subtract_metric(current, previous, metric):
    if metric == "requests":
        return current - previous
    with localcontext() as context:
        context.prec = _decimal_precision((current, previous))
        return current - previous


def _json_metric_number(value, metric):
    if metric == "requests":
        return value
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ScopeValidationError("token result must be a finite Decimal")
    if value == value.to_integral_value():
        plain = format(value, "f")
        limit = _integer_digit_limit()
        digit_count = len(plain.lstrip("-"))
        if limit == 0 or digit_count <= limit:
            return int(value)
        return plain
    return format(value, "f")


def _period_result(period, metric, population):
    zero = 0 if metric == "requests" else Decimal(0)
    values = {user_id: zero for user_id in population}
    excluded_rows = 0
    seen = set()
    rows = period.get("rows")
    if not isinstance(rows, list):
        raise ScopeValidationError("period rows must be an array")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ScopeValidationError("period row %d must be an object" % (index + 1))
        user_id = _string(row.get("user_id"), "period row user_id")
        if user_id in seen:
            raise ScopeValidationError(
                "duplicate user_id %s in period %s" % (user_id, period.get("label"))
            )
        seen.add(user_id)
        value = _metric_value(row.get(metric), metric, user_id)
        if user_id not in population:
            excluded_rows += 1
            continue
        values[user_id] = value
    total = _sum_metric(values.values(), metric)
    return {
        "label": _normalize_text(period.get("label")),
        "from": period.get("from"),
        "to": period.get("to"),
        "total": total,
        "excluded_row_count": excluded_rows,
    }, values


def _delta(previous, current, metric):
    absolute = _subtract_metric(current, previous, metric)
    if previous == 0:
        percent = None
    else:
        decimal_previous = (
            Decimal(previous) if isinstance(previous, int) else Decimal(str(previous))
        )
        decimal_absolute = (
            Decimal(absolute) if isinstance(absolute, int) else Decimal(str(absolute))
        )
        integer_digits = max(
            decimal_absolute.adjusted() - decimal_previous.adjusted() + 3,
            1,
        )
        precision = (
            max(
                len(decimal_previous.as_tuple().digits),
                len(decimal_absolute.as_tuple().digits),
                integer_digits + 2,
                30,
            )
            + 10
        )
        with localcontext() as context:
            context.prec = precision
            rounded = (decimal_absolute * Decimal(100) / decimal_previous).quantize(
                Decimal("0.01")
            )
            percent = format(rounded, ".2f")
    return {
        "absolute": _json_metric_number(absolute, metric),
        "percent": percent,
    }


def _period_phrase(count):
    words = {2: "两个", 3: "三个", 4: "四个", 5: "五个"}
    return "%s周期" % words.get(count, str(count) + "个")


def _scope_statement(metadata, population_size, period_count):
    metric = METRIC_LABELS.get(metadata["metric"], metadata["metric"])
    scope = "部门=%s" % metadata["scope_value"]
    if metadata["scope_type"] == "organization":
        scope = "组织=%s" % metadata["scope_value"]
    exclusions = "已排除未分配、占位及非员工人员。"
    if metadata["scope_type"] == "department":
        exclusions = "已排除未分配、占位、非员工及跨部门人员。"
    return "口径：%s；%s；固定人员集合=%d人；%s均截至%02d:00；%s" % (
        metric,
        scope,
        population_size,
        _period_phrase(period_count),
        metadata["cutoff_hour"],
        exclusions,
    )


def _analyze(payload):
    if not isinstance(payload, dict):
        raise ScopeValidationError("input must be a JSON object")
    comparison = payload.get("comparison")
    roster = payload.get("roster")
    periods = payload.get("periods")
    if not isinstance(comparison, dict):
        raise ScopeValidationError("comparison must be an object")
    if not isinstance(roster, list):
        raise ScopeValidationError("roster must be an array")
    if not isinstance(periods, list):
        raise ScopeValidationError("periods must be an array")

    metadata = _validate_comparison(comparison, periods)
    population, roster_exclusions = _select_population(roster, metadata)
    period_results = []
    values_by_period = []
    for period in periods:
        result, values = _period_result(period, metadata["metric"], population)
        period_results.append(result)
        values_by_period.append(values)

    deltas = []
    for index in range(1, len(period_results)):
        deltas.append(
            {
                "from": period_results[index - 1]["label"],
                "to": period_results[index]["label"],
                **_delta(
                    period_results[index - 1]["total"],
                    period_results[index]["total"],
                    metadata["metric"],
                ),
            }
        )

    contributors = []
    for user_id, member in population.items():
        raw_values = [period_values[user_id] for period_values in values_by_period]
        raw_delta = _subtract_metric(raw_values[-1], raw_values[0], metadata["metric"])
        values = [
            _json_metric_number(value, metadata["metric"]) for value in raw_values
        ]
        contributors.append(
            {
                "user_id": user_id,
                "name": member["name"],
                "department": member["department"],
                "values": values,
                "delta": _json_metric_number(raw_delta, metadata["metric"]),
                "_sort_delta": raw_delta,
            }
        )
    contributors.sort(key=lambda item: (-abs(item["_sort_delta"]), item["user_id"]))
    for contributor in contributors:
        del contributor["_sort_delta"]

    scope = dict(metadata)
    scope["population_size"] = len(population)
    output_periods = []
    for period in period_results:
        output_period = dict(period)
        output_period["total"] = _json_metric_number(
            period["total"], metadata["metric"]
        )
        output_periods.append(output_period)
    return {
        "scope": scope,
        "scope_statement": _scope_statement(metadata, len(population), len(periods)),
        "roster_exclusions": roster_exclusions,
        "periods": output_periods,
        "deltas": deltas,
        "contributors": contributors,
    }


def analyze(payload):
    try:
        return _analyze(payload)
    except ScopeValidationError:
        raise
    except (DecimalException, ValueError, OverflowError) as exc:
        raise ScopeValidationError("invalid numeric calculation") from exc


def _bounded_error(kind, message):
    return {"error": kind, "message": str(message).replace("\n", " ")[:500]}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print(
            json.dumps(
                _bounded_error("usage_error", "usage: compare_scope.py INPUT.json")
            ),
            file=sys.stderr,
        )
        return 2
    try:
        with Path(argv[0]).open(encoding="utf-8") as input_file:
            payload = json.load(input_file, parse_int=_parse_json_integer)
        result = analyze(payload)
        output = json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except ScopeValidationError as exc:
        print(
            json.dumps(
                _bounded_error("scope_validation_error", exc), ensure_ascii=False
            ),
            file=sys.stderr,
        )
        return 2
    except OSError:
        print(
            json.dumps(
                _bounded_error("input_error", "unable to read input file"),
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    except json.JSONDecodeError as exc:
        print(
            json.dumps(
                _bounded_error(
                    "input_error",
                    "invalid JSON at line %d column %d" % (exc.lineno, exc.colno),
                ),
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    except (TypeError, ValueError, OverflowError, DecimalException):
        print(
            json.dumps(
                _bounded_error("input_error", "invalid input value"),
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
