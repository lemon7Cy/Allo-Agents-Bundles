import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOUL = ROOT / "xingyuan-monitor/SOUL.md"
SKILL = ROOT / "xingyuan-monitor/skills/dfcode-usage-analysis/SKILL.md"
ENGINE = ROOT / "xingyuan-monitor/skills/dfcode-usage-analysis/scripts/compare_scope.py"
DESIGN = (
    ROOT
    / "docs/superpowers/specs/2026-07-20-xingyuan-comparison-scope-consistency-design.md"
)


class XingyuanScopeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.soul = SOUL.read_text(encoding="utf-8")
        cls.skill = SKILL.read_text(encoding="utf-8")
        cls.design = DESIGN.read_text(encoding="utf-8")

    def test_soul_requires_engine_and_forbids_ad_hoc_trend_dictionaries(self):
        for phrase in (
            "固定 roster snapshot",
            "compare_scope.py",
            "禁止手工拼装趋势字典",
            "口径不一致必须停止计算",
            "group_by=user",
            "date_semantics=calendar_date_inclusive",
            "相同的包含首尾日持续天数",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.soul)

    def test_skill_defines_normalized_contract_and_exact_invocation(self):
        for phrase in (
            "fixed_roster_snapshot",
            "stable user_id",
            "python skills/dfcode-usage-analysis/scripts/compare_scope.py <input.json>",
            "metric、scope_type、scope_value、timezone、cutoff_hour、population_mode",
            "group_by、date_semantics",
            "不得手工拼装 trend dictionary",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill)

    def test_contract_has_hard_failure_response_and_provisioned_engine(self):
        for phrase in (
            "状态：数据不足",
            "诊断：当前周期口径不一致，已停止计算环比。",
            "缺口：需要使用同一范围、同一固定人员集合和同一截止时间重新取数。",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill)
        self.assertTrue(ENGINE.is_file())

    def test_skill_distinguishes_generic_usage_from_explicit_request_count(self):
        for phrase in (
            "通用“用量”问题默认使用 `tokens`",
            "明确询问请求次数时允许使用 `requests` 进行对比和排名",
            '"group_by": "user"',
            '"date_semantics": "calendar_date_inclusive"',
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill)

    def test_design_normalized_input_includes_grouping_and_date_semantics(self):
        for phrase in (
            '"group_by": "user"',
            '"date_semantics": "calendar_date_inclusive"',
            "identical inclusive duration",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.design)

    def test_skill_templates_are_metric_neutral_and_use_engine_scope_verbatim(self):
        for phrase in (
            "<metric>",
            "原样输出引擎的 `scope_statement`",
            "周期必须按时间严格递增、互不重叠且 label 唯一",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill)
        for contradictory in (
            "同一批人各自的 token delta",
            "逐人列出 `token(周期A) → token(周期B) → Δ`",
            "部门 token 环比",
            "只列 token 变化最大的",
            "用量以 token 计",
            "当部门用量变化时",
            "需要使用同一部门、同一固定人员集合",
        ):
            with self.subTest(contradictory=contradictory):
                self.assertNotIn(contradictory, self.skill)

    def test_design_documents_ordering_value_types_and_scope_wording(self):
        for phrase in (
            "strictly increasing, non-overlapping chronological order",
            "unique period labels",
            "requests values are nonnegative integers",
            "tokens values are nonnegative finite integers or floats",
            "Organization scope statements must not claim cross-department exclusion",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.design)

    def test_percent_contract_is_finite_two_decimal_string(self):
        for document in (self.skill, self.design):
            for phrase in (
                "finite decimal string",
                "two decimal places",
                "zero baseline remains null",
            ):
                with self.subTest(phrase=phrase):
                    self.assertIn(phrase, document)

    def test_token_json_serialization_contract_is_documented(self):
        for document in (self.skill, self.design):
            for phrase in (
                "token values are normalized to Decimal",
                "integral Decimal -> JSON integer",
                "non-integral Decimal -> finite plain decimal string",
                "no exponent",
            ):
                with self.subTest(phrase=phrase):
                    self.assertIn(phrase, document)

    def test_token_digit_limit_contract_is_documented(self):
        for document in (self.skill, self.design):
            for phrase in (
                "safely serializable under Python's integer digit limit",
                "otherwise plain decimal string",
                "parse_int hook",
                "must not change the global integer digit limit",
            ):
                with self.subTest(phrase=phrase):
                    self.assertIn(phrase, document)


if __name__ == "__main__":
    unittest.main()
