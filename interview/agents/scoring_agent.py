"""
ScoringAgent — async + structured output (S1 + S2)

- aprocess() 主入口，内部调用 ainvoke_structured(schema=ScoringOutput)
- 0 分契约（无有效解答）由 schema (ge=0) 与 system prompt 保证
- 完全删除手写 JSON 修复路径，仅在 ValidationError 时走 fallback
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage

from .base_agent import BaseAgent
from .qa_models import get_score
from .schemas import ScoringBreakdown, ScoringOutput


class ScoringAgent(BaseAgent):
    """评分智能体 - 5 维度结构化输出"""

    prompt_name = "scoring_agent"
    output_schema = ScoringOutput

    def __init__(self, model):
        super().__init__(model, "ScoringAgent")
        self.logger = logging.getLogger("interview.agents.scoring_agent")

    # ------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------

    async def aprocess(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步评分。
        input_data: { question, answer, question_type, difficulty, [resume_data ignored] }
        return: dict 形式的 ScoringOutput（保持与旧 API 兼容）
        """
        question = input_data.get("question", "")
        answer = input_data.get("answer", "")
        question_type = input_data.get("question_type", "general")
        difficulty = input_data.get("difficulty", "medium")

        human_text = self.prompt.format_human(
            question_type=question_type,
            difficulty=difficulty,
            question=question,
            answer=answer,
        )

        try:
            result: ScoringOutput = await self.ainvoke_structured(human_text)
            data = result.model_dump(mode="json")
            # 字母等级用 schema 已带，但 LLM 可能给错；兜底重新计算
            if not data.get("letter") or data["letter"] not in ("A", "B", "C", "D"):
                data["letter"] = self._score_to_letter(data.get("score", 5))
            return data

        except Exception as e:
            self.logger.error(f"ScoringAgent 结构化输出失败，使用降级评分: {e}")
            return self._fallback_scoring(question_type, difficulty)

    # ------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------

    def _fallback_scoring(self, question_type: str, difficulty: str) -> Dict[str, Any]:
        """LLM 完全失败时的兜底评分（中位数 5 分，标记低 confidence）"""
        return {
            "score": 5,
            "letter": "C",
            "breakdown": {
                "math_logic": 2,
                "reasoning_rigor": 1,
                "communication": 1,
                "collaboration": 0,
                "potential": 1,
            },
            "reasoning": f"LLM 调用异常，使用降级评分（{question_type} / {difficulty}）",
            "strengths": [],
            "weaknesses": [],
            "suggestions": [],
        }

    def _score_to_letter(self, score: int) -> str:
        """根据数值分映射字母等级（与 system prompt 保持一致）"""
        if score >= 9:
            return "A"
        elif score >= 7:
            return "B"
        elif score >= 5:
            return "C"
        else:
            return "D"

    def evaluate_interview_readiness(
        self, qa_history: List[Dict[str, Any]], min_questions: int = 4
    ) -> Dict[str, Any]:
        """评估是否有足够信息做出面试决定（不变，保留同步签名）"""
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
