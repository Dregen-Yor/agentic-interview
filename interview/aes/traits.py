"""
ASAP 2.0 trait 定义

Reference: ASAP 2.0 dataset (Kaggle: lburleigh/asap-2-0)
Source rubric: ASAP AES competition trait scoring guides + ETS analytic rubrics

我们采用 5-trait analytic 评分（与 ASAP 2.0 中 essay set 6/7/8 的 trait 维度对齐）：
- ideas        : 思想内容是否充分发展、相关、清晰
- organization : 结构是否连贯、过渡是否流畅
- voice        : 写作声音是否真诚、个性化（部分 set 有，否则可选）
- word_choice  : 词汇运用是否准确、丰富
- conventions  : 语法、拼写、标点是否规范

ASAP 2.0 不同 essay set 的 trait 集合不完全一致；本模块提供 5 项主流 trait，
data_loader 会根据具体 set 选择可用的子集。

每个 trait 提供 LOW/MEDIUM/HIGH 三档 rubric 描述（schemajudge 的 evidence_quote
对照对象）。score_range 给出整数分数上下界（与 ASAP 2.0 评分尺度对齐，多数 trait 1-6）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class TraitDef:
    key: str
    name_zh: str           # 中文标签（前端展示用）
    name_en: str           # 英文标签（prompt 用）
    score_range: Tuple[int, int]   # (min, max) 整数分数范围
    levels: Dict[str, str] = field(default_factory=dict)  # LOW/MEDIUM/HIGH → rubric 文字（英文）


# ASAP 2.0 多数 essay set 用 1-6 整数分数；少数 set 用 0-3。我们以 1-6 为默认。
_DEFAULT_RANGE = (1, 6)


TRAITS: Dict[str, TraitDef] = {
    "ideas": TraitDef(
        key="ideas",
        name_zh="思想内容",
        name_en="Ideas / Content",
        score_range=_DEFAULT_RANGE,
        levels={
            "LOW": (
                "Ideas are minimal, unclear, or off-topic. The essay lacks a discernible "
                "central message; supporting details are absent, irrelevant, or contradictory."
            ),
            "MEDIUM": (
                "Ideas are present and generally relevant but partially developed. Supporting "
                "details exist but may be uneven, generic, or insufficient to fully convince."
            ),
            "HIGH": (
                "Ideas are clear, focused, and substantively developed. Supporting details "
                "are specific, relevant, and convincing throughout."
            ),
        },
    ),
    "organization": TraitDef(
        key="organization",
        name_zh="组织结构",
        name_en="Organization",
        score_range=_DEFAULT_RANGE,
        levels={
            "LOW": (
                "The essay lacks clear structure. Paragraphs are missing, misordered, or "
                "fail to connect. Transitions are absent or confusing."
            ),
            "MEDIUM": (
                "An organizational pattern is present but inconsistent. Some transitions "
                "work; others are abrupt or formulaic. The conclusion may feel rushed."
            ),
            "HIGH": (
                "Organization is purposeful and effective. Paragraphs flow logically; "
                "transitions guide the reader smoothly; opening and closing are intentional."
            ),
        },
    ),
    "voice": TraitDef(
        key="voice",
        name_zh="写作声音",
        name_en="Voice",
        score_range=_DEFAULT_RANGE,
        levels={
            "LOW": (
                "Writing feels flat, anonymous, or detached. The author's perspective and "
                "engagement with the topic are not perceptible."
            ),
            "MEDIUM": (
                "A voice emerges occasionally but is uneven. Tone may shift unexpectedly "
                "or feel borrowed rather than authentic."
            ),
            "HIGH": (
                "A distinctive, engaged voice carries the piece. Tone matches purpose and "
                "audience; the author's stance is unambiguous and consistent."
            ),
        },
    ),
    "word_choice": TraitDef(
        key="word_choice",
        name_zh="词汇运用",
        name_en="Word Choice",
        score_range=_DEFAULT_RANGE,
        levels={
            "LOW": (
                "Word choice is limited, repetitive, or inappropriate. Vague nouns and "
                "generic verbs dominate; precision is consistently lacking."
            ),
            "MEDIUM": (
                "Words generally convey meaning but lack precision or freshness. Some "
                "stronger choices appear, but vocabulary skews toward the ordinary."
            ),
            "HIGH": (
                "Words are precise, vivid, and well-suited to context. Verbs are "
                "energetic; specific nouns and modifiers create clear images."
            ),
        },
    ),
    "conventions": TraitDef(
        key="conventions",
        name_zh="语言规范",
        name_en="Conventions (Grammar/Mechanics)",
        score_range=_DEFAULT_RANGE,
        levels={
            "LOW": (
                "Frequent errors in grammar, spelling, capitalization, or punctuation "
                "interfere with comprehension."
            ),
            "MEDIUM": (
                "Errors are noticeable but generally do not impede understanding. Standard "
                "conventions are mostly followed, with occasional lapses."
            ),
            "HIGH": (
                "Conventions are handled skillfully. Errors are rare and do not distract; "
                "punctuation is used purposefully."
            ),
        },
    ),
}


TRAIT_KEYS = list(TRAITS.keys())  # ["ideas", "organization", "voice", "word_choice", "conventions"]

TRAIT_MAX_SCORE: Dict[str, int] = {k: v.score_range[1] for k, v in TRAITS.items()}
TRAIT_MIN_SCORE: Dict[str, int] = {k: v.score_range[0] for k, v in TRAITS.items()}


def format_trait_rubric(trait_key: str) -> str:
    """格式化某 trait 的完整 rubric（送给 LLM）"""
    t = TRAITS.get(trait_key)
    if not t:
        return f"(unknown trait: {trait_key})"
    lines = [f"### {t.name_en} ({t.key}, range {t.score_range[0]}-{t.score_range[1]})"]
    for level, desc in t.levels.items():
        lines.append(f"- {level}: {desc}")
    return "\n".join(lines)


def get_canonical_rubric_clause(trait_key: str, level: str) -> str:
    """返回某 trait + level 的 canonical rubric 文字（schema-enforced 覆盖时用）"""
    t = TRAITS.get(trait_key)
    if not t:
        return ""
    return t.levels.get(level, "")
