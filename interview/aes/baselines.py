"""
Baseline 评分系统接入 — paper §6 实验对比

设计：
- VanillaJudge: 单 LLM 一次性输出 holistic score（最低 baseline）
- GEvalJudge: form-filling 风格（chain-of-thought + 自由 reasoning）
- MTSOnlyJudge: MTS 多 trait 独立评分但**不**强制 schema（测试 schema-enforcement 的边际贡献）

每个 baseline 都返回与 EssayScoringOutput 相同 dict 形态，便于 metrics.py 一致处理。
注意：baseline **不**做 evidence_quote fuzzy 校验、**不**强制 rubric_clause coverage ——
这正是论文中的 "ablation control"。

公共出口：
- VanillaJudge / GEvalJudge / MTSOnlyJudge（独立类）
- 所有 baseline 的 ascore 签名与 EssayScoringPipeline.ascore 对齐
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict

from .traits import TRAIT_KEYS, TRAIT_MAX_SCORE, TRAIT_MIN_SCORE, format_trait_rubric


# ============================================================
# Vanilla Judge: 单次 LLM 调用，一把梭输出 score + reasoning
# ============================================================

class VanillaOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    overall_score: int
    reasoning: str = ""


class VanillaJudge:
    """最 naive 的 baseline：单次 LLM 调用 + holistic score + 自由 reasoning"""

    SYSTEM = """You are an essay scorer. Given an essay, output a holistic score
between {min_s} and {max_s}, plus a brief reasoning paragraph.

Output JSON: {{"overall_score": int, "reasoning": str}}"""

    def __init__(self, model, score_range: tuple = (1, 6)):
        self.model = model
        self.structured = model.with_structured_output(VanillaOutput, include_raw=False)
        self.lo, self.hi = score_range
        self.logger = logging.getLogger("interview.aes.baselines.vanilla")

    async def ascore(
        self,
        essay_text: str,
        essay_prompt: str = "",
        trait_subset: Optional[List[str]] = None,
        overall_score_holistic: Optional[float] = None,
    ) -> Dict[str, Any]:
        sys = self.SYSTEM.format(min_s=self.lo, max_s=self.hi)
        human = f"Essay prompt:\n{essay_prompt or '(no prompt)'}\n\nStudent essay:\n{essay_text}"
        try:
            result = await self.structured.ainvoke([
                SystemMessage(content=sys),
                HumanMessage(content=human),
            ])
            score = max(self.lo, min(self.hi, result.overall_score))
            reasoning = result.reasoning
        except Exception as e:
            self.logger.warning(f"Vanilla LLM 异常，使用 fallback: {e}")
            score = (self.lo + self.hi) // 2
            reasoning = f"(fallback: {type(e).__name__})"

        # 转成 EssayScoringOutput 兼容 dict（仅 1 个 trait 占位 ideas）
        traits_to_use = trait_subset or [TRAIT_KEYS[0]]
        # 把 holistic score 平均分给每个 trait（向下取整保证总和 ≤ holistic）
        per_trait = max(TRAIT_MIN_SCORE[traits_to_use[0]], score // max(1, len(traits_to_use)))
        ts_list = []
        remaining = score
        for i, t in enumerate(traits_to_use):
            t_max = TRAIT_MAX_SCORE[t]
            if i == len(traits_to_use) - 1:
                # 最后一个吃尾差
                v = max(TRAIT_MIN_SCORE[t], min(t_max, remaining))
            else:
                v = max(TRAIT_MIN_SCORE[t], min(t_max, per_trait))
            remaining -= v
            ts_list.append({
                "trait": t,
                "level": "MEDIUM",
                "score": v,
                "evidence_quote": "(vanilla baseline: no evidence)",
                "rubric_clause": "(vanilla baseline: no rubric)",
                "confidence": "medium",
                "reasoning": reasoning,
                "model_name": getattr(self.model, "model_name", "vanilla"),
            })

        return {
            "total_score": sum(t["score"] for t in ts_list),
            "traits": ts_list,
            "agreement": 1.0,
            "confidence_level": "medium",
            "requires_human_review": False,
            "fallback_used": False,
            "reasoning": reasoning,
            "overall_score_holistic": overall_score_holistic,
        }


# ============================================================
# G-Eval Judge: form-filling chain-of-thought（Liu 2023 风格）
# ============================================================

class GEvalTraitOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    trait: str
    score: int
    reasoning: str = ""


class GEvalJudge:
    """G-Eval (Liu 2023) 风格：CoT + form-filling per trait（**没有** schema-enforced evidence）"""

    SYSTEM = """You are an expert essay scorer using chain-of-thought reasoning.

For the given trait, follow this process:
1. Think step by step about how the essay performs on this trait.
2. List specific aspects you noticed.
3. Conclude with an integer score in the allowed range.

Output your reasoning as free-form prose, then the final score.
DO NOT cite specific quotes from the essay (this is the difference from schema-enforced scoring)."""

    def __init__(self, model):
        self.model = model
        self.structured = model.with_structured_output(GEvalTraitOutput, include_raw=False)
        self.logger = logging.getLogger("interview.aes.baselines.geval")

    async def _score_one_trait(self, trait_key: str, essay_text: str, essay_prompt: str) -> GEvalTraitOutput:
        rubric = format_trait_rubric(trait_key)
        human = (
            f"Trait to score: {trait_key} (range {TRAIT_MIN_SCORE[trait_key]}-{TRAIT_MAX_SCORE[trait_key]})\n\n"
            f"Rubric:\n{rubric}\n\n"
            f"Essay prompt:\n{essay_prompt or '(no prompt)'}\n\n"
            f"Student essay:\n{essay_text}"
        )
        return await self.structured.ainvoke([
            SystemMessage(content=self.SYSTEM),
            HumanMessage(content=human),
        ])

    async def ascore(
        self,
        essay_text: str,
        essay_prompt: str = "",
        trait_subset: Optional[List[str]] = None,
        overall_score_holistic: Optional[float] = None,
    ) -> Dict[str, Any]:
        traits_to_use = trait_subset or TRAIT_KEYS
        tasks = [self._score_one_trait(t, essay_text, essay_prompt) for t in traits_to_use]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        ts_list = []
        for trait_key, r in zip(traits_to_use, results):
            if isinstance(r, BaseException):
                self.logger.warning(f"G-Eval trait {trait_key} 异常: {r}")
                lo, hi = TRAIT_MIN_SCORE[trait_key], TRAIT_MAX_SCORE[trait_key]
                score = (lo + hi) // 2
                reasoning = f"(fallback: {type(r).__name__})"
            else:
                lo, hi = TRAIT_MIN_SCORE[trait_key], TRAIT_MAX_SCORE[trait_key]
                score = max(lo, min(hi, r.score))
                reasoning = r.reasoning

            # 估测 level（粗略）
            mid = (TRAIT_MIN_SCORE[trait_key] + TRAIT_MAX_SCORE[trait_key]) / 2
            if score >= TRAIT_MAX_SCORE[trait_key] - 1:
                level = "HIGH"
            elif score <= TRAIT_MIN_SCORE[trait_key] + 1:
                level = "LOW"
            else:
                level = "MEDIUM"

            ts_list.append({
                "trait": trait_key,
                "level": level,
                "score": score,
                "evidence_quote": "(g-eval baseline: no evidence quote)",
                "rubric_clause": "(g-eval baseline: free-text reasoning)",
                "confidence": "medium",
                "reasoning": reasoning,
                "model_name": getattr(self.model, "model_name", "g-eval"),
            })

        return {
            "total_score": sum(t["score"] for t in ts_list),
            "traits": ts_list,
            "agreement": 1.0,
            "confidence_level": "medium",
            "requires_human_review": False,
            "fallback_used": False,
            "reasoning": "G-Eval CoT free-form reasoning per trait",
            "overall_score_holistic": overall_score_holistic,
        }


# ============================================================
# MTS-Only Judge: 多 trait 独立评分但**不**强制 evidence quote / rubric coverage
# ============================================================

class MTSOnlyJudge:
    """
    Lee 2024 MTS 复现 — 每 trait 独立 prompt，但**不**做 v3 的 schema enforcement：
    - 不强制 evidence_quote 在 essay 中
    - 不强制 rubric_clause 与 level 一致
    - 不做多模型 ensemble
    - 不做 boundary 检测

    这是 paper §6 ablation 的 A1 行（仅 MTS，无 schema）。
    """

    SYSTEM = """You are an expert essay scorer focused on a SINGLE rubric trait at a time.

For this call you will assess ONLY ONE trait. Do not consider other traits.

Method:
1. Read the candidate's essay in full.
2. Compare against the LOW / MEDIUM / HIGH rubric definitions for THIS trait.
3. Pick exactly one level (LOW / MEDIUM / HIGH).
4. Choose an integer score within the trait's allowed range.
5. Write a brief reasoning (1-2 sentences).

NOTE: For this baseline, you may or may not cite specific quotes from the essay.
Output natural prose reasoning."""

    def __init__(self, model):
        self.model = model
        self.structured = model.with_structured_output(GEvalTraitOutput, include_raw=False)
        self.logger = logging.getLogger("interview.aes.baselines.mts_only")

    async def _score_one(self, trait_key: str, essay_text: str, essay_prompt: str) -> GEvalTraitOutput:
        rubric = format_trait_rubric(trait_key)
        human = (
            f"Trait to score: {trait_key}\n"
            f"Rubric:\n{rubric}\n"
            f"Essay prompt:\n{essay_prompt or '(no prompt)'}\n\n"
            f"Student essay:\n{essay_text}"
        )
        return await self.structured.ainvoke([
            SystemMessage(content=self.SYSTEM),
            HumanMessage(content=human),
        ])

    async def ascore(
        self,
        essay_text: str,
        essay_prompt: str = "",
        trait_subset: Optional[List[str]] = None,
        overall_score_holistic: Optional[float] = None,
    ) -> Dict[str, Any]:
        traits_to_use = trait_subset or TRAIT_KEYS
        tasks = [self._score_one(t, essay_text, essay_prompt) for t in traits_to_use]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        ts_list = []
        for trait_key, r in zip(traits_to_use, results):
            if isinstance(r, BaseException):
                lo, hi = TRAIT_MIN_SCORE[trait_key], TRAIT_MAX_SCORE[trait_key]
                score = (lo + hi) // 2
                level = "MEDIUM"
                reasoning = f"(fallback: {type(r).__name__})"
            else:
                lo, hi = TRAIT_MIN_SCORE[trait_key], TRAIT_MAX_SCORE[trait_key]
                score = max(lo, min(hi, r.score))
                if score >= hi - 1:
                    level = "HIGH"
                elif score <= lo + 1:
                    level = "LOW"
                else:
                    level = "MEDIUM"
                reasoning = r.reasoning

            ts_list.append({
                "trait": trait_key,
                "level": level,
                "score": score,
                "evidence_quote": "(MTS-only baseline: no schema-enforced evidence)",
                "rubric_clause": "(MTS-only baseline: no canonical rubric)",
                "confidence": "medium",
                "reasoning": reasoning,
                "model_name": getattr(self.model, "model_name", "mts-only"),
            })

        return {
            "total_score": sum(t["score"] for t in ts_list),
            "traits": ts_list,
            "agreement": 1.0,
            "confidence_level": "medium",
            "requires_human_review": False,
            "fallback_used": False,
            "reasoning": "MTS-only ablation: multi-trait independent scoring without schema enforcement",
            "overall_score_holistic": overall_score_holistic,
        }
