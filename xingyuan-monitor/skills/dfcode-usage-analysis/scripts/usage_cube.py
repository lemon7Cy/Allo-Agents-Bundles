#!/usr/bin/env python3
"""usage_cube.py — deterministic 星元 usage-analysis engine.

WHY THIS EXISTS
---------------
星元 (the monitor agent) used to let the LLM make many dfcode MCP calls and then
compute trends / percentages / deltas / slopes IN-CONTEXT. That is fragile
(context blow-up), non-reproducible, and the LLM does arithmetic badly. This
script replaces all of that with a DATA MODEL + DATA FLOW:

  * One fact cube  (employee x department x date x model -> tokens, requests)
  * All views derive from that single cube, so granularity (口径) is consistent
    BY CONSTRUCTION.
  * The engine computes EVERYTHING numeric and deterministic. The AI's only job
    is interpretation (root cause / 推测 / 建议 / narrative) of the digest below.

DETERMINISM CONTRACT
--------------------
  * stdlib only: json, datetime, statistics, sys, argparse.
  * No randomness (no random module), no reliance on the wall clock beyond what
    is provided inside the input JSON (period / dates / holidays).
  * Same input bytes -> same output bytes. Sorting is total (ties broken by a
    secondary key) so ordering never depends on dict insertion noise.

STDIN  (a single JSON object):
  {
    "records": [
      {"employee": str, "department": str, "date": "YYYY-MM-DD",
       "model": str, "tokens": number, "requests": number},
      ...
    ],
    "period": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
    "workdays_only": true,
    "holidays":        ["YYYY-MM-DD", ...],   # optional: closed days to EXCLUDE even if weekday
    "extra_workdays":  ["YYYY-MM-DD", ...],   # optional: 调休 makeup days to INCLUDE even if weekend
    "recent_days": 5,                          # window for the "recent N workdays" view
    "thresholds": {"growth_pct": 50, "drop_pct": 50, "silent_days": 5}  # optional overrides
  }

STDOUT (JSON, see build_result() for the exact shape):
  scope, dept_daily, dept_weekly, overall, model_share, per_person,
  growth, decline, recent_days_view, week_over_week, gaps

WORKDAY RULE
------------
  A date is a workday if  (Mon-Fri AND not in holidays)  OR  (in extra_workdays).
  If workdays_only is true, the cube is filtered to workdays BEFORE every
  computation, so weekends/holidays cannot leak into any trend.

CLASSIFICATION (deterministic, override-able via thresholds):
  growth  : delta_pct >= growth_pct AND slope > 0
  decline : delta_pct <= -drop_pct
            OR "由活转静" (was active >=1 week with meaningful tokens, then the
               last `silent_days` workdays are ~0)
  steady  : otherwise

CLI MODES
---------
  (default)     read STDIN JSON, write result JSON to STDOUT
  --md          read STDIN JSON, write a compact human-readable markdown digest
  --selftest    run a built-in synthetic dataset, assert concrete numbers,
                print PASS / FAIL, exit nonzero on FAIL (no STDIN needed)

ROBUSTNESS
----------
  * Missing / None numeric fields default to 0; missing string fields default
    to "" / "(unknown)".
  * Malformed rows (not a dict, no usable date) are skipped and noted in `gaps`,
    never thrown.
  * Empty records -> a valid, fully-populated-but-empty result plus a gap note.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import statistics
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS = {"growth_pct": 50.0, "drop_pct": 50.0, "silent_days": 5}
DEFAULT_RECENT_DAYS = 5
# A week with tokens below this is treated as "no meaningful usage" when deciding
# whether a person was ever "active" (used for the 由活转静 rule). Kept small and
# absolute on purpose: the cube is in raw tokens.
MEANINGFUL_WEEK_TOKENS = 1.0
SILENT_EPSILON = 1e-9  # tokens <= this counts as "silent" for a workday


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _num(value: Any) -> float:
    """Coerce anything to a finite float; None/bad -> 0.0 (never raises)."""
    if value is None:
        return 0.0
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    # reject NaN / inf so downstream arithmetic stays deterministic
    if f != f or f in (float("inf"), float("-inf")):
        return 0.0
    return f


def _str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _parse_date(value: Any) -> _dt.date | None:
    """Parse 'YYYY-MM-DD' -> date, else None (never raises)."""
    if not isinstance(value, str):
        return None
    try:
        return _dt.datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


def _pct_change(first: float, last: float) -> float:
    """Percentage change from `first` to `last`, rounded to 1 decimal.

    If the baseline is ~0 we cannot form a meaningful percentage:
      * 0 -> 0    => 0.0
      * 0 -> >0   => 100.0 (treat any growth from nothing as +100%, capped)
    """
    if abs(first) <= SILENT_EPSILON:
        return 0.0 if abs(last) <= SILENT_EPSILON else 100.0
    return round((last - first) / first * 100.0, 1)


def _slope(series: list[float]) -> float:
    """Least-squares slope of y=series over x=0..n-1.

    Uses statistics.linear_regression when available (Py>=3.10), else a manual
    closed-form. Returns 0.0 for <2 points or zero variance in x.
    """
    n = len(series)
    if n < 2:
        return 0.0
    xs = list(range(n))
    lin = getattr(statistics, "linear_regression", None)
    if lin is not None:
        try:
            return round(float(lin(xs, series).slope), 4)
        except (statistics.StatisticsError, ValueError):
            pass
    # Manual closed form: slope = Σ(x-x̄)(y-ȳ) / Σ(x-x̄)²
    mean_x = sum(xs) / n
    mean_y = sum(series) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, series))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return round(num / den, 4)


def _iso_monday(d: _dt.date) -> _dt.date:
    """Return the Monday of d's ISO week."""
    return d - _dt.timedelta(days=d.weekday())


def _is_workday(d: _dt.date, holidays: set[str], extra_workdays: set[str]) -> bool:
    iso = d.isoformat()
    if iso in extra_workdays:
        return True
    if d.weekday() >= 5:  # Sat/Sun
        return False
    if iso in holidays:
        return False
    return True


# ---------------------------------------------------------------------------
# The fact cube
# ---------------------------------------------------------------------------

class Cube:
    """The single source of truth: a list of normalized fact rows plus indexes.

    Every view is derived from `self.rows`, guaranteeing consistent 口径.
    """

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.gaps: list[str] = []
        self.workdays: list[_dt.date] = []  # sorted, deduped, within filter

    # -- build -------------------------------------------------------------

    @classmethod
    def from_input(cls, payload: dict[str, Any]) -> "Cube":
        cube = cls()

        period = payload.get("period") or {}
        start = _parse_date(period.get("start"))
        end = _parse_date(period.get("end"))
        workdays_only = bool(payload.get("workdays_only", True))
        holidays = {s for s in (payload.get("holidays") or []) if isinstance(s, str)}
        extra = {s for s in (payload.get("extra_workdays") or []) if isinstance(s, str)}

        raw_records = payload.get("records")
        if not isinstance(raw_records, list):
            raw_records = []
            cube.gaps.append("input.records missing or not a list → treated as empty")

        skipped = 0
        for rec in raw_records:
            if not isinstance(rec, dict):
                skipped += 1
                continue
            d = _parse_date(rec.get("date"))
            if d is None:
                skipped += 1
                continue
            # period filter (inclusive); if no period given, keep all
            if start and d < start:
                continue
            if end and d > end:
                continue
            is_wd = _is_workday(d, holidays, extra)
            if workdays_only and not is_wd:
                continue
            cube.rows.append({
                "employee": _str(rec.get("employee"), "(unknown)") or "(unknown)",
                "department": _str(rec.get("department"), "(none)") or "(none)",
                "date": d,
                "model": _str(rec.get("model"), "(unknown)") or "(unknown)",
                "tokens": _num(rec.get("tokens")),
                "requests": _num(rec.get("requests")),
                "is_workday": is_wd,
            })

        if skipped:
            cube.gaps.append(f"{skipped} malformed row(s) skipped (not a dict / no valid date)")

        # workday calendar for the (filtered) data span
        cube._compute_calendar(start, end, holidays, extra)

        # gap notes about calendar assumptions
        if not holidays:
            cube.gaps.append("no holidays provided → workdays = Mon-Fri, 调休/节假日未校正")
        if not extra:
            cube.gaps.append("no extra_workdays provided → 调休补班日未纳入工作日")

        # stash config the views need
        cube.start = start
        cube.end = end
        cube.workdays_only = workdays_only
        cube.holidays = holidays
        cube.extra = extra
        return cube

    def _compute_calendar(self, start, end, holidays, extra) -> None:
        """Workdays spanning the requested period. The period bounds win when given
        (we do NOT cap the upper bound at the last date that has data), so recent
        workdays with no records still enter the calendar and a whole-team recent
        silence is visible to recent_days_view."""
        self.no_data_workdays: list[_dt.date] = []
        present = sorted({r["date"] for r in self.rows})
        lo = start if start else (present[0] if present else None)
        hi = end if end else (present[-1] if present else None)
        if lo is None or hi is None:
            self.workdays = []
            return
        days: list[_dt.date] = []
        cur = lo
        while cur <= hi:
            if _is_workday(cur, holidays, extra):
                days.append(cur)
            cur += _dt.timedelta(days=1)
        self.workdays = days
        # Workdays in scope with NO records: could be real zero usage OR data not yet
        # available (e.g. today's data not finalized). Flagged for honest interpretation.
        have = {r["date"] for r in self.rows}
        self.no_data_workdays = [d for d in days if d not in have]

    # -- iteration helpers -------------------------------------------------

    def people(self) -> list[str]:
        return sorted({r["employee"] for r in self.rows})

    def models(self) -> list[str]:
        return sorted({r["model"] for r in self.rows})


# ---------------------------------------------------------------------------
# Week bucketing
# ---------------------------------------------------------------------------

def _week_labels(workdays: list[_dt.date]) -> tuple[list[_dt.date], dict[_dt.date, str]]:
    """Return (ordered list of week-Mondays, {monday: label}).

    label like "W1 6/2-6/6" using the first & last workday that fall in the
    Mon-Sun bucket. Weeks are ordered by Monday date and numbered 1..N.
    """
    mondays = sorted({_iso_monday(d) for d in workdays})
    labels: dict[_dt.date, str] = {}
    by_week: dict[_dt.date, list[_dt.date]] = {}
    for d in workdays:
        by_week.setdefault(_iso_monday(d), []).append(d)
    for i, mon in enumerate(mondays, start=1):
        ds = sorted(by_week.get(mon, [mon]))
        lo, hi = ds[0], ds[-1]
        labels[mon] = f"W{i} {lo.month}/{lo.day}-{hi.month}/{hi.day}"
    return mondays, labels


# ---------------------------------------------------------------------------
# View builders (all derive from the cube)
# ---------------------------------------------------------------------------

def _dept_daily(cube: Cube) -> list[dict[str, Any]]:
    agg: dict[_dt.date, dict[str, float]] = {}
    for r in cube.rows:
        a = agg.setdefault(r["date"], {"tokens": 0.0, "requests": 0.0})
        a["tokens"] += r["tokens"]
        a["requests"] += r["requests"]
    out = []
    for d in sorted(agg):
        out.append({
            "date": d.isoformat(),
            "tokens": round(agg[d]["tokens"], 2),
            "requests": round(agg[d]["requests"], 2),
            "is_workday": _is_workday(d, cube.holidays, cube.extra),
        })
    return out


def _week_token_map(cube: Cube, rows: list[dict[str, Any]]) -> dict[_dt.date, float]:
    wk: dict[_dt.date, float] = {}
    for r in rows:
        mon = _iso_monday(r["date"])
        wk[mon] = wk.get(mon, 0.0) + r["tokens"]
    return wk


def _dept_weekly(cube: Cube, labels: dict[_dt.date, str], mondays: list[_dt.date]) -> list[dict[str, Any]]:
    wk = _week_token_map(cube, cube.rows)
    out = []
    for mon in mondays:
        out.append({
            "week_label": labels.get(mon, mon.isoformat()),
            "tokens": round(wk.get(mon, 0.0), 2),
        })
    return out


def _overall(cube: Cube, weekly: list[dict[str, Any]]) -> dict[str, Any]:
    total = round(sum(w["tokens"] for w in weekly), 2)
    if not weekly:
        return {
            "first_week_tokens": 0.0, "last_week_tokens": 0.0, "delta_pct": 0.0,
            "total_tokens": 0.0, "trend": "flat", "inflection_weeks": [],
        }
    first = weekly[0]["tokens"]
    last = weekly[-1]["tokens"]
    delta = _pct_change(first, last)
    if delta >= 10:
        trend = "up"
    elif delta <= -10:
        trend = "down"
    else:
        trend = "flat"
    # inflection: week(s) with the largest absolute WoW change
    inflection: list[str] = []
    if len(weekly) >= 2:
        changes = []
        for i in range(1, len(weekly)):
            changes.append((abs(weekly[i]["tokens"] - weekly[i - 1]["tokens"]),
                            weekly[i]["week_label"]))
        max_change = max(c[0] for c in changes)
        if max_change > 0:
            inflection = [lbl for ch, lbl in changes if ch == max_change]
    return {
        "first_week_tokens": round(first, 2),
        "last_week_tokens": round(last, 2),
        "delta_pct": delta,
        "total_tokens": total,
        "trend": trend,
        "inflection_weeks": inflection,
    }


def _model_share(cube: Cube) -> list[dict[str, Any]]:
    agg: dict[str, float] = {}
    for r in cube.rows:
        agg[r["model"]] = agg.get(r["model"], 0.0) + r["tokens"]
    total = sum(agg.values())
    out = []
    for model in sorted(agg, key=lambda m: (-agg[m], m)):  # desc, tie-break by name
        out.append({
            "model": model,
            "tokens": round(agg[model], 2),
            "pct": round(agg[model] / total * 100.0, 1) if total > 0 else 0.0,
        })
    return out


def _person_rows(cube: Cube, employee: str) -> list[dict[str, Any]]:
    return [r for r in cube.rows if r["employee"] == employee]


def _person_week_tokens(rows: list[dict[str, Any]]) -> dict[_dt.date, float]:
    wk: dict[_dt.date, float] = {}
    for r in rows:
        mon = _iso_monday(r["date"])
        wk[mon] = wk.get(mon, 0.0) + r["tokens"]
    return wk


def _classify_person(
    delta_pct: float,
    slope: float,
    week_tokens: dict[_dt.date, float],
    workday_series: list[tuple[_dt.date, float]],
    thresholds: dict[str, float],
) -> str:
    growth_pct = thresholds["growth_pct"]
    drop_pct = thresholds["drop_pct"]
    silent_days = int(thresholds["silent_days"])

    # growth
    if delta_pct >= growth_pct and slope > 0:
        return "growth"

    # decline by magnitude
    if delta_pct <= -drop_pct:
        return "decline"

    # decline by 由活转静: was ever active (a meaningful week) AND the last
    # `silent_days` workdays of this person's series are ~0.
    was_active = any(v >= MEANINGFUL_WEEK_TOKENS for v in week_tokens.values())
    if was_active and len(workday_series) >= silent_days:
        tail = workday_series[-silent_days:]
        if all(tok <= SILENT_EPSILON for _, tok in tail):
            # require that earlier in the series there WAS usage, else it's just
            # a never-started low-base person (handled as steady here)
            head = workday_series[:-silent_days]
            if any(tok > SILENT_EPSILON for _, tok in head):
                return "decline"

    return "steady"


def _per_person(
    cube: Cube,
    mondays: list[_dt.date],
    thresholds: dict[str, float],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    # map employee -> department (last seen; deterministic via sorted scan)
    dept_of: dict[str, str] = {}
    for r in sorted(cube.rows, key=lambda r: (r["employee"], r["date"].isoformat())):
        dept_of[r["employee"]] = r["department"]

    for emp in cube.people():
        rows = _person_rows(cube, emp)
        wk = _person_week_tokens(rows)
        weeks_present = sorted(wk)
        first_tok = round(wk[weeks_present[0]], 2) if weeks_present else 0.0
        last_tok = round(wk[weeks_present[-1]], 2) if weeks_present else 0.0
        delta = _pct_change(first_tok, last_tok)
        total = round(sum(r["tokens"] for r in rows), 2)

        # per-workday token series across the WHOLE workday calendar (zeros for
        # days with no usage) — this is what slope & 由活转静 operate on.
        per_day: dict[_dt.date, float] = {}
        for r in rows:
            per_day[r["date"]] = per_day.get(r["date"], 0.0) + r["tokens"]
        workday_series = [(d, round(per_day.get(d, 0.0), 2)) for d in cube.workdays]
        slope = _slope([v for _, v in workday_series])

        # top model + per-model trend (first vs last week the model appears)
        model_first: dict[str, tuple[_dt.date, float]] = {}
        model_last: dict[str, tuple[_dt.date, float]] = {}
        model_total: dict[str, float] = {}
        model_week: dict[str, dict[_dt.date, float]] = {}
        for r in rows:
            mon = _iso_monday(r["date"])
            model_week.setdefault(r["model"], {})
            model_week[r["model"]][mon] = model_week[r["model"]].get(mon, 0.0) + r["tokens"]
            model_total[r["model"]] = model_total.get(r["model"], 0.0) + r["tokens"]
        model_trend = []
        for m in sorted(model_week, key=lambda m: (-model_total[m], m)):
            mw = model_week[m]
            mweeks = sorted(mw)
            mf = round(mw[mweeks[0]], 2)
            ml = round(mw[mweeks[-1]], 2)
            model_trend.append({
                "model": m, "first": mf, "last": ml, "delta_pct": _pct_change(mf, ml),
            })
        top_model = model_trend[0]["model"] if model_trend else "(none)"

        cls = _classify_person(delta, slope, wk, workday_series, thresholds)

        out.append({
            "employee": emp,
            "department": dept_of.get(emp, "(none)"),
            "first_tokens": first_tok,
            "last_tokens": last_tok,
            "delta_pct": delta,
            "slope": slope,
            "total_tokens": total,
            "top_model": top_model,
            "class": cls,
            "model_trend": model_trend,
            "_weeks_present": len(weeks_present),  # internal, stripped before output
        })

        if len(weeks_present) < 2:
            cube.gaps.append(f"person {emp} has <2 weeks of data → trend low-confidence")

    # deterministic order: by employee name
    out.sort(key=lambda p: p["employee"])
    return out


def _recent_days_view(
    cube: Cube,
    per_person: list[dict[str, Any]],
    recent_days: int,
) -> dict[str, Any]:
    """Compare the last `recent_days` workdays vs the preceding `recent_days`.

    Directly supports "最近两天用量下来了" style questions.
    """
    wds = cube.workdays
    window = max(1, int(recent_days))
    recent = wds[-window:] if wds else []
    prior = wds[-2 * window:-window] if len(wds) >= window else []
    recent_set = set(recent)
    prior_set = set(prior)

    def dept_sum(days: set[_dt.date]) -> float:
        return sum(r["tokens"] for r in cube.rows if r["date"] in days)

    recent_total = dept_sum(recent_set)
    prior_total = dept_sum(prior_set)
    # compare averages per workday (window lengths may differ at series edges)
    recent_avg = recent_total / len(recent) if recent else 0.0
    prior_avg = prior_total / len(prior) if prior else 0.0
    dept_pct = _pct_change(prior_avg, recent_avg)

    # per-person drops over the same windows
    drops = []
    for emp in cube.people():
        rows = _person_rows(cube, emp)
        per_day: dict[_dt.date, float] = {}
        for r in rows:
            per_day[r["date"]] = per_day.get(r["date"], 0.0) + r["tokens"]
        r_avg = (sum(per_day.get(d, 0.0) for d in recent) / len(recent)) if recent else 0.0
        p_avg = (sum(per_day.get(d, 0.0) for d in prior) / len(prior)) if prior else 0.0
        drop_pct = _pct_change(p_avg, r_avg)
        active_days = [d for d in cube.workdays if per_day.get(d, 0.0) > SILENT_EPSILON]
        last_active = active_days[-1].isoformat() if active_days else None
        # only report genuine drops (negative change AND had prior usage)
        if p_avg > SILENT_EPSILON and drop_pct < 0:
            drops.append({
                "employee": emp,
                "prior_avg": round(p_avg, 2),
                "recent_avg": round(r_avg, 2),
                "drop_pct": drop_pct,
                "last_active_date": last_active,
            })
    # most severe drop first; tie-break by name for determinism
    drops.sort(key=lambda x: (x["drop_pct"], x["employee"]))

    have_dates = {r["date"] for r in cube.rows}
    recent_no_data = [d for d in recent if d not in have_dates]
    if recent_no_data:
        cube.gaps.append(
            f"最近 {len(recent_no_data)} 个工作日（{', '.join(d.isoformat() for d in recent_no_data)}）无数据 —— "
            "可能是真降到 0，也可能是数据未出完整；判断「最近用量下来了」前需复查这些日期的完整数据。"
        )

    return {
        "window_days": window,
        "recent_workdays": [d.isoformat() for d in recent],
        "prior_workdays": [d.isoformat() for d in prior],
        "recent_no_data_workdays": [d.isoformat() for d in recent_no_data],
        "dept_recent_vs_prior_pct": dept_pct,
        "per_person_drops": drops,
    }


def _week_over_week_view(cube: Cube) -> dict[str, Any]:
    """Current ISO week's workdays vs the SAME weekdays of the previous week.

    Why this exists in addition to recent_days_view: the rolling `recent_days` block
    straddles week boundaries and is easily polluted by an odd low workday (e.g. a
    near-zero Friday), so a real partial-week slide — this Mon/Tue far below last
    Mon/Tue — can read as "up". Locking the comparison to MATCHING weekdays
    week-over-week catches a department whose current-week workday level has dropped
    even before the week is over, and is exactly the signal that a monthly +X%
    aggregate hides. Pairs each current-week workday d with d-7 (same weekday).
    """
    wds = cube.workdays
    empty = {
        "current_week_monday": None, "prev_week_monday": None,
        "current_workdays": [], "matched_prior_workdays": [],
        "dept_wow_pct": 0.0, "by_weekday": [], "per_person_drops": [],
    }
    if not wds:
        return empty
    cur_monday = _iso_monday(wds[-1])
    pairs = [(d, d - _dt.timedelta(days=7)) for d in sorted(d for d in wds if _iso_monday(d) == cur_monday)]
    cur_set = {d for d, _ in pairs}
    prev_set = {p for _, p in pairs}

    by_date: dict[_dt.date, float] = {}
    for r in cube.rows:
        by_date[r["date"]] = by_date.get(r["date"], 0.0) + r["tokens"]

    def avg(days: set[_dt.date]) -> float:
        return (sum(by_date.get(d, 0.0) for d in days) / len(days)) if days else 0.0

    dept_pct = _pct_change(avg(prev_set), avg(cur_set))
    by_weekday = [
        {
            "current_date": d.isoformat(), "prior_date": p.isoformat(),
            "current": round(by_date.get(d, 0.0), 2), "prior": round(by_date.get(p, 0.0), 2),
            "pct": _pct_change(by_date.get(p, 0.0), by_date.get(d, 0.0)),
        }
        for d, p in pairs
    ]

    drops = []
    for emp in cube.people():
        per_day: dict[_dt.date, float] = {}
        for r in _person_rows(cube, emp):
            per_day[r["date"]] = per_day.get(r["date"], 0.0) + r["tokens"]
        c = (sum(per_day.get(d, 0.0) for d in cur_set) / len(cur_set)) if cur_set else 0.0
        pv = (sum(per_day.get(d, 0.0) for d in prev_set) / len(prev_set)) if prev_set else 0.0
        if pv > SILENT_EPSILON and c < pv:
            drops.append({"employee": emp, "prior_avg": round(pv, 2),
                          "current_avg": round(c, 2), "drop_pct": _pct_change(pv, c)})
    drops.sort(key=lambda x: (x["drop_pct"], x["employee"]))

    return {
        "current_week_monday": cur_monday.isoformat(),
        "prev_week_monday": (cur_monday - _dt.timedelta(days=7)).isoformat(),
        "current_workdays": [d.isoformat() for d in sorted(cur_set)],
        "matched_prior_workdays": [d.isoformat() for d in sorted(prev_set)],
        "dept_wow_pct": dept_pct,
        "by_weekday": by_weekday,
        "per_person_drops": drops,
    }


# ---------------------------------------------------------------------------
# Top-level assembly
# ---------------------------------------------------------------------------

def _resolve_thresholds(payload: dict[str, Any]) -> dict[str, float]:
    th = dict(DEFAULT_THRESHOLDS)
    given = payload.get("thresholds")
    if isinstance(given, dict):
        for k in ("growth_pct", "drop_pct", "silent_days"):
            if k in given and given[k] is not None:
                try:
                    th[k] = float(given[k])
                except (TypeError, ValueError):
                    pass
    return th


def build_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Compute the full deterministic result dict from the input payload."""
    cube = Cube.from_input(payload)
    thresholds = _resolve_thresholds(payload)
    recent_days = payload.get("recent_days", DEFAULT_RECENT_DAYS)
    try:
        recent_days = int(recent_days)
    except (TypeError, ValueError):
        recent_days = DEFAULT_RECENT_DAYS

    mondays, labels = _week_labels(cube.workdays)

    dept_daily = _dept_daily(cube)
    dept_weekly = _dept_weekly(cube, labels, mondays)
    overall = _overall(cube, dept_weekly)
    model_share = _model_share(cube)
    per_person = _per_person(cube, mondays, thresholds)
    recent_view = _recent_days_view(cube, per_person, recent_days)
    wow_view = _week_over_week_view(cube)

    # growth / decline lists (capped at 8)
    growth = sorted(
        [p for p in per_person if p["class"] == "growth"],
        key=lambda p: (-p["delta_pct"], p["employee"]),
    )[:8]
    decline = sorted(
        [p for p in per_person if p["class"] == "decline"],
        # drop severity: most-negative delta first; 由活转静 (delta may be 0)
        # sinks to severity via slope as a secondary key
        key=lambda p: (p["delta_pct"], p["slope"], p["employee"]),
    )[:8]

    period_out = {
        "start": cube.start.isoformat() if cube.start else None,
        "end": cube.end.isoformat() if cube.end else None,
    }
    scope = {
        "period": period_out,
        "workdays_only": cube.workdays_only,
        "n_records": len(cube.rows),
        "n_people": len(cube.people()),
        "n_models": len(cube.models()),
        "n_workdays": len(cube.workdays),
        "thresholds": thresholds,
        "recent_days": recent_days,
    }

    if not cube.rows:
        cube.gaps.append("no usable records after filtering → empty result")

    # strip internal fields before emitting
    def _clean(p: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in p.items() if not k.startswith("_")}

    # dedupe gaps preserving order
    seen: set[str] = set()
    gaps: list[str] = []
    for g in cube.gaps:
        if g not in seen:
            seen.add(g)
            gaps.append(g)

    return {
        "scope": scope,
        "dept_daily": dept_daily,
        "dept_weekly": dept_weekly,
        "overall": overall,
        "model_share": model_share,
        "per_person": [_clean(p) for p in per_person],
        "growth": [_clean(p) for p in growth],
        "decline": [_clean(p) for p in decline],
        "recent_days_view": recent_view,
        "week_over_week": wow_view,
        "gaps": gaps,
    }


# ---------------------------------------------------------------------------
# Markdown digest (for the agent to read instead of raw JSON)
# ---------------------------------------------------------------------------

def render_markdown(result: dict[str, Any]) -> str:
    s = result["scope"]
    o = result["overall"]
    lines: list[str] = []
    lines.append("# 用量分析数字底稿 (engine digest — numbers are authoritative, do NOT recompute)")
    p = s["period"]
    lines.append(
        f"- 范围: {p.get('start')} → {p.get('end')} | 仅工作日={s['workdays_only']} | "
        f"工作日数={s['n_workdays']} | 人数={s['n_people']} | 模型数={s['n_models']} | "
        f"记录数={s['n_records']}"
    )
    lines.append(
        f"- 阈值: growth≥{s['thresholds']['growth_pct']}% / drop≤-{s['thresholds']['drop_pct']}% / "
        f"silent={int(s['thresholds']['silent_days'])} 工作日 | recent_days={s['recent_days']}"
    )

    lines.append("")
    lines.append("## 整体趋势 (overall)")
    lines.append(
        f"- 趋势={o['trend']} | 首周={o['first_week_tokens']} → 末周={o['last_week_tokens']} | "
        f"环比 Δ={o['delta_pct']}% | 总量={o['total_tokens']}"
    )
    if o["inflection_weeks"]:
        lines.append(f"- 拐点周: {', '.join(o['inflection_weeks'])}")

    if result["dept_weekly"]:
        lines.append("")
        lines.append("## 周度部门用量 (dept_weekly)")
        for w in result["dept_weekly"]:
            lines.append(f"- {w['week_label']}: {w['tokens']}")

    if result["model_share"]:
        lines.append("")
        lines.append("## 模型占比 (model_share)")
        for m in result["model_share"]:
            lines.append(f"- {m['model']}: {m['tokens']} ({m['pct']}%)")

    g = result["growth"]
    lines.append("")
    lines.append(f"## 持续增长 (growth, {len(g)})")
    if g:
        for x in g:
            lines.append(
                f"- {x['employee']}·{x['department']}: {x['first_tokens']} → {x['last_tokens']} "
                f"(Δ{x['delta_pct']}%, slope={x['slope']}), 主用模型={x['top_model']}"
            )
    else:
        lines.append("- (none)")

    dline = result["decline"]
    lines.append("")
    lines.append(f"## 突然下降 (decline, {len(dline)})")
    if dline:
        for x in dline:
            lines.append(
                f"- {x['employee']}·{x['department']}: {x['first_tokens']} → {x['last_tokens']} "
                f"(Δ{x['delta_pct']}%, slope={x['slope']}), 主用模型={x['top_model']}"
            )
    else:
        lines.append("- (none)")

    rv = result["recent_days_view"]
    lines.append("")
    lines.append(f"## 最近 {rv['window_days']} 工作日 vs 前 {rv['window_days']} 工作日 (recent_days_view)")
    lines.append(f"- 近窗工作日: {', '.join(rv['recent_workdays']) or '(none)'}")
    lines.append(f"- 前窗工作日: {', '.join(rv['prior_workdays']) or '(none)'}")
    lines.append(f"- 部门近窗 vs 前窗(按工作日均值): Δ={rv['dept_recent_vs_prior_pct']}%")
    if rv["per_person_drops"]:
        lines.append("- 个人掉量(均值, 近 vs 前):")
        for d in rv["per_person_drops"]:
            lines.append(
                f"  - {d['employee']}: {d['prior_avg']} → {d['recent_avg']} "
                f"(Δ{d['drop_pct']}%, 末次活跃={d['last_active_date']})"
            )
    else:
        lines.append("- 个人掉量: (none)")

    wow = result.get("week_over_week", {})
    lines.append("")
    lines.append("## 本周 vs 上周（同工作日对齐, week_over_week）")
    if wow.get("current_week_monday"):
        lines.append(
            f"- 本周({wow['current_week_monday']}) vs 上周({wow['prev_week_monday']})，"
            f"只取本周已有工作日并配对同星期几: 部门同工作日均值 Δ={wow['dept_wow_pct']}%"
        )
        for b in wow.get("by_weekday", []):
            lines.append(
                f"  - {b['current_date']} {b['current']} vs {b['prior_date']} {b['prior']} (Δ{b['pct']}%)"
            )
        if wow.get("per_person_drops"):
            lines.append("- 个人同工作日掉量(均值, 本周 vs 上周):")
            for d in wow["per_person_drops"]:
                lines.append(
                    f"  - {d['employee']}: {d['prior_avg']} → {d['current_avg']} (Δ{d['drop_pct']}%)"
                )
        else:
            lines.append("- 个人同工作日掉量: (none)")
    else:
        lines.append("- (无足够数据)")

    lines.append("")
    lines.append("## 缺口 (gaps)")
    if result["gaps"]:
        for gp in result["gaps"]:
            lines.append(f"- {gp}")
    else:
        lines.append("- (none)")

    lines.append("")
    lines.append(
        "> AI 职责: 只做解释(根因/推测[需标注]/建议/叙事)。以上数字为引擎确定性计算结果，"
        "禁止在上下文中重算趋势/百分比/斜率/增降分类。"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Self test
# ---------------------------------------------------------------------------

def _selftest() -> int:
    """Run a synthetic dataset and assert concrete numbers. PASS/FAIL + exit code.

    Synthetic scenario (period 2026-06-01 .. 2026-06-12, weekdays only):
      Week 1 workdays: Mon 6/1 .. Fri 6/5
      Week 2 workdays: Mon 6/8 .. Fri 6/12
      (6/6, 6/7, 6/13, 6/14 are weekends -> excluded)

      Alice  — GROWTH: week1 total small, week2 total much bigger, positive slope.
      Bob    — DECLINE (magnitude): week1 big, week2 ~ -100% (drops to near 0).
      Carol  — STEADY: flat usage.
      Dave   — DECLINE (由活转静): active early, then last 5 workdays silent.
    """
    records = []

    def add(emp, dept, date, model, tokens, requests=1):
        records.append({"employee": emp, "department": dept, "date": date,
                        "model": model, "tokens": tokens, "requests": requests})

    week1 = ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04", "2026-06-05"]
    week2 = ["2026-06-08", "2026-06-09", "2026-06-10", "2026-06-11", "2026-06-12"]

    # Alice: rising 100,200,300,400,500 (wk1=1500) then 1000..1400 (wk2=6000)
    for i, d in enumerate(week1):
        add("Alice", "Dept-A", d, "gpt-x", 100 * (i + 1))
    for i, d in enumerate(week2):
        add("Alice", "Dept-A", d, "gpt-x", 1000 + 100 * i)

    # Bob: week1 high (5 * 1000 = 5000), week2 near zero (one tiny day)
    for d in week1:
        add("Bob", "Dept-A", d, "claude-y", 1000)
    add("Bob", "Dept-A", week2[0], "claude-y", 1)  # collapses

    # Carol: steady ~500/day both weeks
    for d in week1 + week2:
        add("Carol", "Dept-A", d, "gpt-x", 500)

    # Dave: active week1 (800/day), silent all of week2 (no records) -> 由活转静
    for d in week1:
        add("Dave", "Dept-B", d, "model-z", 800)

    # weekend noise that must be DROPPED by workdays_only
    add("Alice", "Dept-A", "2026-06-06", "gpt-x", 999999)  # Saturday
    add("Bob", "Dept-A", "2026-06-07", "claude-y", 888888)  # Sunday

    # a malformed row (should be skipped, noted in gaps)
    records.append({"employee": "Ghost", "date": "not-a-date", "tokens": 5})
    records.append("totally bogus")

    payload = {
        "records": records,
        "period": {"start": "2026-06-01", "end": "2026-06-12"},
        "workdays_only": True,
        "recent_days": 2,
        "thresholds": {"growth_pct": 50, "drop_pct": 50, "silent_days": 5},
    }

    result = build_result(payload)
    failures: list[str] = []

    def check(name, cond, detail=""):
        if not cond:
            failures.append(f"{name}: {detail}")

    scope = result["scope"]
    # weekend rows dropped: 4 people * 10 workdays minus Bob's missing wk2 days
    # Alice 10, Bob 6, Carol 10, Dave 5 = 31 rows
    check("n_records", scope["n_records"] == 31, f"got {scope['n_records']} (want 31)")
    check("n_people", scope["n_people"] == 4, f"got {scope['n_people']} (want 4)")
    check("n_workdays", scope["n_workdays"] == 10, f"got {scope['n_workdays']} (want 10)")

    # weekend giant tokens must NOT appear anywhere
    check("weekend_excluded",
          all(d["date"] not in ("2026-06-06", "2026-06-07") for d in result["dept_daily"]),
          "weekend dates leaked into dept_daily")

    # ---- dept overall delta ----
    # week1 dept tokens: Alice1500 + Bob5000 + Carol2500 + Dave4000 = 13000
    # week2 dept tokens: Alice6000 + Bob1   + Carol2500 + Dave0    = 8501
    weekly = {w["week_label"].split()[0]: w["tokens"] for w in result["dept_weekly"]}
    check("week1_total", weekly.get("W1") == 13000, f"got {weekly.get('W1')} (want 13000)")
    check("week2_total", weekly.get("W2") == 8501, f"got {weekly.get('W2')} (want 8501)")
    # delta = (8501-13000)/13000*100 = -34.6%
    check("dept_delta", result["overall"]["delta_pct"] == -34.6,
          f"got {result['overall']['delta_pct']} (want -34.6)")
    check("dept_trend", result["overall"]["trend"] == "down",
          f"got {result['overall']['trend']}")
    check("dept_total", result["overall"]["total_tokens"] == 21501,
          f"got {result['overall']['total_tokens']} (want 21501)")

    # ---- one growth person: Alice ----
    growth_names = [p["employee"] for p in result["growth"]]
    check("alice_growth", "Alice" in growth_names, f"growth={growth_names}")
    alice = next((p for p in result["per_person"] if p["employee"] == "Alice"), None)
    check("alice_obj", alice is not None, "Alice missing from per_person")
    if alice:
        # first week 1500 -> last week 6000 => +300%
        check("alice_delta", alice["delta_pct"] == 300.0, f"got {alice['delta_pct']}")
        check("alice_slope_pos", alice["slope"] > 0, f"slope={alice['slope']}")
        check("alice_class", alice["class"] == "growth", f"class={alice['class']}")
        check("alice_top_model", alice["top_model"] == "gpt-x", f"top={alice['top_model']}")

    # ---- one decline person (magnitude): Bob ----
    decline_names = [p["employee"] for p in result["decline"]]
    check("bob_decline", "Bob" in decline_names, f"decline={decline_names}")
    bob = next((p for p in result["per_person"] if p["employee"] == "Bob"), None)
    if bob:
        # first week 5000 -> last week 1 => -100.0%
        check("bob_delta", bob["delta_pct"] == -100.0, f"got {bob['delta_pct']}")
        check("bob_class", bob["class"] == "decline", f"class={bob['class']}")

    # ---- decline by 由活转静: Dave ----
    dave = next((p for p in result["per_person"] if p["employee"] == "Dave"), None)
    if dave:
        check("dave_class", dave["class"] == "decline", f"class={dave['class']} (want decline 由活转静)")
    check("dave_in_decline", "Dave" in decline_names, f"decline={decline_names}")

    # ---- Carol steady ----
    carol = next((p for p in result["per_person"] if p["employee"] == "Carol"), None)
    if carol:
        check("carol_class", carol["class"] == "steady", f"class={carol['class']}")

    # ---- recent-days view (window=2): recent = 6/11,6/12 ; prior = 6/9,6/10 ----
    rv = result["recent_days_view"]
    check("recent_window", rv["window_days"] == 2, f"got {rv['window_days']}")
    check("recent_days_list", rv["recent_workdays"] == ["2026-06-11", "2026-06-12"],
          f"got {rv['recent_workdays']}")
    check("prior_days_list", rv["prior_workdays"] == ["2026-06-09", "2026-06-10"],
          f"got {rv['prior_workdays']}")
    # Dave silent in both recent windows (no wk2 usage) -> prior_avg 0 -> not a drop row.
    # Bob: prior(6/9,6/10)=0 each -> prior_avg 0 -> not listed (no prior usage in window).
    # Carol: prior 500/500, recent 500/500 -> drop_pct 0 -> not <0 -> not listed.
    # Alice: prior(6/9,6/10)=1100,1200 avg1150 ; recent(6/11,6/12)=1300,1400 avg1350 -> +17.4% (up, not a drop)
    # So per_person_drops should be EMPTY for this synthetic set.
    drop_names = [d["employee"] for d in rv["per_person_drops"]]
    check("recent_drops_empty", drop_names == [], f"got drops={drop_names}")

    # To prove the recent-drop machinery actually fires, run a second tiny case:
    recent_payload = {
        "records": [
            {"employee": "Eve", "department": "D", "date": "2026-06-09", "model": "m", "tokens": 1000, "requests": 1},
            {"employee": "Eve", "department": "D", "date": "2026-06-10", "model": "m", "tokens": 1000, "requests": 1},
            {"employee": "Eve", "department": "D", "date": "2026-06-11", "model": "m", "tokens": 100, "requests": 1},
            {"employee": "Eve", "department": "D", "date": "2026-06-12", "model": "m", "tokens": 100, "requests": 1},
        ],
        "period": {"start": "2026-06-08", "end": "2026-06-12"},
        "workdays_only": True,
        "recent_days": 2,
    }
    rv2 = build_result(recent_payload)["recent_days_view"]
    eve = next((d for d in rv2["per_person_drops"] if d["employee"] == "Eve"), None)
    check("eve_drop_present", eve is not None, "Eve drop not detected")
    if eve:
        # prior avg 1000, recent avg 100 -> -90%
        check("eve_drop_pct", eve["drop_pct"] == -90.0, f"got {eve['drop_pct']}")
    check("eve_dept_pct", rv2["dept_recent_vs_prior_pct"] == -90.0,
          f"got {rv2['dept_recent_vs_prior_pct']}")

    # ---- week_over_week (same-weekday): week2 (current) vs week1 (prior) ----
    # current week = week of last workday 6/12 -> Monday 6/8; paired to 6/1 week.
    wow = result["week_over_week"]
    check("wow_current_week", wow["current_week_monday"] == "2026-06-08",
          f"got {wow['current_week_monday']}")
    check("wow_prev_week", wow["prev_week_monday"] == "2026-06-01",
          f"got {wow['prev_week_monday']}")
    # dept same-weekday avg: wk1 13000/5=2600 -> wk2 8501/5=1700.2 => -34.6%
    check("wow_dept_pct", wow["dept_wow_pct"] == -34.6, f"got {wow['dept_wow_pct']}")
    # Bob (1000->~0) and Dave (800->silent) drop same-weekday; Alice rose, Carol steady.
    wow_drops = [d["employee"] for d in wow["per_person_drops"]]
    check("wow_drops", "Bob" in wow_drops and "Dave" in wow_drops, f"got {wow_drops}")

    # ---- gaps must mention malformed rows ----
    check("gap_malformed", any("malformed" in g for g in result["gaps"]),
          f"gaps={result['gaps']}")

    # ---- empty input must not throw and yields a valid empty result ----
    try:
        empty = build_result({"records": [], "period": {"start": "2026-06-01", "end": "2026-06-05"}})
        check("empty_scope", empty["scope"]["n_records"] == 0, "empty n_records != 0")
        check("empty_overall", empty["overall"]["trend"] == "flat", "empty trend not flat")
        check("empty_gap", any("empty result" in g for g in empty["gaps"]), "empty gap note missing")
    except Exception as exc:  # pragma: no cover - must never happen
        check("empty_no_throw", False, f"threw {exc!r}")

    # ---- markdown render must not throw and include key sections ----
    try:
        md = render_markdown(result)
        check("md_has_growth", "持续增长" in md, "md missing growth section")
        check("md_has_recent", "最近" in md, "md missing recent section")
    except Exception as exc:  # pragma: no cover
        check("md_no_throw", False, f"render_markdown threw {exc!r}")

    # ---- intraday (same-time-window) mode ----
    # Baseline day (Wed 6/10): 100 tokens/hour for hours 0..19  (window@16 = 1600, full = 2000)
    # Today (Thu 6/11):        110 tokens/hour for hours 0..15  (window@16 = 1760)
    # same-window: 1600 -> 1760 = +10.0%
    # naive partial-vs-full: 2000 -> 1760 = -12.0%  (sign flip vs +10% — the whole point)
    # projection: 1760 * 2000/1600 = 2200 -> +10.0% vs baseline full
    intraday_items = (
        [{"hour": f"{h:02d}:00", "date": "2026-06-10", "totalTokens": 100, "requests": 2} for h in range(20)]
        + [{"hour": h, "date": "2026-06-11", "totalTokens": 110, "requests": 2, "model": "gpt-x"} for h in range(16)]
    )
    intr = build_intraday_result({"items": intraday_items, "cutoff_hour": 16})
    o = intr["overall"]
    check("intr_dates", intr["today"] == "2026-06-11" and intr["baseline"] == "2026-06-10",
          f"got {intr['today']} / {intr['baseline']}")
    check("intr_window", o["baseline_window"]["tokens"] == 1600.0 and o["today_window"]["tokens"] == 1760.0,
          f"got {o['baseline_window']['tokens']} -> {o['today_window']['tokens']}")
    check("intr_same_window", o["same_window_delta_pct"] == 10.0, f"got {o['same_window_delta_pct']}")
    check("intr_naive_flips_sign", o["naive_partial_vs_full_pct"] == -12.0, f"got {o['naive_partial_vs_full_pct']}")
    check("intr_projection", o["projected_today_full_tokens"] == 2200.0 and o["projected_vs_baseline_full_pct"] == 10.0,
          f"got {o['projected_today_full_tokens']} / {o['projected_vs_baseline_full_pct']}")
    # per-series: gpt-x rows only exist today -> baseline window 0 -> +100% capped rule
    gptx = next((b for b in intr["per_series"] if b["series"] == "gpt-x"), None)
    check("intr_series_present", gptx is not None, f"per_series={[b['series'] for b in intr['per_series']]}")
    # derived cutoff (no cutoff_hour): today's last active hour is 15 -> cutoff 16, same numbers
    intr2 = build_intraday_result({"items": intraday_items})
    check("intr_derived_cutoff", intr2["cutoff_hour"] == 16, f"got {intr2['cutoff_hour']}")
    check("intr_derived_gap_note", any("cutoff_hour not provided" in g for g in intr2["gaps"]),
          f"gaps={intr2['gaps']}")
    # markdown must not throw and must carry the headline + forbidden labels
    try:
        imd = render_intraday_markdown(intr)
        check("intr_md_headline", "同窗对比" in imd and "禁止口径" in imd, "intraday md missing key labels")
    except Exception as exc:  # pragma: no cover
        check("intr_md_no_throw", False, f"render_intraday_markdown threw {exc!r}")

    # ---- per-user / per-department expected-by-now view ----
    # Org hourly: baseline hours 0..9 @100 (full 1000); today hours 0..4 @100; cutoff 5
    # -> pace_ratio = 500/1000 = 0.5
    iu_items = (
        [{"hour": h, "date": "2026-06-10", "totalTokens": 100, "requests": 1} for h in range(10)]
        + [{"hour": h, "date": "2026-06-11", "totalTokens": 100, "requests": 1} for h in range(5)]
    )
    iu_users = [
        {"name": "甲", "department": "X", "baseline_tokens": 1000, "today_tokens": 200},   # expected 500 -> -60% drop
        {"name": "乙", "department": "Y", "baseline_tokens": 400, "today_tokens": 600},    # expected 200 -> +200% rise
        {"name": "丙", "department": "X", "baseline_tokens": 500, "today_tokens": 0},      # silent_today
        {"name": "丁", "department": "Y", "baseline_tokens": 0, "today_tokens": 300},      # new
    ]
    iu = build_intraday_result({"items": iu_items, "cutoff_hour": 5, "users": iu_users})
    check("iu_ratio", iu["pace_ratio"] == 0.5, f"got {iu['pace_ratio']}")
    by_name = {u["name"]: u for u in iu["users"]}
    check("iu_drop", by_name["甲"]["class"] == "drop" and by_name["甲"]["delta_vs_expected_pct"] == -60.0,
          f"got {by_name['甲']}")
    check("iu_rise", by_name["乙"]["class"] == "rise" and by_name["乙"]["delta_vs_expected_pct"] == 200.0,
          f"got {by_name['乙']}")
    check("iu_silent", by_name["丙"]["class"] == "silent_today", f"got {by_name['丙']['class']}")
    check("iu_new", by_name["丁"]["class"] == "new", f"got {by_name['丁']['class']}")
    by_dept = {d["department"]: d for d in iu["departments"]}
    # dept X: baseline 1500, expected 750, today 200 -> -73.3%; dept Y: expected 200, today 900 -> +350%
    check("iu_dept_x", by_dept["X"]["delta_vs_expected_pct"] == -73.3, f"got {by_dept['X']}")
    check("iu_dept_y", by_dept["Y"]["delta_vs_expected_pct"] == 350.0, f"got {by_dept['Y']}")
    check("iu_dept_order", iu["departments"][0]["department"] == "X", "drops should sort first")
    check("iu_estimate_gap", any("估算" in g for g in iu["gaps"]), f"gaps={iu['gaps']}")
    try:
        iumd = render_intraday_markdown(iu)
        check("iu_md_sections", "分部门" in iumd and "明显下降" in iumd and "今日未使用" in iumd,
              "intraday md missing dept/drop sections")
    except Exception as exc:  # pragma: no cover
        check("iu_md_no_throw", False, f"render_intraday_markdown(users) threw {exc!r}")
    # empty input must not throw
    try:
        empty_intr = build_intraday_result({})
        check("intr_empty_gap", any("empty result" in g for g in empty_intr["gaps"]), f"gaps={empty_intr['gaps']}")
    except Exception as exc:  # pragma: no cover
        check("intr_empty_no_throw", False, f"threw {exc!r}")

    if failures:
        print("FAIL")
        for f in failures:
            print("  - " + f)
        return 1
    print("PASS")
    print(f"  checks: dept Δ=-34.6% (down), growth=Alice(+300%), "
          f"decline=Bob(-100%)+Dave(由活转静), recent-drop=Eve(-90%), "
          f"weekend/malformed correctly excluded.")
    return 0


# ---------------------------------------------------------------------------
# Intraday (same-time-window) comparison — "今天 vs 昨天" done RIGHT
# ---------------------------------------------------------------------------
# WHY: comparing "today's partial accumulation" against "yesterday's FULL day"
# is a dirty comparison (window length AND date both move) and can even flip
# the sign of the conclusion (real incident 2026-07-02: naive said -31.9%
# "明显下降", same-window said +4.8% — slightly UP). The agent must never hand
# "按同一时间点再复核" back to the user; this mode computes it.
#
# STDIN (with --intraday):
#   {
#     "items": [   # raw rows from dfcode `query_usage groupBy=hour_day`
#                  # (or per-model rows from two `groupBy=model_hour` calls,
#                  #  each row then tagged with its "date")
#       {"hour": "16:00"|16, "date": "YYYY-MM-DD",
#        "totalTokens": n, "requests": n, "model": "optional"},
#       ...
#     ],
#     "today":        "YYYY-MM-DD",  # optional; default = max date in items
#     "baseline":     "YYYY-MM-DD",  # optional; default = latest date < today
#     "cutoff_hour":  16             # optional; window = hours [0, cutoff).
#                                    # default = (today's last active hour)+1,
#                                    # derived from DATA (deterministic, no wall clock)
#   }
#
# OUTPUT: same_window_delta_pct is THE headline number.
# naive_partial_vs_full_pct is included ONLY to name the forbidden comparison.


def _parse_hour(value: Any) -> int | None:
    """Accept 16, "16", "16:00", "07:00" -> 16/7; else None (never raises)."""
    s = _str(value).strip()
    if not s:
        return None
    s = s.split(":")[0]
    try:
        h = int(s)
    except ValueError:
        return None
    return h if 0 <= h <= 23 else None


def _intraday_window(series: dict[int, tuple[float, float]], upto: int) -> dict[str, float]:
    tokens = sum(t for h, (t, _r) in series.items() if h < upto)
    requests = sum(r for h, (_t, r) in series.items() if h < upto)
    return {"tokens": round(tokens, 2), "requests": round(requests, 2)}


def build_intraday_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Same-time-window today-vs-baseline comparison from hourly rows."""
    gaps: list[str] = []
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raw_items = []
        gaps.append("no items[] provided → empty result")

    # cube: series -> date -> hour -> (tokens, requests). "总量" always maintained.
    cube: dict[str, dict[str, dict[int, tuple[float, float]]]] = {}
    malformed = 0
    for it in raw_items:
        if not isinstance(it, dict):
            malformed += 1
            continue
        d = _parse_date(_str(it.get("date")))
        h = _parse_hour(it.get("hour"))
        if d is None or h is None:
            malformed += 1
            continue
        tokens = _num(it.get("totalTokens", it.get("tokens")))
        requests = _num(it.get("requests", it.get("totalRequests")))
        series_names = ["总量"]
        model = _str(it.get("model") or it.get("series")).strip()
        if model:
            series_names.append(model)
        for name in series_names:
            day = cube.setdefault(name, {}).setdefault(d.isoformat(), {})
            t0, r0 = day.get(h, (0.0, 0.0))
            day[h] = (t0 + tokens, r0 + requests)
    if malformed:
        gaps.append(f"{malformed} malformed item(s) skipped (bad date/hour)")

    total = cube.get("总量", {})
    dates = sorted(total)
    today = _str(payload.get("today")) or (dates[-1] if dates else "")
    baseline = _str(payload.get("baseline") or payload.get("yesterday"))
    if not baseline:
        prior = [d for d in dates if d < today]
        baseline = prior[-1] if prior else ""
    if not today or not baseline:
        gaps.append("cannot determine today/baseline dates from items → empty result")

    cutoff_raw = payload.get("cutoff_hour")
    if cutoff_raw is None:
        hours_today = [h for h, (t, r) in total.get(today, {}).items() if t > 0 or r > 0]
        cutoff = (max(hours_today) + 1) if hours_today else 24
        gaps.append(f"cutoff_hour not provided → derived from data as {cutoff:02d}:00 (today's last active hour + 1); pass cutoff_hour explicitly for a wall-clock cut")
    else:
        cutoff = max(0, min(24, int(_num(cutoff_raw))))

    td, bd = _parse_date(today), _parse_date(baseline)
    if bd is not None and bd.weekday() >= 5:
        gaps.append(f"baseline {baseline} 是周末——工作日问题建议改用上一个工作日或上周同星期几作基线")
    if td is not None and bd is not None and (td - bd).days != 1:
        gaps.append(f"baseline 与 today 相差 {(td - bd).days} 天(非昨天)——确认这是有意选择的基线")

    def series_block(series: dict[str, dict[int, tuple[float, float]]]) -> dict[str, Any]:
        tw = _intraday_window(series.get(today, {}), cutoff)
        bw = _intraday_window(series.get(baseline, {}), cutoff)
        bf = _intraday_window(series.get(baseline, {}), 24)
        tf = _intraday_window(series.get(today, {}), 24)
        projected = round(tw["tokens"] * bf["tokens"] / bw["tokens"], 2) if bw["tokens"] > 0 else None
        return {
            "today_window": tw,
            "baseline_window": bw,
            "same_window_delta_pct": _pct_change(bw["tokens"], tw["tokens"]),
            "same_window_requests_delta_pct": _pct_change(bw["requests"], tw["requests"]),
            "baseline_full_day": bf,
            "naive_partial_vs_full_pct": _pct_change(bf["tokens"], tf["tokens"]),
            "projected_today_full_tokens": projected,
            "projected_vs_baseline_full_pct": _pct_change(bf["tokens"], projected) if projected is not None else None,
        }

    overall = series_block(total)
    per_series: list[dict[str, Any]] = []
    for name in sorted(cube):
        if name == "总量":
            continue
        block = series_block(cube[name])
        block["series"] = name
        block["window_delta_tokens"] = round(block["today_window"]["tokens"] - block["baseline_window"]["tokens"], 2)
        per_series.append(block)
    per_series.sort(key=lambda b: (-abs(b["window_delta_tokens"]), b["series"]))

    # ---- per-user / per-department expected-by-now view ------------------
    # Hourly data has no user/department dimension (and per-person hourly calls
    # would blow the query budget), so we scale each user's BASELINE FULL DAY by
    # the org-wide intraday pace ratio (org baseline window / org baseline full)
    # to get an "expected by now" figure, then compare today's partial against
    # THAT — an estimate (assumes shared intraday shape), always labeled 估算.
    thresholds = {**DEFAULT_THRESHOLDS, **(payload.get("thresholds") or {})}
    bw_tokens = overall["baseline_window"]["tokens"]
    bf_tokens = overall["baseline_full_day"]["tokens"]
    pace_ratio = round(bw_tokens / bf_tokens, 4) if bf_tokens > 0 else None
    users_out: list[dict[str, Any]] = []
    departments_out: list[dict[str, Any]] = []
    raw_users = payload.get("users")
    if isinstance(raw_users, list) and raw_users:
        if pace_ratio is None:
            gaps.append("baseline full-day tokens are 0 → cannot scale expected-by-now; per-user view skipped")
        else:
            dept_acc: dict[str, dict[str, float]] = {}
            for u in raw_users:
                if not isinstance(u, dict):
                    continue
                name = _str(u.get("name") or u.get("employee") or u.get("user")).strip() or "(unknown)"
                dept = _str(u.get("department")).strip() or "(未分组)"
                base_full = _num(u.get("baseline_tokens", u.get("baseline_full_tokens")))
                today_tokens = _num(u.get("today_tokens", u.get("tokens")))
                expected = round(base_full * pace_ratio, 2)
                if base_full <= SILENT_EPSILON and today_tokens > SILENT_EPSILON:
                    klass = "new"
                    delta = None
                elif base_full > SILENT_EPSILON and today_tokens <= SILENT_EPSILON:
                    klass = "silent_today"
                    delta = -100.0
                else:
                    delta = _pct_change(expected, today_tokens) if expected > SILENT_EPSILON else None
                    if delta is not None and delta <= -float(thresholds["drop_pct"]):
                        klass = "drop"
                    elif delta is not None and delta >= float(thresholds["growth_pct"]):
                        klass = "rise"
                    else:
                        klass = "steady"
                users_out.append({
                    "name": name,
                    "department": dept,
                    "baseline_full_tokens": round(base_full, 2),
                    "expected_window_tokens": expected,
                    "today_window_tokens": round(today_tokens, 2),
                    "delta_vs_expected_pct": delta,
                    "class": klass,
                })
                acc = dept_acc.setdefault(dept, {"baseline_full": 0.0, "today": 0.0})
                acc["baseline_full"] += base_full
                acc["today"] += today_tokens
            for dept in sorted(dept_acc):
                acc = dept_acc[dept]
                d_expected = round(acc["baseline_full"] * pace_ratio, 2)
                departments_out.append({
                    "department": dept,
                    "baseline_full_tokens": round(acc["baseline_full"], 2),
                    "expected_window_tokens": d_expected,
                    "today_window_tokens": round(acc["today"], 2),
                    "delta_vs_expected_pct": _pct_change(d_expected, acc["today"]) if d_expected > SILENT_EPSILON else None,
                })
            departments_out.sort(key=lambda d: (d["delta_vs_expected_pct"] if d["delta_vs_expected_pct"] is not None else 0.0, d["department"]))
            gaps.append(f"分部门/个人为估算口径:昨日整日 × 全局进度比 {pace_ratio}(假设各人日内节奏相同),非严格同窗")

    return {
        "mode": "intraday",
        "today": today,
        "baseline": baseline,
        "cutoff_hour": cutoff,
        "window_desc": f"两天均取 00:00–{cutoff:02d}:00 累计(同窗)",
        "pace_ratio": pace_ratio,
        "overall": overall,
        "per_series": per_series,
        "departments": departments_out,
        "users": users_out,
        "gaps": gaps,
    }


def render_intraday_markdown(result: dict[str, Any]) -> str:
    o = result["overall"]
    cutoff = result["cutoff_hour"]
    lines = [
        f"## 当日同窗对比 · {result['today']} vs {result['baseline']}(均截至 {cutoff:02d}:00)",
        "",
        f"- **同窗对比(结论用这个)**: {o['baseline_window']['tokens']:,.0f} → {o['today_window']['tokens']:,.0f} tokens,**Δ {o['same_window_delta_pct']:+.1f}%**;请求 Δ {o['same_window_requests_delta_pct']:+.1f}%",
        f"- 参考·基线日整日: {o['baseline_full_day']['tokens']:,.0f} tokens",
    ]
    if o.get("projected_today_full_tokens") is not None:
        lines.append(f"- 参考·按今日节奏折算全日(推测): ≈{o['projected_today_full_tokens']:,.0f} tokens,较基线日整日 {o['projected_vs_baseline_full_pct']:+.1f}%")
    lines.append(f"- ⚠️ 禁止口径·今日累计 vs 基线日整日: {o['naive_partial_vs_full_pct']:+.1f}%(时间窗不等长,不得作结论)")
    if result["per_series"]:
        lines += ["", "### 分序列同窗变化(按 |Δtokens| 排序)"]
        for b in result["per_series"][:10]:
            lines.append(f"- {b['series']}: {b['baseline_window']['tokens']:,.0f} → {b['today_window']['tokens']:,.0f}(Δ {b['same_window_delta_pct']:+.1f}%,{b['window_delta_tokens']:+,.0f} tokens)")

    def _fmt_delta(v: float | None) -> str:
        return f"{v:+.1f}%" if v is not None else "n/a"

    if result.get("departments"):
        lines += ["", "### 分部门(昨日整日×进度比=到此刻期望 vs 今日实际,估算)"]
        for d in result["departments"]:
            lines.append(f"- {d['department']}: 期望≈{d['expected_window_tokens']:,.0f} vs 实际 {d['today_window_tokens']:,.0f}(Δ {_fmt_delta(d['delta_vs_expected_pct'])})")
    users = result.get("users") or []
    drops = sorted([u for u in users if u["class"] in ("drop", "silent_today")], key=lambda u: (u["delta_vs_expected_pct"] if u["delta_vs_expected_pct"] is not None else -100.0))
    rises = sorted([u for u in users if u["class"] == "rise"], key=lambda u: -(u["delta_vs_expected_pct"] or 0.0))
    news = [u for u in users if u["class"] == "new"]
    if drops:
        lines += ["", f"### 📉 较期望明显下降({len(drops)} 人)"]
        for u in drops[:8]:
            tag = "今日未使用" if u["class"] == "silent_today" else f"Δ {_fmt_delta(u['delta_vs_expected_pct'])}"
            lines.append(f"- {u['name']}·{u['department']}: 期望≈{u['expected_window_tokens']:,.0f} vs 实际 {u['today_window_tokens']:,.0f}({tag})")
    if rises:
        lines += ["", f"### 📈 较期望明显上升({len(rises)} 人)"]
        for u in rises[:8]:
            lines.append(f"- {u['name']}·{u['department']}: 期望≈{u['expected_window_tokens']:,.0f} vs 实际 {u['today_window_tokens']:,.0f}(Δ {_fmt_delta(u['delta_vs_expected_pct'])})")
    if news:
        lines += ["", f"### 🆕 昨日无用量、今日新增({len(news)} 人)"]
        for u in news[:5]:
            lines.append(f"- {u['name']}·{u['department']}: 今日 {u['today_window_tokens']:,.0f}")
    if result["gaps"]:
        lines += ["", "缺口: " + "; ".join(result["gaps"])]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic 星元 usage-analysis engine (the fact cube).",
    )
    parser.add_argument("--md", action="store_true",
                        help="emit a compact markdown digest instead of JSON")
    parser.add_argument("--intraday", action="store_true",
                        help="same-time-window today-vs-baseline comparison from hourly rows (query_usage groupBy=hour_day)")
    parser.add_argument("--selftest", action="store_true",
                        help="run the built-in synthetic dataset, assert numbers, print PASS/FAIL")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        # never throw; emit a valid empty result with a gap note
        payload = {}
        if args.intraday:
            result = build_intraday_result(payload)
            result["gaps"].insert(0, f"STDIN was not valid JSON ({exc}) → empty result")
            print(render_intraday_markdown(result) if args.md else json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        result = build_result(payload)
        result["gaps"].insert(0, f"STDIN was not valid JSON ({exc}) → empty result")
        if args.md:
            print(render_markdown(result))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if not isinstance(payload, dict):
        payload = {}

    if args.intraday:
        result = build_intraday_result(payload)
        print(render_intraday_markdown(result) if args.md else json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    result = build_result(payload)
    if args.md:
        print(render_markdown(result))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
