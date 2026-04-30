"""
Pydantic Schemas — 所有 Agent 的结构化输出契约（S2）

通过 model.with_structured_output(Schema) 强约束 LLM 输出，
彻底替代手写 _fix_common_json_issues + json.loads + 字段补全的脆弱方案。

设计原则：
- 字段名与原 dict 输出 1:1 兼容，前端/数据库可平滑过渡
- 使用 Literal / Field(ge=, le=) 在 schema 层就校验范围
- 全部包含 model_config = ConfigDict(extra="ignore") 以容忍 LLM 多输出字段
"""

from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


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
# ScoringAgent 输出
# ============================================================

class ScoringBreakdown(BaseModel):
    model_config = ConfigDict(extra="ignore")

    math_logic: int = Field(..., ge=0, le=4, description="数学/逻辑基础 0-4")
    reasoning_rigor: int = Field(..., ge=0, le=2, description="推理严谨性 0-2")
    communication: int = Field(..., ge=0, le=2, description="表达与沟通 0-2")
    collaboration: int = Field(..., ge=0, le=1, description="合作与社交 0-1")
    potential: int = Field(..., ge=0, le=1, description="成长潜力 0-1")


class ScoringOutput(BaseModel):
    """评分智能体输出契约"""
    model_config = ConfigDict(extra="ignore")

    score: int = Field(..., ge=0, le=10, description="总分 0-10，无有效解答给 0")
    letter: Literal["A", "B", "C", "D"] = Field(default="C")
    breakdown: ScoringBreakdown
    reasoning: str = Field(default="", description="评分理由")
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


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
# SummaryAgent 输出
# ============================================================

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
    """总结智能体输出契约"""
    model_config = ConfigDict(extra="ignore")

    final_grade: Literal["A", "B", "C", "D"] = Field(default="C")
    final_decision: FinalDecision = Field(default=FinalDecision.conditional)
    overall_score: float = Field(..., ge=0, le=10)
    summary: str = Field(default="")
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    recommendations: Recommendations = Field(default_factory=Recommendations)
    confidence_level: Literal["high", "medium", "low"] = Field(default="medium")
    detailed_analysis: DetailedAnalysis = Field(default_factory=DetailedAnalysis)


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
