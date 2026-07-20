import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "xingyuan-monitor/skills/dfcode-usage-analysis/scripts/compare_scope.py"
FIXTURE = ROOT / "tests/fixtures/xingyuan_scope_incident.json"


def load_engine():
    spec = importlib.util.spec_from_file_location("compare_scope", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load compare_scope engine")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class XingyuanScopeComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = load_engine()
        cls.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_incident_fixture_uses_one_fixed_roster_and_excludes_noise(self):
        result = self.engine.analyze(self.payload)

        self.assertEqual(
            [period["total"] for period in result["periods"]], [150, 120, 200]
        )
        self.assertEqual(result["scope"]["population_size"], 3)
        self.assertEqual(
            result["roster_exclusions"],
            {
                "empty_department": 1,
                "non_staff": 1,
                "out_of_scope": 2,
                "placeholder_department": 2,
            },
        )
        self.assertEqual(
            [period["excluded_row_count"] for period in result["periods"]], [2, 3, 4]
        )
        self.assertEqual(
            [delta["percent"] for delta in result["deltas"]], ["-20.00", "66.67"]
        )
        ranked_ids = {item["user_id"] for item in result["contributors"]}
        self.assertEqual(ranked_ids, {"u-001", "u-002", "u-003"})

    def test_joins_by_user_id_and_zero_fills_missing_rows(self):
        result = self.engine.analyze(self.payload)
        users = {item["user_id"]: item for item in result["contributors"]}

        self.assertEqual(users["u-002"]["name"], "同名用户")
        self.assertEqual(users["u-002"]["values"], [50, 0, 70])
        self.assertEqual(users["u-003"]["values"], [0, 40, 20])
        self.assertEqual(users["u-001"]["values"], [100, 80, 110])

    def test_generates_scope_statement_from_validated_metadata(self):
        result = self.engine.analyze(self.payload)

        self.assertEqual(
            result["scope_statement"],
            "口径：请求次数；部门=智能视迅；固定人员集合=3人；三个周期均截至18:00；已排除未分配、占位、非员工及跨部门人员。",
        )

    def assert_mismatch(self, field, value):
        payload = copy.deepcopy(self.payload)
        payload["periods"][2][field] = value
        with self.assertRaisesRegex(self.engine.ScopeValidationError, field):
            self.engine.analyze(payload)

    def assert_invalid(self, payload, message):
        with self.assertRaisesRegex(self.engine.ScopeValidationError, message):
            self.engine.analyze(payload)

    def test_rejects_department_versus_organization_scope(self):
        self.assert_mismatch("scope_type", "organization")

    def test_rejects_cutoff_mismatch(self):
        self.assert_mismatch("cutoff_hour", 24)

    def test_rejects_metric_mismatch(self):
        self.assert_mismatch("metric", "tokens")

    def test_rejects_scope_value_timezone_and_population_mode_mismatches(self):
        for field, value in (
            ("scope_value", "系统部"),
            ("timezone", "UTC"),
            ("population_mode", "period_roster"),
        ):
            with self.subTest(field=field):
                self.assert_mismatch(field, value)

    def test_requires_user_grouping_and_matching_date_semantics(self):
        for field, value in (
            ("group_by", "department"),
            ("date_semantics", "utc_window"),
        ):
            with self.subTest(field=field):
                self.assert_mismatch(field, value)

        for field, value in (("group_by", "department"), ("date_semantics", "")):
            payload = copy.deepcopy(self.payload)
            payload["comparison"][field] = value
            with self.subTest(comparison_field=field):
                self.assert_invalid(payload, field)

    def test_rejects_invalid_or_unequal_period_date_windows(self):
        cases = (
            ("from", "2026/07/13", "ISO date"),
            ("to", "not-a-date", "ISO date"),
            ("to", "2026-07-12", "from must be on or before to"),
        )
        for field, value, message in cases:
            payload = copy.deepcopy(self.payload)
            payload["periods"][2][field] = value
            with self.subTest(field=field, value=value):
                self.assert_invalid(payload, message)

        payload = copy.deepcopy(self.payload)
        payload["periods"][1]["to"] = "2026-07-07"
        self.assert_invalid(payload, "inclusive duration")

    def test_rejects_unsupported_metrics_and_invalid_cutoffs(self):
        for metric in ("cost", "", 123):
            payload = copy.deepcopy(self.payload)
            payload["comparison"]["metric"] = metric
            for period in payload["periods"]:
                period["metric"] = metric
            with self.subTest(metric=metric):
                self.assert_invalid(payload, "metric")

        for cutoff in (True, False, -1, 24, 18.0):
            payload = copy.deepcopy(self.payload)
            payload["comparison"]["cutoff_hour"] = cutoff
            for period in payload["periods"]:
                period["cutoff_hour"] = cutoff
            with self.subTest(cutoff=cutoff):
                self.assert_invalid(payload, "cutoff_hour")

    def test_accepts_tokens_as_the_other_supported_metric(self):
        payload = copy.deepcopy(self.payload)
        payload["comparison"]["metric"] = "tokens"
        for period in payload["periods"]:
            period["metric"] = "tokens"
            for row in period["rows"]:
                row["tokens"] = row.pop("requests")

        result = self.engine.analyze(payload)

        self.assertEqual(
            [period["total"] for period in result["periods"]], [150, 120, 200]
        )
        self.assertIn("Token 用量", result["scope_statement"])

    def test_mixed_large_integer_and_fractional_tokens_aggregate_exactly(self):
        payload = copy.deepcopy(self.payload)
        huge = 10**400
        payload["comparison"]["metric"] = "tokens"
        for period in payload["periods"]:
            period["metric"] = "tokens"
            for row in period["rows"]:
                row["tokens"] = row.pop("requests")
        payload["periods"][0]["rows"][0]["tokens"] = huge
        payload["periods"][0]["rows"][1]["tokens"] = 0.5

        result = self.engine.analyze(payload)

        self.assertEqual(result["periods"][0]["total"], str(huge) + ".5")
        users = {item["user_id"]: item for item in result["contributors"]}
        self.assertEqual(users["u-001"]["values"][0], huge)
        self.assertEqual(users["u-002"]["values"][0], "0.5")

    def test_mixed_token_contributor_deltas_serialize_exactly(self):
        payload = copy.deepcopy(self.payload)
        huge = 10**400
        payload["comparison"]["metric"] = "tokens"
        for period in payload["periods"]:
            period["metric"] = "tokens"
            for row in period["rows"]:
                row["tokens"] = row.pop("requests")
        payload["periods"][0]["rows"][0]["tokens"] = huge
        payload["periods"][1]["rows"][0]["tokens"] = huge + 1
        payload["periods"][2]["rows"][0]["tokens"] = 0.5
        payload["periods"][0]["rows"][1]["tokens"] = 0.5
        payload["periods"][2]["rows"][1]["tokens"] = 2

        result = self.engine.analyze(payload)
        users = {item["user_id"]: item for item in result["contributors"]}

        self.assertEqual(users["u-001"]["values"], [huge, huge + 1, "0.5"])
        self.assertEqual(users["u-001"]["delta"], "-" + str(huge - 1) + ".5")
        self.assertEqual(users["u-002"]["values"], ["0.5", 0, 2])
        self.assertEqual(users["u-002"]["delta"], "1.5")

    def test_mixed_token_cli_output_strict_parses_without_leaks(self):
        payload = copy.deepcopy(self.payload)
        huge = 10**400
        payload["comparison"]["metric"] = "tokens"
        for period in payload["periods"]:
            period["metric"] = "tokens"
            for row in period["rows"]:
                row["tokens"] = row.pop("requests")
        payload["periods"][0]["rows"][0]["tokens"] = huge
        payload["periods"][0]["rows"][1]["tokens"] = 0.5

        def reject_constant(value):
            raise ValueError("non-standard JSON constant: %s" % value)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "secret-mixed-token.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(path)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        parsed = json.loads(completed.stdout, parse_constant=reject_constant)
        self.assertEqual(parsed["periods"][0]["total"], str(huge) + ".5")
        self.assertNotIn("E+", completed.stdout)
        self.assertNotIn("Infinity", completed.stdout)
        self.assertNotIn("NaN", completed.stdout)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertNotIn(str(path), completed.stderr)

    def test_direct_analyze_serializes_over_limit_integral_token_as_string(self):
        payload = copy.deepcopy(self.payload)
        huge = 10**5000
        huge_text = "1" + "0" * 5000
        payload["comparison"]["metric"] = "tokens"
        for period in payload["periods"]:
            period["metric"] = "tokens"
            for row in period["rows"]:
                row["tokens"] = row.pop("requests")
        payload["periods"][0]["rows"][0]["tokens"] = huge
        payload["periods"][0]["rows"][1]["tokens"] = 0

        result = self.engine.analyze(payload)

        self.assertEqual(result["periods"][0]["total"], huge_text)
        users = {item["user_id"]: item for item in result["contributors"]}
        self.assertEqual(users["u-001"]["values"][0], huge_text)

    def test_raw_cli_over_limit_numeric_token_uses_local_parse_policy(self):
        huge_text = "1" + "0" * 5000
        total_text = "1" + "0" * 4998 + "50"
        payload = copy.deepcopy(self.payload)
        payload["comparison"]["metric"] = "tokens"
        for period in payload["periods"]:
            period["metric"] = "tokens"
            for row in period["rows"]:
                row["tokens"] = row.pop("requests")
        payload["periods"][0]["rows"][0]["tokens"] = "RAW_HUGE_TOKEN"
        raw_json = json.dumps(payload, ensure_ascii=False).replace(
            '"RAW_HUGE_TOKEN"', huge_text
        )

        def reject_constant(value):
            raise ValueError("non-standard JSON constant: %s" % value)

        before_limit = sys.get_int_max_str_digits()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "secret-over-limit-token.json"
            path.write_text(raw_json, encoding="utf-8")

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                return_code = self.engine.main([str(path)])

            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(path)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(sys.get_int_max_str_digits(), before_limit)
        self.assertNotIn("set_int_max_str_digits", SCRIPT.read_text(encoding="utf-8"))
        self.assertEqual(return_code, 0, stderr.getvalue())
        in_process = json.loads(stdout.getvalue(), parse_constant=reject_constant)
        self.assertEqual(in_process["periods"][0]["total"], total_text)
        self.assertEqual(in_process["scope"]["cutoff_hour"], 18)
        self.assertIsInstance(in_process["scope"]["cutoff_hour"], int)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        parsed = json.loads(completed.stdout, parse_constant=reject_constant)
        self.assertEqual(parsed["periods"][0]["total"], total_text)
        self.assertNotIn("Infinity", completed.stdout)
        self.assertNotIn("NaN", completed.stdout)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertNotIn(str(path), completed.stderr)

    def test_preserves_arbitrarily_large_integer_totals_and_deltas(self):
        payload = copy.deepcopy(self.payload)
        huge = 10**80 + 123
        payload["periods"][0]["rows"][0]["requests"] = huge
        payload["periods"][0]["rows"][1]["requests"] = 7
        payload["periods"][1]["rows"][0]["requests"] = huge + 9
        payload["periods"][1]["rows"][1]["requests"] = 8
        payload["periods"][1]["rows"][1]["user_id"] = "u-002"
        payload["periods"][2]["rows"][0]["requests"] = huge + 20
        payload["periods"][2]["rows"][1]["requests"] = 10
        payload["periods"][2]["rows"][2]["requests"] = 0

        result = self.engine.analyze(payload)

        self.assertEqual(result["periods"][0]["total"], huge + 7)
        self.assertEqual(result["periods"][1]["total"], huge + 17)
        self.assertEqual(result["periods"][2]["total"], huge + 30)
        self.assertIsInstance(result["periods"][0]["total"], int)
        self.assertEqual(result["deltas"][0]["absolute"], 10)
        self.assertEqual(result["deltas"][1]["absolute"], 13)
        self.assertIsInstance(result["contributors"][0]["values"][0], int)

    def test_preserves_arbitrarily_large_integer_tokens(self):
        payload = copy.deepcopy(self.payload)
        huge = 10**400 + 77
        payload["comparison"]["metric"] = "tokens"
        for period in payload["periods"]:
            period["metric"] = "tokens"
            for row in period["rows"]:
                row["tokens"] = row.pop("requests")
        payload["periods"][0]["rows"][0]["tokens"] = huge
        payload["periods"][1]["rows"][0]["tokens"] = huge + 1
        payload["periods"][2]["rows"][0]["tokens"] = huge + 3

        result = self.engine.analyze(payload)

        self.assertIsInstance(result["periods"][0]["total"], int)
        self.assertEqual(result["periods"][0]["total"], huge + 50)
        self.assertEqual(result["deltas"][0]["absolute"], -9)
        self.assertEqual(result["deltas"][1]["absolute"], 52)

    def test_percentage_is_finite_two_decimal_string_for_huge_values(self):
        payload = copy.deepcopy(self.payload)
        huge = 10**400
        payload["periods"][0]["rows"][0]["requests"] = huge
        payload["periods"][0]["rows"][1]["requests"] = 0
        payload["periods"][1]["rows"][0]["requests"] = huge * 2
        payload["periods"][1]["rows"][1]["requests"] = 0
        payload["periods"][1]["rows"][1]["user_id"] = "u-002"
        payload["periods"][2]["rows"][0]["requests"] = huge // 3
        payload["periods"][2]["rows"][1]["requests"] = 0
        payload["periods"][2]["rows"][2]["requests"] = 0

        result = self.engine.analyze(payload)

        self.assertEqual(result["deltas"][0]["percent"], "100.00")
        self.assertEqual(result["deltas"][1]["percent"], "-83.33")
        self.assertIsInstance(result["deltas"][0]["percent"], str)

        zero = copy.deepcopy(self.payload)
        for row in zero["periods"][0]["rows"]:
            row["requests"] = 0
        self.assertIsNone(self.engine.analyze(zero)["deltas"][0]["percent"])

    def test_percentage_string_handles_extreme_finite_token_float_ratio(self):
        payload = copy.deepcopy(self.payload)
        payload["comparison"]["metric"] = "tokens"
        for period in payload["periods"]:
            period["metric"] = "tokens"
            for row in period["rows"]:
                row["tokens"] = 0.0
                row.pop("requests")
        payload["periods"][0]["rows"][0]["tokens"] = 5e-324
        payload["periods"][1]["rows"][0]["tokens"] = 1e308

        result = self.engine.analyze(payload)

        percent = result["deltas"][0]["percent"]
        self.assertIsInstance(percent, str)
        self.assertRegex(percent, r"^[0-9]+\.00$")
        self.assertNotIn("Infinity", percent)
        self.assertNotIn("E", percent)

    def test_finite_token_floats_aggregate_as_decimal_without_overflow(self):
        payload = copy.deepcopy(self.payload)
        payload["comparison"]["metric"] = "tokens"
        for period in payload["periods"]:
            period["metric"] = "tokens"
            for row in period["rows"]:
                row["tokens"] = float(row.pop("requests"))
        payload["periods"][0]["rows"][0]["tokens"] = 1e308
        payload["periods"][0]["rows"][1]["tokens"] = 1e308

        result = self.engine.analyze(payload)

        self.assertEqual(result["periods"][0]["total"], 2 * 10**308)

    def test_cli_strict_json_for_10_to_400_and_no_diagnostics_leak(self):
        payload = copy.deepcopy(self.payload)
        huge = 10**400
        payload["comparison"]["metric"] = "tokens"
        for period in payload["periods"]:
            period["metric"] = "tokens"
            for row in period["rows"]:
                row["tokens"] = row.pop("requests")
        payload["periods"][0]["rows"][0]["tokens"] = huge
        payload["periods"][1]["rows"][0]["tokens"] = huge * 2

        def reject_constant(value):
            raise ValueError("non-standard JSON constant: %s" % value)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "secret-huge-input.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(path)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout, parse_constant=reject_constant)
        self.assertEqual(result["periods"][0]["total"], huge + 50)
        self.assertEqual(result["deltas"][0]["percent"], "100.00")
        self.assertNotIn("Infinity", completed.stdout)
        self.assertNotIn("NaN", completed.stdout)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertNotIn(str(path), completed.stderr)

    def test_organization_scope_statement_does_not_claim_cross_department_exclusion(
        self,
    ):
        payload = copy.deepcopy(self.payload)
        payload["comparison"]["scope_type"] = "organization"
        payload["comparison"]["scope_value"] = "全公司"
        for period in payload["periods"]:
            period["scope_type"] = "organization"
            period["scope_value"] = "全公司"

        result = self.engine.analyze(payload)

        self.assertIn("组织=全公司", result["scope_statement"])
        self.assertNotIn("跨部门", result["scope_statement"])
        self.assertIn("已排除未分配、占位及非员工人员", result["scope_statement"])

    def test_rejects_non_chronological_duplicate_or_overlapping_periods(self):
        cases = []

        reversed_periods = copy.deepcopy(self.payload)
        reversed_periods["periods"][0], reversed_periods["periods"][1] = (
            reversed_periods["periods"][1],
            reversed_periods["periods"][0],
        )
        cases.append((reversed_periods, "strictly increasing"))

        duplicate_label = copy.deepcopy(self.payload)
        duplicate_label["periods"][1]["label"] = duplicate_label["periods"][0]["label"]
        cases.append((duplicate_label, "duplicate period label"))

        duplicate_window = copy.deepcopy(self.payload)
        duplicate_window["periods"][1]["from"] = duplicate_window["periods"][0]["from"]
        duplicate_window["periods"][1]["to"] = duplicate_window["periods"][0]["to"]
        cases.append((duplicate_window, "strictly increasing"))

        overlapping = copy.deepcopy(self.payload)
        for period, start, end in zip(
            overlapping["periods"],
            ("2026-06-29", "2026-07-05", "2026-07-12"),
            ("2026-07-05", "2026-07-11", "2026-07-18"),
        ):
            period["from"] = start
            period["to"] = end
        cases.append((overlapping, "must not overlap"))

        for payload, message in cases:
            with self.subTest(message=message):
                self.assert_invalid(payload, message)

    def test_requests_require_integers_but_tokens_allow_finite_floats(self):
        for value in (1.5, True, False):
            payload = copy.deepcopy(self.payload)
            payload["periods"][0]["rows"][0]["requests"] = value
            with self.subTest(requests=value):
                self.assert_invalid(payload, "requests must be a nonnegative integer")

        payload = copy.deepcopy(self.payload)
        payload["comparison"]["metric"] = "tokens"
        for period in payload["periods"]:
            period["metric"] = "tokens"
            for row in period["rows"]:
                row["tokens"] = float(row.pop("requests")) + 0.5
        result = self.engine.analyze(payload)
        self.assertEqual(result["periods"][0]["total"], 151)

        for value in (True, float("inf"), float("nan"), -0.5):
            invalid = copy.deepcopy(payload)
            invalid["periods"][0]["rows"][0]["tokens"] = value
            with self.subTest(tokens=value):
                self.assert_invalid(
                    invalid, "tokens must be a nonnegative finite number"
                )

    def test_rejects_duplicate_roster_ids_before_scope_filtering(self):
        payload = copy.deepcopy(self.payload)
        payload["roster"].insert(
            0,
            {
                "user_id": "u-001",
                "name": "contradictory excluded record",
                "department": "未设置",
                "employment_status": "active",
            },
        )
        self.assert_invalid(payload, "duplicate roster user_id: u-001")

    def test_rejects_malformed_nested_input_as_scope_validation_errors(self):
        mutations = (
            (
                lambda payload: payload["roster"].__setitem__(0, "bad-member"),
                "roster member 1",
            ),
            (
                lambda payload: payload["periods"].__setitem__(0, "bad-period"),
                "period 1",
            ),
            (
                lambda payload: payload["periods"][0].__setitem__("rows", {}),
                "rows must be an array",
            ),
            (
                lambda payload: payload["periods"][0]["rows"].__setitem__(0, "bad-row"),
                "row 1",
            ),
        )
        for mutate, message in mutations:
            payload = copy.deepcopy(self.payload)
            mutate(payload)
            with self.subTest(message=message):
                self.assert_invalid(payload, message)

    def test_rejects_non_string_identity_and_metadata_fields(self):
        mutations = (
            (
                lambda payload: payload["roster"][0].__setitem__(
                    "user_id", {"bad": "id"}
                ),
                "user_id must be a string",
            ),
            (
                lambda payload: payload["roster"][0].__setitem__(
                    "department", ["智能视迅"]
                ),
                "department must be a string",
            ),
            (
                lambda payload: payload["periods"][0]["rows"][0].__setitem__(
                    "user_id", 123
                ),
                "user_id must be a string",
            ),
            (
                lambda payload: payload["comparison"].__setitem__(
                    "timezone", ["Asia/Shanghai"]
                ),
                "timezone must be a string",
            ),
            (
                lambda payload: payload["periods"][0].__setitem__("label", 123),
                "period label must be a string",
            ),
        )
        for mutate, message in mutations:
            payload = copy.deepcopy(self.payload)
            mutate(payload)
            with self.subTest(message=message):
                self.assert_invalid(payload, message)

    def test_validates_metric_values_even_for_excluded_rows(self):
        payload = copy.deepcopy(self.payload)
        payload["periods"][0]["rows"][2]["requests"] = "nine hundred"

        self.assert_invalid(payload, "u-004 requests must be a nonnegative integer")

    def test_cli_sanitizes_all_expected_input_errors(self):
        malformed_payloads = (
            {"comparison": [], "roster": [], "periods": []},
            {"comparison": {}, "roster": ["bad-member"], "periods": [{}]},
            {
                "comparison": self.payload["comparison"],
                "roster": self.payload["roster"],
                "periods": ["bad-period"],
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, payload in enumerate(malformed_payloads):
                path = Path(directory) / ("secret-input-%d.json" % index)
                path.write_text(
                    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                )
                failure = subprocess.run(
                    [sys.executable, str(SCRIPT), str(path)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                with self.subTest(index=index):
                    error = json.loads(failure.stderr)
                    self.assertNotEqual(failure.returncode, 0)
                    self.assertEqual(failure.stdout, "")
                    self.assertIn(
                        error["error"], {"scope_validation_error", "input_error"}
                    )
                    self.assertLessEqual(len(error["message"]), 500)
                    self.assertNotIn(str(path), failure.stderr)
                    self.assertNotIn("Traceback", failure.stderr)

        missing = ROOT / "secret-does-not-exist.json"
        failure = subprocess.run(
            [sys.executable, str(SCRIPT), str(missing)],
            check=False,
            capture_output=True,
            text=True,
        )
        error = json.loads(failure.stderr)
        self.assertEqual(error["error"], "input_error")
        self.assertNotIn(str(missing), failure.stderr)
        self.assertNotIn("Traceback", failure.stderr)

    def test_cli_emits_structured_json_and_bounded_nonzero_error(self):
        success = subprocess.run(
            [sys.executable, str(SCRIPT), str(FIXTURE)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertEqual(json.loads(success.stdout)["periods"][2]["total"], 200)

        invalid = copy.deepcopy(self.payload)
        invalid["periods"][1]["metric"] = "tokens"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(invalid, ensure_ascii=False), encoding="utf-8")
            failure = subprocess.run(
                [sys.executable, str(SCRIPT), str(path)],
                check=False,
                capture_output=True,
                text=True,
            )
        error = json.loads(failure.stderr)
        self.assertNotEqual(failure.returncode, 0)
        self.assertEqual(error["error"], "scope_validation_error")
        self.assertIn("metric", error["message"])
        self.assertLessEqual(len(error["message"]), 500)
        self.assertEqual(failure.stdout, "")


if __name__ == "__main__":
    unittest.main()
