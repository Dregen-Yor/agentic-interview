"""
v4 单测：单题整体评分 + RULERS evidence-anchored + CISC ensemble

覆盖：
1. schemas.py 校验：ScoringOutput 边界、SingleScoreCandidate 必填字段、DecisionEvidence 必填字段
2. ScoringAgent 关键方法：quote fuzzy match 降 confidence、CISC 加权聚合、agreement 计算、fallback
3. mock LLM 端到端：单模型/多模型并行、disagreement → requires_human_review

运行：
  uv run python -m unittest interview.tests.test_scoring_mts -v
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock
from typing import List

from pydantic import ValidationError

from interview.agents.schemas import (
    DecisionEvidence,
    ScoringOutput,
    SingleScoreCandidate,
    SummaryOutput,
)
from interview.agents.scoring_agent import (
    ScoringAgent,
    _AGREEMENT_THRESHOLD,
    _CONFIDENCE_WEIGHTS,
)


def _mk_cand(score=8, conf="medium", quote="正确的解法是", focus="算法实现", reasoning="", model_name=None):
    """便捷构造 SingleScoreCandidate"""
    return SingleScoreCandidate(
        score=score,
        evidence_quote=quote,
        question_focus=focus,
        confidence=conf,
        reasoning=reasoning,
        model_name=model_name,
    )


# ============================================================
# Schema 校验
# ============================================================

class SingleScoreCandidateSchema(unittest.TestCase):

    def test_valid_score(self):
        c = _mk_cand(score=8)
        self.assertEqual(c.score, 8)

    def test_score_below_zero_rejected(self):
        with self.assertRaises(ValidationError):
            _mk_cand(score=-1)

    def test_score_above_ten_rejected(self):
        with self.assertRaises(ValidationError):
            _mk_cand(score=11)

    def test_evidence_quote_min_length(self):
        with self.assertRaises(ValidationError):
            SingleScoreCandidate(
                score=8, evidence_quote="a", question_focus="算法实现",
                confidence="medium",
            )

    def test_question_focus_min_length(self):
        with self.assertRaises(ValidationError):
            SingleScoreCandidate(
                score=8, evidence_quote="abc", question_focus="a",
                confidence="medium",
            )

    def test_confidence_literal(self):
        with self.assertRaises(ValidationError):
            SingleScoreCandidate(
                score=8, evidence_quote="abc", question_focus="算法实现",
                confidence="invalid_value",
            )


class ScoringOutputSchema(unittest.TestCase):

    def test_valid_output(self):
        out = ScoringOutput(
            score=8,
            evidence_quote="正确的解法",
            question_focus="算法实现",
            agreement=1.0,
            confidence_level="high",
            requires_human_review=False,
            fallback_used=False,
        )
        self.assertEqual(out.score, 8)
        self.assertEqual(out.confidence_level, "high")

    def test_score_above_ten_rejected(self):
        with self.assertRaises(ValidationError):
            ScoringOutput(
                score=11, evidence_quote="abc", question_focus="算法",
                agreement=1.0, confidence_level="high",
            )

    def test_score_below_zero_rejected(self):
        with self.assertRaises(ValidationError):
            ScoringOutput(
                score=-1, evidence_quote="abc", question_focus="算法",
                agreement=1.0, confidence_level="high",
            )

    def test_agreement_range(self):
        with self.assertRaises(ValidationError):
            ScoringOutput(
                score=5, evidence_quote="abc", question_focus="算法",
                agreement=1.5, confidence_level="medium",
            )

    def test_evidence_quote_required(self):
        with self.assertRaises(ValidationError):
            ScoringOutput(
                score=5, question_focus="算法",
                agreement=1.0, confidence_level="medium",
            )


# ============================================================
# DecisionEvidence + SummaryOutput
# ============================================================

class DecisionEvidenceSchema(unittest.TestCase):

    def test_valid(self):
        ev = DecisionEvidence(
            turn_index=0,
            question_focus="算法实现",
            answer_snippet="使用动态规划",
            rationale="候选人正确识别 DP 子问题",
            impact="positive",
        )
        self.assertEqual(ev.impact, "positive")

    def test_negative_turn_rejected(self):
        with self.assertRaises(ValidationError):
            DecisionEvidence(
                turn_index=-1, question_focus="算法",
                answer_snippet="ab", rationale="ab", impact="neutral",
            )

    def test_missing_rationale_rejected(self):
        with self.assertRaises(ValidationError):
            DecisionEvidence(
                turn_index=0, question_focus="算法",
                answer_snippet="ab", impact="neutral",
            )

    def test_no_dimension_field(self):
        # v4：不再有 dimension / observed_level / rubric_clause 字段
        ev = DecisionEvidence(
            turn_index=0, question_focus="算法", answer_snippet="ab",
            rationale="ab", impact="positive",
        )
        # extra="ignore"，dimension 字段如果传入会被静默丢弃
        ev2 = DecisionEvidence(
            turn_index=0, question_focus="算法", answer_snippet="ab",
            rationale="ab", impact="positive",
            dimension="math_logic",  # 旧字段，应被忽略
        )
        self.assertFalse(hasattr(ev, "dimension"))
        self.assertFalse(hasattr(ev2, "dimension"))


class SummaryOutputSchema(unittest.TestCase):

    def _evidences(self, n=3):
        return [
            DecisionEvidence(
                turn_index=i,
                question_focus="focus",
                answer_snippet=f"snippet {i}",
                rationale=f"rationale {i}",
                impact="neutral",
            )
            for i in range(n)
        ]

    def test_valid(self):
        out = SummaryOutput(
            final_grade="B", final_decision="conditional",
            overall_score=7.5,
            decision_evidence=self._evidences(3),
        )
        self.assertEqual(out.final_grade, "B")

    def test_evidence_min_length_3(self):
        with self.assertRaises(ValidationError):
            SummaryOutput(
                overall_score=5.0,
                decision_evidence=self._evidences(2),
            )

    def test_overall_analysis_default(self):
        out = SummaryOutput(
            overall_score=7.0,
            decision_evidence=self._evidences(3),
        )
        # overall_analysis 默认空字符串，不报错
        self.assertEqual(out.overall_analysis, "")


# ============================================================
# ScoringAgent 关键私有方法
# ============================================================

class ScoringAgentAggregation(unittest.TestCase):
    """测试 _aggregate_scores / _compute_score_agreement / _derive_confidence"""

    def setUp(self):
        # 用一个 mock model 构造 ScoringAgent
        self.fake_model = MagicMock()
        self.fake_model.with_structured_output = MagicMock(return_value=MagicMock())
        self.fake_model.model_name = "fake_model"
        self.agent = ScoringAgent([self.fake_model])

    def test_agreement_single_model_is_one(self):
        cands = [_mk_cand(score=7)]
        self.assertEqual(self.agent._compute_score_agreement(cands), 1.0)

    def test_agreement_zero_diff_is_one(self):
        cands = [_mk_cand(score=8), _mk_cand(score=8)]
        self.assertEqual(self.agent._compute_score_agreement(cands), 1.0)

    def test_agreement_diff_5_is_half(self):
        cands = [_mk_cand(score=2), _mk_cand(score=7)]
        self.assertEqual(self.agent._compute_score_agreement(cands), 0.5)

    def test_agreement_diff_10_is_zero(self):
        cands = [_mk_cand(score=0), _mk_cand(score=10)]
        self.assertEqual(self.agent._compute_score_agreement(cands), 0.0)

    def test_aggregate_weighted_average(self):
        # high (1.0) * 8 + low (0.3) * 2 = 8.6 → /1.3 ≈ 6.6 → round 7
        cands = [_mk_cand(score=8, conf="high"), _mk_cand(score=2, conf="low")]
        agg = self.agent._aggregate_scores(cands, "abc")
        self.assertEqual(agg["score"], 7)

    def test_aggregate_picks_high_confidence_evidence(self):
        cands = [
            _mk_cand(score=5, conf="low", quote="弱证据"),
            _mk_cand(score=8, conf="high", quote="强证据"),
        ]
        # answer 同时含两个 quote
        answer = "强证据 是正确的，弱证据 也包含"
        agg = self.agent._aggregate_scores(cands, answer)
        self.assertEqual(agg["evidence_quote"], "强证据")

    def test_aggregate_clamps_to_0_10(self):
        # 即使 LLM 返回越界（虽然 schema 已挡），二次保护仍生效
        cands = [_mk_cand(score=10, conf="high"), _mk_cand(score=10, conf="high")]
        agg = self.agent._aggregate_scores(cands, "abc")
        self.assertLessEqual(agg["score"], 10)

    def test_derive_confidence_high_when_agreement_strong(self):
        cands = [_mk_cand(score=8, conf="high"), _mk_cand(score=8, conf="high")]
        # agreement=1.0, low_count=0 → high
        conf = self.agent._derive_confidence(1.0, cands, all_fallback=False)
        self.assertEqual(conf, "high")

    def test_derive_confidence_low_when_all_low(self):
        cands = [_mk_cand(score=5, conf="low"), _mk_cand(score=5, conf="low")]
        conf = self.agent._derive_confidence(1.0, cands, all_fallback=False)
        # agreement=1.0 但全 low → low（n=2, max(1,n//2)=1, low_count=2 > 1 → low）
        self.assertEqual(conf, "low")

    def test_derive_confidence_low_when_agreement_low(self):
        cands = [_mk_cand(score=2, conf="high"), _mk_cand(score=9, conf="high")]
        # agreement=0.3 < 0.7 → low
        conf = self.agent._derive_confidence(0.3, cands, all_fallback=False)
        self.assertEqual(conf, "low")


# ============================================================
# Fallback
# ============================================================

class ScoringAgentFallback(unittest.TestCase):

    def setUp(self):
        self.fake_model = MagicMock()
        self.fake_model.with_structured_output = MagicMock(return_value=MagicMock())
        self.fake_model.model_name = "fake_model"
        self.agent = ScoringAgent([self.fake_model])

    def test_fallback_score_is_5(self):
        out = self.agent._fallback_scoring()
        self.assertEqual(out["score"], 5)
        self.assertTrue(out["fallback_used"])
        self.assertTrue(out["requires_human_review"])
        self.assertEqual(out["confidence_level"], "low")

    def test_fallback_evidence_quote_marker(self):
        out = self.agent._fallback_scoring()
        self.assertIn("fallback", out["evidence_quote"].lower())


# ============================================================
# Quote fuzzy match 降 confidence
# ============================================================

class QuoteFuzzyMatch(unittest.TestCase):
    """quote 不在 answer 中应当降 confidence 而非 reject"""

    def setUp(self):
        self.fake_model = MagicMock()
        self.fake_model.with_structured_output = MagicMock(return_value=MagicMock())
        self.fake_model.model_name = "fake_model"
        self.agent = ScoringAgent([self.fake_model])

    def test_aprocess_demotes_confidence_when_quote_missing(self):
        async def run():
            # mock _structured_models[0].ainvoke 返回的 candidate 含 fabricated quote
            candidate = SingleScoreCandidate(
                score=8,
                evidence_quote="完全不在 answer 中的虚构片段 abcdefxyz123",
                question_focus="算法",
                confidence="high",
                reasoning="x",
            )
            self.agent._structured_models[0].ainvoke = AsyncMock(return_value=candidate)

            result = await self.agent.aprocess({
                "question": "请实现快速排序",
                "answer": "我使用了递归方法",
                "question_type": "math_logic",
            })
            return result

        result = asyncio.run(run())
        # quote 被 fuzzy 降级 → 单候选 confidence 变 low → 整体 confidence_level = low
        self.assertEqual(result["confidence_level"], "low")
        self.assertTrue(result["requires_human_review"])


# ============================================================
# 端到端 mock：双模型 ensemble disagreement
# ============================================================

class EndToEndDisagreement(unittest.TestCase):

    def test_two_model_disagreement_triggers_review(self):
        fake_model_a = MagicMock()
        fake_model_a.with_structured_output = MagicMock(return_value=MagicMock())
        fake_model_a.model_name = "model_a"
        fake_model_b = MagicMock()
        fake_model_b.with_structured_output = MagicMock(return_value=MagicMock())
        fake_model_b.model_name = "model_b"
        agent = ScoringAgent([fake_model_a, fake_model_b])

        cand_a = SingleScoreCandidate(
            score=2, evidence_quote="错的", question_focus="算法",
            confidence="high", reasoning="低分",
        )
        cand_b = SingleScoreCandidate(
            score=9, evidence_quote="对的", question_focus="算法",
            confidence="high", reasoning="高分",
        )
        agent._structured_models[0].ainvoke = AsyncMock(return_value=cand_a)
        agent._structured_models[1].ainvoke = AsyncMock(return_value=cand_b)

        async def run():
            return await agent.aprocess({
                "question": "Q", "answer": "答案中包含 错的 和 对的 两个标记",
            })

        result = asyncio.run(run())
        # diff=7, agreement = 0.3 < 0.7 → requires_human_review=True
        self.assertLess(result["agreement"], _AGREEMENT_THRESHOLD)
        self.assertTrue(result["requires_human_review"])


if __name__ == "__main__":
    unittest.main()
