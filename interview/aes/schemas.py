"""
AES 模块独立 schemas — 与 interview.agents.schemas 同构但独立

设计：
- TraitScore：单 trait 评分契约（与 DimensionScore 对应，但 trait 字段是 ASAP traits）
- EssayScoringOutput：聚合输出（与 ScoringOutput 对应）

为什么不复用 DimensionScore：
- DimensionScore.dimension 是 Literal["math_logic", ..., "growth_potential"]，
  绑定面试 5 维度。AES 用 TRAITS 中定义的 trait 词汇（ideas / organization / ...）。
- 修改 DimensionScore 会破坏面试系统的 schema 校验。新建并行 schema 是最干净的解。

不变量（与面试 schema 一致，证明 paper 中"trait-agnostic"是真的）：
- score 必须在 trait 的 (min, max) 内
- 各 trait score 求和 = total（公式聚合，非 LLM 自由输出）
- evidence_quote 通过 fuzzy match 校验（复用 utils.validate_quote_in_answer）
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .traits import TRAIT_KEYS, TRAIT_MAX_SCORE, TRAIT_MIN_SCORE


# Literal 必须用字面量列表，trait 词汇与 traits.TRAIT_KEYS 一致
# （Pydantic v2 不支持运行时构造 Literal，所以这里硬编码 — 如果未来改 traits 必须同步）
TraitKey = Literal[
    "ideas",
    "organization",
    "voice",
    "word_choice",
    "conventions",
]


class TraitScore(BaseModel):
    """ASAP 2.0 单 trait 评分契约

    论文锚点：MTS (arXiv:2404.04941) + RULERS (arXiv:2601.08654)
    与 interview.agents.schemas.DimensionScore 同构。
    """
    model_config = ConfigDict(extra="ignore")

    trait: TraitKey = Field(..., description="ASAP 2.0 trait 之一")
    level: Literal["LOW", "MEDIUM", "HIGH"]
    score: int = Field(..., description="trait 整数分；范围由 model_validator 校验")
    evidence_quote: str = Field(
        ...,
        min_length=2,
        description="essay 中支撑此判断的原文片段（fuzzy match 校验）",
    )
    rubric_clause: str = Field(
        ...,
        description="rubric 中对应 LOW/MEDIUM/HIGH 的描述文字",
    )
    confidence: Literal["high", "medium", "low"] = "medium"
    reasoning: str = ""
    model_name: Optional[str] = None

    @model_validator(mode="after")
    def check_score_range(self):
        lo, hi = TRAIT_MIN_SCORE[self.trait], TRAIT_MAX_SCORE[self.trait]
        if not (lo <= self.score <= hi):
            raise ValueError(
                f"{self.trait} 分数 {self.score} 越界 [{lo}, {hi}]"
            )
        return self


class EssayScoringOutput(BaseModel):
    """聚合 essay 评分 — total = sum(trait scores)，schema 强制内部一致性"""
    model_config = ConfigDict(extra="ignore")

    total_score: int = Field(..., description="所有 trait score 求和（公式聚合）")
    traits: List[TraitScore] = Field(
        ...,
        min_length=1,
        description="参与评分的 trait 列表；不同 ASAP set 可用 trait 子集（≥1）",
    )
    agreement: float = Field(default=1.0, ge=0.0, le=1.0,
        description="多模型 ensemble 一致性（单模型 = 1.0）")
    confidence_level: Literal["high", "medium", "low"] = "medium"
    requires_human_review: bool = False
    fallback_used: bool = False
    reasoning: str = ""

    # AES 特有：domain1_score 用于直接比 ASAP 2.0 的 ground truth（如果存在）
    overall_score_holistic: Optional[float] = Field(
        default=None,
        description="如 ASAP set 提供 holistic score，记录便于对照"
    )

    @model_validator(mode="after")
    def check_consistency(self):
        # trait 不重复
        keys = [t.trait for t in self.traits]
        if len(keys) != len(set(keys)):
            raise ValueError(f"trait 重复: {keys}")
        # total 必须 = 各 trait score 求和
        s = sum(t.score for t in self.traits)
        if self.total_score != s:
            raise ValueError(
                f"total_score 内部不一致：total={self.total_score} vs sum={s}"
            )
        return self


class TraitEvidence(BaseModel):
    """essay 级 decision evidence（论文 §5 explainability metrics 用）"""
    model_config = ConfigDict(extra="ignore")

    trait: TraitKey
    observed_level: Literal["LOW", "MEDIUM", "HIGH"]
    rubric_clause: str
    essay_snippet: str = Field(..., min_length=2)
    impact: Literal["positive", "negative", "neutral"] = "neutral"
