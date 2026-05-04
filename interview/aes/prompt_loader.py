"""
AES prompt loader — 与 interview.agents.prompts 同构但独立读取本模块的 prompts/

不复用 interview.agents.prompts.load_prompt：
- 那个 loader 路径写死指向 interview/agents/prompts/
- 本模块的 prompts 在 interview/aes/prompts/，独立加载更干净
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml


_PROMPTS_DIR = Path(__file__).parent / "prompts"


class AESPromptTemplate:
    """与 interview.agents.prompts.PromptTemplate 同构 — `{{ var }}` 占位符简单替换"""

    def __init__(self, name: str, version: str, system: str, human: str, metadata: Dict[str, Any]):
        self.name = name
        self.version = version
        self.system = system
        self.human = human
        self.metadata = metadata

    def format_human(self, **kwargs: Any) -> str:
        text = self.human
        for key, value in kwargs.items():
            text = re.sub(r"\{\{\s*" + re.escape(key) + r"\s*\}\}", str(value), text)
        return text

    def format_system(self, **kwargs: Any) -> str:
        text = self.system
        for key, value in kwargs.items():
            text = re.sub(r"\{\{\s*" + re.escape(key) + r"\s*\}\}", str(value), text)
        return text


@lru_cache(maxsize=8)
def load_aes_prompt(name: str) -> AESPromptTemplate:
    """从 interview/aes/prompts/<name>.yaml 加载"""
    path = _PROMPTS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"AES prompt not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    meta = data.get("metadata", {})
    return AESPromptTemplate(
        name=meta.get("name", name),
        version=str(meta.get("version", "0.0")),
        system=data.get("system_prompt", ""),
        human=data.get("human_template", ""),
        metadata=meta,
    )
