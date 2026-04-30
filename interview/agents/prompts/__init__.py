"""
Prompt Loader (S12) — YAML 模板外置 + 版本管理 + 缓存

设计目标：
- prompt 内容与代码解耦，非工程师可直接编辑 YAML
- 每个模板自带 metadata（version / cache_eligible / model_hint），便于 A/B 与回滚
- @lru_cache 避免重复读盘解析
- 支持 {{ var }} 占位符的简单替换（不引 Jinja2 依赖）
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

logger = logging.getLogger("interview.agents.prompts")

_PROMPT_DIR = Path(__file__).parent
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


@dataclass
class PromptTemplate:
    """单个 agent 的 prompt 模板（含 system + 可选 human + metadata）"""

    name: str
    version: str
    system: str
    human_template: str = ""
    cache_eligible: bool = True
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def format_human(self, **kwargs) -> str:
        """用 {{ var }} 占位符替换实际内容；缺失变量保留占位符（不抛异常）"""
        if not self.human_template:
            return ""

        def _sub(match: re.Match) -> str:
            key = match.group(1)
            if key in kwargs:
                value = kwargs[key]
                return str(value) if value is not None else ""
            logger.warning(f"prompt {self.name}: 占位符 {{ {key} }} 未提供值")
            return match.group(0)

        return _PLACEHOLDER_RE.sub(_sub, self.human_template)


@lru_cache(maxsize=32)
def load_prompt(name: str) -> PromptTemplate:
    """加载并缓存指定 agent 的 prompt 模板（YAML 文件名应与 agent name 对应）"""
    yaml_path = _PROMPT_DIR / f"{name}.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"Prompt 模板不存在: {yaml_path}")

    with yaml_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    metadata = data.get("metadata", {})
    return PromptTemplate(
        name=metadata.get("name", name),
        version=str(metadata.get("version", "unknown")),
        system=data.get("system_prompt", "").strip(),
        human_template=data.get("human_template", "").strip(),
        cache_eligible=bool(metadata.get("cache_eligible", True)),
        description=metadata.get("description", ""),
        metadata=metadata,
    )


def reload_prompts() -> None:
    """开发期热重载：清空 lru_cache 强制重新读 YAML"""
    load_prompt.cache_clear()
    logger.info("Prompt 缓存已清空，下次调用将重新加载")
