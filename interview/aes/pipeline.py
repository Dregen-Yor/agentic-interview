"""
EssayScoringPipeline — ASAP 2.0 instantiation 的核心评分管线

设计：
- 与 interview.agents.scoring_agent.ScoringAgent **同构但独立**：
  - 5 trait × N 模型并行 LLM 调用
  - CISC confidence-weighted ensemble 聚合
  - schema-enforced rubric_clause 覆盖
  - fuzzy quote validation（复用 interview.agents.utils.validate_quote_in_answer）
  - all_fallback / fallback dim 行为
- 不依赖任何 interview.agents.* 状态：纯函数式 essay → EssayScoringOutput

公共出口：
- EssayScoringPipeline.ascore(essay, prompt_text, trait_subset=None)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from interview.agents.utils import validate_quote_in_answer

from .prompt_loader import load_aes_prompt
from .schemas import EssayScoringOutput, TraitScore
from .traits import (
    TRAIT_KEYS,
    TRAIT_MAX_SCORE,
    TRAIT_MIN_SCORE,
    TRAITS,
    format_trait_rubric,
    get_canonical_rubric_clause,
)


# CISC 加权聚合（与 ScoringAgent 一致）
_CONFIDENCE_WEIGHTS = {"high": 1.0, "medium": 0.6, "low": 0.3}
_AGREEMENT_THRESHOLD = 0.5

# 下限分（fallback / 0-分契约）— ASAP 2.0 1-6 范围下，fallback 取范围中位
def _fallback_score(trait_key: str) -> int:
    lo, hi = TRAIT_MIN_SCORE[trait_key], TRAIT_MAX_SCORE[trait_key]
    return (lo + hi) // 2


class EssayScoringPipeline:
    """trait-agnostic ScoringAgent 在 AES 场景的 instantiation

    使用方式：
        from interview.llm import gemini_model, doubao_model
        pipeline = EssayScoringPipeline(models=[doubao_model, gemini_model])
        result = await pipeline.ascore(
            essay_text=essay,
            essay_prompt=prompt,
            trait_subset=["ideas", "organization", "conventions"],
        )
    """

    PROMPT_NAME = "aes_trait_scoring"

    def __init__(self, models, similar_cases_provider=None):
        """
        Args:
            models: ChatOpenAI 单个或 List[ChatOpenAI]
            similar_cases_provider: 可选的 callable(essay, prompt) -> str
                返回 RAG anchors 文本（默认无 anchors）
        """
        if not isinstance(models, list):
            models = [models]
        if not models:
            raise ValueError("EssayScoringPipeline: 至少需要 1 个 model")
        self.models = list(models)
        self._structured_models = [
            m.with_structured_output(TraitScore, include_raw=False) for m in self.models
        ]
        self.similar_cases_provider = similar_cases_provider
        self.prompt = load_aes_prompt(self.PROMPT_NAME)
        self.logger = logging.getLogger("interview.aes.pipeline")
        self.logger.info(
            "EssayScoringPipeline initialized: models=%s",
            [getattr(m, "model_name", "unknown") for m in self.models],
        )

    # ------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------

    async def ascore(
        self,
        essay_text: str,
        essay_prompt: str = "",
        trait_subset: Optional[List[str]] = None,
        overall_score_holistic: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        异步评分一篇 essay（trait × model 并行）。

        Args:
            essay_text: 学生 essay 全文
            essay_prompt: writing prompt 文字（可选）
            trait_subset: 要评分的 trait 子集；None=全部 5 个 traits
            overall_score_holistic: 如 ASAP set 提供 holistic score，记录便于对照

        Returns:
            EssayScoringOutput dict 形式
        """
        traits_to_score = trait_subset or TRAIT_KEYS
        # 校验 trait 名合法
        for t in traits_to_score:
            if t not in TRAITS:
                raise ValueError(f"Unknown trait '{t}'，必须是 {TRAIT_KEYS}")

        # RAG anchors（可选）
        anchors = ""
        if self.similar_cases_provider:
            try:
                anchors = await asyncio.to_thread(
                    self.similar_cases_provider, essay_text, essay_prompt
                )
            except Exception as e:
                self.logger.warning(f"similar_cases_provider 异常（不阻塞）: {e}")
                anchors = ""

        # trait × model 并行调用
        tasks = [
            self._score_one(trait_key, essay_text, essay_prompt, anchors, model_idx)
            for trait_key in traits_to_score
            for model_idx in range(len(self.models))
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 按 trait 分组
        grouped: Dict[str, List[TraitScore]] = {t: [] for t in traits_to_score}
        exceptions: List[BaseException] = []
        for r in results:
            if isinstance(r, BaseException):
                exceptions.append(r)
            elif isinstance(r, TraitScore):
                grouped[r.trait].append(r)
        if exceptions:
            self.logger.warning(
                "Pipeline ensemble: %d/%d 调用异常: %s",
                len(exceptions),
                len(results),
                [str(e)[:60] for e in exceptions[:2]],
            )

        # 每个 trait 聚合
        final_traits: List[TraitScore] = []
        all_fallback = True
        for trait_key in traits_to_score:
            cands = grouped[trait_key]
            if cands:
                final_traits.append(self._aggregate_ensemble(trait_key, cands))
                all_fallback = False
            else:
                final_traits.append(self._fallback_trait(trait_key))

        # agreement / confidence
        agreement = self._compute_agreement(grouped)
        confidence_level = self._derive_confidence(agreement, final_traits, all_fallback)
        requires_review = (
            all_fallback
            or agreement < _AGREEMENT_THRESHOLD
            or sum(1 for t in final_traits if t.confidence == "low") >= max(2, len(final_traits) // 2)
        )

        total = sum(t.score for t in final_traits)
        try:
            output = EssayScoringOutput(
                total_score=total,
                traits=final_traits,
                agreement=round(agreement, 3),
                confidence_level=confidence_level,
                requires_human_review=requires_review,
                fallback_used=all_fallback,
                reasoning=self._summarize_reasoning(final_traits),
                overall_score_holistic=overall_score_holistic,
            )
            return output.model_dump(mode="json")
        except Exception as e:
            self.logger.error(f"EssayScoringOutput 校验失败: {e}")
            return self._full_fallback(traits_to_score, overall_score_holistic)

    # ------------------------------------------------------------
    # 内部：单 trait × 单模型 LLM 调用
    # ------------------------------------------------------------

    async def _score_one(
        self,
        trait_key: str,
        essay_text: str,
        essay_prompt: str,
        anchors: str,
        model_idx: int,
    ) -> TraitScore:
        rubric_text = format_trait_rubric(trait_key)
        score_range = f"{TRAIT_MIN_SCORE[trait_key]}-{TRAIT_MAX_SCORE[trait_key]}"
        human_text = self.prompt.format_human(
            trait_key=trait_key,
            rubric_clause=rubric_text,
            score_range=score_range,
            essay_prompt=essay_prompt or "(no prompt provided)",
            essay_text=essay_text,
            similar_cases=anchors or "(no historical reference cases)",
        )
        messages = [
            SystemMessage(content=self.prompt.system),
            HumanMessage(content=human_text),
        ]

        result: TraitScore = await self._structured_models[model_idx].ainvoke(messages)

        # ============================================================
        # P0-1 + P2-2 等价处理：强制 rubric_clause 与 level 对应（覆盖 LLM）
        # ============================================================
        canonical = get_canonical_rubric_clause(trait_key, result.level)
        if canonical and result.rubric_clause != canonical:
            self.logger.debug(
                "rubric_clause 与 level 不一致（trait=%s level=%s），覆盖",
                trait_key, result.level,
            )
            result = result.model_copy(update={"rubric_clause": canonical})

        # quote fuzzy match（不在则降 confidence，RULERS soft fallback）
        if not validate_quote_in_answer(result.evidence_quote, essay_text):
            self.logger.debug(
                "Quote 不在 essay 中（trait=%s, model=%d），降 confidence",
                trait_key, model_idx,
            )
            result = result.model_copy(update={"confidence": "low"})

        # 强制 trait 与请求一致（防 LLM 写错 key）
        if result.trait != trait_key:
            self.logger.warning(
                "LLM 返回 trait=%s 与请求 %s 不符，纠正",
                result.trait, trait_key,
            )
            # 边界保护：score 越界时 clamp
            lo, hi = TRAIT_MIN_SCORE[trait_key], TRAIT_MAX_SCORE[trait_key]
            corrected_score = max(lo, min(hi, result.score))
            result = result.model_copy(update={"trait": trait_key, "score": corrected_score})

        # 记录模型来源
        try:
            result = result.model_copy(
                update={"model_name": getattr(self.models[model_idx], "model_name", f"model_{model_idx}")}
            )
        except Exception:
            result = result.model_copy(update={"model_name": f"model_{model_idx}"})
        return result

    # ------------------------------------------------------------
    # CISC ensemble 聚合（与 ScoringAgent._aggregate_ensemble 同构）
    # ------------------------------------------------------------

    def _aggregate_ensemble(
        self, trait_key: str, candidates: List[TraitScore]
    ) -> TraitScore:
        # weighted score
        weighted = 0.0
        weight_sum = 0.0
        for c in candidates:
            w = _CONFIDENCE_WEIGHTS.get(c.confidence, 0.6)
            weighted += w * c.score
            weight_sum += w
        if weight_sum > 0:
            score = int(round(weighted / weight_sum))
        else:
            score = candidates[0].score
        lo, hi = TRAIT_MIN_SCORE[trait_key], TRAIT_MAX_SCORE[trait_key]
        score = max(lo, min(score, hi))

        # weighted level vote
        level_votes: Dict[str, float] = {}
        for c in candidates:
            w = _CONFIDENCE_WEIGHTS.get(c.confidence, 0.6)
            level_votes[c.level] = level_votes.get(c.level, 0.0) + w
        level = max(level_votes.keys(), key=lambda lv: level_votes[lv])

        best = max(candidates, key=lambda d: _CONFIDENCE_WEIGHTS.get(d.confidence, 0.6))

        # ensemble confidence
        if len(candidates) >= 2:
            same_level = sum(1 for c in candidates if c.level == level)
            if same_level == len(candidates):
                ens_conf = best.confidence
            elif same_level >= len(candidates) * 0.5:
                ens_conf = "medium"
            else:
                ens_conf = "low"
        else:
            ens_conf = best.confidence

        # 用 canonical rubric_clause（保证 P0-1 一致性）
        canonical = get_canonical_rubric_clause(trait_key, level) or best.rubric_clause

        return TraitScore(
            trait=trait_key,
            level=level,
            score=score,
            evidence_quote=best.evidence_quote,
            rubric_clause=canonical,
            confidence=ens_conf,
            reasoning=best.reasoning,
            model_name=f"ensemble({len(candidates)})",
        )

    def _compute_agreement(self, grouped: Dict[str, List[TraitScore]]) -> float:
        if not any(grouped.values()):
            return 0.0
        agreements = []
        for cands in grouped.values():
            if len(cands) <= 1:
                agreements.append(1.0)
                continue
            level_counts: Dict[str, int] = {}
            for c in cands:
                level_counts[c.level] = level_counts.get(c.level, 0) + 1
            agreements.append(max(level_counts.values()) / len(cands))
        return sum(agreements) / len(agreements)

    def _derive_confidence(
        self, agreement: float, traits: List[TraitScore], all_fallback: bool
    ) -> str:
        if all_fallback:
            return "low"
        low_count = sum(1 for t in traits if t.confidence == "low")
        if agreement >= 0.8 and low_count == 0:
            return "high"
        if agreement >= _AGREEMENT_THRESHOLD and low_count <= max(1, len(traits) // 2):
            return "medium"
        return "low"

    def _summarize_reasoning(self, traits: List[TraitScore]) -> str:
        return "; ".join(f"{t.trait}={t.level}({t.score})" for t in traits)

    # ------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------

    def _fallback_trait(self, trait_key: str) -> TraitScore:
        return TraitScore(
            trait=trait_key,
            level="LOW",
            score=_fallback_score(trait_key),
            evidence_quote="(fallback: LLM unavailable)",
            rubric_clause=get_canonical_rubric_clause(trait_key, "LOW") or f"Fallback: {trait_key}",
            confidence="low",
            reasoning="All ensemble models failed; using fallback median score",
            model_name="fallback",
        )

    def _full_fallback(
        self,
        traits_to_score: List[str],
        overall_score_holistic: Optional[float],
    ) -> Dict[str, Any]:
        ts = [self._fallback_trait(k) for k in traits_to_score]
        total = sum(t.score for t in ts)
        return EssayScoringOutput(
            total_score=total,
            traits=ts,
            agreement=0.0,
            confidence_level="low",
            requires_human_review=True,
            fallback_used=True,
            reasoning="EssayScoringPipeline full fallback",
            overall_score_holistic=overall_score_holistic,
        ).model_dump(mode="json")
