"""
ScoringAgent — MTS 多维度独立评分 + 多模型 ensemble + RAG anchors (W1.2 重构)

论文锚点：
- MTS (Lee 2024, arXiv:2404.04941): 每维度独立 prompt，retrieve quotes 作为证据
- RULERS (Hong 2026, arXiv:2601.08654): evidence-anchored decoding，fail soft 降 confidence
- CISC (arXiv:2502.06233): confidence-weighted ensemble，agreement < 0.5 触发 review
- LLMs Cannot Self-Correct (ICLR 2024): 必须用多模型 ensemble，不要同模型自我批评
- arXiv:2603.06424: RAG anchors k=2 即可稳定 borderline case

核心改动 vs v2：
- 单次 LLM 调用 → 5 维度 × N 模型 = 5N 次并行调用
- 总分由公式聚合 (sum(dim.score))，不让 LLM 自由输出
- evidence_quote fuzzy match 校验 → 不在 answer 时降 confidence（不 reject）
- confidence-weighted ensemble + agreement 计算
- RAG anchors 自动注入（k=2，跨会话相似案例，exclude 当前 session 避免 self-leak）
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from interview.rubrics import RUBRIC_DIMENSIONS

from .base_agent import BaseAgent
from .cache import cached_system_message
from .qa_models import get_score
from .schemas import DIMENSION_MAX_SCORE, DimensionScore, ScoringOutput
from .utils import validate_quote_in_answer as _validate_quote_in_answer_impl


# 5 维度顺序固定（与 schemas.py / rubrics.py 一致）
_DIM_KEYS = list(DIMENSION_MAX_SCORE.keys())

# CISC 加权聚合的 confidence weights（论文风格）
_CONFIDENCE_WEIGHTS = {"high": 1.0, "medium": 0.6, "low": 0.3}

# Agreement 阈值（低于此值 → requires_human_review）
_AGREEMENT_THRESHOLD = 0.5


def _format_dim_rubric(dim_key: str) -> str:
    """格式化某维度的 LOW/MEDIUM/HIGH rubric clause（送给 LLM）"""
    dim = RUBRIC_DIMENSIONS.get(dim_key)
    if not dim:
        return f"(unknown dimension: {dim_key})"
    lines = [f"### {dim['name']} ({dim_key}, weight {dim['weight']})"]
    for level, desc in dim["levels"].items():
        lines.append(f"- {level}: {desc}")
    return "\n".join(lines)


# 注：fuzzy match / normalize 已统一收敛到 interview.agents.utils（2026-05-04 重构）
# _validate_quote_in_answer_impl 是从 utils.validate_quote_in_answer 的别名


class ScoringAgent(BaseAgent):
    """MTS 多维度评分 + 多模型 ensemble"""

    prompt_name = "scoring_dimension"
    output_schema = DimensionScore  # 注意：单维度 schema（不是 ScoringOutput）

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
            m.with_structured_output(DimensionScore, include_raw=False) for m in self.models
        ]
        self.logger = logging.getLogger("interview.agents.scoring_agent")
        self.logger.info(
            "ScoringAgent v3 (MTS + ensemble) 初始化，models=%s, memory_retriever=%s",
            [getattr(m, "model_name", "unknown") for m in self.models],
            "yes" if memory_retriever else "no",
        )

    # ------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------

    async def aprocess(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步评分 (MTS 5 维度独立 × N 模型 ensemble)。

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

        # 2. 5 维度 × N 模型并行（5N 次 LLM 调用）
        tasks = [
            self._score_one(
                dim_key, question, answer, anchors, question_type, difficulty, model_idx
            )
            for dim_key in _DIM_KEYS
            for model_idx in range(len(self.models))
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 3. 按 dim 分组并聚合
        grouped: Dict[str, List[DimensionScore]] = {dim: [] for dim in _DIM_KEYS}
        exceptions: List[BaseException] = []
        for r in results:
            if isinstance(r, BaseException):
                exceptions.append(r)
            elif isinstance(r, DimensionScore):
                grouped[r.dimension].append(r)
        if exceptions:
            self.logger.warning(
                "ScoringAgent ensemble: %d/%d 调用异常: %s",
                len(exceptions),
                len(results),
                [str(e)[:60] for e in exceptions[:2]],
            )

        final_dims: List[DimensionScore] = []
        all_fallback = True
        for dim_key in _DIM_KEYS:
            cands = grouped[dim_key]
            if cands:
                final_dims.append(self._aggregate_ensemble(dim_key, cands))
                all_fallback = False
            else:
                final_dims.append(self._fallback_dim(dim_key))

        # 4. agreement / confidence_level / requires_human_review
        agreement = self._compute_agreement(grouped)
        confidence_level = self._derive_confidence(agreement, final_dims, all_fallback)
        requires_review = (
            all_fallback
            or agreement < _AGREEMENT_THRESHOLD
            or sum(1 for d in final_dims if d.confidence == "low") >= 3
        )

        total = sum(d.score for d in final_dims)
        try:
            output = ScoringOutput(
                score=total,
                dimensions=final_dims,
                agreement=round(agreement, 3),
                confidence_level=confidence_level,
                requires_human_review=requires_review,
                fallback_used=all_fallback,
                reasoning=self._summarize_reasoning(final_dims),
            )
            return output.model_dump(mode="json")
        except Exception as e:
            self.logger.error(f"ScoringOutput 校验失败，全降级: {e}")
            return self._fallback_scoring()

    # ------------------------------------------------------------
    # 单次评分 / 聚合 / 校验
    # ------------------------------------------------------------

    async def _score_one(
        self,
        dim_key: str,
        question: str,
        answer: str,
        anchors: str,
        question_type: str,
        difficulty: str,
        model_idx: int,
    ) -> DimensionScore:
        """单维度 × 单模型 LLM 调用，返回 DimensionScore（失败抛异常由上层 gather 捕获）"""
        rubric_clause = _format_dim_rubric(dim_key)
        score_range = f"0-{DIMENSION_MAX_SCORE[dim_key]}"
        human_text = self.prompt.format_human(
            dimension_key=dim_key,
            rubric_clause=rubric_clause,
            score_range=score_range,
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

        result: DimensionScore = await self._structured_models[model_idx].ainvoke(messages)

        # ============================================================
        # P0-1 + P2-2: 强制 rubric_clause 与 level 对应（覆盖 LLM 输出）
        # ============================================================
        # LLM 可能：
        # (a) 给出 level=HIGH 但 rubric_clause 是 LOW 描述（自相矛盾，P0-1）
        # (b) 给出 rubric 的 paraphrase 而非精确文字（漂移风险，P2-2）
        # 修复：直接用 RUBRIC_DIMENSIONS 中的精确 LOW/MEDIUM/HIGH 描述覆盖 LLM 输出。
        # 这样 LLM 只决定 level + score，rubric_clause 由代码保证与 level 一致。
        canonical_rubric = (
            RUBRIC_DIMENSIONS.get(dim_key, {}).get("levels", {}).get(result.level)
        )
        if canonical_rubric and result.rubric_clause != canonical_rubric:
            self.logger.debug(
                "rubric_clause 与 level 不一致（dim=%s level=%s），覆盖：LLM='%s...' → canonical='%s...'",
                dim_key,
                result.level,
                (result.rubric_clause or "")[:40],
                canonical_rubric[:40],
            )
            result = result.model_copy(update={"rubric_clause": canonical_rubric})

        # ============================================================
        # quote fuzzy match：不在 answer 中 → 降 confidence（RULERS soft fallback）
        # ============================================================
        if not self._validate_quote_in_answer(result.evidence_quote, answer):
            self.logger.debug(
                "Quote 不在 answer 中（dim=%s, model=%d），降 confidence: quote=%s",
                dim_key,
                model_idx,
                (result.evidence_quote or "")[:30],
            )
            result = result.model_copy(update={"confidence": "low"})

        # ============================================================
        # 强制 dimension 与请求一致（防止 LLM 写错维度 key）
        # ============================================================
        if result.dimension != dim_key:
            self.logger.warning(
                "LLM 返回的 dimension=%s 与请求 %s 不符，已纠正",
                result.dimension,
                dim_key,
            )
            cap = DIMENSION_MAX_SCORE[dim_key]
            corrected_score = min(result.score, cap)
            result = result.model_copy(update={"dimension": dim_key, "score": corrected_score})

        # 记录模型来源
        try:
            result = result.model_copy(
                update={"model_name": getattr(self.models[model_idx], "model_name", f"model_{model_idx}")}
            )
        except Exception:
            result = result.model_copy(update={"model_name": f"model_{model_idx}"})
        return result

    def _aggregate_ensemble(
        self, dim_key: str, candidates: List[DimensionScore]
    ) -> DimensionScore:
        """CISC 风格 confidence-weighted 聚合（论文 arXiv:2502.06233）"""
        # score：confidence-weighted 平均，向最近整数靠拢
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
        # 上限保护
        score = max(0, min(score, DIMENSION_MAX_SCORE[dim_key]))

        # level：confidence-weighted 投票多数
        level_votes: Dict[str, float] = {}
        for c in candidates:
            w = _CONFIDENCE_WEIGHTS.get(c.confidence, 0.6)
            level_votes[c.level] = level_votes.get(c.level, 0.0) + w
        level = max(level_votes.keys(), key=lambda lv: level_votes[lv])

        # 选 confidence 最高的候选给出的 evidence_quote / rubric_clause / reasoning
        best = max(candidates, key=lambda d: _CONFIDENCE_WEIGHTS.get(d.confidence, 0.6))

        # ensemble confidence：根据投票一致性推断
        if len(candidates) >= 2:
            same_level_count = sum(1 for c in candidates if c.level == level)
            if same_level_count == len(candidates):
                ens_conf = best.confidence
            elif same_level_count >= len(candidates) * 0.5:
                ens_conf = "medium"
            else:
                ens_conf = "low"
        else:
            ens_conf = best.confidence

        return DimensionScore(
            dimension=dim_key,
            level=level,
            score=score,
            evidence_quote=best.evidence_quote,
            rubric_clause=best.rubric_clause,
            confidence=ens_conf,
            reasoning=best.reasoning,
            model_name=f"ensemble({len(candidates)})",
        )

    def _compute_agreement(self, grouped: Dict[str, List[DimensionScore]]) -> float:
        """计算多模型 ensemble 的整体 agreement（5 维度的 level agreement 均值）"""
        if not any(grouped.values()):
            return 0.0
        agreements = []
        for cands in grouped.values():
            if len(cands) <= 1:
                # 单模型时 agreement = 1.0（没有不一致可言）
                agreements.append(1.0)
                continue
            # 该维度的 level agreement = 最多投票数 / 总数
            level_counts: Dict[str, int] = {}
            for c in cands:
                level_counts[c.level] = level_counts.get(c.level, 0) + 1
            agreements.append(max(level_counts.values()) / len(cands))
        return sum(agreements) / len(agreements)

    def _derive_confidence(
        self, agreement: float, dims: List[DimensionScore], all_fallback: bool
    ) -> str:
        """根据 agreement 和维度 confidence 推导整体 confidence_level"""
        if all_fallback:
            return "low"
        low_count = sum(1 for d in dims if d.confidence == "low")
        if agreement >= 0.8 and low_count == 0:
            return "high"
        if agreement >= _AGREEMENT_THRESHOLD and low_count <= 2:
            return "medium"
        return "low"

    def _summarize_reasoning(self, dims: List[DimensionScore]) -> str:
        """聚合 5 维度 reasoning 为单行总结（供 ScoringOutput.reasoning）"""
        parts = [f"{d.dimension}={d.level}({d.score})" for d in dims]
        return "; ".join(parts)

    @staticmethod
    def _validate_quote_in_answer(quote: str, answer: str) -> bool:
        """fuzzy match 委托给 utils.validate_quote_in_answer（保持向后兼容的静态方法签名）"""
        return _validate_quote_in_answer_impl(quote, answer)

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
                2,  # top_k=2，论文推荐
                session_id,  # exclude_session_id 避免 self-leak
                None,
                0.0,
            )
            return self.memory_retriever.format_cases_for_scoring(similar)
        except Exception as e:
            self.logger.warning(f"RAG anchors 检索失败（不阻塞评分）: {e}")
            return ""

    # ------------------------------------------------------------
    # Fallback / readiness
    # ------------------------------------------------------------

    def _fallback_dim(self, dim_key: str) -> DimensionScore:
        """单维度全部模型失败时的降级（confidence=low, score=cap//2）"""
        cap = DIMENSION_MAX_SCORE[dim_key]
        # 中位数：cap=4→2, cap=2→1, cap=1→0（偏保守）
        score = cap // 2 if cap >= 2 else 0
        return DimensionScore(
            dimension=dim_key,
            level="LOW",
            score=score,
            evidence_quote="(fallback: LLM unavailable)",
            rubric_clause=f"Fallback: {dim_key} 评分降级",
            confidence="low",
            reasoning="所有 ensemble 模型调用失败，使用降级评分（中位数）",
            model_name="fallback",
        )

    def _fallback_scoring(self) -> Dict[str, Any]:
        """ScoringOutput 校验失败时返回完整 fallback dict"""
        dims = [self._fallback_dim(k) for k in _DIM_KEYS]
        total = sum(d.score for d in dims)
        return ScoringOutput(
            score=total,
            dimensions=dims,
            agreement=0.0,
            confidence_level="low",
            requires_human_review=True,
            fallback_used=True,
            reasoning="ScoringAgent 全降级（schema 校验失败）",
        ).model_dump(mode="json")

    def evaluate_interview_readiness(
        self, qa_history: List[Dict[str, Any]], min_questions: int = 4
    ) -> Dict[str, Any]:
        """评估是否有足够信息做出面试决定（沿用 v2 逻辑，通过 qa_models.get_score 兼容新旧 score_details）"""
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
