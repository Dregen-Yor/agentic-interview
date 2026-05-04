"""
QuestionVerifier — CoVe (Chain-of-Verification) factor+revise 变种 (W3.2)

论文锚点：
- Dhuliawala 2024, arXiv:2309.11495 — Plan & Execute 风格的题目校验
  - Plan: 列出 N 个独立验证问题
  - Answer independently (factor): 每个验证问题独立调用 LLM，避免 cross-bias
  - Final: 不一致 → revise

设计：
- 5 个验证轴（length / type_quota / resume_anchor / no_repeat / difficulty_match）
- 同步规则验证（length / type_quota）：纯代码判断，不消耗 LLM
- LLM 验证（resume_anchor / no_repeat / difficulty_match）：每轴一次独立调用
- factor: asyncio.gather 并行
- factor+revise: averify() 返回 violations 后，由 next_question_node 触发 revise

不实现 yes/no 验证（论文证明 yes/no 偏差大，开放式回答更准）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from .base_agent import BaseAgent
from .cache import cached_system_message
from .qa_models import get_question_type
from .schemas import QuestionVerificationOutput, VerificationCheck


# 题型上限（与 question_generator.py 保持一致：每种题型最多 2 题）
_TYPE_QUOTA = 2

# 题目长度上限（与 prompt 中 60 字一致）
_QUESTION_MAX_LEN = 80  # 给 LLM 一些余量，但超过 80 就 fail


class QuestionVerifier(BaseAgent):
    """CoVe verifier — Plan & Execute 风格的题目校验"""

    prompt_name = "question_verifier"
    output_schema = VerificationCheck  # 单轴 schema

    def __init__(self, model: ChatOpenAI):
        super().__init__(model, "QuestionVerifier")
        self.logger = logging.getLogger("interview.agents.question_verifier")

    # ------------------------------------------------------------
    # BaseAgent 抽象接口适配（dict in/out）
    # ------------------------------------------------------------

    async def aprocess(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """BaseAgent 兼容入口 — 推荐直接调用 averify() 拿 typed 输出"""
        result = await self.averify(
            candidate_question=input_data.get("candidate_question") or {},
            parsed_profile=input_data.get("parsed_profile"),
            qa_history=input_data.get("qa_history"),
        )
        return result.model_dump(mode="json")

    # ------------------------------------------------------------
    # 主入口（typed）
    # ------------------------------------------------------------

    async def averify(
        self,
        candidate_question: Dict[str, Any],
        parsed_profile: Optional[Dict[str, Any]] = None,
        qa_history: Optional[List[Dict[str, Any]]] = None,
    ) -> QuestionVerificationOutput:
        """
        averify(candidate_question) → QuestionVerificationOutput

        - 同步规则：length / type_quota
        - LLM 异步：resume_anchor / no_repeat / difficulty_match
        """
        qa_history = qa_history or []

        # Plan: 5 个独立验证（前 2 个同步规则，后 3 个 LLM）
        sync_checks = [
            self._verify_length(candidate_question),
            self._verify_type_quota(candidate_question, qa_history),
        ]

        # LLM 验证轴（factor: 并行独立调用）
        llm_axes = ["resume_anchor", "no_repeat", "difficulty_match"]
        recent_qa_text = self._format_recent_qa(qa_history, n=3)
        avg_score = self._compute_avg_score(qa_history)

        candidate_q_json = self._safe_json(candidate_question)
        parsed_profile_json = self._safe_json(parsed_profile or {})

        llm_tasks = [
            self._verify_with_llm(
                axis=axis,
                candidate_q_json=candidate_q_json,
                parsed_profile_json=parsed_profile_json,
                recent_qa=recent_qa_text,
                current_score=avg_score,
            )
            for axis in llm_axes
        ]
        llm_checks = await asyncio.gather(*llm_tasks, return_exceptions=True)

        # Answer independently → 收集所有 check
        all_checks: List[VerificationCheck] = list(sync_checks)
        for axis, c in zip(llm_axes, llm_checks):
            if isinstance(c, BaseException):
                self.logger.warning(f"[CoVe] LLM 验证 {axis} 异常（视为通过，soft-fail）: {c}")
                all_checks.append(
                    VerificationCheck(
                        name=axis, passed=True,
                        message=f"(verifier soft-fail: {type(c).__name__})",
                    )
                )
            elif isinstance(c, VerificationCheck):
                all_checks.append(c)
            else:
                all_checks.append(
                    VerificationCheck(name=axis, passed=True, message="(unexpected verifier return)")
                )

        violations = [c.message for c in all_checks if not c.passed]
        is_valid = len(violations) == 0
        suggested = self._build_revision_hint(all_checks)

        return QuestionVerificationOutput(
            is_valid=is_valid,
            checks=all_checks,
            violations=violations,
            suggested_revision=suggested,
        )

    # ------------------------------------------------------------
    # 同步规则验证（不消耗 LLM）
    # ------------------------------------------------------------

    def _verify_length(self, candidate_q: Dict[str, Any]) -> VerificationCheck:
        question_text = candidate_q.get("question", "") if isinstance(candidate_q, dict) else str(candidate_q)
        if not question_text:
            return VerificationCheck(name="length", passed=False, message="题目为空")
        if len(question_text) > _QUESTION_MAX_LEN:
            return VerificationCheck(
                name="length",
                passed=False,
                message=f"题目过长（{len(question_text)}字 > {_QUESTION_MAX_LEN}字上限）",
            )
        return VerificationCheck(name="length", passed=True, message="")

    def _verify_type_quota(
        self,
        candidate_q: Dict[str, Any],
        qa_history: List[Dict[str, Any]],
    ) -> VerificationCheck:
        candidate_type = candidate_q.get("type") if isinstance(candidate_q, dict) else None
        if not candidate_type or candidate_type in ("general", "opening"):
            return VerificationCheck(name="type_quota", passed=True, message="")

        # 统计历史题型
        counts: Dict[str, int] = {}
        for qa in qa_history:
            t = get_question_type(qa)
            if t and t not in ("general", "opening"):
                counts[t] = counts.get(t, 0) + 1

        used = counts.get(candidate_type, 0)
        if used >= _TYPE_QUOTA:
            return VerificationCheck(
                name="type_quota",
                passed=False,
                message=f"题型 {candidate_type} 已使用 {used} 次（上限 {_TYPE_QUOTA}），应换其他类型",
            )
        return VerificationCheck(name="type_quota", passed=True, message="")

    # ------------------------------------------------------------
    # LLM 验证轴（factor: 每轴独立 LLM 调用）
    # ------------------------------------------------------------

    async def _verify_with_llm(
        self,
        axis: str,
        candidate_q_json: str,
        parsed_profile_json: str,
        recent_qa: str,
        current_score: float,
    ) -> VerificationCheck:
        human_text = self.prompt.format_human(
            check_name=axis,
            candidate_question_json=candidate_q_json,
            parsed_profile_json=parsed_profile_json,
            recent_qa=recent_qa,
            current_score=f"{current_score:.1f}",
        )
        messages = [
            cached_system_message(self.get_system_prompt()),
            HumanMessage(content=human_text),
        ]
        # 用 BaseAgent 预绑定的 _structured_model
        result: VerificationCheck = await self._structured_model.ainvoke(messages)
        # 强制 name 与请求一致
        if result.name != axis:
            result = result.model_copy(update={"name": axis})
        return result

    # ------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------

    @staticmethod
    def _format_recent_qa(qa_history: List[Dict[str, Any]], n: int = 3) -> str:
        if not qa_history:
            return "(无历史)"
        lines = []
        for qa in qa_history[-n:]:
            q = (qa.get("question") or "")[:200]
            a = (qa.get("answer") or "")[:200]
            t = get_question_type(qa)
            lines.append(f"[{t}] Q: {q}\n   A: {a}")
        return "\n".join(lines)

    @staticmethod
    def _compute_avg_score(qa_history: List[Dict[str, Any]]) -> float:
        scores = []
        for qa in qa_history:
            sd = qa.get("score_details") or {}
            s = sd.get("score")
            if isinstance(s, (int, float)) and s > 0:
                scores.append(float(s))
        return sum(scores) / len(scores) if scores else 0.0

    @staticmethod
    def _safe_json(obj: Any) -> str:
        try:
            return json.dumps(obj, ensure_ascii=False)[:1500]
        except Exception:
            return str(obj)[:1500]

    @staticmethod
    def _build_revision_hint(checks: List[VerificationCheck]) -> str:
        violations = [c for c in checks if not c.passed]
        if not violations:
            return ""
        return "请修订题目使其满足以下要求：" + "；".join(c.message for c in violations)
