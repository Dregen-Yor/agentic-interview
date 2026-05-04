"""
Pydantic Schemas — 所有 Agent 的结构化输出契约（v3 - W1 论文落地）

v3 改动（2026-05-03，论文驱动重构）：
- 引入 `DimensionScore`：MTS (arXiv:2404.04941) 单维度独立评分契约
- 引入 `DecisionEvidence`：RULERS (arXiv:2601.08654) evidence-anchored 三元组
- `ScoringOutput` v3：总分由公式聚合（score = sum(dim.score)），不再让 LLM 自由输出
  + `model_validator` 强制内部一致性（score 必须等于维度求和；5 维度齐全）
  + 新增 `agreement` / `confidence_level` / `requires_human_review` / `fallback_used`（CISC arXiv:2502.06233）
- `SummaryOutput` v3：必填 `decision_evidence >= 3`；新增 `boundary_case` / `requires_human_review` / `decision_confidence` / `abstain_reason`（BAS arXiv:2604.03216 selective prediction）

设计原则：
- 维度上限由 `DimensionScore.check_score_bound` 在 schema 层校验（math_logic 0-4, reasoning_rigor 0-2, ...）
- `evidence_quote` 仅约束最小长度；是否出现在 answer 中由 ScoringAgent 在 fuzzy match 阶段降 confidence 而非拒绝
- 完全删除 v2 的 `ScoringBreakdown / letter / strengths / weaknesses / suggestions` 字段（破坏性重构，前端同步更新）
- v2 删除的字段已通过 `qa_models.get_score()` 在读旧数据时兼容
"""

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ============================================================
# 通用枚举
# ============================================================

class QuestionType(str, Enum):
    math_logic = "math_logic"
    technical = "technical"
    behavioral = "behavioral"
    experience = "experience"
    opening = "opening"
    general = "general"


class Difficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class SuggestedAction(str, Enum):
    cont = "continue"
    warning = "warning"
    block = "block"


class FinalDecision(str, Enum):
    accept = "accept"
    reject = "reject"
    conditional = "conditional"


class DimensionSignal(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    NO_SIGNAL = "NO_SIGNAL"


class Involvement(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# 5 维度统一 key（ScoringAgent / SummaryAgent / ResumeParser 共用）
DimensionKey = Literal[
    "math_logic",
    "reasoning_rigor",
    "communication",
    "collaboration",
    "growth_potential",
]

# 5 维度的分数上限（与 interview/rubrics.py::RUBRIC_DIMENSIONS 的 weight 字段对齐）
DIMENSION_MAX_SCORE = {
    "math_logic": 4,
    "reasoning_rigor": 2,
    "communication": 2,
    "collaboration": 1,
    "growth_potential": 1,
}


# ============================================================
# QuestionGeneratorAgent 输出
# ============================================================

class QuestionOutput(BaseModel):
    """出题智能体输出契约"""
    model_config = ConfigDict(extra="ignore")

    question: str = Field(..., description="题目正文（中文，含必要定义解释）")
    type: QuestionType = Field(default=QuestionType.general, description="题目类型")
    difficulty: Difficulty = Field(default=Difficulty.medium, description="难度")
    reasoning: str = Field(default="", description="出题理由：锚定哪个简历项 / 测哪个维度")


# ============================================================
# QuestionVerifier 输出（W3.2 CoVe）
# ============================================================

class VerificationCheck(BaseModel):
    """单条 CoVe 验证结果"""
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="验证项名称，如 length/type_quota/resume_anchor 等")
    passed: bool = Field(...)
    message: str = Field(default="", description="未通过时的失败原因")


class QuestionVerificationOutput(BaseModel):
    """CoVe verifier 聚合输出 (Dhuliawala 2024, arXiv:2309.11495)"""
    model_config = ConfigDict(extra="ignore")

    is_valid: bool = Field(...)
    checks: List[VerificationCheck] = Field(default_factory=list)
    violations: List[str] = Field(default_factory=list)
    suggested_revision: str = Field(default="", description="若 is_valid=False，给出修订指引")


# ============================================================
# ScoringAgent v3 — MTS + RULERS 单维度 + ensemble
# ============================================================

class DimensionScore(BaseModel):
    """单维度评分 — RULERS evidence-anchored + MTS 单 prompt 单维度

    论文锚点：
    - MTS (arXiv:2404.04941): 每维度独立 prompt，retrieve quotes 作为证据
    - RULERS (arXiv:2601.08654): unverifiable reasoning 是失败模式之一，必须 evidence-anchored
    """
    model_config = ConfigDict(extra="ignore")

    dimension: Literal[
        "math_logic",
        "reasoning_rigor",
        "communication",
        "collaboration",
        "growth_potential",
    ] = Field(..., description="5 维度之一")
    level: Literal["LOW", "MEDIUM", "HIGH"] = Field(..., description="基于 rubric 的等级判断")
    score: int = Field(
        ...,
        ge=0,
        description="该维度得分；上限由 DIMENSION_MAX_SCORE 在 model_validator 中校验",
    )
    evidence_quote: str = Field(
        ...,
        min_length=2,
        description="候选人答案中支撑此判断的原文片段（应在 answer 内，由 ScoringAgent fuzzy match 校验）",
    )
    rubric_clause: str = Field(
        ...,
        description="rubric 中 LOW/MEDIUM/HIGH 的对应描述文字（来自 RUBRIC_DIMENSIONS）",
    )
    confidence: Literal["high", "medium", "low"] = Field(
        default="medium",
        description="LLM 自报置信度；CISC 加权聚合时使用",
    )
    reasoning: str = Field(default="", description="为何给出该 level / score")
    model_name: Optional[str] = Field(
        default=None, description="ensemble 时记录哪个模型给的分（如 gpt-5-mini / gemini-2.5-flash）"
    )

    @model_validator(mode="after")
    def check_score_bound(self):
        cap = DIMENSION_MAX_SCORE[self.dimension]
        if self.score > cap:
            raise ValueError(
                f"{self.dimension} 分数 {self.score} 超过上限 {cap}（请检查 LLM 输出）"
            )
        return self


class ScoringOutput(BaseModel):
    """聚合评分输出 — 总分由公式聚合，model_validator 强制内部一致性

    论文锚点：
    - CISC (arXiv:2502.06233): confidence-weighted ensemble，agreement < 0.5 触发 review
    - LLMs Cannot Self-Correct (ICLR 2024): 多模型 ensemble 才有效，不要同模型自我批评
    """
    model_config = ConfigDict(extra="ignore")

    score: int = Field(..., ge=0, le=10, description="5 维度 score 求和（公式聚合，不允许 LLM 自由输出）")
    dimensions: List[DimensionScore] = Field(
        ..., min_length=5, max_length=5, description="必须 5 项齐全且 dimension 各异"
    )
    agreement: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="多模型 ensemble 一致性（单模型时 = 1.0）",
    )
    confidence_level: Literal["high", "medium", "low"] = Field(default="medium")
    requires_human_review: bool = Field(default=False)
    fallback_used: bool = Field(default=False, description="是否触发了 fallback（LLM 全部失败时）")
    reasoning: str = Field(default="")

    @model_validator(mode="after")
    def check_consistency(self):
        # 5 维度 key 必须齐全且唯一
        keys = {d.dimension for d in self.dimensions}
        expected = set(DIMENSION_MAX_SCORE.keys())
        if keys != expected:
            missing = expected - keys
            extra = keys - expected
            raise ValueError(
                f"维度 key 不正确（缺失 {missing}，多余 {extra}）；必须恰好 5 项"
            )
        # 总分必须 = 维度求和（强一致性）
        dim_sum = sum(d.score for d in self.dimensions)
        if self.score != dim_sum:
            raise ValueError(
                f"score 内部不一致：score={self.score} 但 dimensions 求和={dim_sum}"
            )
        return self


# ============================================================
# SecurityAgent 输出
# ============================================================

class SecurityOutput(BaseModel):
    """安全检测智能体输出契约"""
    model_config = ConfigDict(extra="ignore")

    is_safe: bool = Field(default=True)
    risk_level: RiskLevel = Field(default=RiskLevel.low)
    detected_issues: List[str] = Field(default_factory=list)
    reasoning: str = Field(default="")
    suggested_action: SuggestedAction = Field(default=SuggestedAction.cont)


# ============================================================
# SummaryAgent v3 — RULERS evidence triple + BAS selective prediction
# ============================================================

class DecisionEvidence(BaseModel):
    """SummaryAgent 决策证据三元组 — RULERS-style

    每条证据指向一个具体 turn，明确该轮在某维度上的表现，并引用 rubric 对应描述。
    招生老师可凭此追溯决策依据，避免「黑盒决策」。
    """
    model_config = ConfigDict(extra="ignore")

    turn_index: int = Field(..., ge=0, description="对应 qa_history 中的轮次（0-indexed）")
    dimension: Literal[
        "math_logic",
        "reasoning_rigor",
        "communication",
        "collaboration",
        "growth_potential",
    ] = Field(..., description="此证据涉及的 rubric 维度")
    observed_level: Literal["LOW", "MEDIUM", "HIGH"] = Field(
        ..., description="该轮该维度的观察等级"
    )
    rubric_clause: str = Field(..., description="rubric 中对应等级的描述文字（不要改写）")
    answer_snippet: str = Field(
        ..., min_length=2, description="候选人答案的关键片段（应是 answer 子串）"
    )
    impact: Literal["positive", "negative", "neutral"] = Field(
        default="neutral", description="该证据对最终决策的影响方向"
    )


class Recommendations(BaseModel):
    model_config = ConfigDict(extra="ignore")

    for_candidate: str = Field(default="")
    for_program: str = Field(default="")


class DetailedAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    math_logic: str = Field(default="")
    reasoning_rigor: str = Field(default="")
    communication: str = Field(default="")
    collaboration: str = Field(default="")
    growth_potential: str = Field(default="")


class SummaryOutput(BaseModel):
    """新版 SummaryOutput — 强制证据链 + boundary case 显式标记

    论文锚点：
    - RULERS (arXiv:2601.08654): evidence-anchored decoding，决策必须可审计
    - BAS (arXiv:2604.03216): selective prediction，边界情况建议 abstain（人工复核）
    """
    model_config = ConfigDict(extra="ignore")

    final_grade: Literal["A", "B", "C", "D"] = Field(default="C")
    final_decision: FinalDecision = Field(default=FinalDecision.conditional)
    overall_score: float = Field(..., ge=0, le=10)
    summary: str = Field(default="")
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    recommendations: Recommendations = Field(default_factory=Recommendations)
    detailed_analysis: DetailedAnalysis = Field(default_factory=DetailedAnalysis)

    # ---------- v3 新增：证据链 + boundary case ----------
    decision_evidence: List[DecisionEvidence] = Field(
        ...,
        min_length=3,
        description="必须给出至少 3 条证据三元组；建议覆盖 ≥ 2 个维度",
    )
    boundary_case: bool = Field(
        default=False,
        description="overall_score 在 [4.5,5.5] ∪ [6.5,7.5] ∪ [8.0,9.0] 时应为 True",
    )
    decision_confidence: Literal["high", "medium", "low"] = Field(default="medium")
    requires_human_review: bool = Field(
        default=False,
        description="boundary_case 或 fallback_used 或 avg(turn.agreement) < 0.6 时应为 True",
    )
    abstain_reason: Optional[str] = Field(
        default=None, description="requires_human_review=True 时填充（说明为何建议人工复核）"
    )


# ============================================================
# ResumeParser 输出
# ============================================================

class DimensionSignals(BaseModel):
    model_config = ConfigDict(extra="ignore")

    math_logic: DimensionSignal = Field(default=DimensionSignal.NO_SIGNAL)
    reasoning_rigor: DimensionSignal = Field(default=DimensionSignal.NO_SIGNAL)
    communication: DimensionSignal = Field(default=DimensionSignal.NO_SIGNAL)
    collaboration: DimensionSignal = Field(default=DimensionSignal.NO_SIGNAL)
    growth_potential: DimensionSignal = Field(default=DimensionSignal.NO_SIGNAL)


class ResumeItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    category: Literal["project", "competition", "coursework", "self_study", "extracurricular"]
    summary: str
    inferred_involvement: Involvement = Field(default=Involvement.MEDIUM)
    inferred_motivation: str = Field(default="")
    knowledge_gaps: List[str] = Field(default_factory=list)
    ksd_possessed: List[str] = Field(default_factory=list)
    dimension_signals: DimensionSignals = Field(default_factory=DimensionSignals)


class AggregateSignals(BaseModel):
    model_config = ConfigDict(extra="ignore")

    math_logic: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    reasoning_rigor: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    communication: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    collaboration: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    growth_potential: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"


class ResumeProfile(BaseModel):
    """简历结构化解析输出契约"""
    model_config = ConfigDict(extra="ignore")

    items: List[ResumeItem] = Field(default_factory=list)
    aggregate_signals: AggregateSignals = Field(default_factory=AggregateSignals)
    weakest_dimensions: List[str] = Field(default_factory=list)
    strongest_dimensions: List[str] = Field(default_factory=list)
    suggested_probe_items: List[str] = Field(default_factory=list)
