"""
Pydantic Schemas — 所有 Agent 的结构化输出契约（v4 - 单题整体评分）

v4 改动（2026-05-07，单分制重构）：
- 删除 `DimensionScore` / `DimensionKey` / `DIMENSION_MAX_SCORE` / `DetailedAnalysis`
- `ScoringOutput` 改为单一 0-10 总分 + evidence_quote + question_focus + ensemble 元数据
- `DecisionEvidence` 重写：去 dimension/observed_level，加 question_focus / rationale
- `SummaryOutput` 删除 `detailed_analysis`，改为单字段 `overall_analysis: str`
- 评分仍然是 RULERS 证据锚定 + CISC 双模型 ensemble，但维度独立打分被废弃

设计原则：
- LLM 只看「题目考察方向 + 答案正确性」给一个总分；不再分 5 维度
- evidence_quote 仍是必填，由 ScoringAgent fuzzy match 校验，不通过时降 confidence（不 reject）
- agreement 公式从「level 投票一致率」改为「1 - (max - min) / 10」
- 旧 v3 数据中的 dimensions / detailed_analysis 字段在新 schema 中被忽略
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
# ScoringAgent v4 — 单题整体评分（保留 evidence + ensemble）
# ============================================================

class SingleScoreCandidate(BaseModel):
    """单模型一次评分输出（ScoringAgent 内部使用，N 模型并行后聚合为 ScoringOutput）

    LLM 通过 with_structured_output 直接产出此 schema。
    """
    model_config = ConfigDict(extra="ignore")

    score: int = Field(..., ge=0, le=10, description="总分 0-10")
    evidence_quote: str = Field(
        ...,
        min_length=2,
        description="候选人答案中支撑此评分的原文片段（fuzzy match 校验在 answer 内）",
    )
    question_focus: str = Field(
        ...,
        min_length=2,
        description="题目考察方向（自由短语，如「递归边界条件」「DP 状态转移」）",
    )
    confidence: Literal["high", "medium", "low"] = Field(
        default="medium",
        description="LLM 自报置信度；CISC 加权聚合时使用",
    )
    reasoning: str = Field(default="", description="为何给此分；1-2 句中文")
    model_name: Optional[str] = Field(default=None, description="ensemble 时记录哪个模型")


class ScoringOutput(BaseModel):
    """聚合评分输出 — N 模型 CISC 加权聚合后的最终单题评分

    论文锚点：
    - RULERS (arXiv:2601.08654): evidence-anchored decoding，必须给 evidence_quote
    - CISC (arXiv:2502.06233): confidence-weighted ensemble，agreement < 阈值触发 review
    - LLMs Cannot Self-Correct (ICLR 2024): 多模型 ensemble 才有效
    """
    model_config = ConfigDict(extra="ignore")

    score: int = Field(..., ge=0, le=10, description="单题总分（CISC 加权聚合后）")
    evidence_quote: str = Field(
        ...,
        min_length=2,
        description="候选人答案中支撑此评分的原文片段",
    )
    question_focus: str = Field(
        ...,
        description="题目考察方向（自由短语）",
    )
    agreement: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="多模型一致性 = 1 - (max_score - min_score) / 10；单模型时 = 1.0",
    )
    confidence_level: Literal["high", "medium", "low"] = Field(default="medium")
    requires_human_review: bool = Field(default=False)
    fallback_used: bool = Field(default=False, description="是否触发了 fallback（LLM 全部失败时）")
    reasoning: str = Field(default="")
    model_name: Optional[str] = Field(
        default=None,
        description="ensemble 来源标记，单模型为 model_name，多模型为 ensemble(N)",
    )


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
# SummaryAgent v4 — RULERS evidence triple + BAS selective prediction
# ============================================================

class DecisionEvidence(BaseModel):
    """SummaryAgent 决策证据三元组 — RULERS-style（v4 单分制版本）

    每条证据指向一个具体 turn，引用题目考察方向 + 答案片段，并附一句话说明
    为何此证据支持最终决策，便于招生老师追溯。
    """
    model_config = ConfigDict(extra="ignore")

    turn_index: int = Field(..., ge=0, description="对应 qa_history 中的轮次（0-indexed）")
    question_focus: str = Field(
        ...,
        description="该轮题目考察方向（来自 score_details.question_focus）",
    )
    answer_snippet: str = Field(
        ..., min_length=2, description="候选人答案的关键片段（应是 answer 子串）"
    )
    rationale: str = Field(
        ...,
        min_length=2,
        description="一句话说明为何此证据支撑最终决策（中文）",
    )
    impact: Literal["positive", "negative", "neutral"] = Field(
        default="neutral", description="该证据对最终决策的影响方向"
    )


class Recommendations(BaseModel):
    model_config = ConfigDict(extra="ignore")

    for_candidate: str = Field(default="")
    for_program: str = Field(default="")


class SummaryOutput(BaseModel):
    """新版 SummaryOutput — 单分制 + 强制证据链 + boundary case 显式标记

    论文锚点：
    - RULERS (arXiv:2601.08654): evidence-anchored decoding，决策必须可审计
    - BAS (arXiv:2604.03216): selective prediction，边界情况建议 abstain（人工复核）
    """
    model_config = ConfigDict(extra="ignore")

    final_grade: Literal["A", "B", "C", "D"] = Field(default="C")
    final_decision: FinalDecision = Field(default=FinalDecision.conditional)
    overall_score: float = Field(..., ge=0, le=10)
    summary: str = Field(default="")
    overall_analysis: str = Field(
        default="",
        description="整体表现分析（替代 v3 的 detailed_analysis 5 字段）",
    )
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    recommendations: Recommendations = Field(default_factory=Recommendations)

    # ---------- v3 保留：证据链 + boundary case ----------
    decision_evidence: List[DecisionEvidence] = Field(
        ...,
        min_length=3,
        description="必须给出至少 3 条证据三元组",
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
    """简历解析阶段的 5 维度信号 — 仅出题端使用，与评分链路解耦

    注：v4 评分链路已删除 5 维度，但 ResumeParser 仍按维度抽取信号供
    QuestionGeneratorAgent 在弱维度上多出题（见 question_generator.py 引用 RUBRIC_DIMENSIONS）。
    """
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
