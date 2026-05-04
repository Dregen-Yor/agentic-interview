"""
W3.2 单测：CoVe verifier (Chain-of-Verification factor+revise)

论文锚点：Dhuliawala 2024, arXiv:2309.11495

覆盖：
1. 同步规则：length / type_quota
2. LLM 验证轴并行（resume_anchor / no_repeat / difficulty_match）
3. averify 输出 violations + suggested_revision
4. 异常 soft-fail（验证失败不阻塞主流程）
5. aprocess（BaseAgent 兼容接口）

运行：
  uv run python -m unittest interview.tests.test_question_verifier -v
"""

from __future__ import annotations

import logging
import unittest
from unittest.mock import AsyncMock, MagicMock

from interview.agents.question_verifier import QuestionVerifier
from interview.agents.schemas import VerificationCheck


class FakeModel:
    model_name = "fake-verifier"

    def with_structured_output(self, schema, include_raw=False):
        m = MagicMock()
        m.ainvoke = AsyncMock()
        return m


def _make_verifier():
    return QuestionVerifier(FakeModel())


class SyncRules(unittest.TestCase):

    def setUp(self):
        self.qv = _make_verifier()

    def test_length_short_passes(self):
        c = self.qv._verify_length({"question": "请举一个反例。"})
        self.assertTrue(c.passed)

    def test_length_too_long_fails(self):
        c = self.qv._verify_length({"question": "x" * 100})
        self.assertFalse(c.passed)
        self.assertIn("过长", c.message)

    def test_length_empty_fails(self):
        c = self.qv._verify_length({"question": ""})
        self.assertFalse(c.passed)

    def test_type_quota_within_limit(self):
        qa = [{"question_type": "math_logic"}]
        c = self.qv._verify_type_quota({"type": "math_logic"}, qa)
        self.assertTrue(c.passed)

    def test_type_quota_exceeded(self):
        qa = [
            {"question_type": "math_logic"},
            {"question_type": "math_logic"},
        ]
        c = self.qv._verify_type_quota({"type": "math_logic"}, qa)
        self.assertFalse(c.passed)
        self.assertIn("math_logic", c.message)

    def test_opening_bypasses_quota(self):
        qa = [{"question_type": "opening"}, {"question_type": "opening"}]
        c = self.qv._verify_type_quota({"type": "opening"}, qa)
        self.assertTrue(c.passed)


class LLMVerificationAxes(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.qv = _make_verifier()
        # mock 3 个 LLM 验证轴的返回
        async def fake_ainvoke(messages):
            content = messages[1].content if len(messages) > 1 else ""
            for axis in ("resume_anchor", "no_repeat", "difficulty_match"):
                if f"Verification axis: {axis}" in content:
                    return VerificationCheck(name=axis, passed=True, message="")
            return VerificationCheck(name="unknown", passed=True, message="")
        self.qv._structured_model.ainvoke = AsyncMock(side_effect=fake_ainvoke)

    async def test_all_pass_returns_valid(self):
        result = await self.qv.averify(
            candidate_question={"question": "请简述", "type": "math_logic"},
            parsed_profile={"items": [{"id": "item_0", "summary": "数据结构"}]},
            qa_history=[],
        )
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.violations), 0)

    async def test_length_failure_short_circuits(self):
        result = await self.qv.averify(
            candidate_question={"question": "x" * 200, "type": "math_logic"},
            parsed_profile={},
            qa_history=[],
        )
        self.assertFalse(result.is_valid)
        # length 同步检查应在 violations 中
        self.assertTrue(any("过长" in v for v in result.violations))

    async def test_type_quota_violation_in_revisions(self):
        result = await self.qv.averify(
            candidate_question={"question": "短题目", "type": "math_logic"},
            parsed_profile={},
            qa_history=[
                {"question_type": "math_logic"},
                {"question_type": "math_logic"},
            ],
        )
        self.assertFalse(result.is_valid)
        self.assertTrue(any("math_logic" in v for v in result.violations))

    async def test_llm_exception_soft_fails(self):
        async def fail(_messages):
            raise RuntimeError("LLM down")
        self.qv._structured_model.ainvoke = AsyncMock(side_effect=fail)

        # LLM 全挂 → 仍能返回结果（soft-fail），同步规则正常工作
        result = await self.qv.averify(
            candidate_question={"question": "短题目", "type": "math_logic"},
            parsed_profile={},
            qa_history=[],
        )
        # 异常被 soft-fail 视为 passed（避免阻塞主流程）
        # is_valid 由 length + type_quota 决定（都通过）
        self.assertTrue(result.is_valid)
        # 但 LLM check 应该带 soft-fail 提示
        soft_fail_checks = [c for c in result.checks if "soft-fail" in c.message]
        self.assertEqual(len(soft_fail_checks), 3)

    async def test_aprocess_dict_compat(self):
        """BaseAgent 兼容接口"""
        result_dict = await self.qv.aprocess({
            "candidate_question": {"question": "短题目", "type": "math_logic"},
            "parsed_profile": {},
            "qa_history": [],
        })
        self.assertIsInstance(result_dict, dict)
        self.assertIn("is_valid", result_dict)
        self.assertIn("checks", result_dict)


class RevisionHint(unittest.TestCase):

    def setUp(self):
        self.qv = _make_verifier()

    def test_no_violations_empty_hint(self):
        checks = [VerificationCheck(name="length", passed=True, message="")]
        hint = self.qv._build_revision_hint(checks)
        self.assertEqual(hint, "")

    def test_violations_aggregate_to_hint(self):
        checks = [
            VerificationCheck(name="length", passed=False, message="题目过长"),
            VerificationCheck(name="type_quota", passed=False, message="题型超额"),
        ]
        hint = self.qv._build_revision_hint(checks)
        self.assertIn("题目过长", hint)
        self.assertIn("题型超额", hint)


class HelperFunctions(unittest.TestCase):

    def setUp(self):
        self.qv = _make_verifier()

    def test_format_recent_qa_truncates_to_n(self):
        qa = [{"question": f"q{i}", "answer": f"a{i}", "question_type": "math_logic"}
              for i in range(5)]
        text = self.qv._format_recent_qa(qa, n=3)
        # 只包含最后 3 个
        self.assertNotIn("q0", text)
        self.assertIn("q4", text)

    def test_format_recent_qa_empty(self):
        self.assertEqual(self.qv._format_recent_qa([]), "(无历史)")

    def test_compute_avg_score(self):
        qa = [
            {"score_details": {"score": 8}},
            {"score_details": {"score": 6}},
            {"score_details": {"score": 0}},  # 排除
        ]
        self.assertAlmostEqual(self.qv._compute_avg_score(qa), 7.0)


if __name__ == "__main__":
    unittest.main()
