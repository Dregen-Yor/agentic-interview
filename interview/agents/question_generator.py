"""
QuestionGeneratorAgent — async + structured output + tool calling (S1 + S2)

- aprocess() 为主入口
- structured output 用 QuestionOutput
- 工具调用循环改为 async（abind_tools / ainvoke）
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from interview.rubrics import RUBRIC_DIMENSIONS
from interview.tools.rag_tools import RetrievalSystem, rag_search as rag_search_tool

from .base_agent import BaseAgent
from .qa_models import get_question_type
from .schemas import QuestionOutput


class QuestionGeneratorAgent(BaseAgent):
    """问题生成智能体 - 结构化输出 + RAG 工具调用"""

    prompt_name = "question_generator"
    output_schema = QuestionOutput

    def __init__(self, model, retrieval_system: RetrievalSystem):
        super().__init__(model, "QuestionGenerator")
        self.retrieval_system = retrieval_system
        self.logger = logging.getLogger("interview.agents.question_generator")

    # ------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------

    async def aprocess(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步出题。
        input_data: {
            interview_stage, previous_qa, current_score, target_type,
            parsed_profile, similar_cases_context
        }
        """
        try:
            human_text = self._build_human_prompt(input_data)
        except Exception as e:
            self.logger.error(f"构造 prompt 失败: {e}")
            return self._fallback_question()

        # 出题工具调用循环（如需要 RAG），最后一步用 structured output
        try:
            # 第一步：让 LLM 决定是否需要 rag_search
            tool_results = await self._maybe_call_rag(human_text)
            if tool_results:
                augmented_text = (
                    human_text + "\n\n=== 知识库检索补充 ===\n" + tool_results
                )
            else:
                augmented_text = human_text

            # 第二步：用 structured output 生成最终题目
            result: QuestionOutput = await self.ainvoke_structured(augmented_text)
            return result.model_dump(mode="json")

        except Exception as e:
            self.logger.error(f"QuestionGenerator 异常: {e}")
            return self._fallback_question()

    # ------------------------------------------------------------
    # Prompt 构造
    # ------------------------------------------------------------

    def _build_human_prompt(self, input_data: Dict[str, Any]) -> str:
        """组装 human message 内容（不含 system，由 BaseAgent 统一加 cached system）"""
        interview_stage = input_data.get("interview_stage", "technical")
        previous_qa = input_data.get("previous_qa", [])
        current_score = input_data.get("current_score", 0)
        target_type = input_data.get("target_type")
        parsed_profile = input_data.get("parsed_profile")
        similar_cases = input_data.get("similar_cases_context")

        parts: List[str] = []

        # Memento 历史案例
        if similar_cases:
            parts.append(f"以下是来自其他类似面试的历史参考案例：\n{similar_cases}")
            parts.append("这些案例仅供参考，请勿直接复制题目，需根据当前候选人情况调整。")

        # 简历结构化 profile
        if parsed_profile and parsed_profile.get("items"):
            parts.append(self._format_profile_for_prompt(parsed_profile))
            weak_dims = parsed_profile.get("weakest_dimensions", [])
            if weak_dims:
                dim_names = [
                    RUBRIC_DIMENSIONS[d]["name"] for d in weak_dims if d in RUBRIC_DIMENSIONS
                ]
                if dim_names:
                    parts.append(
                        f"The candidate shows weaker signals in: {', '.join(dim_names)}. "
                        f"Prioritize questions that can elicit evidence for these dimensions."
                    )
            items_map = {item["id"]: item for item in parsed_profile["items"]}
            for pid in parsed_profile.get("suggested_probe_items", []):
                item = items_map.get(pid)
                if item:
                    gaps = ", ".join(item.get("knowledge_gaps", [])[:3]) or "none identified"
                    parts.append(f"Suggested probe: '{item['summary']}' (gaps: {gaps})")

        # 阶段相关引导
        if interview_stage == "opening":
            parts.append(
                "This is the opening stage of the interview (5-6 rounds total). Generate an efficient "
                "opening question that probes background and reflects mathematical-logical foundation. "
                "It should be friendly but with differentiation to quickly understand the candidate's "
                "thinking ability."
            )
        elif interview_stage == "technical":
            desired_type = target_type or "math_logic"

            if desired_type == "math_logic":
                difficulty_hint = "easy to medium" if current_score < 6 else "medium to hard"
                parts.append(
                    "Please generate a math_logic type question, emphasizing the chain of reasoning and "
                    "verifiability."
                )
                parts.append(
                    "Prioritize abstract modeling, intuition in sets/graphs/number theory/probability, "
                    "or algorithm intuition that does not rely on programming."
                )
                parts.append("Avoid memory-based questions; allow multi-step reasoning.")
                parts.append(
                    f"Difficulty hint: {difficulty_hint}. You may decide to call rag_search if needed."
                )
                parts.append("Set type to math_logic and explain differentiation source in reasoning.")

            elif desired_type == "technical":
                parts.append(
                    "Design a core technical question around content the candidate mentioned in "
                    "self-statement/resume, getting at the essence of their understanding."
                )
                parts.append(
                    "Ask for principle explanations, comparisons, boundary analysis, or complexity "
                    "assessment."
                )
                parts.append("Set type to technical.")

            elif desired_type == "behavioral":
                parts.append(
                    "Generate a behavioral interview question on cooperation, conflict resolution, "
                    "reflection, improvement. Should prompt STAR-style answer."
                )
                parts.append("Set type to behavioral.")

            else:
                parts.append(
                    "Generate an experience review question requiring abstraction of transferable "
                    "methodologies. Guide them to provide key metrics, lessons, and next-step strategies."
                )
                parts.append("Set type to experience.")

        elif interview_stage == "behavioral":
            parts.append(
                "Generate an efficient behavioral interview question to assess basic qualities and "
                "interpersonal skills (cooperation, listening, conflict resolution, respect, clarity). "
                "Relevant to campus research/team project scenarios; reflect multiple dimensions."
            )

        # 历史问答 + 类型上限约束
        if previous_qa:
            qa_history = "\n".join(
                [
                    f"Q: {qa.get('question', '')}\nA: {qa.get('answer', '')}"
                    for qa in previous_qa[-3:]
                ]
            )
            parts.append(f"Previous Q&A record:\n{qa_history}")
            parts.append(f"Current average score: {current_score}/10")
            parts.append(
                f"This is round {len(previous_qa)+1} (out of 5-6 total). Generate efficient targeted "
                f"question."
            )

            type_counts = self._count_question_types(previous_qa)
            if type_counts:
                reached_limit_types = [t for t, c in type_counts.items() if c >= 2]
                parts.append(
                    f"Type usage statistics (cumulative): {json.dumps(type_counts, ensure_ascii=False)}"
                )
                if reached_limit_types:
                    blocked = ", ".join(reached_limit_types)
                    parts.append(
                        f"The following types reached the 2-round limit: {blocked}. The new question "
                        f"MUST avoid these types."
                    )
            parts.append(
                "Strictly adhere to type limits and diversity rules: each type at most twice in the "
                "entire process."
            )

        return "\n\n".join(parts) if parts else "Please generate the next interview question."

    # ------------------------------------------------------------
    # 工具调用层（async）
    # ------------------------------------------------------------

    async def _maybe_call_rag(self, human_text: str) -> str:
        """
        让 LLM 自主决定是否调用 rag_search。最多 2 次循环（足以覆盖典型场景，避免无限调用）。
        返回拼接的工具结果文本，供后续 structured output 阶段参考。
        """
        try:
            tools = [rag_search_tool]
            model_with_tools = self.model.bind_tools(tools)

            from langchain_core.messages import SystemMessage
            from .cache import cached_system_message

            history = [
                cached_system_message(self.get_system_prompt()),
                HumanMessage(content=human_text),
            ]

            collected_results: List[str] = []
            for _ in range(2):
                ai_msg = await model_with_tools.ainvoke(history)
                tool_calls = getattr(ai_msg, "tool_calls", None)
                if not tool_calls:
                    return "\n\n".join(collected_results)

                history.append(ai_msg)
                for tool_call in tool_calls:
                    tool_name = tool_call.get("name") if isinstance(tool_call, dict) else tool_call.name
                    tool_args = tool_call.get("args", {}) if isinstance(tool_call, dict) else tool_call.args
                    tool_id = tool_call.get("id") if isinstance(tool_call, dict) else tool_call.id

                    if tool_name == "rag_search":
                        try:
                            # rag_search 是同步 LangChain @tool；在 thread 中跑避免阻塞 event loop
                            import asyncio
                            result = await asyncio.to_thread(
                                lambda: rag_search_tool.invoke(tool_args)
                                if hasattr(rag_search_tool, "invoke")
                                else rag_search_tool(**tool_args)
                            )
                        except Exception as e:
                            result = f"Error executing RAG search: {e}"
                    else:
                        result = f"Unrecognized tool: {tool_name}"

                    collected_results.append(str(result))
                    history.append(
                        ToolMessage(content=str(result), name=tool_name, tool_call_id=tool_id)
                    )

            return "\n\n".join(collected_results)
        except Exception as e:
            self.logger.warning(f"工具调用循环失败，跳过 RAG: {e}")
            return ""

    # ------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------

    def _fallback_question(self) -> Dict[str, Any]:
        return {
            "question": "请简单介绍你最近接触过的一个数学或逻辑问题，及你的思考过程。",
            "type": "general",
            "difficulty": "easy",
            "reasoning": "Default fallback question due to error",
        }

    def _format_profile_for_prompt(self, profile: Dict[str, Any]) -> str:
        """将 structured_profile 格式化为紧凑的 prompt 文本"""
        lines = ["=== Candidate Resume Profile ==="]
        for item in profile.get("items", []):
            signals = item.get("dimension_signals", {})
            active = [f"{k}={v}" for k, v in signals.items() if v != "NO_SIGNAL"]
            lines.append(
                f"- [{item.get('id')}] ({item.get('category', 'unknown')}) "
                f"{item.get('summary', '')} | involvement={item.get('inferred_involvement', '?')} | "
                f"signals: {', '.join(active) if active else 'none'}"
            )

        agg = profile.get("aggregate_signals", {})
        if agg:
            agg_str = ", ".join(f"{k}={v}" for k, v in agg.items())
            lines.append(f"Aggregate signals: {agg_str}")

        return "\n".join(lines)

    def _count_question_types(self, previous_qa: List[Dict[str, Any]]) -> Dict[str, int]:
        """统计历史问答中各题型出现次数"""
        counts: Dict[str, int] = {}
        if not previous_qa:
            return counts
        for qa in previous_qa:
            qa_type = get_question_type(qa)
            if not qa_type or qa_type == "general":
                continue
            counts[qa_type] = counts.get(qa_type, 0) + 1
        return counts
