"""
Guardrails (S7) — 多层安全检测

第一层：OpenAI Moderation API（omni-moderation-latest）
    - 通用 toxicity / violence / sexual / harassment / self_harm 等 11 类
    - 免费、低延迟（~100ms）、官方 SDK
    - 通过 GPT_API_KEY 代理调用（与现有 chatgpt_model 同一通道）
    - 仅做"明显有害内容"过滤，不专门防 prompt injection

第二层：定制 SecurityAgent (LLM)
    - 专门检测 prompt injection / 元叙述注入 / 角色扮演绕过
    - 在 Moderation 通过后才调用，节省成本
    - 用 structured output 输出 SecurityOutput

两层任一标红即视为 block。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

from openai import AsyncOpenAI

logger = logging.getLogger("interview.agents.guardrails")

_MODERATION_MODEL = "omni-moderation-latest"

# 复用 chatgpt 通道（含代理）— 与 llm.py 中 chatgpt_model 同一来源
_async_client: AsyncOpenAI | None = None


def _get_async_client() -> AsyncOpenAI:
    """懒加载 AsyncOpenAI 客户端，复用 GPT_API_KEY/GPT_BASE_URL"""
    global _async_client
    if _async_client is None:
        _async_client = AsyncOpenAI(
            api_key=os.getenv("GPT_API_KEY"),
            base_url=os.getenv("GPT_BASE_URL"),
        )
    return _async_client


async def moderate_text(text: str) -> Dict[str, Any]:
    """
    第一层防御：OpenAI Moderation API 调用。

    返回标准化结果：
    {
      "flagged": bool,
      "categories": {"hate": bool, "violence": bool, ...},
      "category_scores": {...},
      "risk_level": "low" | "medium" | "high",
      "detected_issues": [string],
      "error": Optional[str]
    }

    异常时降级返回 flagged=False（不能因防御层崩溃影响面试）+ error 字段。
    """
    if not text or not text.strip():
        return {
            "flagged": False,
            "risk_level": "low",
            "detected_issues": [],
            "categories": {},
            "category_scores": {},
        }

    try:
        client = _get_async_client()
        response = await client.moderations.create(model=_MODERATION_MODEL, input=text)
        result = response.results[0]

        flagged = bool(result.flagged)
        categories = {k: bool(v) for k, v in result.categories.model_dump().items()} if hasattr(
            result.categories, "model_dump"
        ) else dict(result.categories)
        category_scores = (
            result.category_scores.model_dump()
            if hasattr(result.category_scores, "model_dump")
            else dict(result.category_scores)
        )

        triggered = [k for k, v in categories.items() if v]
        # 按最高分类得分映射风险
        max_score = max(category_scores.values()) if category_scores else 0.0
        if flagged or max_score >= 0.85:
            risk_level = "high"
        elif max_score >= 0.5:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "flagged": flagged,
            "risk_level": risk_level,
            "detected_issues": triggered,
            "categories": categories,
            "category_scores": category_scores,
        }

    except Exception as e:
        logger.warning(f"Moderation API 调用失败，降级 fail-open: {e}")
        return {
            "flagged": False,
            "risk_level": "low",
            "detected_issues": [],
            "categories": {},
            "category_scores": {},
            "error": str(e),
        }


def merge_moderation_into_security(
    security_result: Dict[str, Any],
    moderation_result: Dict[str, Any],
) -> Dict[str, Any]:
    """合并 Moderation 结果到 SecurityAgent 输出，按最高风险等级合并 issues。"""
    from .security_agent import _max_risk  # 复用现有风险等级合并函数

    if moderation_result.get("flagged") or moderation_result.get("risk_level") == "high":
        security_result = dict(security_result)
        security_result["risk_level"] = _max_risk(
            security_result.get("risk_level", "low"),
            moderation_result.get("risk_level", "low"),
        )
        security_result["detected_issues"] = list(set(
            security_result.get("detected_issues", [])
            + [f"moderation:{i}" for i in moderation_result.get("detected_issues", [])]
        ))
        if security_result["risk_level"] == "high":
            security_result["suggested_action"] = "block"
            security_result["is_safe"] = False

    return security_result
