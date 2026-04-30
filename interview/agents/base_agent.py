"""
Base Agent — async + structured output 模板（S1 + S2 + S3）

核心改动：
- 新增 ainvoke_structured(): 一站式 build_messages → with_structured_output → ainvoke → 返回 BaseModel/dict
- 旧的 _invoke_model + _fix_common_json_issues 仅作为 fallback 路径保留
- 集成 prompt cache 标记（S3）
- 自动从 YAML 加载 system prompt（S12）
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type, TypeVar

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from .cache import cached_system_message
from .prompts import PromptTemplate, load_prompt


# 模块级正则：兼容旧路径（fallback 路径仍可能用）
_TRAILING_COMMA_OBJ = re.compile(r",\s*}")
_TRAILING_COMMA_ARR = re.compile(r",\s*]")


def fix_common_json_issues(response: str) -> str:
    """
    修复 LLM 输出常见 JSON 格式问题（fallback 路径用，不在主流程中调用）。
    主流程现已使用 with_structured_output 强约束，本函数保留用于兼容旧代码或异常降级。
    """
    if not response:
        return ""

    cleaned = response.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    open_braces = cleaned.count("{")
    close_braces = cleaned.count("}")
    if open_braces > close_braces:
        cleaned += "}" * (open_braces - close_braces)

    cleaned = _TRAILING_COMMA_OBJ.sub("}", cleaned)
    cleaned = _TRAILING_COMMA_ARR.sub("]", cleaned)

    return cleaned


T = TypeVar("T", bound=BaseModel)


class BaseAgent(ABC):
    """
    Agent 抽象基类 — async + structured output 模板。

    子类约定：
    - 类属性 `prompt_name` 指定 YAML 文件名（不含扩展名），自动加载 system prompt
    - 类属性 `output_schema` 指定 Pydantic 输出模型，自动启用 structured output
    - 子类 process(input_data) 仍保留同步签名（默认走 asyncio.run），推荐覆盖 aprocess(input_data)
    """

    prompt_name: str = ""              # YAML 文件名（如 "scoring_agent"）
    output_schema: Optional[Type[BaseModel]] = None  # Pydantic 输出契约

    def __init__(self, model: ChatOpenAI, name: str):
        self.model = model
        self.name = name
        self.logger = logging.getLogger(f"interview.agents.{name}")

        # 加载 prompt 模板
        if self.prompt_name:
            try:
                self.prompt: PromptTemplate = load_prompt(self.prompt_name)
            except FileNotFoundError as e:
                self.logger.warning(f"Prompt 模板未找到，使用空 prompt: {e}")
                self.prompt = PromptTemplate(name=name, version="0", system="")
        else:
            self.prompt = PromptTemplate(name=name, version="0", system="")

        # 预绑定 structured output 模型（如有 schema）
        self._structured_model = (
            self.model.with_structured_output(self.output_schema, include_raw=False)
            if self.output_schema is not None
            else None
        )

    # ------------------------------------------------------------
    # 抽象接口
    # ------------------------------------------------------------

    @abstractmethod
    async def aprocess(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """异步主入口（async-first）— 子类必须实现"""

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """同步 wrapper — 仅供旧调用方使用，新代码走 aprocess"""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 已经在事件循环中：交给 to_thread 启动新 loop 跑（避免嵌套阻塞）
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(asyncio.run, self.aprocess(input_data)).result()
        except RuntimeError:
            pass
        return asyncio.run(self.aprocess(input_data))

    def get_system_prompt(self) -> str:
        """从 YAML 模板取 system prompt"""
        return self.prompt.system

    # ------------------------------------------------------------
    # async + structured output 核心方法
    # ------------------------------------------------------------

    async def ainvoke_structured(
        self,
        human_text: str,
        *,
        schema: Optional[Type[T]] = None,
        extra_messages: Optional[List[BaseMessage]] = None,
    ) -> T | BaseModel | Dict[str, Any]:
        """
        async + structured output 一站式方法：

        1. 构造 [SystemMessage(cached), HumanMessage(human_text), *extra]
        2. 用 with_structured_output(schema).ainvoke(...) 强约束 JSON
        3. 返回 Pydantic 实例（schema=None 时返回 model 原始 AIMessage）

        失败时记录日志并抛出，由调用方决定 fallback。
        """
        target_schema = schema or self.output_schema
        system_msg = cached_system_message(self.get_system_prompt())
        messages: List[BaseMessage] = [system_msg, HumanMessage(content=human_text)]
        if extra_messages:
            messages.extend(extra_messages)

        if target_schema is not None:
            structured = (
                self._structured_model
                if schema is None
                else self.model.with_structured_output(target_schema, include_raw=False)
            )
            try:
                self.logger.debug(f"{self.name} ainvoke_structured (schema={target_schema.__name__})")
                result = await structured.ainvoke(messages)
                return result
            except ValidationError as e:
                self.logger.error(f"{self.name} structured output 校验失败: {e}")
                raise
            except Exception as e:
                self.logger.error(f"{self.name} ainvoke_structured 调用异常: {e}")
                raise

        # 无 schema 时回退到普通文本调用
        self.logger.debug(f"{self.name} ainvoke (raw text)")
        ai_msg = await self.model.ainvoke(messages)
        return ai_msg

    async def ainvoke_text(self, messages: List[BaseMessage]) -> str:
        """无结构化的 raw 文本调用（用于工具调用循环等场景）"""
        try:
            self.logger.debug(f"{self.name} ainvoke (text)")
            ai_msg = await self.model.ainvoke(messages)
            return ai_msg.content if hasattr(ai_msg, "content") else str(ai_msg)
        except Exception as e:
            self.logger.error(f"{self.name} ainvoke_text 异常: {e}")
            return f"Error: {e}"

    # ------------------------------------------------------------
    # Fallback / 兼容方法
    # ------------------------------------------------------------

    def _invoke_model(self, messages: List[BaseMessage]) -> str:
        """旧式同步调用（保留用于尚未 async 化的辅助代码）"""
        try:
            self.logger.debug(f"{self.name} invoke (sync legacy)")
            response = self.model.invoke(messages)
            return response.content
        except Exception as e:
            self.logger.error(f"{self.name} invoke 异常: {e}")
            return f"Error: {e}"

    def _fix_common_json_issues(self, response: str) -> str:
        """委托给模块级函数（fallback 路径用）"""
        return fix_common_json_issues(response)


class InterviewState:
    """旧版 InterviewState — 保留以兼容遗留导入；当前流程已使用 InterviewSession"""

    def __init__(self, candidate_name: str, resume_data: Dict[str, Any] = None):
        self.candidate_name = candidate_name
        self.resume_data = resume_data or {}
        self.questions_asked: List[str] = []
        self.answers_given: List[str] = []
        self.scores: List[int] = []
        self.current_score = 0
        self.total_questions = 0
        self.interview_complete = False
        self.final_decision: Optional[str] = None
        self.summary = ""
        self.security_alerts: List[Any] = []

    def add_qa_pair(self, question: str, answer: str, score: int = 0):
        self.questions_asked.append(question)
        self.answers_given.append(answer)
        if score > 0:
            self.scores.append(score)
        self.total_questions += 1

    def get_current_context(self) -> Dict[str, Any]:
        return {
            "candidate_name": self.candidate_name,
            "resume_data": self.resume_data,
            "questions_asked": self.questions_asked,
            "answers_given": self.answers_given,
            "scores": self.scores,
            "current_score": sum(self.scores) / len(self.scores) if self.scores else 0,
            "total_questions": self.total_questions,
            "interview_complete": self.interview_complete,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            **self.get_current_context(),
            "interview_complete": self.interview_complete,
            "final_decision": self.final_decision,
            "summary": self.summary,
            "security_alerts": self.security_alerts,
        }
