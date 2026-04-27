"""
统一的问答数据结构定义
- QATurn：单轮问答的标准 dataclass，避免各 agent / coordinator 之间字段名漂移
- get_score / get_question_type：从 dict 形态的 qa 中安全提取常用字段（兼容历史字段名）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


SCORE_DETAILS_KEY = "score_details"
QUESTION_TYPE_KEY = "question_type"
LEGACY_QUESTION_TYPE_KEY = "type"


@dataclass
class QATurn:
    """单轮问答 — 系统内 qa_history 的标准实体"""

    question: str
    answer: str
    question_type: str = "general"
    difficulty: str = "medium"
    question_data: Optional[Dict[str, Any]] = None
    score_details: Optional[Dict[str, Any]] = None
    security_check: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def score(self) -> float:
        if self.score_details and isinstance(self.score_details, dict):
            return float(self.score_details.get("score", 0) or 0)
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            QUESTION_TYPE_KEY: self.question_type,
            "difficulty": self.difficulty,
            "question_data": self.question_data,
            SCORE_DETAILS_KEY: self.score_details,
            "security_check": self.security_check,
            "timestamp": self.timestamp,
        }


def get_score(qa: Optional[Dict[str, Any]]) -> float:
    """从 qa dict 中安全提取分数（先看 score_details.score，再回退到顶层 score）"""
    if not qa:
        return 0.0
    details = qa.get(SCORE_DETAILS_KEY)
    if isinstance(details, dict):
        val = details.get("score")
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return 0.0
    legacy = qa.get("score")
    try:
        return float(legacy) if legacy is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def get_question_type(qa: Optional[Dict[str, Any]]) -> str:
    """从 qa dict 中安全提取题型（兼容旧字段 'type'）"""
    if not qa:
        return "general"
    return (
        qa.get(QUESTION_TYPE_KEY)
        or qa.get(LEGACY_QUESTION_TYPE_KEY)
        or "general"
    )
