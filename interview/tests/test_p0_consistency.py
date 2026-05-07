"""
P0 内部一致性漏洞修复的回归测试（v4 单分制）

覆盖：
- P0-2: SummaryAgent.overall_score 与 qa_history mean 偏差 > 0.5 → 强制覆盖
- P0-3: decision_evidence.turn_index 越界 → 过滤 + 占位补全
- P0-4: decision_evidence.answer_snippet 不在 answer 中 → 过滤

P0-1 / P2-2（rubric_clause 强制覆盖）随 v4 单分制重构一并废弃，因为
ScoringAgent 不再按维度独立打分，rubric_clause 字段已从 schema 中移除。

运行：
  uv run python -m unittest interview.tests.test_p0_consistency -v
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from interview.agents.scoring_agent import ScoringAgent
from interview.agents.summary_agent import (
    SummaryAgent,
    _compute_actual_mean,
    _OVERALL_SCORE_TOLERANCE,
)


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
            "overall_analysis": "...",
            "decision_evidence": [],
            "boundary_case": False,
            "decision_confidence": "high",
            "requires_human_review": False,
        }

    def _qa(self, scores):
        """构造 v4 qa_history（每条 score 来自 scores list）"""
        return [
            {
                "question": "q",
                "answer": "the actual long candidate answer text for fuzzy match",
                "score_details": {
                    "score": s,
                    "evidence_quote": "abc",
                    "question_focus": "算法",
                    "agreement": 0.9,
                    "confidence_level": "high",
                    "fallback_used": False,
                },
            }
            for s in scores
        ]

    def test_compute_actual_mean(self):
        qa = self._qa([6, 7, 8, 9])
        self.assertAlmostEqual(_compute_actual_mean(qa), 7.5)

    def test_compute_actual_mean_excludes_zero(self):
        qa = self._qa([5, 0, 7])
        self.assertAlmostEqual(_compute_actual_mean(qa), 6.0)

    def test_compute_actual_mean_empty(self):
        self.assertIsNone(_compute_actual_mean([]))

    def test_overall_score_within_tolerance_kept(self):
        """LLM=7.0, mean=7.33，差 0.33 < 0.5 → 保留 LLM 值"""
        data = self._data(score=7.0)
        qa = self._qa([7, 7, 8])
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
        qa = self._qa([7, 8, 8])
        out = self.sa._validate_summary_result(data, 7.67, qa)
        self.assertAlmostEqual(out["overall_score"], 7.7, places=1)

    def test_grade_uses_corrected_score(self):
        """LLM=8.5（A），实际 mean=6.0（C） → 覆盖后 grade=C"""
        data = self._data(score=8.5)
        qa = self._qa([6, 6, 6])
        out = self.sa._validate_summary_result(data, 6.0, qa)
        self.assertEqual(out["overall_score"], 6.0)
        self.assertEqual(out["final_grade"], "C")
        self.assertEqual(out["final_decision"], "reject")

    def test_no_qa_history_falls_back_to_average_score(self):
        """qa_history 空 → fallback 到 input 的 average_score"""
        data = self._data(score=7.5)
        qa = []
        out = self.sa._validate_summary_result(data, 7.5, qa)
        self.assertEqual(out["overall_score"], 7.5)


# ============================================================
# P0-3: decision_evidence.turn_index 越界检查
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
            "overall_analysis": "...",
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
                "score_details": {
                    "score": 6, "evidence_quote": "abc",
                    "question_focus": "算法",
                    "agreement": 0.9, "confidence_level": "high",
                    "fallback_used": False,
                },
            }
            for i in range(n_turns)
        ]

    def _ev(self, turn_index, snippet="this is the"):
        return {
            "turn_index": turn_index,
            "question_focus": "算法",
            "answer_snippet": snippet,
            "rationale": "ab",
            "impact": "neutral",
        }

    def test_valid_turn_indices_kept(self):
        qa = self._qa(5)
        data = self._data_with_evidence([self._ev(0), self._ev(2), self._ev(4)])
        out = self.sa._validate_summary_result(data, 6.0, qa)
        self.assertEqual(len(out["decision_evidence"]), 3)
        self.assertEqual({ev["turn_index"] for ev in out["decision_evidence"]}, {0, 2, 4})

    def test_out_of_bound_turn_index_filtered(self):
        qa = self._qa(3)
        data = self._data_with_evidence([
            self._ev(0),
            self._ev(99),
            self._ev(-1),
        ])
        out = self.sa._validate_summary_result(data, 6.0, qa)
        self.assertGreaterEqual(len(out["decision_evidence"]), 3)
        for ev in out["decision_evidence"]:
            self.assertGreaterEqual(ev["turn_index"], 0)
            self.assertLess(ev["turn_index"], 3)

    def test_padding_when_all_evidence_filtered(self):
        qa = self._qa(5)
        data = self._data_with_evidence([self._ev(99), self._ev(100)])
        out = self.sa._validate_summary_result(data, 6.0, qa)
        self.assertEqual(len(out["decision_evidence"]), 3)
        for ev in out["decision_evidence"]:
            self.assertLess(ev["turn_index"], 5)


# ============================================================
# P0-4: answer_snippet fuzzy validation
# ============================================================

class P04_AnswerSnippetFuzzyValidation(unittest.TestCase):

    def setUp(self):
        self.sa = _new_summary_agent()

    def _data_with_evidence(self, evidence_list):
        return {
            "final_grade": "C",
            "final_decision": "reject",
            "overall_score": 6.0,
            "summary": "...",
            "overall_analysis": "...",
            "decision_evidence": evidence_list,
            "boundary_case": False,
            "decision_confidence": "medium",
            "requires_human_review": False,
        }

    def _qa_with_answer(self, answer):
        return [{
            "question": "q",
            "answer": answer,
            "score_details": {
                "score": 6, "evidence_quote": "abc",
                "question_focus": "算法",
                "agreement": 0.9, "confidence_level": "high",
                "fallback_used": False,
            },
        }]

    def test_valid_snippet_kept(self):
        qa = self._qa_with_answer("我用归纳法证明 n=k+1 时成立。先验证基础情况。")
        data = self._data_with_evidence([
            {"turn_index": 0, "question_focus": "算法",
             "answer_snippet": "归纳法证明", "rationale": "ab", "impact": "positive"},
            {"turn_index": 0, "question_focus": "推理",
             "answer_snippet": "我用归纳法证明 n=k+1 时成立", "rationale": "ab", "impact": "positive"},
            {"turn_index": 0, "question_focus": "表达",
             "answer_snippet": "先验证基础情况", "rationale": "ab", "impact": "neutral"},
        ])
        out = self.sa._validate_summary_result(data, 6.0, qa)
        self.assertEqual(len(out["decision_evidence"]), 3)

    def test_fabricated_snippet_filtered(self):
        qa = self._qa_with_answer("我用归纳法证明 n=k+1 时成立")
        data = self._data_with_evidence([
            {"turn_index": 0, "question_focus": "算法",
             "answer_snippet": "量子力学的态叠加原理",
             "rationale": "ab", "impact": "positive"},
        ])
        out = self.sa._validate_summary_result(data, 6.0, qa)
        # 这条被过滤后 → padding 补 3 条
        self.assertEqual(len(out["decision_evidence"]), 3)
        snippets = [ev["answer_snippet"] for ev in out["decision_evidence"]]
        self.assertNotIn("量子力学的态叠加原理", snippets)

    def test_special_marker_snippet_passes(self):
        """0 分契约 / fallback / 占位标记永远视为合法"""
        qa = self._qa_with_answer("answer")
        data = self._data_with_evidence([
            {"turn_index": 0, "question_focus": "算法",
             "answer_snippet": "(no valid solution)",
             "rationale": "ab", "impact": "negative"},
            {"turn_index": 0, "question_focus": "推理",
             "answer_snippet": "无有效解答",
             "rationale": "ab", "impact": "negative"},
            {"turn_index": 0, "question_focus": "表达",
             "answer_snippet": "(security_violation)",
             "rationale": "ab", "impact": "neutral"},
        ])
        out = self.sa._validate_summary_result(data, 6.0, qa)
        self.assertEqual(len(out["decision_evidence"]), 3)
        snippets = [ev["answer_snippet"] for ev in out["decision_evidence"]]
        self.assertIn("(no valid solution)", snippets)
        self.assertIn("无有效解答", snippets)
        self.assertIn("(security_violation)", snippets)

    def test_paraphrase_snippet_passes(self):
        qa = self._qa_with_answer("我用归纳法证明 n=k+1 的情况成立，先验证基础情况")
        data = self._data_with_evidence([
            {"turn_index": 0, "question_focus": "算法",
             "answer_snippet": "用归纳法证明 n=k+1 时成立",
             "rationale": "ab", "impact": "positive"},
            {"turn_index": 0, "question_focus": "推理",
             "answer_snippet": "(no valid solution)", "rationale": "ab", "impact": "neutral"},
            {"turn_index": 0, "question_focus": "表达",
             "answer_snippet": "(no valid solution)", "rationale": "ab", "impact": "neutral"},
        ])
        out = self.sa._validate_summary_result(data, 6.0, qa)
        self.assertEqual(len(out["decision_evidence"]), 3)
        first_ev = out["decision_evidence"][0]
        self.assertEqual(first_ev["answer_snippet"], "用归纳法证明 n=k+1 时成立")


# ============================================================
# 端到端：所有 P0 修复在一个 case 中协同工作
# ============================================================

class IntegrationP0Fixes(unittest.TestCase):

    def setUp(self):
        self.sa = _new_summary_agent()

    def test_combined_p0_fixes(self):
        """LLM 同时输出 3 类一致性问题 → 全部被纠正"""
        qa = [
            {
                "question": "q1",
                "answer": "我用归纳法证明",
                "score_details": {
                    "score": 5, "evidence_quote": "归纳法",
                    "question_focus": "算法",
                    "agreement": 0.9, "confidence_level": "high",
                    "fallback_used": False,
                },
            },
            {
                "question": "q2",
                "answer": "考虑反例 n=4",
                "score_details": {
                    "score": 6, "evidence_quote": "反例",
                    "question_focus": "推理",
                    "agreement": 0.9, "confidence_level": "high",
                    "fallback_used": False,
                },
            },
        ]
        # mean = 5.5 (boundary)
        # LLM overall_score=9.0 → P0-2 覆盖到 5.5
        data = {
            "final_grade": "A",      # 与 score=5.5 不符 → 改为 C
            "final_decision": "accept",
            "overall_score": 9.0,    # ← P0-2
            "summary": "...",
            "overall_analysis": "...",
            "decision_evidence": [
                {"turn_index": 99, "question_focus": "算法",        # ← P0-3 越界
                 "answer_snippet": "归纳法", "rationale": "ab", "impact": "positive"},
                {"turn_index": 0, "question_focus": "算法",
                 "answer_snippet": "完全不存在的内容",                # ← P0-4 编造
                 "rationale": "ab", "impact": "positive"},
                {"turn_index": 1, "question_focus": "推理",
                 "answer_snippet": "反例",
                 "rationale": "ab", "impact": "neutral"},          # ← 合法
            ],
            "boundary_case": False,
            "decision_confidence": "high",
            "requires_human_review": False,
        }

        out = self.sa._validate_summary_result(data, 5.5, qa)

        # P0-2: overall_score 被覆盖到 5.5
        self.assertEqual(out["overall_score"], 5.5)
        self.assertEqual(out["final_grade"], "C")
        # 5.5 ∈ boundary[4.5,5.5] → boundary_case=True + 强制 review
        self.assertTrue(out["boundary_case"])
        self.assertTrue(out["requires_human_review"])
        # P0-3 + P0-4: 越界 + 编造 evidence 被过滤后 padding 补全
        self.assertGreaterEqual(len(out["decision_evidence"]), 3)
        for ev in out["decision_evidence"]:
            self.assertLess(ev["turn_index"], 2)
            self.assertNotEqual(ev["answer_snippet"], "完全不存在的内容")


if __name__ == "__main__":
    unittest.main()
