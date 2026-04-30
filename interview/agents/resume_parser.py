"""
ResumeParser — async + structured output (S1 + S2)

不继承 BaseAgent（保持原有独立接口），但使用同样的 prompt loader + structured output。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from langchain_core.messages import HumanMessage

from interview.rubrics import RUBRIC_DIMENSIONS, format_rubric_for_prompt

from .cache import cached_system_message
from .prompts import load_prompt
from .schemas import ResumeProfile

logger = logging.getLogger("interview.agents.resume_parser")

_ALL_DIMENSIONS = list(RUBRIC_DIMENSIONS.keys())


class ResumeParser:
    """简历结构化解析器 — async + structured output"""

    def __init__(self, model):
        self.model = model
        try:
            self.prompt = load_prompt("resume_parser")
        except FileNotFoundError as e:
            logger.warning(f"resume_parser prompt 未找到: {e}")
            from .prompts import PromptTemplate
            self.prompt = PromptTemplate(name="resume_parser", version="0", system="")

        self._structured_model = self.model.with_structured_output(ResumeProfile, include_raw=False)

    # ------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------

    async def aparse(self, resume_data: Dict[str, Any]) -> Dict[str, Any]:
        """异步解析简历，返回结构化 profile dict"""
        if not resume_data or not isinstance(resume_data, dict):
            logger.warning("简历数据为空或格式异常，使用降级 profile")
            return self._generate_fallback_profile()

        try:
            resume_json = json.dumps(resume_data, ensure_ascii=False, indent=2)
            human_text = self.prompt.format_human(
                rubric_text=format_rubric_for_prompt(),
                resume_json=resume_json,
            )

            # ResumeParser system prompt 中含 {{ rubric_text }}，需要在 system 层渲染
            system_content = self.prompt.system.replace(
                "{{ rubric_text }}", format_rubric_for_prompt()
            )
            messages = [
                cached_system_message(system_content),
                HumanMessage(content=human_text),
            ]

            logger.debug("ResumeParser 调用 LLM (structured)")
            result: ResumeProfile = await self._structured_model.ainvoke(messages)
            return result.model_dump(mode="json")

        except Exception as e:
            logger.error(f"ResumeParser 解析失败，使用降级 profile: {e}")
            return self._generate_fallback_profile()

    def parse(self, resume_data: Dict[str, Any]) -> Dict[str, Any]:
        """同步 wrapper（旧调用方使用）"""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(asyncio.run, self.aparse(resume_data)).result()
        except RuntimeError:
            pass
        return asyncio.run(self.aparse(resume_data))

    # ------------------------------------------------------------
    # 降级
    # ------------------------------------------------------------

    def _generate_fallback_profile(self) -> Dict[str, Any]:
        """LLM 失败时的降级 profile — 全维度 MEDIUM"""
        return {
            "items": [],
            "aggregate_signals": {d: "MEDIUM" for d in _ALL_DIMENSIONS},
            "weakest_dimensions": list(_ALL_DIMENSIONS),
            "strongest_dimensions": [],
            "suggested_probe_items": [],
        }
