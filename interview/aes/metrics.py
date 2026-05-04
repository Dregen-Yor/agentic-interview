"""
5 个 Explainability Metrics — paper §5 (C2 核心 contribution)

定义这 5 个 metrics 是为了把先前论文的"more explainable"定性 claim 量化为可复现指标。
所有 metrics 都是 trait-agnostic 的：输入 List[EssayScoringOutput] + ground truth，输出标量。

公共出口（按论文顺序）：
1. evidence_grounded_recall(outputs, essays)  → float [0, 1]
2. cross_trait_consistency_rate(outputs)        → float [0, 1]
3. boundary_calibration_ece(outputs, gt_scores, boundary_bands) → float ≥ 0
4. counterfactual_stability(outputs_orig, outputs_paraphrased) → float [0, 1]
5. reviewer_trust_score(...)  — 协议占位（人工 panel 收集，不在代码中计算）

这些 metrics 都不依赖 LLM 二次评估（避免 LLM-as-Meta-Judge 循环论证），可直接在
脚本中计算。reviewer_trust 是唯一需要人工的，提供 protocol description。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from interview.agents.utils import validate_quote_in_answer


# ============================================================
# Metric 1: Evidence-Grounded Recall
# ============================================================

def evidence_grounded_recall(
    outputs: Sequence[Dict[str, Any]],
    essays: Sequence[str],
) -> Dict[str, Any]:
    """
    检查 evidence_quote 是否真的能在 essay 中 fuzzy-match 上。

    论文动机：G-Eval / Prometheus 的 reasoning 字段是自由文本，对原文没有 contractual
    grounding。我们的 schema 强制 evidence_quote。这个 metric 量化"被 fuzzy 校验通过"的
    比例，**不需要 LLM 二次评估**。

    Args:
        outputs: List[EssayScoringOutput dict]，每个含 traits[*].evidence_quote
        essays: 与 outputs 一一对应的 essay 原文

    Returns:
        {
            "recall": float [0, 1],
            "n_quotes": int,
            "n_grounded": int,
            "per_trait_recall": Dict[trait, float],
        }
    """
    if len(outputs) != len(essays):
        raise ValueError("outputs 与 essays 长度必须一致")

    n_total = 0
    n_grounded = 0
    per_trait_total: Dict[str, int] = {}
    per_trait_grounded: Dict[str, int] = {}

    for output, essay in zip(outputs, essays):
        traits = output.get("traits", [])
        for t in traits:
            if not isinstance(t, dict):
                continue
            quote = t.get("evidence_quote", "")
            trait_key = t.get("trait", "unknown")
            n_total += 1
            per_trait_total[trait_key] = per_trait_total.get(trait_key, 0) + 1
            if validate_quote_in_answer(quote, essay):
                n_grounded += 1
                per_trait_grounded[trait_key] = per_trait_grounded.get(trait_key, 0) + 1

    return {
        "recall": (n_grounded / n_total) if n_total > 0 else 0.0,
        "n_quotes": n_total,
        "n_grounded": n_grounded,
        "per_trait_recall": {
            k: per_trait_grounded.get(k, 0) / v
            for k, v in per_trait_total.items() if v > 0
        },
    }


# ============================================================
# Metric 2: Cross-Trait Consistency Rate
# ============================================================

# 跨 trait 矛盾对：在同一 essay 上极不可能同时出现的 (trait_a + level_a, trait_b + level_b) 对
# AES 文献支持：ideas + organization 通常 strongly correlated，
# voice 与 word_choice 也 correlated。一个 trait HIGH 而 strongly correlated trait LOW 视为可疑。
#
# 注：这是 conservative 定义 — 只标记最明显的矛盾，避免误杀 trait 真实差异。
_CONTRADICTION_PAIRS = [
    # (trait_a, level_a, trait_b, level_b)：trait_a 是这个 level 时 trait_b 不应该是反向 level
    ("ideas", "HIGH", "organization", "LOW"),
    ("ideas", "LOW", "organization", "HIGH"),
    ("organization", "HIGH", "ideas", "LOW"),
    ("organization", "LOW", "ideas", "HIGH"),
    ("word_choice", "HIGH", "voice", "LOW"),
    ("word_choice", "LOW", "voice", "HIGH"),
]


def cross_trait_consistency_rate(outputs: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """
    在多 essay 上检查 trait 间是否出现"显然矛盾"组合的比例。

    论文动机：v2 一次评 5 trait 容易出现「ideas HIGH + organization LOW」这种语义矛盾
    （essay 内容好但结构差是反常组合）。Schema-enforced + MTS 独立评分应减少这类矛盾。

    Returns:
        {
            "consistency_rate": float [0, 1],  # 1 - (含矛盾的 essay 比例)
            "n_essays": int,
            "n_with_contradiction": int,
            "contradiction_examples": [{essay_idx, pair}, ...]
        }
    """
    n_total = len(outputs)
    if n_total == 0:
        return {
            "consistency_rate": 1.0,
            "n_essays": 0,
            "n_with_contradiction": 0,
            "contradiction_examples": [],
        }

    n_with_contra = 0
    examples: List[Dict[str, Any]] = []
    for idx, output in enumerate(outputs):
        traits_list = output.get("traits", [])
        # 构建 trait → level 映射
        trait_levels = {}
        for t in traits_list:
            if isinstance(t, dict):
                trait_levels[t.get("trait")] = t.get("level")

        found_contra = False
        for trait_a, lvl_a, trait_b, lvl_b in _CONTRADICTION_PAIRS:
            if (
                trait_levels.get(trait_a) == lvl_a
                and trait_levels.get(trait_b) == lvl_b
            ):
                found_contra = True
                if len(examples) < 5:
                    examples.append({
                        "essay_idx": idx,
                        "pair": f"{trait_a}={lvl_a} & {trait_b}={lvl_b}",
                    })
                break

        if found_contra:
            n_with_contra += 1

    return {
        "consistency_rate": 1.0 - n_with_contra / n_total,
        "n_essays": n_total,
        "n_with_contradiction": n_with_contra,
        "contradiction_examples": examples,
    }


# ============================================================
# Metric 3: Boundary Calibration ECE
# ============================================================

# 默认 boundary bands（与 SummaryAgent 中一致；ASAP 1-6 范围下相对窄）
# 一般定义：边界 ±0.5 内视为"可能因 1 题改变结论"
DEFAULT_BOUNDARY_HALF_WIDTH = 0.5


def boundary_calibration_ece(
    outputs: Sequence[Dict[str, Any]],
    gt_scores: Sequence[float],
    boundary_thresholds: Optional[Sequence[float]] = None,
    half_width: float = DEFAULT_BOUNDARY_HALF_WIDTH,
    n_bins: int = 10,
) -> Dict[str, Any]:
    """
    Expected Calibration Error for boundary case detection.

    论文动机：BAS (arXiv:2604.03216) 提出选择性预测——边界情况应该 abstain。
    我们的 framework 用 requires_human_review 标记。这个 metric 量化"标记的 boundary
    样本 vs 实际人工 grade 改变的样本"的校准误差。

    数据需求：
    - outputs: List[EssayScoringOutput dict]，每个有 requires_human_review: bool
    - gt_scores: 对应的人工 ground truth scores（用于判断是否真的处于边界）

    简化定义：
    - 视 gt_scores 为概率「这个 score 接近 grade boundary」
    - score 在某个 boundary_threshold ± half_width 内 → 真实需要 review
    - requires_human_review=True 视为预测概率 = 1，否则 = 0
    - 计算 binary ECE（n_bins=10）

    Returns:
        {
            "ece": float ≥ 0 (越小越好),
            "n_samples": int,
            "n_predicted_review": int,
            "n_actual_boundary": int,
        }
    """
    if len(outputs) != len(gt_scores):
        raise ValueError("outputs 与 gt_scores 长度必须一致")
    if not outputs:
        return {"ece": 0.0, "n_samples": 0, "n_predicted_review": 0, "n_actual_boundary": 0}

    if boundary_thresholds is None:
        # ASAP 2.0 默认 1-6 整数刻度，假设 grade 边界在每个整数刻度
        boundary_thresholds = [2.5, 3.5, 4.5]

    def is_actual_boundary(score: float) -> int:
        return int(any(abs(score - thr) <= half_width for thr in boundary_thresholds))

    pred_probs: List[float] = []
    actual_labels: List[int] = []
    n_pred_review = 0
    for output, gt in zip(outputs, gt_scores):
        pred = 1.0 if output.get("requires_human_review", False) else 0.0
        pred_probs.append(pred)
        actual_labels.append(is_actual_boundary(float(gt)))
        if output.get("requires_human_review", False):
            n_pred_review += 1

    # binary ECE
    bin_edges = [i / n_bins for i in range(n_bins + 1)]
    total_ece = 0.0
    n_total = len(pred_probs)
    for b in range(n_bins):
        lo, hi = bin_edges[b], bin_edges[b + 1]
        in_bin = [
            (p, a)
            for p, a in zip(pred_probs, actual_labels)
            if (lo <= p < hi) or (b == n_bins - 1 and p == hi)
        ]
        if not in_bin:
            continue
        avg_pred = sum(p for p, _ in in_bin) / len(in_bin)
        avg_actual = sum(a for _, a in in_bin) / len(in_bin)
        total_ece += (len(in_bin) / n_total) * abs(avg_pred - avg_actual)

    return {
        "ece": round(total_ece, 4),
        "n_samples": n_total,
        "n_predicted_review": n_pred_review,
        "n_actual_boundary": sum(actual_labels),
    }


# ============================================================
# Metric 4: Counterfactual Stability
# ============================================================

def counterfactual_stability(
    outputs_orig: Sequence[Dict[str, Any]],
    outputs_paraphrased: Sequence[Dict[str, Any]],
    score_tolerance: float = 0.5,
) -> Dict[str, Any]:
    """
    检查 essay 经过语义保持的 paraphrase 后，框架的评分与 evidence 是否稳定。

    论文动机：稳定的可解释系统应该在小语义扰动下产出相近 score 与相似 evidence_quote。
    Verbal CoT 自由文本不一定满足这个性质（reviewer 抗议"换个 paraphrase 就完全不一样"）。

    Args:
        outputs_orig: 原始 essays 的评分输出
        outputs_paraphrased: paraphrase 后 essays 的评分输出（一一对应）
        score_tolerance: 总分变化 ≤ 此值视为稳定

    Returns:
        {
            "score_stability_rate": float [0, 1],
            "level_agreement_rate": float [0, 1],   # trait-level 投票稳定性
            "n_pairs": int,
        }
    """
    if len(outputs_orig) != len(outputs_paraphrased):
        raise ValueError("两组 outputs 长度必须一致")
    if not outputs_orig:
        return {"score_stability_rate": 1.0, "level_agreement_rate": 1.0, "n_pairs": 0}

    n_score_stable = 0
    n_total_traits = 0
    n_level_agree = 0

    for orig, para in zip(outputs_orig, outputs_paraphrased):
        # total score stability
        s_orig = orig.get("total_score", 0)
        s_para = para.get("total_score", 0)
        if abs(s_orig - s_para) <= score_tolerance:
            n_score_stable += 1

        # per-trait level agreement
        traits_orig = {t.get("trait"): t.get("level") for t in orig.get("traits", []) if isinstance(t, dict)}
        traits_para = {t.get("trait"): t.get("level") for t in para.get("traits", []) if isinstance(t, dict)}
        common_traits = set(traits_orig) & set(traits_para)
        for trait_key in common_traits:
            n_total_traits += 1
            if traits_orig[trait_key] == traits_para[trait_key]:
                n_level_agree += 1

    return {
        "score_stability_rate": n_score_stable / len(outputs_orig),
        "level_agreement_rate": (n_level_agree / n_total_traits) if n_total_traits > 0 else 1.0,
        "n_pairs": len(outputs_orig),
    }


# ============================================================
# Metric 5: Reviewer Trust Score（协议占位 — 人工收集）
# ============================================================

REVIEWER_TRUST_PROTOCOL = """
Reviewer Trust Score Protocol (manual collection)

Setup:
1. Sample N=30 essays (10 LOW / 10 MEDIUM / 10 HIGH overall_score) from ASAP 2.0 test split.
2. For each essay, generate two reports:
   - Report A: SchemaJudge framework output (含 evidence triples)
   - Report B: Baseline output (G-Eval 或 Prometheus-2 free-text reasoning)
3. Anonymize: blind labels A/B, randomize order per reviewer.

Reviewers:
- 30 educators (high school English teachers / MA students in education)
- Each reviewer rates 10 essay × 2 reports = 20 reports total
- Demographics balanced across teaching experience tiers

Rating instrument (per report):
- "I trust this evaluation report would be useful for grading decisions" (1=strongly disagree, 5=strongly agree)
- "Specific evidence in this report could be defended to a student or parent" (1-5)
- "This report's reasoning corresponds to specific moments in the essay" (1-5)
- Average the 3 sub-items → Reviewer Trust score per report

Aggregation:
- Mean Trust(SchemaJudge) − Mean Trust(Baseline) → reported delta with 95% CI
- Wilcoxon signed-rank test (paired by reviewer × essay) for significance

Reporting:
- Table 3 row: Reviewer Trust (1-5)
- 论文 §5.4 Reviewer Trust 章节描述协议 + Appendix 提供完整问卷
"""


def reviewer_trust_protocol() -> str:
    """返回 reviewer trust 收集协议文本（用于 paper appendix）"""
    return REVIEWER_TRUST_PROTOCOL.strip()


# ============================================================
# 综合评估接口（一次性跑全部 metrics）
# ============================================================

@dataclass
class ExplainabilityReport:
    """5 个 metrics 的综合报告（除 reviewer_trust 需人工）"""
    evidence_grounded_recall: float
    cross_trait_consistency_rate: float
    boundary_calibration_ece: float
    counterfactual_stability_score: Optional[float] = None
    counterfactual_stability_level: Optional[float] = None
    n_essays: int = 0
    n_quotes_total: int = 0
    detail: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_grounded_recall": self.evidence_grounded_recall,
            "cross_trait_consistency_rate": self.cross_trait_consistency_rate,
            "boundary_calibration_ece": self.boundary_calibration_ece,
            "counterfactual_stability_score": self.counterfactual_stability_score,
            "counterfactual_stability_level": self.counterfactual_stability_level,
            "n_essays": self.n_essays,
            "n_quotes_total": self.n_quotes_total,
            "detail": self.detail or {},
        }


def compute_all_metrics(
    outputs: Sequence[Dict[str, Any]],
    essays: Sequence[str],
    gt_scores: Optional[Sequence[float]] = None,
    outputs_paraphrased: Optional[Sequence[Dict[str, Any]]] = None,
    boundary_thresholds: Optional[Sequence[float]] = None,
) -> ExplainabilityReport:
    """一次性跑所有可计算 metrics（reviewer_trust 不在内，需人工收集）"""
    egr = evidence_grounded_recall(outputs, essays)
    ctc = cross_trait_consistency_rate(outputs)

    if gt_scores is not None and len(gt_scores) == len(outputs):
        bce = boundary_calibration_ece(outputs, gt_scores, boundary_thresholds)
        ece_val = bce["ece"]
    else:
        bce = {}
        ece_val = float("nan")

    if outputs_paraphrased is not None and len(outputs_paraphrased) == len(outputs):
        cfs = counterfactual_stability(outputs, outputs_paraphrased)
        cfs_score = cfs["score_stability_rate"]
        cfs_level = cfs["level_agreement_rate"]
    else:
        cfs = {}
        cfs_score = None
        cfs_level = None

    return ExplainabilityReport(
        evidence_grounded_recall=egr["recall"],
        cross_trait_consistency_rate=ctc["consistency_rate"],
        boundary_calibration_ece=ece_val,
        counterfactual_stability_score=cfs_score,
        counterfactual_stability_level=cfs_level,
        n_essays=len(outputs),
        n_quotes_total=egr["n_quotes"],
        detail={
            "evidence_per_trait_recall": egr["per_trait_recall"],
            "contradiction_examples": ctc["contradiction_examples"],
            "boundary_detail": bce,
            "counterfactual_detail": cfs,
        },
    )
