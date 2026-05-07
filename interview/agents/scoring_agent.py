"""
ScoringAgent — 单题整体评分 + 多模型 ensemble + RAG anchors (v4 重构)

设计要点（vs v3 5 维度独立）：
- LLM 不再按维度独立打分。每模型每题输出 ONE 个 0-10 总分 + evidence_quote + question_focus
- N 模型并行 → CISC confidence-weighted 聚合为单题最终分
- agreement = 1 - (max - min) / 10，反映多模型分差
- requires_human_review 触发条件：fallback / agreement<0.7 / 多数 confidence=low

论文锚点：
- RULERS (Hong 2026, arXiv:2601.08654): evidence-anchored，必须给 quote
- CISC (arXiv:2502.06233): confidence-weighted ensemble
- LLMs Cannot Self-Correct (ICLR 2024): 多模型 ensemble 比同模型自校验更可靠
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from .base_agent import BaseAgent
from .cache import cached_system_message
from .qa_models import get_score
from .schemas import ScoringOutput, SingleScoreCandidate
from .utils import validate_quote_in_answer as _validate_quote_in_answer_impl


# CISC 加权聚合的 confidence weights
_CONFIDENCE_WEIGHTS = {"high": 1.0, "medium": 0.6, "low": 0.3}

# Agreement 阈值（低于此值 → requires_human_review）
# v4 公式：agreement = 1 - (max - min) / 10；阈值 0.7 对应分差 ≥ 3
_AGREEMENT_THRESHOLD = 0.7

# 单题分数上下限
_SCORE_MIN = 0
_SCORE_MAX = 10


class ScoringAgent(BaseAgent):
    """单题整体评分 + 多模型 ensemble"""

    prompt_name = "scoring_holistic"
    output_schema = SingleScoreCandidate  # 每模型一次调用产出此 schema

    def __init__(self, models, memory_retriever=None):
        """
        Args:
            models: ChatOpenAI 单个或 List[ChatOpenAI]。建议传入 2 个不同 API 来源的模型
                    (如 [doubao_model, gemini_model]) 启用 ensemble。
            memory_retriever: MemoryRetriever 实例，用于注入 RAG anchors。可空（跳过 RAG）。
        """
        if not isinstance(models, list):
            models = [models]
        if not models:
            raise ValueError("ScoringAgent: 至少需要 1 个 model")
        # 第 0 个作为 BaseAgent 的 default model（继承的 prompt 加载等）
        super().__init__(models[0], "ScoringAgent")
        self.models: List[ChatOpenAI] = list(models)
        self.memory_retriever = memory_retriever
        # 为每个模型预编译 structured output（避免每次调用重新绑定）
        self._structured_models = [
            m.with_structured_output(SingleScoreCandidate, include_raw=False)
            for m in self.models
        ]
        self.logger = logging.getLogger("interview.agents.scoring_agent")
        self.logger.info(
            "ScoringAgent v4 (holistic + ensemble) 初始化，models=%s, memory_retriever=%s",
            [getattr(m, "model_name", "unknown") for m in self.models],
            "yes" if memory_retriever else "no",
        )

    # ------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------

    async def aprocess(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步评分（N 模型并行 → CISC 加权聚合）。

        input_data:
            question: str
            answer: str
            question_type: str (default "general")
            difficulty: str (default "medium")
            session_id: Optional[str] (用于 RAG anchors 排除当前会话)

        Returns: ScoringOutput 的 dict 形式
        """
        question = input_data.get("question", "")
        answer = input_data.get("answer", "")
        question_type = input_data.get("question_type", "general")
        difficulty = input_data.get("difficulty", "medium")
        session_id = input_data.get("session_id")

        # 1. RAG anchors（k=2，跨会话相似案例）
        anchors = await self._fetch_rag_anchors(question, answer, session_id)

        # 2. N 模型并行调用（每模型 1 次）
        tasks = [
            self._score_with_model(
                question, answer, question_type, difficulty, anchors, model_idx
            )
            for model_idx in range(len(self.models))
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 3. 收集成功的 candidates
        candidates: List[SingleScoreCandidate] = []
        exceptions: List[BaseException] = []
        for r in results:
            if isinstance(r, BaseException):
                exceptions.append(r)
            elif isinstance(r, SingleScoreCandidate):
                candidates.append(r)
        if exceptions:
            self.logger.warning(
                "ScoringAgent ensemble: %d/%d 调用异常: %s",
                len(exceptions),
                len(results),
                [str(e)[:60] for e in exceptions[:2]],
            )

        # 4. 全降级 / 正常聚合
        if not candidates:
            return self._fallback_scoring()

        aggregated = self._aggregate_scores(candidates, answer)
        agreement = self._compute_score_agreement(candidates)
        confidence_level = self._derive_confidence(agreement, candidates, all_fallback=False)

        low_count = sum(1 for c in candidates if c.confidence == "low")
        requires_review = (
            agreement < _AGREEMENT_THRESHOLD
            or (len(candidates) >= 2 and low_count >= len(candidates))
            or (len(candidates) == 1 and candidates[0].confidence == "low")
        )

        try:
            output = ScoringOutput(
                score=aggregated["score"],
                evidence_quote=aggregated["evidence_quote"],
                question_focus=aggregated["question_focus"],
                agreement=round(agreement, 3),
                confidence_level=confidence_level,
                requires_human_review=requires_review,
                fallback_used=False,
                reasoning=aggregated["reasoning"],
                model_name=aggregated["model_name"],
            )
            return output.model_dump(mode="json")
        except Exception as e:
            self.logger.error(f"ScoringOutput 校验失败，全降级: {e}")
            return self._fallback_scoring()

    # ------------------------------------------------------------
    # 单模型调用
    # ------------------------------------------------------------

    async def _score_with_model(
        self,
        question: str,
        answer: str,
        question_type: str,
        difficulty: str,
        anchors: str,
        model_idx: int,
    ) -> SingleScoreCandidate:
        """单模型一次评分调用"""
        human_text = self.prompt.format_human(
            question_type=question_type,
            difficulty=difficulty,
            question=question,
            answer=answer,
            similar_cases=anchors or "（无历史参考案例）",
        )
        messages = [
            cached_system_message(self.get_system_prompt()),
            HumanMessage(content=human_text),
        ]

        result: SingleScoreCandidate = await self._structured_models[model_idx].ainvoke(messages)

        # ------------------------------------------------------------
        # quote fuzzy match：不在 answer 中 → 降 confidence (RULERS soft fallback)
        # 不 reject，避免单点失败拖垮整轮评分
        # ------------------------------------------------------------
        if not _validate_quote_in_answer_impl(result.evidence_quote, answer):
            self.logger.debug(
                "Quote 不在 answer 中（model=%d），降 confidence: quote=%s",
                model_idx,
                (result.evidence_quote or "")[:40],
            )
            result = result.model_copy(update={"confidence": "low"})

        # 防御 clamp（pydantic ge=0,le=10 已校验，但保险起见）
        if result.score < _SCORE_MIN or result.score > _SCORE_MAX:
            clamped = max(_SCORE_MIN, min(_SCORE_MAX, result.score))
            self.logger.warning(
                "score=%d 越界，clamp 到 %d", result.score, clamped
            )
            result = result.model_copy(update={"score": clamped})

        # 记录模型来源
        try:
            result = result.model_copy(
                update={"model_name": getattr(self.models[model_idx], "model_name", f"model_{model_idx}")}
            )
        except Exception:
            result = result.model_copy(update={"model_name": f"model_{model_idx}"})
        return result

    # ------------------------------------------------------------
    # CISC 聚合 / agreement / confidence
    # ------------------------------------------------------------

    def _aggregate_scores(
        self, candidates: List[SingleScoreCandidate], answer: str
    ) -> Dict[str, Any]:
        """CISC 风格 confidence-weighted 聚合"""
        weighted_score = 0.0
        weight_sum = 0.0
        for c in candidates:
            w = _CONFIDENCE_WEIGHTS.get(c.confidence, 0.6)
            weighted_score += w * c.score
            weight_sum += w
        if weight_sum > 0:
            score = int(round(weighted_score / weight_sum))
        else:
            score = candidates[0].score
        score = max(_SCORE_MIN, min(_SCORE_MAX, score))

        # evidence_quote / question_focus / reasoning：取 confidence 最高的候选
        # （若 quote fuzzy match 不通过 → 取下一个 confidence 更高的；否则就用最高）
        sorted_cands = sorted(
            candidates,
            key=lambda d: _CONFIDENCE_WEIGHTS.get(d.confidence, 0.6),
            reverse=True,
        )
        best = sorted_cands[0]
        # 优先选 evidence_quote 在 answer 中的候选
        for c in sorted_cands:
            if _validate_quote_in_answer_impl(c.evidence_quote, answer):
                best = c
                break

        model_name = (
            f"ensemble({len(candidates)})" if len(candidates) >= 2 else best.model_name
        )

        return {
            "score": score,
            "evidence_quote": best.evidence_quote,
            "question_focus": best.question_focus,
            "reasoning": best.reasoning,
            "model_name": model_name,
        }

    @staticmethod
    def _compute_score_agreement(candidates: List[SingleScoreCandidate]) -> float:
        """计算多模型 agreement = 1 - (max - min) / 10

        - 单模型时 = 1.0（无不一致可言）
        - 两模型分差 0 → 1.0；分差 5 → 0.5；分差 10 → 0.0
        """
        if len(candidates) <= 1:
            return 1.0
        scores = [c.score for c in candidates]
        diff = max(scores) - min(scores)
        return max(0.0, 1.0 - diff / 10.0)

    @staticmethod
    def _derive_confidence(
        agreement: float,
        candidates: List[SingleScoreCandidate],
        all_fallback: bool,
    ) -> str:
        """根据 agreement 和候选 confidence 推导整体 confidence_level"""
        if all_fallback:
            return "low"
        low_count = sum(1 for c in candidates if c.confidence == "low")
        n = len(candidates)
        # 全部候选都是 low → 整体 low（不论 agreement，避免单模型 quote 失效仍判 medium）
        if low_count >= n:
            return "low"
        if agreement >= 0.9 and low_count == 0:
            return "high"
        if agreement >= _AGREEMENT_THRESHOLD and low_count <= max(1, n // 2):
            return "medium"
        return "low"

    # ------------------------------------------------------------
    # RAG anchors
    # ------------------------------------------------------------

    async def _fetch_rag_anchors(
        self, question: str, answer: str, session_id: Optional[str]
    ) -> str:
        """从 MemoryRetriever 取 k=2 跨会话相似案例（论文 arXiv:2603.06424）"""
        if not self.memory_retriever:
            return ""
        try:
            query = f"{question}\n{answer}"[:1000]
            similar = await asyncio.to_thread(
                self.memory_retriever.retrieve_similar_cases,
                query,
                2,  # top_k=2
                session_id,  # exclude_session_id 避免 self-leak
                None,
                0.0,
            )
            return self.memory_retriever.format_cases_for_scoring(similar)
        except Exception as e:
            self.logger.warning(f"RAG anchors 检索失败（不阻塞评分）: {e}")
            return ""

    # ------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------

    def _fallback_scoring(self) -> Dict[str, Any]:
        """所有模型调用失败时的全降级：score=5（中位数）+ requires_human_review=True"""
        try:
            output = ScoringOutput(
                score=5,
                evidence_quote="(fallback: LLM unavailable)",
                question_focus="(fallback)",
                agreement=0.0,
                confidence_level="low",
                requires_human_review=True,
                fallback_used=True,
                reasoning="所有 ensemble 模型调用失败，使用降级评分（中位数 5）",
                model_name="fallback",
            )
            return output.model_dump(mode="json")
        except Exception as e:
            # 极端兜底（理论上不应到这里）
            self.logger.error(f"_fallback_scoring 自身校验失败: {e}")
            return {
                "score": 5,
                "evidence_quote": "(fallback)",
                "question_focus": "(fallback)",
                "agreement": 0.0,
                "confidence_level": "low",
                "requires_human_review": True,
                "fallback_used": True,
                "reasoning": "fallback",
                "model_name": "fallback",
            }

    # ------------------------------------------------------------
    # readiness（沿用 v3 逻辑）
    # ------------------------------------------------------------

    def evaluate_interview_readiness(
        self, qa_history: List[Dict[str, Any]], min_questions: int = 4
    ) -> Dict[str, Any]:
        """评估是否有足够信息做出面试决定。仅依赖 score 字段（通过 qa_models.get_score）"""
        total_questions = len(qa_history)

        if total_questions < min_questions:
            return {
                "ready": False,
                "reason": f"问题数量不足，当前{total_questions}题，建议至少{min_questions}题",
                "recommendation": "continue",
            }

        scores = [get_score(qa) for qa in qa_history]
        scores = [s for s in scores if s > 0]
        if not scores:
            return {
                "ready": False,
                "reason": "缺少评分信息",
                "recommendation": "continue",
            }

        avg_score = sum(scores) / len(scores)
        high_scores = sum(1 for s in scores if s >= 7)
        low_scores = sum(1 for s in scores if s <= 4)

        if avg_score >= 7 and high_scores >= total_questions * 0.6:
            return {
                "ready": True,
                "reason": f"候选人表现优秀，平均分{avg_score:.1f}",
                "recommendation": "accept",
            }
        elif avg_score <= 4 or low_scores >= total_questions * 0.5:
            return {
                "ready": True,
                "reason": f"候选人表现不佳，平均分{avg_score:.1f}",
                "recommendation": "reject",
            }
        elif total_questions >= 5:
            decision = "accept" if avg_score >= 6 else "reject"
            return {
                "ready": True,
                "reason": f"已完成{total_questions}题评估，平均分{avg_score:.1f}",
                "recommendation": decision,
            }
        else:
            return {
                "ready": False,
                "reason": f"需要更多信息，当前平均分{avg_score:.1f}，建议继续面试",
                "recommendation": "continue",
            }
