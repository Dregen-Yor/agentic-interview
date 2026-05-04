"""
W2 集成测试：多模型 ensemble + RAG anchors

覆盖：
1. RAG anchors 注入：memory_retriever 被调用，anchors 文本进入 prompt
2. RAG 失败时不阻塞评分（soft fail）
3. exclude_session_id 避免 self-leak
4. ensemble 中不同模型给出不同 confidence → CISC 加权
5. coordinator 接入 scoring_models 列表的端到端

运行：
  uv run python -m unittest interview.tests.test_scoring_ensemble -v
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from interview.agents.scoring_agent import ScoringAgent, _DIM_KEYS
from interview.agents.schemas import DIMENSION_MAX_SCORE, DimensionScore


class FakeModel:
    def __init__(self, name="fake"):
        self.model_name = name

    def with_structured_output(self, schema, include_raw=False):
        m = MagicMock()
        m.ainvoke = AsyncMock()
        return m


def _mk_dim(dim, score=2, conf="high", quote="(no valid solution)"):
    return DimensionScore(
        dimension=dim, level="MEDIUM", score=score,
        evidence_quote=quote, rubric_clause="x", confidence=conf,
    )


def _make_dim_scorer(target_score=2, target_conf="high"):
    """生成根据 prompt 中 dimension key 返回对应 DimensionScore 的 fake LLM"""
    async def fake(messages):
        for m in messages:
            content = getattr(m, "content", "")
            if "Dimension to score:" in content:
                # 找第一个出现的维度 key
                for k in _DIM_KEYS:
                    if f"Dimension to score: {k}" in content:
                        cap = DIMENSION_MAX_SCORE[k]
                        return _mk_dim(k, score=min(target_score, cap), conf=target_conf)
        return _mk_dim("math_logic", score=target_score, conf=target_conf)
    return fake


# ============================================================
# RAG anchors 注入
# ============================================================

class RagAnchorsInjection(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_retriever = MagicMock()
        # 模拟 retrieve_similar_cases 返回 2 条案例
        self.mock_retriever.retrieve_similar_cases = MagicMock(return_value=[
            {
                "action": {"question_text": "历史题", "answer_text": "历史答"},
                "reward": {"score": 7, "reasoning": "过往评分"},
            },
            {
                "action": {"question_text": "另一题", "answer_text": "另一答"},
                "reward": {"score": 5, "reasoning": "中等"},
            },
        ])
        self.mock_retriever.format_cases_for_scoring = MagicMock(
            return_value="=== 评分参考案例 ===\n案例1: 得分 7\n案例2: 得分 5"
        )
        self.agent = ScoringAgent(
            [FakeModel("doubao"), FakeModel("gemini")],
            memory_retriever=self.mock_retriever,
        )
        for sm in self.agent._structured_models:
            sm.ainvoke = AsyncMock(side_effect=_make_dim_scorer())

    async def test_retrieve_called_with_correct_args(self):
        await self.agent.aprocess({
            "question": "测试问题",
            "answer": "测试答案",
            "session_id": "session_xyz",
        })
        # retrieve_similar_cases 应被调用，且 exclude_session_id="session_xyz"
        self.mock_retriever.retrieve_similar_cases.assert_called_once()
        args, kwargs = self.mock_retriever.retrieve_similar_cases.call_args
        # 位置参数：query, top_k=2, exclude_session_id, filters, min_importance
        self.assertEqual(args[1], 2)  # top_k=2 (论文锚点)
        self.assertEqual(args[2], "session_xyz")  # exclude self-leak

    async def test_anchors_passed_to_prompt(self):
        await self.agent.aprocess({
            "question": "Q",
            "answer": "A",
            "session_id": "s1",
        })
        # 检查每个 structured model 的 ainvoke 都收到了带 anchors 的 prompt
        for sm in self.agent._structured_models:
            calls = sm.ainvoke.call_args_list
            self.assertTrue(len(calls) > 0)
            for call in calls[:1]:  # 只看第一个 call
                messages = call.args[0]
                human_text = messages[1].content
                self.assertIn("评分参考案例", human_text)

    async def test_retrieval_failure_does_not_block_scoring(self):
        # mock retrieval 抛异常
        self.mock_retriever.retrieve_similar_cases = MagicMock(
            side_effect=RuntimeError("MongoDB down")
        )
        result = await self.agent.aprocess({
            "question": "Q",
            "answer": "A",
            "session_id": "s1",
        })
        # 评分仍应成功（5 维度齐全）
        self.assertEqual(len(result["dimensions"]), 5)
        self.assertFalse(result["fallback_used"])

    async def test_no_retriever_skips_anchors(self):
        agent_no_rag = ScoringAgent([FakeModel("m1")], memory_retriever=None)
        for sm in agent_no_rag._structured_models:
            sm.ainvoke = AsyncMock(side_effect=_make_dim_scorer())

        result = await agent_no_rag.aprocess({
            "question": "Q",
            "answer": "A",
        })
        # 应正常评分，prompt 中 similar_cases 部分会是 "（无历史参考案例）"
        self.assertEqual(len(result["dimensions"]), 5)


# ============================================================
# CISC 加权聚合：不同 confidence 的多模型分歧
# ============================================================

class CISCWeightedEnsemble(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.agent = ScoringAgent(
            [FakeModel("model_a"), FakeModel("model_b")],
            memory_retriever=None,
        )

    async def test_high_confidence_dominates(self):
        # model_a 全给 score=4 (high)，model_b 全给 score=1 (low)
        # CISC 加权：(1.0*4 + 0.3*1) / 1.3 = 4.3/1.3 ≈ 3.31 → round = 3
        self.agent._structured_models[0].ainvoke = AsyncMock(
            side_effect=_make_dim_scorer(target_score=4, target_conf="high")
        )
        self.agent._structured_models[1].ainvoke = AsyncMock(
            side_effect=_make_dim_scorer(target_score=1, target_conf="low")
        )

        result = await self.agent.aprocess({
            "question": "Q", "answer": "A",
        })
        # math_logic（cap=4）：(1.0*4 + 0.3*1) / 1.3 ≈ 3.31 → 3
        ml = next(d for d in result["dimensions"] if d["dimension"] == "math_logic")
        self.assertEqual(ml["score"], 3)

    async def test_total_score_is_sum_of_dim_scores(self):
        # 双模型同意 → 总分应该是各维度 cap 求和
        for sm in self.agent._structured_models:
            sm.ainvoke = AsyncMock(side_effect=_make_dim_scorer(target_score=99, target_conf="high"))
            # 99 会被 clip 到 cap

        result = await self.agent.aprocess({
            "question": "Q", "answer": "A",
        })
        expected_total = sum(DIMENSION_MAX_SCORE.values())  # 10
        self.assertEqual(result["score"], expected_total)


# ============================================================
# Coordinator 端到端注入
# ============================================================

class CoordinatorEnsembleWiring(unittest.TestCase):

    def test_scoring_models_list_wired(self):
        from interview.agents.coordinator import MultiAgentCoordinator

        with patch("interview.agents.coordinator.RetrievalSystem"), \
             patch("interview.agents.coordinator.MemoryStore"), \
             patch("interview.agents.coordinator.MemoryRetriever") as MR:
            mr_inst = MagicMock()
            MR.return_value = mr_inst

            c = MultiAgentCoordinator({
                "question_model": FakeModel("q"),
                "scoring_models": [FakeModel("doubao"), FakeModel("gemini")],
                "security_model": FakeModel("sec"),
                "summary_model": FakeModel("sum"),
            })

            self.assertEqual(len(c.scoring_agent.models), 2)
            self.assertEqual(c.scoring_agent.memory_retriever, mr_inst)

    def test_legacy_scoring_model_wired(self):
        from interview.agents.coordinator import MultiAgentCoordinator

        with patch("interview.agents.coordinator.RetrievalSystem"), \
             patch("interview.agents.coordinator.MemoryStore"), \
             patch("interview.agents.coordinator.MemoryRetriever"):
            c = MultiAgentCoordinator({
                "question_model": FakeModel("q"),
                "scoring_model": FakeModel("legacy"),
                "security_model": FakeModel("sec"),
                "summary_model": FakeModel("sum"),
            })
            self.assertEqual(len(c.scoring_agent.models), 1)


if __name__ == "__main__":
    unittest.main()
