"""
Prompt Cache Helper (S3) — 显式标记长 system prompt 走 prompt caching

策略：
- Anthropic Claude: SystemMessage 加 cache_control={"type": "ephemeral"} 即可
- OpenAI: server-side 自动 cache（>1024 input tokens），无需显式标记
- 通过代理时通常透传，仍按 OpenAI 路径对待

由于本项目所有模型都通过 langchain_openai.ChatOpenAI 走 OpenAI 兼容协议，
prompt caching 在服务端自动处理，无需手动 cache_control 字段。
本模块保留接口为将来切换 Anthropic 直连预留。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from langchain_core.messages import SystemMessage

logger = logging.getLogger("interview.agents.cache")


def cached_system_message(content: str, *, provider: str = "openai") -> SystemMessage:
    """
    构造一个 SystemMessage；若 provider 为 anthropic 则附加 cache_control。

    OpenAI / OpenAI-compatible proxy: 服务端自动缓存（≥1024 tokens 自动）；本函数等价于
    SystemMessage(content)。
    Anthropic native: 客户端需显式 cache_control={"type":"ephemeral"} 标记 system block。
    """
    if provider == "anthropic":
        # Anthropic block-format: list of dicts with cache_control
        return SystemMessage(
            content=[
                {
                    "type": "text",
                    "text": content,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        )
    return SystemMessage(content=content)


def annotate_cache_metadata(invoke_kwargs: Dict[str, Any], cache_eligible: bool = True) -> Dict[str, Any]:
    """
    给 model.ainvoke 的 kwargs 添加 cache 提示元数据（langfuse / langsmith 可选用于观测）。
    不影响 LLM 行为。
    """
    if cache_eligible:
        meta = invoke_kwargs.setdefault("metadata", {})
        meta["prompt_cache_eligible"] = True
    return invoke_kwargs
