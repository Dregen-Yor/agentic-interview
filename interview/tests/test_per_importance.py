"""
W3.3 单测：PER (Prioritized Experience Replay) importance

论文锚点：Schaul 2015, arXiv:1511.05952
公式：priority = (|TD-error| + ε) ** α，α=0.6（rank-based variant 推荐值）

运行：
  uv run python -m unittest interview.tests.test_per_importance -v
"""

from __future__ import annotations

import logging
import unittest

from interview.agents.memory.store import MemoryStore


def _new_store():
    """绕过 RetrievalSystem 依赖创建一个 MemoryStore 用于测试 _compute_importance"""
    ms = MemoryStore.__new__(MemoryStore)
    ms.logger = logging.getLogger("test")
    return ms


class PERFormula(unittest.TestCase):

    def setUp(self):
        self.ms = _new_store()

    def test_score_equal_baseline_low_importance(self):
        # baseline=5, score=5 → TD-error=0, base ≈ ε^α / 5^α = 0.063 / 2.626 ≈ 0.024
        # + 0.10 (medium difficulty) = 0.124
        imp = self.ms._compute_importance(5, "medium", False, baseline_score=5.0)
        self.assertLess(imp, 0.20)
        self.assertGreater(imp, 0.05)

    def test_max_distance_capped_at_1(self):
        # baseline=5, score=10 → TD-error=5, base = 1.0 + 0.1 → clipped to 1.0
        imp_high = self.ms._compute_importance(10, "medium", False, baseline_score=5.0)
        # baseline=5, score=0 → TD-error=5, base = 1.0 → 同
        imp_low = self.ms._compute_importance(0, "medium", False, baseline_score=5.0)
        self.assertGreaterEqual(imp_high, 0.95)
        self.assertGreaterEqual(imp_low, 0.95)
        self.assertLessEqual(imp_high, 1.0)
        self.assertLessEqual(imp_low, 1.0)

    def test_security_event_adds_bonus(self):
        # 同 score+baseline，安全事件应增加 0.30
        no_sec = self.ms._compute_importance(5, "medium", False, baseline_score=5.0)
        with_sec = self.ms._compute_importance(5, "medium", True, baseline_score=5.0)
        self.assertAlmostEqual(with_sec - no_sec, 0.30, places=2)

    def test_difficulty_bonus(self):
        # 难度 hard +0.20 vs easy +0.0
        easy = self.ms._compute_importance(5, "easy", False, baseline_score=5.0)
        hard = self.ms._compute_importance(5, "hard", False, baseline_score=5.0)
        self.assertAlmostEqual(hard - easy, 0.20, places=2)

    def test_personalized_baseline(self):
        """高分候选人突然失分 → 重要；低分候选人偶尔失分 → 也重要"""
        # 候选人均分 7（高表现）
        imp_persistent_high = self.ms._compute_importance(7, "medium", False, baseline_score=7.0)
        # 突然失分到 2 → 重要
        imp_sudden_drop = self.ms._compute_importance(2, "medium", False, baseline_score=7.0)
        self.assertLess(imp_persistent_high, 0.20)
        self.assertGreater(imp_sudden_drop, imp_persistent_high * 4)

    def test_baseline_default_5(self):
        """不传 baseline_score 时默认 5.0（向后兼容）"""
        imp_default = self.ms._compute_importance(7, "medium", False)
        imp_explicit = self.ms._compute_importance(7, "medium", False, baseline_score=5.0)
        self.assertEqual(imp_default, imp_explicit)


class PERMonotonicity(unittest.TestCase):
    """PER importance 应该是 |score - baseline| 的单调函数"""

    def setUp(self):
        self.ms = _new_store()

    def test_monotonic_in_distance(self):
        # 固定 baseline=5，score 从 5 → 0/10，importance 应递增
        baseline = 5.0
        prev = -1
        for d in range(0, 6):
            imp_high = self.ms._compute_importance(int(baseline + d), "medium", False, baseline_score=baseline)
            self.assertGreaterEqual(
                imp_high, prev,
                f"importance 应在距离 {d} 时不减"
            )
            prev = imp_high


if __name__ == "__main__":
    unittest.main()
