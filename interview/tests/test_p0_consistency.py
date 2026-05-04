"""
P0 内部一致性漏洞修复的回归测试

覆盖 4 个一致性修复（+ 顺手解决的 P2-2）：
- P0-1: rubric_clause 与 level 不一致 → 强制覆盖（ScoringAgent._score_one）
- P0-2: SummaryAgent.overall_score 与 qa_history mean 偏差 > 0.5 → 强制覆盖
- P0-3: decision_evidence.turn_index 越界 → 过滤 + 占位补全
- P0-4: decision_evidence.answer_snippet 不在 answer 中 → 过滤
- P2-2: rubric_clause 自由 paraphrase → 用 RUBRIC_DIMENSIONS 精确文字覆盖

运行：
  uv run python -m unittest interview.tests.test_p0_consistency -v
"""

from __future__ import annotations

import logging
import unittest
from unittest.mock import AsyncMock, MagicMock

from interview.agents.scoring_agent import ScoringAgent
from interview.agents.schemas import DimensionScore, DecisionEvidence, SummaryOutput
from interview.agents.summary_agent import (
    SummaryAgent,
    _compute_actual_mean,
    _OVERALL_SCORE_TOLERANCE,
)
from interview.rubrics import RUBRIC_DIMENSIONS


class FakeModel:
    model_name = "fake"

    def with_structured_output(self, schema, include_raw=False):
        m = MagicMock()
        m.ainvoke = AsyncMock()
        return m


def _new_summary_agent():
    return SummaryAgent(FakeModel())


def _new_scoring_agent(n_models=1):
    return ScoringAgent([FakeModel() for _ in range(n_models)])


# ============================================================
# P0-1 + P2-2: rubric_clause 一致性
# ============================================================

class P01_RubricClauseConsistency(unittest.IsolatedAsyncioTestCase):
    """P0-1: 当 LLM 给出的 rubric_clause 与 level 不对应时，应被代码覆盖为 canonical 文字"""

    async def asyncSetUp(self):
        self.agent = _new_scoring_agent()

    async def test_inconsistent_rubric_clause_overwritten(self):
        """LLM 返回 level=HIGH 但 rubric_clause 是 LOW 描述 → 覆盖为 HIGH 描述"""
        wrong_rubric_clause = (
            "LOW: Only reproduces memorized formulas; cannot reason beyond single-step deduction."
        )
        canonical_high = RUBRIC_DIMENSIONS["math_logic"]["levels"]["HIGH"]

        mock_result = DimensionScore(
            dimension="math_logic",
            level="HIGH",
            score=4,
            evidence_quote="(no valid solution)",
            rubric_clause=wrong_rubric_clause,  # ← 故意写成 LOW 描述
            confidence="high",
        )
        self.agent._structured_models[0].ainvoke = AsyncMock(return_value=mock_result)

        result = await self.agent._score_one(
            "math_logic", "Q", "A", "", "math_logic", "medium", 0
        )
        self.assertEqual(result.rubric_clause, canonical_high)
        self.assertEqual(result.level, "HIGH")  # level 不变

    async def test_paraphrased_rubric_clause_overwritten(self):
        """P2-2: LLM paraphrase rubric → 覆盖为 verbatim"""
        paraphrased = "The candidate just memorizes formulas without abstraction"  # paraphrase of LOW
        canonical_low = RUBRIC_DIMENSIONS["math_logic"]["levels"]["LOW"]

        mock_result = DimensionScore(
            dimension="math_logic",
            level="LOW",
            score=1,
            evidence_quote="(no valid solution)",
            rubric_clause=paraphrased,
            confidence="medium",
        )
        self.agent._structured_models[0].ainvoke = AsyncMock(return_value=mock_result)

        result = await self.agent._score_one(
            "math_logic", "Q", "A", "", "math_logic", "medium", 0
        )
        self.assertEqual(result.rubric_clause, canonical_low)

    async def test_correct_rubric_clause_unchanged(self):
        """LLM 给的 rubric_clause 已经精确 → 不变"""
        canonical_medium = RUBRIC_DIMENSIONS["math_logic"]["levels"]["MEDIUM"]

        mock_result = DimensionScore(
            dimension="math_logic",
            level="MEDIUM",
            score=2,
            evidence_quote="(no valid solution)",
            rubric_clause=canonical_medium,
            confidence="high",
        )
        self.agent._structured_models[0].ainvoke = AsyncMock(return_value=mock_result)

        result = await self.agent._score_one(
            "math_logic", "Q", "A", "", "math_logic", "medium", 0
        )
        self.assertEqual(result.rubric_clause, canonical_medium)

    async def test_all_5_dimensions_get_canonical_rubric(self):
        """5 个维度都正确填充对应 level 的 canonical rubric"""
        for dim in ["math_logic", "reasoning_rigor", "communication", "collaboration", "growth_potential"]:
            for level in ["LOW", "MEDIUM", "HIGH"]:
                canonical = RUBRIC_DIMENSIONS[dim]["levels"][level]
                wrong = "Some random LLM-paraphrased text that doesn't match"
                cap = {"math_logic": 4, "reasoning_rigor": 2, "communication": 2,
                       "collaboration": 1, "growth_potential": 1}[dim]
                score = {"LOW": 0, "MEDIUM": min(1, cap), "HIGH": cap}[level]

                mock_result = DimensionScore(
                    dimension=dim, level=level, score=score,
                    evidence_quote="(no valid solution)",
                    rubric_clause=wrong, confidence="medium",
                )
                self.agent._structured_models[0].ainvoke = AsyncMock(return_value=mock_result)

                result = await self.agent._score_one(
                    dim, "Q", "A", "", "math_logic", "medium", 0
                )
                self.assertEqual(
                    result.rubric_clause, canonical,
                    f"{dim}/{level}: rubric_clause 应被覆盖为 canonical",
                )


# ============================================================
# P0-2: overall_score 与 qa mean 一致性
# ============================================================

class P02_OverallScoreConsistency(unittest.TestCase):

    def setUp(self):
        self.sa = _new_summary_agent()

    def _data(self, score=7.0):
        return {
            "final_grade": "C",
            "final_decision": "reject",
            "overall_score": score,
            "summary": "...",
            "decision_evidence": [],
            "boundary_case": False,
            "decision_confidence": "high",
            "requires_human_review": False,
        }

    def _qa(self, scores):
        """构造 qa_history，每条 score 来自 scores list"""
        return [
            {
                "question": "q",
                "answer": "the actual long candidate answer text for fuzzy match",
                "score_details": {
                    "score": s, "agreement": 0.9, "confidence_level": "high",
                    "fallback_used": False, "dimensions": [],
                },
            }
            for s in scores
        ]

    def test_compute_actual_mean(self):
        qa = self._qa([6, 7, 8, 9])
        self.assertAlmostEqual(_compute_actual_mean(qa), 7.5)

    def test_compute_actual_mean_excludes_zero(self):
        qa = self._qa([5, 0, 7])  # 0 视为无效
        self.assertAlmostEqual(_compute_actual_mean(qa), 6.0)

    def test_compute_actual_mean_empty(self):
        self.assertIsNone(_compute_actual_mean([]))

    def test_overall_score_within_tolerance_kept(self):
        """LLM=7.0, mean=7.3，差 0.3 < 0.5 → 保留 LLM 值"""
        data = self._data(score=7.0)
        qa = self._qa([7, 7, 8])  # mean=7.33
        out = self.sa._validate_summary_result(data, 7.0, qa)
        self.assertEqual(out["overall_score"], 7.0)

    def test_overall_score_above_tolerance_overridden(self):
        """LLM=8.0, mean=5.0，差 3.0 > 0.5 → 覆盖为 5.0"""
        data = self._data(score=8.0)
        qa = self._qa([5, 5, 5])
        out = self.sa._validate_summary_result(data, 5.0, qa)
        self.assertEqual(out["overall_score"], 5.0)
        # 5.0 落在 boundary [4.5, 5.5] → 触发 review
        self.assertTrue(out["requires_human_review"])
        self.assertIn("覆盖", out.get("abstain_reason", ""))

    def test_overall_score_missing_filled_with_mean(self):
        """LLM 没给 overall_score → 用 mean 填"""
        data = self._data(score=8.0)
        data["overall_score"] = None
        qa = self._qa([7, 8, 8])  # mean=7.67
        out = self.sa._validate_summary_result(data, 7.67, qa)
        self.assertAlmostEqual(out["overall_score"], 7.7, places=1)

    def test_grade_uses_corrected_score(self):
        """LLM=8.5（A），实际 mean=6.0（C） → 覆盖后 grade=C"""
        data = self._data(score=8.5)
        qa = self._qa([6, 6, 6])  # mean=6.0
        out = self.sa._validate_summary_result(data, 6.0, qa)
        self.assertEqual(out["overall_score"], 6.0)
        self.assertEqual(out["final_grade"], "C")  # 使用校正后的分数算 grade
        self.assertEqual(out["final_decision"], "reject")

    def test_no_qa_history_falls_back_to_average_score(self):
        """qa_history 空 → fallback 到 input 的 average_score"""
        data = self._data(score=7.5)
        qa = []
        out = self.sa._validate_summary_result(data, 7.5, qa)
        # 无 qa 数据时不会触发 P0-2 覆盖（因为 actual_mean = average_score = 7.5）
        self.assertEqual(out["overall_score"], 7.5)


# ============================================================
# P0-3 + P0-4: decision_evidence 校验
# ============================================================

class P03_TurnIndexBounds(unittest.TestCase):

    def setUp(self):
        self.sa = _new_summary_agent()

    def _data_with_evidence(self, evidence_list):
        return {
            "final_grade": "C",
            "final_decision": "reject",
            "overall_score": 6.0,
            "summary": "...",
            "decision_evidence": evidence_list,
            "boundary_case": False,
            "decision_confidence": "medium",
            "requires_human_review": False,
        }

    def _qa(self, n_turns):
        return [
            {
                "question": f"q{i}",
                "answer": f"this is the long candidate answer text for turn {i}",
                "score_details": {"score": 6, "agreement": 0.9,
                                  "confidence_level": "high", "fallback_used": False,
                                  "dimensions": []},
            }
            for i in range(n_turns)
        ]

    def _ev(self, turn_index, snippet="this is the"):
        return {
            "turn_index": turn_index,
            "dimension": "math_logic",
            "observed_level": "MEDIUM",
            "rubric_clause": "x",
            "answer_snippet": snippet,
            "impact": "neutral",
        }

    def test_valid_turn_indices_kept(self):
        qa = self._qa(5)
        data = self._data_with_evidence([self._ev(0), self._ev(2), self._ev(4)])
        out = self.sa._validate_summary_result(data, 6.0, qa)
        self.assertEqual(len(out["decision_evidence"]), 3)
        self.assertEqual({ev["turn_index"] for ev in out["decision_evidence"]}, {0, 2, 4})

    def test_out_of_bound_turn_index_filtered(self):
        """turn_index=99 不存在 → 过滤"""
        qa = self._qa(3)
        # 给 1 条合法 + 2 条越界
        data = self._data_with_evidence([
            self._ev(0),
            self._ev(99),     # 越界
            self._ev(-1),     # 负数
        ])
        out = self.sa._validate_summary_result(data, 6.0, qa)
        # 过滤后只剩 1 条 → padding 补到 3 条
        self.assertGreaterEqual(len(out["decision_evidence"]), 3)
        # 所有 turn_index 必须在 [0, 3) 范围内
        for ev in out["decision_evidence"]:
            self.assertGreaterEqual(ev["turn_index"], 0)
            self.assertLess(ev["turn_index"], 3)

    def test_padding_when_all_evidence_filtered(self):
        """所有 evidence 越界 → 全部过滤后 padding 补 3 条"""
        qa = self._qa(5)
        data = self._data_with_evidence([self._ev(99), self._ev(100)])
        out = self.sa._validate_summary_result(data, 6.0, qa)
        self.assertEqual(len(out["decision_evidence"]), 3)
        for ev in out["decision_evidence"]:
            self.assertLess(ev["turn_index"], 5)


class P04_AnswerSnippetFuzzyValidation(unittest.TestCase):

    def setUp(self):
        self.sa = _new_summary_agent()

    def _data_with_evidence(self, evidence_list):
        return {
            "final_grade": "C",
            "final_decision": "reject",
            "overall_score": 6.0,
            "summary": "...",
            "decision_evidence": evidence_list,
            "boundary_case": False,
            "decision_confidence": "medium",
            "requires_human_review": False,
        }

    def _qa_with_answer(self, answer):
        return [{
            "question": "q",
            "answer": answer,
            "score_details": {"score": 6, "agreement": 0.9,
                              "confidence_level": "high", "fallback_used": False,
                              "dimensions": []},
        }]

    def test_valid_snippet_kept(self):
        qa = self._qa_with_answer("我用归纳法证明 n=k+1 时成立。先验证基础情况。")
        data = self._data_with_evidence([
            {"turn_index": 0, "dimension": "math_logic", "observed_level": "HIGH",
             "rubric_clause": "x", "answer_snippet": "归纳法证明", "impact": "positive"},
            {"turn_index": 0, "dimension": "reasoning_rigor", "observed_level": "MEDIUM",
             "rubric_clause": "y", "answer_snippet": "我用归纳法证明 n=k+1 时成立", "impact": "positive"},
            {"turn_index": 0, "dimension": "communication", "observed_level": "MEDIUM",
             "rubric_clause": "z", "answer_snippet": "先验证基础情况", "impact": "neutral"},
        ])
        out = self.sa._validate_summary_result(data, 6.0, qa)
        self.assertEqual(len(out["decision_evidence"]), 3)

    def test_fabricated_snippet_filtered(self):
        """LLM 编了一个不在 answer 中的 snippet → 过滤"""
        qa = self._qa_with_answer("我用归纳法证明 n=k+1 时成立")
        data = self._data_with_evidence([
            {"turn_index": 0, "dimension": "math_logic", "observed_level": "HIGH",
             "rubric_clause": "x",
             "answer_snippet": "量子力学的态叠加原理",  # ← 完全不在 answer 中
             "impact": "positive"},
        ])
        out = self.sa._validate_summary_result(data, 6.0, qa)
        # 这条被过滤后 → padding 补 3 条
        self.assertEqual(len(out["decision_evidence"]), 3)
        # 不应包含被过滤的 quote
        snippets = [ev["answer_snippet"] for ev in out["decision_evidence"]]
        self.assertNotIn("量子力学的态叠加原理", snippets)

    def test_special_marker_snippet_passes(self):
        """0 分契约 / fallback / 占位标记永远视为合法"""
        qa = self._qa_with_answer("answer")
        data = self._data_with_evidence([
            {"turn_index": 0, "dimension": "math_logic", "observed_level": "LOW",
             "rubric_clause": "x", "answer_snippet": "(no valid solution)", "impact": "negative"},
            {"turn_index": 0, "dimension": "reasoning_rigor", "observed_level": "LOW",
             "rubric_clause": "x", "answer_snippet": "无有效解答", "impact": "negative"},
            {"turn_index": 0, "dimension": "communication", "observed_level": "LOW",
             "rubric_clause": "x", "answer_snippet": "(security_violation)", "impact": "neutral"},
        ])
        out = self.sa._validate_summary_result(data, 6.0, qa)
        self.assertEqual(len(out["decision_evidence"]), 3)
        # 三条特殊标记都应被保留
        snippets = [ev["answer_snippet"] for ev in out["decision_evidence"]]
        self.assertIn("(no valid solution)", snippets)
        self.assertIn("无有效解答", snippets)
        self.assertIn("(security_violation)", snippets)

    def test_paraphrase_snippet_passes(self):
        """轻度 paraphrase 通过 fuzzy match"""
        qa = self._qa_with_answer("我用归纳法证明 n=k+1 的情况成立，先验证基础情况")
        data = self._data_with_evidence([
            {"turn_index": 0, "dimension": "math_logic", "observed_level": "HIGH",
             "rubric_clause": "x",
             "answer_snippet": "用归纳法证明 n=k+1 时成立",  # paraphrase
             "impact": "positive"},
            {"turn_index": 0, "dimension": "reasoning_rigor", "observed_level": "MEDIUM",
             "rubric_clause": "y", "answer_snippet": "(no valid solution)", "impact": "neutral"},
            {"turn_index": 0, "dimension": "communication", "observed_level": "MEDIUM",
             "rubric_clause": "z", "answer_snippet": "(no valid solution)", "impact": "neutral"},
        ])
        out = self.sa._validate_summary_result(data, 6.0, qa)
        self.assertEqual(len(out["decision_evidence"]), 3)
        # paraphrase quote 应保留
        first_ev = out["decision_evidence"][0]
        self.assertEqual(first_ev["answer_snippet"], "用归纳法证明 n=k+1 时成立")


# ============================================================
# 端到端：所有 P0 修复在一个 case 中协同工作
# ============================================================

class IntegrationP0Fixes(unittest.TestCase):

    def setUp(self):
        self.sa = _new_summary_agent()

    def test_combined_p0_fixes(self):
        """LLM 同时输出 4 类一致性问题 → 全部被纠正"""
        qa = [
            {
                "question": "q1",
                "answer": "我用归纳法证明",
                "score_details": {"score": 5, "agreement": 0.9,
                                  "confidence_level": "high", "fallback_used": False,
                                  "dimensions": []},
            },
            {
                "question": "q2",
                "answer": "考虑反例 n=4",
                "score_details": {"score": 6, "agreement": 0.9,
                                  "confidence_level": "high", "fallback_used": False,
                                  "dimensions": []},
            },
        ]
        # mean = 5.5 (boundary [4.5, 5.5])
        # LLM overall_score=9.0（明显偏高） → P0-2 覆盖到 5.5
        # decision_evidence 含越界 + 编造 quote
        data = {
            "final_grade": "A",       # 与覆盖后 score=5.5 不一致 → 应被改为 C
            "final_decision": "accept",
            "overall_score": 9.0,     # ← P0-2 触发覆盖
            "summary": "...",
            "decision_evidence": [
                {"turn_index": 99, "dimension": "math_logic",   # ← P0-3 越界
                 "observed_level": "HIGH", "rubric_clause": "x",
                 "answer_snippet": "归纳法", "impact": "positive"},
                {"turn_index": 0, "dimension": "math_logic",
                 "observed_level": "HIGH", "rubric_clause": "x",
                 "answer_snippet": "完全不存在的内容",         # ← P0-4 编造
                 "impact": "positive"},
                {"turn_index": 1, "dimension": "reasoning_rigor",
                 "observed_level": "MEDIUM", "rubric_clause": "y",
                 "answer_snippet": "反例", "impact": "neutral"},   # ← 合法
            ],
            "boundary_case": False,
            "decision_confidence": "high",
            "requires_human_review": False,
        }

        out = self.sa._validate_summary_result(data, 5.5, qa)

        # P0-2: overall_score 被覆盖到 5.5
        self.assertEqual(out["overall_score"], 5.5)
        # grade 跟随校正后的 score → C
        self.assertEqual(out["final_grade"], "C")
        # 5.5 ∈ boundary[4.5,5.5] → boundary_case=True + 强制 review
        self.assertTrue(out["boundary_case"])
        self.assertTrue(out["requires_human_review"])
        # P0-3 + P0-4: 越界 + 编造 evidence 被过滤后 padding 补全
        self.assertGreaterEqual(len(out["decision_evidence"]), 3)
        for ev in out["decision_evidence"]:
            self.assertLess(ev["turn_index"], 2)  # 都在 [0, 2) 内
            self.assertNotEqual(ev["answer_snippet"], "完全不存在的内容")


if __name__ == "__main__":
    unittest.main()
