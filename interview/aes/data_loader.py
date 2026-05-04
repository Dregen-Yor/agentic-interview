"""
ASAP 2.0 数据加载（Kaggle: lburleigh/asap-2-0）

ASAP 2.0 标准列结构（基于 Kaggle 数据集）：
- essay_id        : int
- essay_set       : int (1-8 不同 prompt sets)
- essay           : str（学生作文文本）
- domain1_score   : int / float（主评分，holistic）
- rater1_domain1, rater2_domain1: 两位评分者
- 部分 set 含 trait scores（但列名不一致）

我们的 loader：
- 灵活列映射：通过 trait_columns dict 配置每个 set 的 trait → 列名映射
- 默认仅加载 essay + domain1_score（holistic）
- 提供 split_by_set 便于按 essay set 分别评估

不依赖 pandas（虽然实际上 ASAP 2.0 是 CSV）；使用 csv 标准库 + Python dataclass 加载。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple


@dataclass
class ASAPEssay:
    essay_id: str
    essay_set: int
    essay: str
    domain1_score: Optional[float] = None
    rater1_domain1: Optional[float] = None
    rater2_domain1: Optional[float] = None
    trait_scores: Dict[str, float] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)  # 原始 row（debug）

    @property
    def has_holistic(self) -> bool:
        return self.domain1_score is not None

    def __repr__(self) -> str:
        return (
            f"ASAPEssay(id={self.essay_id}, set={self.essay_set}, "
            f"len={len(self.essay)}chars, holistic={self.domain1_score})"
        )


# ASAP 2.0 essay set → trait 列名 → 我们的 trait_key 映射
# 不同 essay set 列名可能不同；下方为 ASAP 1.0 的标准 mapping，2.0 沿用大部分
DEFAULT_TRAIT_COLUMN_MAPPING: Dict[int, Dict[str, str]] = {
    # ASAP set 7 / 8 通常包含 5 个 analytic traits
    7: {
        "ideas_score": "ideas",
        "organization_score": "organization",
        "voice_score": "voice",
        "word_choice_score": "word_choice",
        "conventions_score": "conventions",
    },
    8: {
        "ideas_score": "ideas",
        "organization_score": "organization",
        "voice_score": "voice",
        "word_choice_score": "word_choice",
        "conventions_score": "conventions",
    },
}


def _safe_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_asap(
    csv_path: str | Path,
    essay_set_filter: Optional[Iterable[int]] = None,
    limit: Optional[int] = None,
    trait_column_mapping: Optional[Dict[int, Dict[str, str]]] = None,
    encoding: str = "utf-8-sig",
) -> List[ASAPEssay]:
    """
    加载 ASAP 2.0 CSV 文件。

    Args:
        csv_path: CSV 文件路径
        essay_set_filter: 仅加载指定 set 的 essays（None=all）
        limit: 仅加载前 N 条
        trait_column_mapping: 自定义 set → {csv_col: trait_key}；None 用 DEFAULT
        encoding: CSV 编码（默认 utf-8-sig 处理 BOM）

    Returns:
        List[ASAPEssay]
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"ASAP CSV not found: {csv_path}")

    mapping = trait_column_mapping or DEFAULT_TRAIT_COLUMN_MAPPING
    set_filter = set(essay_set_filter) if essay_set_filter else None

    essays: List[ASAPEssay] = []
    with csv_path.open("r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                essay_set = int(row.get("essay_set", row.get("EssaySet", 0)) or 0)
            except (TypeError, ValueError):
                continue
            if set_filter is not None and essay_set not in set_filter:
                continue

            essay_text = row.get("essay") or row.get("Essay") or ""
            if not essay_text.strip():
                continue

            # trait scores（按本 set 的 mapping 提取）
            trait_scores: Dict[str, float] = {}
            for col, trait_key in mapping.get(essay_set, {}).items():
                v = _safe_float(row.get(col))
                if v is not None:
                    trait_scores[trait_key] = v

            essays.append(ASAPEssay(
                essay_id=str(row.get("essay_id") or row.get("EssayID") or len(essays)),
                essay_set=essay_set,
                essay=essay_text,
                domain1_score=_safe_float(row.get("domain1_score")),
                rater1_domain1=_safe_float(row.get("rater1_domain1")),
                rater2_domain1=_safe_float(row.get("rater2_domain1")),
                trait_scores=trait_scores,
                raw=dict(row),
            ))

            if limit is not None and len(essays) >= limit:
                break

    return essays


def split_by_set(essays: List[ASAPEssay]) -> Dict[int, List[ASAPEssay]]:
    """按 essay_set 分组（便于 per-set 评估）"""
    by_set: Dict[int, List[ASAPEssay]] = {}
    for e in essays:
        by_set.setdefault(e.essay_set, []).append(e)
    return by_set


def iter_with_traits(essays: Iterable[ASAPEssay]) -> Iterator[Tuple[ASAPEssay, List[str]]]:
    """
    迭代 essays，返回 (essay, available_traits)。
    某些 set 没有 analytic traits → available_traits 为空，调用方应回退到 holistic。
    """
    for e in essays:
        yield e, list(e.trait_scores.keys())


def quadratic_weighted_kappa(
    rater_a: List[int], rater_b: List[int],
    min_rating: Optional[int] = None, max_rating: Optional[int] = None,
) -> float:
    """
    Quadratic Weighted Kappa - ASAP 评估标准 metric

    论文用：QWK 是 AES 文献标准（cohen 1968 + ASAP 竞赛官方），
    无外部依赖直接用 numpy 也可以但这里用纯 Python 保持 zero-dependency。
    """
    if not rater_a or len(rater_a) != len(rater_b):
        return 0.0
    rater_a = [int(x) for x in rater_a]
    rater_b = [int(x) for x in rater_b]
    min_r = min_rating if min_rating is not None else min(min(rater_a), min(rater_b))
    max_r = max_rating if max_rating is not None else max(max(rater_a), max(rater_b))
    n_ratings = max_r - min_r + 1

    # confusion matrix
    conf = [[0] * n_ratings for _ in range(n_ratings)]
    for a, b in zip(rater_a, rater_b):
        conf[a - min_r][b - min_r] += 1

    # weight matrix（quadratic）
    weights = [
        [((i - j) ** 2) / ((n_ratings - 1) ** 2) if n_ratings > 1 else 0
         for j in range(n_ratings)]
        for i in range(n_ratings)
    ]

    # marginals & expected
    n = len(rater_a)
    hist_a = [sum(conf[i]) for i in range(n_ratings)]
    hist_b = [sum(conf[i][j] for i in range(n_ratings)) for j in range(n_ratings)]
    expected = [
        [(hist_a[i] * hist_b[j]) / n for j in range(n_ratings)]
        for i in range(n_ratings)
    ]

    num = sum(weights[i][j] * conf[i][j] for i in range(n_ratings) for j in range(n_ratings))
    den = sum(weights[i][j] * expected[i][j] for i in range(n_ratings) for j in range(n_ratings))

    return 1.0 - (num / den) if den > 0 else 0.0
