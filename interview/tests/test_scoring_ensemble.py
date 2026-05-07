"""
v4 集成测试：多模型 ensemble + RAG anchors（单分制）

覆盖：
1. RAG anchors 注入：memory_retriever 被调用（k=2，exclude_session_id），anchors 文本进入 prompt
2. RAG 失败时不阻塞评分（soft fail）
3. ensemble 中不同模型给出不同 confidence → CISC 加权
4. coordinator 接入 scoring_models 列表的端到端

运行：
  uv run python -m unittest interview.tests.test_scoring_ensemble -v
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from interview.agents.scoring_agent import ScoringAgent
from interview.agents.schemas import SingleScoreCandidate


class FakeModel:
    def __init__(self, name="fake"):
        self.model_name = name

    def with_structured_output(self, schema, include_raw=False):
        m = MagicMock()
        m.ainvoke = AsyncMock()
        return m


def _mk_cand(score=8, conf="high", quote="正确解法"):
    return SingleScoreCandidate(
        score=score,
        evidence_quote=quote,
        question_focus="算法",
        confidence=conf,
        reasoning="ok",
    )


def _make_scorer(target_score=8, target_conf="high", quote="正确解法"):
    """生成总是返回同一 candidate 的 fake LLM"""
    async def fake(messages):
        return _mk_cand(score=target_score, conf=target_conf, quote=quote)
    return fake


# ============================================================
# RAG anchors 注入
# ============================================================

class RagAnchorsInjection(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_retriever = MagicMock()
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
            sm.ainvoke = AsyncMock(side_effect=_make_scorer())

    async def test_retrieve_called_with_correct_args(self):
        await self.agent.aprocess({
            "question": "测试问题",
            "answer": "测试答案 包含 正确解法 字样",
            "session_id": "session_xyz",
        })
        # retrieve_similar_cases 应被调用，exclude_session_id="session_xyz"
        self.mock_retriever.retrieve_similar_cases.assert_called_once()
        args, _kwargs = self.mock_retriever.retrieve_similar_cases.call_args
        self.assertEqual(args[1], 2)  # top_k=2
        self.assertEqual(args[2], "session_xyz")

    async def test_anchors_passed_to_prompt(self):
        await self.agent.aprocess({
            "question": "Q",
            "answer": "A 正确解法 in answer",
            "session_id": "s1",
        })
        for sm in self.agent._structured_models:
            calls = sm.ainvoke.call_args_list
            self.assertTrue(len(calls) > 0)
            for call in calls[:1]:
                messages = call.args[0]
                human_text = messages[1].content
                self.assertIn("评分参考案例", human_text)

    async def test_retrieval_failure_does_not_block_scoring(self):
        self.mock_retriever.retrieve_similar_cases = MagicMock(
            side_effect=RuntimeError("MongoDB down")
        )
        result = await self.agent.aprocess({
            "question": "Q",
            "answer": "A 正确解法",
            "session_id": "s1",
        })
        # 评分仍应成功
        self.assertFalse(result["fallback_used"])
        self.assertIn("score", result)

    async def test_no_retriever_skips_anchors(self):
        agent_no_rag = ScoringAgent([FakeModel("m1")], memory_retriever=None)
        for sm in agent_no_rag._structured_models:
            sm.ainvoke = AsyncMock(side_effect=_make_scorer())

        result = await agent_no_rag.aprocess({
            "question": "Q",
            "answer": "A 正确解法",
        })
        self.assertFalse(result["fallback_used"])


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
        # model_a: score=8 high, model_b: score=2 low
        # 加权：(1.0*8 + 0.3*2) / 1.3 = 8.6/1.3 ≈ 6.6 → round 7
        self.agent._structured_models[0].ainvoke = AsyncMock(
            side_effect=_make_scorer(target_score=8, target_conf="high")
        )
        self.agent._structured_models[1].ainvoke = AsyncMock(
            side_effect=_make_scorer(target_score=2, target_conf="low")
        )

        result = await self.agent.aprocess({
            "question": "Q", "answer": "A 正确解法",
        })
        self.assertEqual(result["score"], 7)

    async def test_both_models_agree_yields_full_score(self):
        for sm in self.agent._structured_models:
            sm.ainvoke = AsyncMock(side_effect=_make_scorer(target_score=10, target_conf="high"))

        result = await self.agent.aprocess({
            "question": "Q", "answer": "A 正确解法",
        })
        self.assertEqual(result["score"], 10)
        self.assertEqual(result["agreement"], 1.0)

    async def test_disagreement_marks_review(self):
        self.agent._structured_models[0].ainvoke = AsyncMock(
            side_effect=_make_scorer(target_score=2, target_conf="high")
        )
        self.agent._structured_models[1].ainvoke = AsyncMock(
            side_effect=_make_scorer(target_score=9, target_conf="high")
        )

        result = await self.agent.aprocess({
            "question": "Q", "answer": "A 正确解法",
        })
        # diff=7 → agreement=0.3 → requires_human_review
        self.assertLess(result["agreement"], 0.5)
        self.assertTrue(result["requires_human_review"])


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
