"""
简历结构化解析器 — LLM 驱动
将任意 JSON 简历数据解析为结构化 profile，产出各维度 LOW/MEDIUM/HIGH 信号。
在 start_interview() 中调用一次，结果缓存在 session 中。
"""

import json
import logging
import re
from typing import Dict, Any, List

from langchain_core.messages import SystemMessage, HumanMessage

from interview.rubrics import RUBRIC_DIMENSIONS, format_rubric_for_prompt

logger = logging.getLogger("interview.agents.resume_parser")

# 所有维度 key 列表
_ALL_DIMENSIONS = list(RUBRIC_DIMENSIONS.keys())

# 合法信号值
_VALID_SIGNALS = {"LOW", "MEDIUM", "HIGH", "NO_SIGNAL"}
_VALID_LEVELS = {"LOW", "MEDIUM", "HIGH"}


class ResumeParser:
    """简历结构化解析器"""

    def __init__(self, model):
        self.model = model

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def parse(self, resume_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        主入口：解析简历数据，返回 structured_profile。
        LLM 调用失败时返回降级 profile，保证下游不中断。
        """
        if not resume_data or not isinstance(resume_data, dict):
            logger.warning("简历数据为空或格式异常，使用降级 profile")
            return self._generate_fallback_profile()

        try:
            resume_json = json.dumps(resume_data, ensure_ascii=False, indent=2)
            messages = self._build_parse_prompt(resume_json)

            logger.debug("===== ResumeParser 开始调用 LLM =====")
            ai_msg = self.model.invoke(messages)
            raw = ai_msg.content if hasattr(ai_msg, "content") else str(ai_msg)
            logger.debug(f"ResumeParser 原始响应长度: {len(raw)}")

            fixed = self._fix_common_json_issues(raw)
            profile = json.loads(fixed)

            # 基础校验 + 补全
            profile = self._validate_and_fix_profile(profile)
            return profile

        except Exception as e:
            logger.error(f"ResumeParser 解析失败，使用降级 profile: {e}")
            return self._generate_fallback_profile()

    # ------------------------------------------------------------------
    # Prompt 构建
    # ------------------------------------------------------------------

    def _build_parse_prompt(self, resume_json: str) -> list:
        rubric_text = format_rubric_for_prompt()

        system = (
            "You are a resume analysis expert for university CS program admissions.\n"
            "Given a candidate's resume (first-year student), extract structured items "
            "and assess evidence signals against a rubric.\n\n"
            "For EACH experience (project, competition, coursework, self_study, extracurricular):\n"
            "1. Summarize in one sentence\n"
            "2. Infer involvement depth (LOW/MEDIUM/HIGH)\n"
            "3. Infer motivation\n"
            "4. Identify knowledge gaps to probe in interview\n"
            "5. List KSD (Knowledge/Skills/Dispositions) relevant to rubric dimensions\n"
            "6. Rate dimension signals per dimension (LOW/MEDIUM/HIGH/NO_SIGNAL)\n\n"
            f"Rubric:\n{rubric_text}\n\n"
            "Then produce aggregate signals, weakest/strongest dimensions, "
            "and 2-3 item IDs most worth probing.\n\n"
            "Output strict JSON matching this schema:\n"
            "{\n"
            '  "items": [\n'
            "    {\n"
            '      "id": "item_0",\n'
            '      "category": "project"|"competition"|"coursework"|"self_study"|"extracurricular",\n'
            '      "summary": "one sentence",\n'
            '      "inferred_involvement": "LOW"|"MEDIUM"|"HIGH",\n'
            '      "inferred_motivation": "string",\n'
            '      "knowledge_gaps": ["gap1"],\n'
            '      "ksd_possessed": ["ksd1"],\n'
            '      "dimension_signals": {\n'
            '        "math_logic": "LOW"|"MEDIUM"|"HIGH"|"NO_SIGNAL",\n'
            '        "reasoning_rigor": "...",\n'
            '        "communication": "...",\n'
            '        "collaboration": "...",\n'
            '        "growth_potential": "..."\n'
            "      }\n"
            "    }\n"
            "  ],\n"
            '  "aggregate_signals": { "math_logic": "LOW"|"MEDIUM"|"HIGH", ... },\n'
            '  "weakest_dimensions": ["dim1"],\n'
            '  "strongest_dimensions": ["dim1"],\n'
            '  "suggested_probe_items": ["item_0"]\n'
            "}\n\n"
            "IMPORTANT: Return ONLY valid JSON. No markdown, no extra text."
        )

        human = f"Candidate resume:\n{resume_json}"

        return [SystemMessage(content=system), HumanMessage(content=human)]

    # ------------------------------------------------------------------
    # 降级 profile
    # ------------------------------------------------------------------

    def _generate_fallback_profile(self) -> Dict[str, Any]:
        """LLM 失败时的降级 profile — 全维度 MEDIUM，下游退化为无锚定行为"""
        return {
            "items": [],
            "aggregate_signals": {d: "MEDIUM" for d in _ALL_DIMENSIONS},
            "weakest_dimensions": list(_ALL_DIMENSIONS),
            "strongest_dimensions": [],
            "suggested_probe_items": [],
        }

    # ------------------------------------------------------------------
    # JSON 修复 & 校验
    # ------------------------------------------------------------------

    def _fix_common_json_issues(self, response: str) -> str:
        cleaned = response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        # 补全缺失的大括号
        open_b = cleaned.count("{")
        close_b = cleaned.count("}")
        if open_b > close_b:
            cleaned += "}" * (open_b - close_b)

        # 移除尾逗号
        cleaned = re.sub(r",\s*}", "}", cleaned)
        cleaned = re.sub(r",\s*]", "]", cleaned)
        return cleaned

    def _validate_and_fix_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """校验并补全 profile 字段，确保下游消费安全"""
        # items
        if "items" not in profile or not isinstance(profile.get("items"), list):
            profile["items"] = []

        for i, item in enumerate(profile["items"]):
            if "id" not in item:
                item["id"] = f"item_{i}"
            # 确保 dimension_signals 包含所有维度
            signals = item.get("dimension_signals", {})
            for d in _ALL_DIMENSIONS:
                if d not in signals or signals[d] not in _VALID_SIGNALS:
                    signals[d] = "NO_SIGNAL"
            item["dimension_signals"] = signals

        # aggregate_signals
        agg = profile.get("aggregate_signals", {})
        for d in _ALL_DIMENSIONS:
            if d not in agg or agg[d] not in _VALID_LEVELS:
                agg[d] = "MEDIUM"
        profile["aggregate_signals"] = agg

        # weakest / strongest
        if "weakest_dimensions" not in profile or not isinstance(profile["weakest_dimensions"], list):
            profile["weakest_dimensions"] = [d for d in _ALL_DIMENSIONS if agg.get(d) == "LOW"]
        if "strongest_dimensions" not in profile or not isinstance(profile["strongest_dimensions"], list):
            profile["strongest_dimensions"] = [d for d in _ALL_DIMENSIONS if agg.get(d) == "HIGH"]

        # suggested_probe_items
        if "suggested_probe_items" not in profile or not isinstance(profile["suggested_probe_items"], list):
            profile["suggested_probe_items"] = [item["id"] for item in profile["items"][:3]]

        return profile
