"""
Agent 共享工具函数

模块级函数，供多个 agent 复用：
- validate_quote_in_answer：fuzzy match 验证 evidence quote 是否出现在 answer 中
- normalize_text：归一化文本（去标点、空白、转小写）

提取自 ScoringAgent，目的是让 SummaryAgent 也能用同一套校验逻辑（保持 quote 校验
策略一致），避免「ScoringAgent quote 严格但 SummaryAgent answer_snippet 宽松」的
不对称漏洞。
"""

from __future__ import annotations

import re

# --- 常量（与 ScoringAgent 中的保持一致） ---

# Quote fuzzy match 阈值：用 recall（quote 的多少 3-gram 出现在 answer 中）而非 Jaccard。
# 理由：Jaccard 是对称度量，长 answer + 短 quote 时 |union| 被 answer 拉大，导致合理
# paraphrase 的 Jaccard 偏低（如 7/23=0.30）。recall 只看 quote 的覆盖度（quote 是否
# 大部分来自 answer），更契合「verify quote 来自 answer」的语义。
_QUOTE_RECALL_MIN = 0.6

# Quote 切换 substring vs n-gram 的字符长度阈值
_QUOTE_SHORT_CUTOFF = 8

# 0-分契约的特殊标记（永远视为合法 evidence_quote / answer_snippet）
_NO_SOLUTION_MARKERS = (
    "no valid solution",
    "no valid essay",         # AES instantiation 用此标记
    "no answer",
    "(empty)",
    "无有效解答",
    "无有效内容",
    "未答",
    "无回答",
    "(security_violation)",  # SummaryAgent 安全终止专用占位
    "(fallback)",            # SummaryAgent 降级占位
    "(auto-filled)",         # SummaryAgent 补全占位
    "vanilla baseline",       # AES baselines 占位
    "g-eval baseline",
    "mts-only baseline",
)


def normalize_text(text: str) -> str:
    """归一化文本：去标点、空白、转小写。中文/英文通用。"""
    return re.sub(r"[\s\W_]+", "", text or "").lower()


def validate_quote_in_answer(quote: str, answer: str) -> bool:
    """
    fuzzy match：归一化后 substring 或字符 3-gram recall ≥ 阈值。

    校验策略：
    - 0 分契约 / fallback / 占位标记 → 永远视为合法
    - 短引用（< 8 字符）走严格 substring（避免歧义）
    - 长引用：先尝试 substring，再 quote-recall（quote 的多少 3-gram 出现在 answer 中）≥ 0.6

    使用 recall 而非 Jaccard 的原因：长 answer + 短 paraphrase quote 时 Jaccard 会被
    answer 的 n-gram 数量稀释（合理 paraphrase 也只有 0.3 Jaccard），但 recall 不受影响。

    使用场景：
    - ScoringAgent: 校验 DimensionScore.evidence_quote 是否在候选人 answer 中
    - SummaryAgent: 校验 DecisionEvidence.answer_snippet 是否在该 turn 的 answer 中
    """
    if not quote:
        return False

    # 0 分契约 / fallback / 占位的特殊标记
    ql = quote.lower()
    if any(s in ql for s in _NO_SOLUTION_MARKERS):
        return True

    nq = normalize_text(quote)
    na = normalize_text(answer)
    if not nq or not na:
        return False

    # 严格 substring（短引用）
    if len(nq) < _QUOTE_SHORT_CUTOFF:
        return nq in na

    # 长引用：先尝试 substring
    if nq in na:
        return True
    if len(nq) < 3 or len(na) < 3:
        return nq in na

    # n-gram recall：quote 的 3-gram 中有多少出现在 answer 中
    ngrams_q = {nq[i : i + 3] for i in range(len(nq) - 2)}
    ngrams_a = {na[i : i + 3] for i in range(len(na) - 2)}
    if not ngrams_q:
        return False
    recall = len(ngrams_q & ngrams_a) / len(ngrams_q)
    return recall >= _QUOTE_RECALL_MIN
