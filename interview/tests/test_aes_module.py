"""
AES 模块单测 — 覆盖 traits / schemas / pipeline / metrics / baselines / data_loader

不测试 LLM 实际调用（用 fake model + AsyncMock）。
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from pydantic import ValidationError

from interview.aes import TRAITS, TRAIT_KEYS, TRAIT_MAX_SCORE
from interview.aes.baselines import GEvalJudge, MTSOnlyJudge, VanillaJudge
from interview.aes.data_loader import ASAPEssay, quadratic_weighted_kappa, split_by_set
from interview.aes.metrics import (
    boundary_calibration_ece,
    compute_all_metrics,
    counterfactual_stability,
    cross_trait_consistency_rate,
    evidence_grounded_recall,
    reviewer_trust_protocol,
)
from interview.aes.pipeline import EssayScoringPipeline
from interview.aes.prompt_loader import load_aes_prompt
from interview.aes.schemas import EssayScoringOutput, TraitScore


class FakeModel:
    def __init__(self, name="fake"):
        self.model_name = name

    def with_structured_output(self, schema, include_raw=False):
        m = MagicMock()
        m.ainvoke = AsyncMock()
        return m


# ============================================================
# Traits
# ============================================================

class TraitsModule(unittest.TestCase):
    def test_5_traits_defined(self):
        self.assertEqual(len(TRAITS), 5)
        for k in ["ideas", "organization", "voice", "word_choice", "conventions"]:
            self.assertIn(k, TRAITS)

    def test_each_trait_has_3_levels(self):
        for k, t in TRAITS.items():
            self.assertEqual(set(t.levels.keys()), {"LOW", "MEDIUM", "HIGH"})
            for level, desc in t.levels.items():
                self.assertGreater(len(desc), 30, f"{k}/{level} rubric 太短")

    def test_score_range_consistency(self):
        for k, t in TRAITS.items():
            lo, hi = t.score_range
            self.assertEqual(TRAIT_MAX_SCORE[k], hi)


# ============================================================
# Schemas
# ============================================================

class SchemasModule(unittest.TestCase):
    def test_traitscore_score_in_range(self):
        ts = TraitScore(trait="ideas", level="HIGH", score=6,
                        evidence_quote="ab", rubric_clause="x")
        self.assertEqual(ts.score, 6)

    def test_traitscore_score_out_of_range(self):
        with self.assertRaises(ValidationError):
            TraitScore(trait="ideas", level="HIGH", score=10,
                       evidence_quote="ab", rubric_clause="x")

    def test_essayscoring_total_consistency(self):
        ts = [
            TraitScore(trait="ideas", level="HIGH", score=5,
                       evidence_quote="ab", rubric_clause="x"),
            TraitScore(trait="organization", level="MEDIUM", score=4,
                       evidence_quote="ab", rubric_clause="x"),
        ]
        out = EssayScoringOutput(total_score=9, traits=ts)
        self.assertEqual(out.total_score, 9)

    def test_essayscoring_inconsistent_total_rejected(self):
        ts = [TraitScore(trait="ideas", level="HIGH", score=5,
                         evidence_quote="ab", rubric_clause="x")]
        with self.assertRaises(ValidationError):
            EssayScoringOutput(total_score=10, traits=ts)

    def test_essayscoring_dup_trait_rejected(self):
        t = TraitScore(trait="ideas", level="HIGH", score=5,
                       evidence_quote="ab", rubric_clause="x")
        with self.assertRaises(ValidationError):
            EssayScoringOutput(total_score=10, traits=[t, t])


# ============================================================
# Pipeline 关键方法
# ============================================================

class PipelineUnitMethods(unittest.TestCase):
    def setUp(self):
        self.pipe = EssayScoringPipeline([FakeModel(), FakeModel()])

    def test_fallback_trait(self):
        fb = self.pipe._fallback_trait("ideas")
        self.assertEqual(fb.confidence, "low")
        self.assertEqual(fb.score, 3)  # 1-6 中位
        self.assertEqual(fb.model_name, "fallback")

    def test_aggregate_unanimous(self):
        cands = [
            TraitScore(trait="ideas", level="HIGH", score=6,
                       evidence_quote="ab", rubric_clause="x", confidence="high"),
            TraitScore(trait="ideas", level="HIGH", score=6,
                       evidence_quote="cd", rubric_clause="x", confidence="high"),
        ]
        agg = self.pipe._aggregate_ensemble("ideas", cands)
        self.assertEqual(agg.level, "HIGH")
        self.assertEqual(agg.score, 6)
        self.assertEqual(agg.confidence, "high")

    def test_aggregate_disagree(self):
        cands = [
            TraitScore(trait="ideas", level="HIGH", score=6,
                       evidence_quote="ab", rubric_clause="x", confidence="high"),
            TraitScore(trait="ideas", level="LOW", score=1,
                       evidence_quote="cd", rubric_clause="x", confidence="low"),
        ]
        agg = self.pipe._aggregate_ensemble("ideas", cands)
        self.assertEqual(agg.level, "HIGH")  # high conf 投票胜
        self.assertEqual(agg.confidence, "medium")  # 50% 同意

    def test_score_clipped_to_trait_range(self):
        # 即使 weighted 算出超过 max 也被 clip
        cands = [
            TraitScore(trait="conventions", level="HIGH", score=6,
                       evidence_quote="ab", rubric_clause="x", confidence="high"),
        ]
        agg = self.pipe._aggregate_ensemble("conventions", cands)
        self.assertLessEqual(agg.score, TRAIT_MAX_SCORE["conventions"])

    def test_compute_agreement_unanimous(self):
        same = [
            TraitScore(trait="ideas", level="HIGH", score=6,
                       evidence_quote="ab", rubric_clause="x")
        ] * 3
        ag = self.pipe._compute_agreement({"ideas": same})
        self.assertEqual(ag, 1.0)

    def test_compute_agreement_split(self):
        cands = [
            TraitScore(trait="ideas", level="HIGH", score=6,
                       evidence_quote="ab", rubric_clause="x"),
            TraitScore(trait="ideas", level="LOW", score=1,
                       evidence_quote="cd", rubric_clause="x"),
        ]
        ag = self.pipe._compute_agreement({"ideas": cands})
        self.assertEqual(ag, 0.5)


class PipelineEndToEndMock(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pipe = EssayScoringPipeline([FakeModel("m1"), FakeModel("m2")])

        async def fake_score(messages):
            content = messages[1].content if len(messages) > 1 else ""
            for k in TRAIT_KEYS:
                if f"Trait to score: {k}" in content:
                    return TraitScore(
                        trait=k, level="MEDIUM",
                        score=(TRAIT_MAX_SCORE[k] + 1) // 2,
                        evidence_quote="(no valid essay)",
                        rubric_clause="some rubric",
                        confidence="high",
                    )
            return TraitScore(
                trait="ideas", level="MEDIUM", score=3,
                evidence_quote="(no valid essay)",
                rubric_clause="x", confidence="medium",
            )

        for sm in self.pipe._structured_models:
            sm.ainvoke = AsyncMock(side_effect=fake_score)

    async def test_full_5_traits(self):
        result = await self.pipe.ascore(
            essay_text="This is a test essay about something.",
            essay_prompt="Write about your favorite hobby.",
        )
        self.assertEqual(len(result["traits"]), 5)
        self.assertFalse(result["fallback_used"])
        # total = sum(trait scores)
        self.assertEqual(result["total_score"], sum(t["score"] for t in result["traits"]))

    async def test_subset_2_traits(self):
        result = await self.pipe.ascore(
            essay_text="essay",
            trait_subset=["ideas", "conventions"],
        )
        self.assertEqual(len(result["traits"]), 2)
        trait_keys_returned = {t["trait"] for t in result["traits"]}
        self.assertEqual(trait_keys_returned, {"ideas", "conventions"})

    async def test_invalid_trait_rejected(self):
        with self.assertRaises(ValueError):
            await self.pipe.ascore(essay_text="x", trait_subset=["nonexistent_trait"])


# ============================================================
# Metrics
# ============================================================

class MetricsModule(unittest.TestCase):
    def test_evidence_grounded_recall_basic(self):
        outputs = [{
            "traits": [
                {"trait": "ideas", "evidence_quote": "归纳法证明"},
                {"trait": "organization", "evidence_quote": "(no valid essay)"},  # 特殊标记必过
                {"trait": "voice", "evidence_quote": "完全编造的话"},
            ],
        }]
        essays = ["我用归纳法证明 n=k+1"]
        res = evidence_grounded_recall(outputs, essays)
        self.assertEqual(res["n_quotes"], 3)
        # ideas (substring) + organization (special marker) 通过, voice 不通过
        self.assertEqual(res["n_grounded"], 2)
        self.assertAlmostEqual(res["recall"], 2 / 3, places=2)

    def test_cross_trait_contradiction_detected(self):
        outputs = [
            {"traits": [
                {"trait": "ideas", "level": "HIGH"},
                {"trait": "organization", "level": "LOW"},  # 矛盾对
            ]},
            {"traits": [
                {"trait": "ideas", "level": "MEDIUM"},
                {"trait": "organization", "level": "MEDIUM"},
            ]},
        ]
        res = cross_trait_consistency_rate(outputs)
        self.assertEqual(res["consistency_rate"], 0.5)
        self.assertEqual(res["n_with_contradiction"], 1)

    def test_boundary_ece(self):
        outputs = [
            {"requires_human_review": True},
            {"requires_human_review": False},
            {"requires_human_review": True},
        ]
        gt = [3.5, 5.0, 4.5]  # 3.5/4.5 是边界
        res = boundary_calibration_ece(outputs, gt, boundary_thresholds=[3.5, 4.5])
        self.assertGreaterEqual(res["ece"], 0.0)
        self.assertEqual(res["n_samples"], 3)

    def test_counterfactual_stability_identical(self):
        out = [{
            "total_score": 18,
            "traits": [{"trait": "ideas", "level": "HIGH"}],
        }]
        res = counterfactual_stability(out, out)
        self.assertEqual(res["score_stability_rate"], 1.0)
        self.assertEqual(res["level_agreement_rate"], 1.0)

    def test_counterfactual_stability_unstable(self):
        out_orig = [{
            "total_score": 18,
            "traits": [{"trait": "ideas", "level": "HIGH"}],
        }]
        out_para = [{
            "total_score": 12,  # 差 6 > tolerance 0.5
            "traits": [{"trait": "ideas", "level": "MEDIUM"}],
        }]
        res = counterfactual_stability(out_orig, out_para)
        self.assertEqual(res["score_stability_rate"], 0.0)
        self.assertEqual(res["level_agreement_rate"], 0.0)

    def test_compute_all_smoke(self):
        outputs = [{
            "traits": [{"trait": "ideas", "level": "HIGH",
                        "evidence_quote": "ab"}],
            "requires_human_review": False,
            "total_score": 5,
        }]
        report = compute_all_metrics(outputs, ["abcd ef"])
        self.assertEqual(report.n_essays, 1)
        # gt 未提供 → ece 为 nan
        import math
        self.assertTrue(math.isnan(report.boundary_calibration_ece))

    def test_reviewer_trust_protocol_present(self):
        proto = reviewer_trust_protocol()
        self.assertIn("N=30", proto)
        self.assertIn("Wilcoxon", proto)


# ============================================================
# Data loader
# ============================================================

class DataLoaderModule(unittest.TestCase):
    def test_qwk_perfect(self):
        self.assertAlmostEqual(quadratic_weighted_kappa([1, 2, 3], [1, 2, 3]), 1.0)

    def test_qwk_inverted(self):
        self.assertAlmostEqual(quadratic_weighted_kappa([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]), -1.0)

    def test_qwk_empty(self):
        self.assertEqual(quadratic_weighted_kappa([], []), 0.0)

    def test_split_by_set(self):
        es = [
            ASAPEssay(essay_id="1", essay_set=7, essay="a"),
            ASAPEssay(essay_id="2", essay_set=7, essay="b"),
            ASAPEssay(essay_id="3", essay_set=8, essay="c"),
        ]
        by_set = split_by_set(es)
        self.assertEqual(len(by_set[7]), 2)
        self.assertEqual(len(by_set[8]), 1)


# ============================================================
# Baselines（仅检查能实例化 + ascore 接口存在）
# ============================================================

class BaselinesInterface(unittest.IsolatedAsyncioTestCase):
    async def test_vanilla_ascore_interface(self):
        v = VanillaJudge(FakeModel())

        # Mock structured output
        mock_out = MagicMock()
        mock_out.overall_score = 4
        mock_out.reasoning = "decent"
        v.structured.ainvoke = AsyncMock(return_value=mock_out)

        result = await v.ascore(essay_text="x", trait_subset=["ideas"])
        self.assertEqual(result["total_score"], 4)
        self.assertEqual(len(result["traits"]), 1)

    async def test_geval_ascore_interface(self):
        g = GEvalJudge(FakeModel())

        async def fake(messages):
            from interview.aes.baselines import GEvalTraitOutput
            return GEvalTraitOutput(trait="ideas", score=5, reasoning="ok")
        g.structured.ainvoke = AsyncMock(side_effect=fake)

        result = await g.ascore(essay_text="x", trait_subset=["ideas"])
        self.assertEqual(result["traits"][0]["score"], 5)
        # G-Eval 故意不存 evidence_quote
        self.assertIn("g-eval baseline", result["traits"][0]["evidence_quote"])

    async def test_mts_only_ascore_interface(self):
        m = MTSOnlyJudge(FakeModel())

        async def fake(messages):
            from interview.aes.baselines import GEvalTraitOutput
            return GEvalTraitOutput(trait="ideas", score=4, reasoning="ok")
        m.structured.ainvoke = AsyncMock(side_effect=fake)

        result = await m.ascore(essay_text="x", trait_subset=["ideas"])
        self.assertEqual(result["traits"][0]["score"], 4)
        # MTS-only 故意不存 schema-enforced evidence
        self.assertIn("MTS-only baseline", result["traits"][0]["evidence_quote"])


# ============================================================
# Prompt loader
# ============================================================

class PromptLoaderModule(unittest.TestCase):
    def test_load_aes_trait_scoring(self):
        p = load_aes_prompt("aes_trait_scoring")
        self.assertEqual(p.name, "aes_trait_scoring")
        self.assertIn("MTS divide-and-conquer", p.system)
        self.assertIn("{{ trait_key }}", p.human)

    def test_format_human_substitutes(self):
        p = load_aes_prompt("aes_trait_scoring")
        text = p.format_human(
            trait_key="ideas",
            rubric_clause="rubric here",
            score_range="1-6",
            essay_prompt="prompt",
            essay_text="essay",
            similar_cases="(none)",
        )
        self.assertIn("ideas", text)
        self.assertIn("1-6", text)
        self.assertNotIn("{{ trait_key }}", text)


if __name__ == "__main__":
    unittest.main()
