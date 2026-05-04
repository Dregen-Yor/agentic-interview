"""
AES (Automated Essay Scoring) 实验模块 — EMNLP 2026 论文 ASAP 2.0 instantiation

设计原则：
- **不修改** interview/agents/ 下任何文件（保持 AI 面试系统逻辑完全不变）
- **复用** interview.agents.utils.validate_quote_in_answer（fuzzy 校验工具）
- **平行** 设计：本模块定义独立的 TraitScore / EssayScoringOutput / EssayScoringPipeline
  与面试场景的 DimensionScore / ScoringOutput / ScoringAgent 同构但独立

公共出口：
- TRAITS：ASAP 2.0 trait 定义（rubric LOW/MEDIUM/HIGH）
- TraitScore / EssayScoringOutput：本模块 schema（schemas.py）
- EssayScoringPipeline：核心评分管线（pipeline.py）
- metrics：5 个 explainability metrics
- baselines：vanilla / G-Eval / MTS-only 等 baseline 实现

paper map：
- §3 SchemaJudge core 的 trait-agnostic 论证 — 本模块的 schema 与 interview.agents.schemas 同构
- §6 ASAP 2.0 instantiation — 本模块的 pipeline + metrics + baselines
- §5 Explainability metrics — 本模块的 metrics.py
"""

from .traits import TRAITS, TraitDef, TRAIT_KEYS, TRAIT_MAX_SCORE

__all__ = [
    "TRAITS",
    "TraitDef",
    "TRAIT_KEYS",
    "TRAIT_MAX_SCORE",
]
