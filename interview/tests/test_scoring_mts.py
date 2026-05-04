"""
W1 单测：MTS 多维度评分 + RULERS evidence-anchored + CISC ensemble

覆盖：
1. schemas.py 校验：DimensionScore 上限、ScoringOutput 一致性、SummaryOutput 必填 evidence
2. ScoringAgent 关键方法：fuzzy match、ensemble 聚合、agreement 计算、fallback
3. mock LLM 端到端：5 维度并行调用、quote 校验、ensemble disagreement → confidence

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
    DIMENSION_MAX_SCORE,
    DimensionScore,
    ScoringOutput,
    DecisionEvidence,
    SummaryOutput,
)
from interview.agents.scoring_agent import (
    ScoringAgent,
    _DIM_KEYS,
    _CONFIDENCE_WEIGHTS,
)


def _mk_dim(dim, level="MEDIUM", score=1, conf="medium", quote="abc", clause="x"):
    """便捷构造 DimensionScore"""
    return DimensionScore(
        dimension=dim,
        level=level,
        score=score,
        evidence_quote=quote,
        rubric_clause=clause,
        confidence=conf,
    )


def _full_5(scores=None):
    """快速构造合法的 5 维度列表"""
    scores = scores or {"math_logic": 2, "reasoning_rigor": 1, "communication": 1, "collaboration": 0, "growth_potential": 1}
    return [_mk_dim(k, score=v) for k, v in scores.items()]


# ============================================================
# Schema 校验
# ============================================================

class DimensionScoreSchema(unittest.TestCase):

    def test_score_within_bound(self):
        d = _mk_dim("math_logic", score=4)
        self.assertEqual(d.score, 4)

    def test_math_logic_score_above_4_rejected(self):
        with self.assertRaises(ValidationError):
            _mk_dim("math_logic", score=5)

    def test_collaboration_score_above_1_rejected(self):
        with self.assertRaises(ValidationError):
            _mk_dim("collaboration", score=2)

    def test_growth_potential_score_above_1_rejected(self):
        with self.assertRaises(ValidationError):
            _mk_dim("growth_potential", score=3)

    def test_evidence_quote_min_length(self):
        with self.assertRaises(ValidationError):
            DimensionScore(
                dimension="math_logic", level="HIGH", score=4,
                evidence_quote="a", rubric_clause="x",
            )


class ScoringOutputConsistency(unittest.TestCase):

    def test_score_equals_dim_sum_accepted(self):
        dims = _full_5()  # 总和 = 2+1+1+0+1 = 5
        so = ScoringOutput(score=5, dimensions=dims)
        self.assertEqual(so.score, 5)
        self.assertEqual(so.agreement, 1.0)

    def test_inconsistent_score_rejected(self):
        dims = _full_5()
        with self.assertRaises(ValidationError):
            ScoringOutput(score=8, dimensions=dims)

    def test_missing_dimension_rejected(self):
        dims = _full_5()[:4]
        with self.assertRaises(ValidationError):
            ScoringOutput(score=4, dimensions=dims)

    def test_duplicate_dimension_rejected(self):
        dims = [_full_5()[0]] * 5
        with self.assertRaises(ValidationError):
            ScoringOutput(score=10, dimensions=dims)

    def test_score_above_10_rejected(self):
        # math_logic=4, reasoning_rigor=2, communication=2, collaboration=1, growth_potential=1 → max=10
        # 这里只能造出 sum=10，不能 sum>10。但可以测 score=11 不一致
        dims = _full_5({"math_logic": 4, "reasoning_rigor": 2, "communication": 2, "collaboration": 1, "growth_potential": 1})
        with self.assertRaises(ValidationError):
            ScoringOutput(score=11, dimensions=dims)


class SummaryOutputSchema(unittest.TestCase):

    def _ev(self, n=3):
        return [
            DecisionEvidence(
                turn_index=i, dimension="math_logic", observed_level="MEDIUM",
                rubric_clause="x", answer_snippet="ab",
            )
            for i in range(n)
        ]

    def test_three_evidence_accepted(self):
        so = SummaryOutput(overall_score=7.0, decision_evidence=self._ev(3))
        self.assertEqual(so.final_grade, "C")  # default

    def test_empty_evidence_rejected(self):
        with self.assertRaises(ValidationError):
            SummaryOutput(overall_score=7.0, decision_evidence=[])

    def test_two_evidence_rejected(self):
        with self.assertRaises(ValidationError):
            SummaryOutput(overall_score=7.0, decision_evidence=self._ev(2))


# ============================================================
# ScoringAgent — quote validation
# ============================================================

class QuoteValidation(unittest.TestCase):

    def test_short_substring_passes(self):
        self.assertTrue(ScoringAgent._validate_quote_in_answer("反例", "我可以举一个反例：考虑 n=4 时..."))

    def test_short_non_substring_fails(self):
        self.assertFalse(ScoringAgent._validate_quote_in_answer("归纳", "我直接给出反例"))

    def test_long_verbatim_passes(self):
        self.assertTrue(ScoringAgent._validate_quote_in_answer(
            "我用归纳法证明 n=k+1 的情况",
            "首先，我用归纳法证明 n=k+1 的情况成立...",
        ))

    def test_long_paraphrase_passes(self):
        self.assertTrue(ScoringAgent._validate_quote_in_answer(
            "用归纳法证明 n=k+1 时成立",
            "我用归纳法证明 n=k+1 的情况成立",
        ))

    def test_no_solution_marker_always_passes(self):
        self.assertTrue(ScoringAgent._validate_quote_in_answer("(no valid solution)", ""))
        self.assertTrue(ScoringAgent._validate_quote_in_answer("无有效解答", "我不会"))

    def test_unrelated_long_quote_fails(self):
        self.assertFalse(ScoringAgent._validate_quote_in_answer(
            "量子力学的态叠加原理",
            "我用归纳法证明 n=k+1",
        ))

    def test_empty_quote_fails(self):
        self.assertFalse(ScoringAgent._validate_quote_in_answer("", "答案文本"))


# ============================================================
# ScoringAgent — ensemble 聚合 / fallback
# ============================================================

class FakeModel:
    """伪装 ChatOpenAI 接口，仅提供 model_name + with_structured_output"""
    def __init__(self, name="fake-model"):
        self.model_name = name

    def with_structured_output(self, schema, include_raw=False):
        m = MagicMock()
        m.ainvoke = AsyncMock()
        return m


def _new_agent(n_models=2):
    return ScoringAgent([FakeModel(f"m{i}") for i in range(n_models)])


class EnsembleAggregation(unittest.TestCase):

    def setUp(self):
        self.agent = _new_agent(n_models=2)

    def test_unanimous_high_confidence(self):
        cands = [
            _mk_dim("math_logic", level="HIGH", score=4, conf="high"),
            _mk_dim("math_logic", level="HIGH", score=4, conf="high"),
        ]
        agg = self.agent._aggregate_ensemble("math_logic", cands)
        self.assertEqual(agg.level, "HIGH")
        self.assertEqual(agg.score, 4)
        self.assertEqual(agg.confidence, "high")
        self.assertEqual(agg.model_name, "ensemble(2)")

    def test_disagreement_drops_confidence(self):
        cands = [
            _mk_dim("math_logic", level="HIGH", score=4, conf="high"),
            _mk_dim("math_logic", level="LOW", score=1, conf="low"),
        ]
        agg = self.agent._aggregate_ensemble("math_logic", cands)
        # HIGH 投票权重 1.0, LOW 投票权重 0.3 → HIGH 赢
        self.assertEqual(agg.level, "HIGH")
        # weighted score: (1.0*4 + 0.3*1) / 1.3 = 4.3/1.3 ≈ 3.31 → round = 3
        self.assertEqual(agg.score, 3)
        # 50% same level → "medium"
        self.assertEqual(agg.confidence, "medium")

    def test_score_clipped_to_dim_cap(self):
        # 即使 weighted average 算出超过 cap，也应被 clip
        cands = [
            _mk_dim("collaboration", level="HIGH", score=1, conf="high"),
            _mk_dim("collaboration", level="HIGH", score=1, conf="high"),
        ]
        agg = self.agent._aggregate_ensemble("collaboration", cands)
        self.assertLessEqual(agg.score, 1)

    def test_picks_best_evidence_quote(self):
        cands = [
            _mk_dim("math_logic", level="HIGH", score=4, conf="low", quote="weak quote"),
            _mk_dim("math_logic", level="HIGH", score=4, conf="high", quote="strong quote"),
        ]
        agg = self.agent._aggregate_ensemble("math_logic", cands)
        # 选 confidence 最高的
        self.assertEqual(agg.evidence_quote, "strong quote")


class FallbackBehavior(unittest.TestCase):

    def setUp(self):
        self.agent = _new_agent(n_models=2)

    def test_fallback_dim_math_logic(self):
        d = self.agent._fallback_dim("math_logic")
        self.assertEqual(d.dimension, "math_logic")
        self.assertEqual(d.score, 2)  # cap=4 // 2
        self.assertEqual(d.confidence, "low")
        self.assertEqual(d.model_name, "fallback")

    def test_fallback_dim_collaboration(self):
        d = self.agent._fallback_dim("collaboration")
        self.assertEqual(d.score, 0)  # cap=1 时取 0

    def test_full_fallback_scoring(self):
        out = self.agent._fallback_scoring()
        self.assertEqual(len(out["dimensions"]), 5)
        self.assertTrue(out["fallback_used"])
        self.assertTrue(out["requires_human_review"])
        self.assertEqual(out["confidence_level"], "low")
        # 所有维度 conf=low
        self.assertTrue(all(d["confidence"] == "low" for d in out["dimensions"]))


class AgreementComputation(unittest.TestCase):

    def setUp(self):
        self.agent = _new_agent(n_models=2)

    def test_unanimous_agreement_1(self):
        same = [_mk_dim("math_logic", level="HIGH", score=4)] * 2
        grouped = {k: [] for k in _DIM_KEYS}
        grouped["math_logic"] = same
        ag = self.agent._compute_agreement(grouped)
        # 1 维度全同意 + 4 维度空（视为 1.0） → 1.0
        self.assertAlmostEqual(ag, 1.0)

    def test_split_agreement(self):
        cands = [
            _mk_dim("math_logic", level="HIGH", score=4),
            _mk_dim("math_logic", level="LOW", score=1),
        ]
        grouped = {k: [] for k in _DIM_KEYS}
        grouped["math_logic"] = cands
        ag = self.agent._compute_agreement(grouped)
        # math_logic: 1/2=0.5; 其余 4 维度空 → 1.0 → (0.5+4*1.0)/5 = 0.9
        self.assertAlmostEqual(ag, 0.9)

    def test_single_model_always_1(self):
        grouped = {k: [_mk_dim(k)] for k in _DIM_KEYS}
        ag = self.agent._compute_agreement(grouped)
        self.assertAlmostEqual(ag, 1.0)


class ConfidenceDerivation(unittest.TestCase):

    def setUp(self):
        self.agent = _new_agent()

    def test_high_when_all_high_confidence(self):
        dims = [_mk_dim(k, conf="high") for k in _DIM_KEYS]
        c = self.agent._derive_confidence(0.9, dims, all_fallback=False)
        self.assertEqual(c, "high")

    def test_low_when_fallback(self):
        dims = [_mk_dim(k, conf="medium") for k in _DIM_KEYS]
        c = self.agent._derive_confidence(0.9, dims, all_fallback=True)
        self.assertEqual(c, "low")

    def test_low_when_three_low_dims(self):
        dims = [_mk_dim("math_logic", conf="low"), _mk_dim("reasoning_rigor", conf="low"),
                _mk_dim("communication", conf="low"), _mk_dim("collaboration", conf="medium"),
                _mk_dim("growth_potential", conf="medium")]
        c = self.agent._derive_confidence(0.9, dims, all_fallback=False)
        self.assertEqual(c, "low")

    def test_medium_when_low_agreement(self):
        dims = [_mk_dim(k, conf="high") for k in _DIM_KEYS]
        c = self.agent._derive_confidence(0.6, dims, all_fallback=False)
        self.assertEqual(c, "medium")


# ============================================================
# 端到端 mock：5 维度并行调用
# ============================================================

class MockedEndToEnd(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # 准备一个 agent，结构化模型 ainvoke 返回固定 DimensionScore
        self.agent = _new_agent(n_models=2)

        # 构造 10 个返回值（5 维度 × 2 模型），全 HIGH/4
        async def fake_ainvoke(messages):
            # 解析 human message 拿到 dimension_key
            # 简化：从 prompt 中找 "Dimension to score:"
            for m in messages:
                content = getattr(m, "content", "")
                if "Dimension to score:" in content:
                    for k in _DIM_KEYS:
                        if k in content:
                            cap = DIMENSION_MAX_SCORE[k]
                            return _mk_dim(k, level="HIGH", score=cap,
                                           conf="high", quote="(no valid solution)")
            # 默认
            return _mk_dim("math_logic", level="HIGH", score=4,
                           conf="high", quote="(no valid solution)")

        for sm in self.agent._structured_models:
            sm.ainvoke = AsyncMock(side_effect=fake_ainvoke)

    async def test_5_dims_parallel(self):
        result = await self.agent.aprocess({
            "question": "测试问题",
            "answer": "测试答案",
            "question_type": "math_logic",
            "difficulty": "medium",
        })
        self.assertEqual(result["score"], 4 + 2 + 2 + 1 + 1)  # 10
        self.assertEqual(len(result["dimensions"]), 5)
        self.assertFalse(result["fallback_used"])
        self.assertEqual(result["agreement"], 1.0)
        self.assertEqual(result["confidence_level"], "high")
        self.assertFalse(result["requires_human_review"])

    async def test_one_model_exception_still_succeeds(self):
        # 模型 0 抛异常，模型 1 正常
        async def model0_fail(_messages):
            raise RuntimeError("simulated LLM failure")

        async def model1_ok(messages):
            for m in messages:
                content = getattr(m, "content", "")
                if "Dimension to score:" in content:
                    for k in _DIM_KEYS:
                        if k in content:
                            cap = DIMENSION_MAX_SCORE[k]
                            return _mk_dim(k, level="HIGH", score=cap,
                                           conf="high", quote="(no valid solution)")
            return _mk_dim("math_logic", level="HIGH", score=4,
                           conf="high", quote="(no valid solution)")

        self.agent._structured_models[0].ainvoke = AsyncMock(side_effect=model0_fail)
        self.agent._structured_models[1].ainvoke = AsyncMock(side_effect=model1_ok)

        result = await self.agent.aprocess({
            "question": "Q", "answer": "A", "question_type": "math_logic", "difficulty": "easy",
        })
        # 仍然成功（5 维度都从模型 1 拿到）
        self.assertEqual(len(result["dimensions"]), 5)
        self.assertFalse(result["fallback_used"])

    async def test_all_models_fail_triggers_fallback(self):
        async def fail(_messages):
            raise RuntimeError("all models down")

        for sm in self.agent._structured_models:
            sm.ainvoke = AsyncMock(side_effect=fail)

        result = await self.agent.aprocess({
            "question": "Q", "answer": "A", "question_type": "math_logic", "difficulty": "easy",
        })
        self.assertTrue(result["fallback_used"])
        self.assertTrue(result["requires_human_review"])
        self.assertEqual(result["confidence_level"], "low")
        self.assertEqual(result["agreement"], 0.0)


if __name__ == "__main__":
    unittest.main()
