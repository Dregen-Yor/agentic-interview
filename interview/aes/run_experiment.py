"""
AES Experiment Runner — paper §6 实验主入口

CLI 用法（W3 Hard Gate 时跑）：
    # 跑 SchemaJudge full + 4 个 baselines on ASAP set 8 前 50 条
    uv run python -m interview.aes.run_experiment \\
        --asap-csv data/asap_2.0/training.tsv \\
        --essay-set 8 \\
        --limit 50 \\
        --systems schemajudge,vanilla,geval,mts_only \\
        --output results/asap_set8_n50.json

    # 仅跑 schemajudge（快速 dry-run）
    uv run python -m interview.aes.run_experiment --asap-csv ... --systems schemajudge --limit 5

输出 JSON 结构：
{
    "config": {...},
    "per_system": {
        "schemajudge": {
            "outputs": [EssayScoringOutput, ...],
            "qwk": float,
            "pearson": float,
            "explainability": {evidence_grounded_recall: ..., ...}
        },
        ...
    }
}

paper map：Table 1 (Main results) + Table 2 (Ablation) + Table 3 (Explainability)
都从这个 JSON 提取。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 关键：本模块不会触发 interview.consumers 之类的 Django 导入；
# 只 import LLM 实例与本模块代码。

logger = logging.getLogger("interview.aes.run_experiment")


def _build_systems(system_names: List[str], score_range: tuple = (1, 6)) -> Dict[str, Any]:
    """根据 --systems 参数构造对应的 judge 实例

    所有 judge 共享 ascore(essay_text, essay_prompt, trait_subset, overall_score_holistic)
    -> dict 接口（鸭子类型）。
    """
    # 延迟导入：仅在真实跑实验时才需要 LLM 实例
    from interview.llm import doubao_model, gemini_model, chatgpt_model
    from .baselines import GEvalJudge, MTSOnlyJudge, VanillaJudge
    from .pipeline import EssayScoringPipeline

    systems: Dict[str, Any] = {}
    for name in system_names:
        if name == "schemajudge":
            # 默认双模型 ensemble
            systems[name] = EssayScoringPipeline([doubao_model, gemini_model])
        elif name == "schemajudge_single":
            # 单模型变体（W3 ablation 用）
            systems[name] = EssayScoringPipeline([gemini_model])
        elif name == "vanilla":
            systems[name] = VanillaJudge(chatgpt_model, score_range=score_range)
        elif name == "geval":
            systems[name] = GEvalJudge(chatgpt_model)
        elif name == "mts_only":
            systems[name] = MTSOnlyJudge(gemini_model)
        else:
            logger.warning(f"Unknown system: {name}, skipping")
    return systems


async def _score_one_essay(
    judge: Any,
    essay,
    trait_subset: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """安全跑一篇 essay；异常返回 fallback dict"""
    try:
        return await judge.ascore(
            essay_text=essay.essay,
            essay_prompt=essay.raw.get("essay_prompt", ""),
            trait_subset=trait_subset,
            overall_score_holistic=essay.domain1_score,
        )
    except Exception as e:
        logger.error(f"Essay {essay.essay_id} score failed: {e}")
        return {
            "total_score": 0,
            "traits": [],
            "agreement": 0.0,
            "confidence_level": "low",
            "requires_human_review": True,
            "fallback_used": True,
            "reasoning": f"experiment-level exception: {type(e).__name__}",
            "overall_score_holistic": essay.domain1_score,
            "_error": str(e),
        }


async def _run_one_system(
    system_name: str,
    judge: Any,
    essays: List,
    trait_subset: Optional[List[str]],
    concurrency: int = 4,
) -> List[Dict[str, Any]]:
    """对所有 essays 跑同一个 judge（并发，避免 rate limit）"""
    sem = asyncio.Semaphore(concurrency)

    async def task(essay):
        async with sem:
            return await _score_one_essay(judge, essay, trait_subset)

    logger.info(f"[{system_name}] scoring {len(essays)} essays (concurrency={concurrency})...")
    return await asyncio.gather(*(task(e) for e in essays))


def _pearson(xs: List[float], ys: List[float]) -> float:
    if not xs or len(xs) != len(ys):
        return 0.0
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = (sum((x - mx) ** 2 for x in xs)) ** 0.5
    dy = (sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / (dx * dy) if dx * dy > 0 else 0.0


async def _async_main(args) -> Dict[str, Any]:
    from .data_loader import load_asap, quadratic_weighted_kappa
    from .metrics import compute_all_metrics

    # 加载 ASAP
    essays = load_asap(
        args.asap_csv,
        essay_set_filter=[args.essay_set] if args.essay_set else None,
        limit=args.limit,
    )
    logger.info(f"Loaded {len(essays)} essays from {args.asap_csv}")
    if not essays:
        logger.error("No essays loaded; abort")
        return {}

    # 决定 trait_subset：用第一个 essay 可用的 traits（如果 set 有 trait scores）
    trait_subset = None
    if essays[0].trait_scores:
        trait_subset = list(essays[0].trait_scores.keys())
        logger.info(f"Using trait subset: {trait_subset}")

    # 构造 systems
    systems = _build_systems(args.systems.split(","), score_range=(1, args.max_score))

    per_system: Dict[str, Dict[str, Any]] = {}
    for name, judge in systems.items():
        outputs = await _run_one_system(name, judge, essays, trait_subset, args.concurrency)

        # 计算 QWK / Pearson（用 total_score vs holistic GT）
        gt_scores = [e.domain1_score for e in essays if e.domain1_score is not None]
        if gt_scores and len(gt_scores) == len(outputs):
            pred_scores = [o.get("total_score", 0) for o in outputs]
            qwk = quadratic_weighted_kappa(
                pred_scores, [int(round(g)) for g in gt_scores]
            )
            pearson = _pearson(pred_scores, gt_scores)
        else:
            qwk, pearson = 0.0, 0.0

        # explainability metrics
        report = compute_all_metrics(
            outputs=outputs,
            essays=[e.essay for e in essays],
            gt_scores=gt_scores if gt_scores else None,
        )

        per_system[name] = {
            "outputs": outputs,
            "qwk": round(qwk, 4),
            "pearson": round(pearson, 4),
            "explainability": report.to_dict(),
        }
        logger.info(
            f"[{name}] QWK={qwk:.3f} Pearson={pearson:.3f} "
            f"EGR={report.evidence_grounded_recall:.3f} "
            f"CTC={report.cross_trait_consistency_rate:.3f}"
        )

    return {
        "config": {
            "asap_csv": str(args.asap_csv),
            "essay_set": args.essay_set,
            "limit": args.limit,
            "n_essays": len(essays),
            "systems": list(systems.keys()),
            "trait_subset": trait_subset,
        },
        "per_system": per_system,
    }


def main():
    parser = argparse.ArgumentParser(description="AES experiment runner — EMNLP 2026")
    parser.add_argument("--asap-csv", required=True, help="Path to ASAP 2.0 CSV/TSV")
    parser.add_argument("--essay-set", type=int, default=None, help="Filter by essay_set")
    parser.add_argument("--limit", type=int, default=None, help="Max essays to score")
    parser.add_argument(
        "--systems",
        default="schemajudge,vanilla,geval,mts_only",
        help="Comma-separated: schemajudge,schemajudge_single,vanilla,geval,mts_only",
    )
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent essays per system")
    parser.add_argument("--max-score", type=int, default=6, help="Max trait score (default 6 for ASAP 2.0)")
    parser.add_argument("--output", default="results/asap_run.json", help="Output JSON path")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    result = asyncio.run(_async_main(args))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"Results saved to {output_path}")

    # 打印简要 summary
    print("\n=== Summary ===")
    for name, data in (result.get("per_system") or {}).items():
        print(
            f"  {name:25s}  QWK={data['qwk']:.3f}  Pearson={data['pearson']:.3f}  "
            f"EGR={data['explainability']['evidence_grounded_recall']:.3f}  "
            f"CTC={data['explainability']['cross_trait_consistency_rate']:.3f}"
        )


if __name__ == "__main__":
    main()
