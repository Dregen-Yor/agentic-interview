"""
SummaryAgent v3 — RULERS evidence triple + BAS selective prediction (W1.3 重构)

论文锚点：
- RULERS (Hong 2026, arXiv:2601.08654): evidence-anchored decoding，决策必须可审计
- BAS (arXiv:2604.03216): selective prediction，边界情况建议 abstain（人工复核）

核心改动 vs v2：
- 接收 dimension_history（每轮 5 维度数据），prompt 强制要求生成 decision_evidence
- 输出新增 boundary_case / requires_human_review / decision_confidence / abstain_reason
- 自动 boundary case 检测 + post-validation：LLM 漏标时强制纠正
- 兼容旧 score_details 结构（v2 数据无 dimensions 字段时退回 score+breakdown）
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base_agent import BaseAgent
from .schemas import DecisionEvidence, SummaryOutput
from .utils import validate_quote_in_answer


# 边界带（与 prompt 中保持一致）
_BOUNDARY_BANDS = [(4.5, 5.5), (6.5, 7.5), (8.0, 9.0)]

# overall_score 与 qa_history mean 的容忍偏差（P0-2）
# LLM 可能整体校准（看到 boundary case 整体压低/抬高），允许 ±0.5；超过则强制覆盖
_OVERALL_SCORE_TOLERANCE = 0.5

# 维度顺序
_DIM_KEYS = [
    "math_logic",
    "reasoning_rigor",
    "communication",
    "collaboration",
    "growth_potential",
]

# 安全终止时的最低 evidence 占位（绕开 schema min_length=3）
_SECURITY_TERMINATION_PLACEHOLDER_EVIDENCE = [
    DecisionEvidence(
        turn_index=0,
        dimension="reasoning_rigor",
        observed_level="LOW",
        rubric_clause="安全违规终止：候选人在面试中触发了安全策略",
        answer_snippet="(security_violation)",
        impact="negative",
    ),
    DecisionEvidence(
        turn_index=0,
        dimension="communication",
        observed_level="LOW",
        rubric_clause="安全违规终止：候选人在面试中触发了安全策略",
        answer_snippet="(security_violation)",
        impact="negative",
    ),
    DecisionEvidence(
        turn_index=0,
        dimension="growth_potential",
        observed_level="LOW",
        rubric_clause="安全违规终止：候选人在面试中触发了安全策略",
        answer_snippet="(security_violation)",
        impact="negative",
    ),
]


def _is_boundary_score(score: float) -> bool:
    return any(lo <= score <= hi for lo, hi in _BOUNDARY_BANDS)


def _extract_dim_history_text(qa_history: List[Dict[str, Any]]) -> str:
    """格式化每轮的 5 维度数据为文本（供 LLM 引用 turn_index）"""
    lines = []
    for i, qa in enumerate(qa_history):
        sd = qa.get("score_details") or {}
        dims = sd.get("dimensions") or []
        agreement = sd.get("agreement", 1.0)
        confidence = sd.get("confidence_level", "medium")
        fallback = sd.get("fallback_used", False)
        lines.append(
            f"--- Turn {i} (agreement={agreement}, conf={confidence}, fallback={fallback}) ---"
        )
        lines.append(f"Q: {qa.get('question', '')[:200]}")
        lines.append(f"A: {qa.get('answer', '')[:300]}")
        if dims:
            for d in dims:
                if isinstance(d, dict):
                    lines.append(
                        f"  {d.get('dimension')}: {d.get('level')} "
                        f"(score={d.get('score')}, conf={d.get('confidence')})"
                    )
                    snippet = d.get("evidence_quote", "")[:80]
                    if snippet:
                        lines.append(f"    quote: {snippet}")
        else:
            # v2 旧数据兼容：只有 score+breakdown
            score = sd.get("score", "?")
            breakdown = sd.get("breakdown", {})
            lines.append(f"  (legacy) score={score}, breakdown={breakdown}")
        lines.append("")
    return "\n".join(lines) if lines else "(no turns recorded)"


def _avg_agreement(qa_history: List[Dict[str, Any]]) -> float:
    """计算每轮 score_details.agreement 的均值"""
    vals = []
    for qa in qa_history:
        sd = qa.get("score_details") or {}
        a = sd.get("agreement")
        if isinstance(a, (int, float)):
            vals.append(float(a))
    return sum(vals) / len(vals) if vals else 1.0


def _any_fallback(qa_history: List[Dict[str, Any]]) -> bool:
    return any((qa.get("score_details") or {}).get("fallback_used") for qa in qa_history)


def _any_low_confidence(qa_history: List[Dict[str, Any]]) -> bool:
    return any(
        (qa.get("score_details") or {}).get("confidence_level") == "low"
        for qa in qa_history
    )


def _compute_actual_mean(qa_history: List[Dict[str, Any]]) -> Optional[float]:
    """
    从 qa_history 提取所有有效 score（>0），返回算术平均；
    无有效分数时返回 None（让调用方决定 fallback）。

    用于 P0-2 一致性校验：overall_score 必须 ≈ 这个 mean。
    """
    scores: List[float] = []
    for qa in qa_history:
        sd = qa.get("score_details") or {}
        s = sd.get("score")
        if isinstance(s, (int, float)) and s > 0:
            scores.append(float(s))
    if not scores:
        return None
    return sum(scores) / len(scores)


class SummaryAgent(BaseAgent):
    """总结智能体 v3 — RULERS evidence triple + BAS selective prediction"""

    prompt_name = "summary_agent"
    output_schema = SummaryOutput

    def __init__(self, model):
        super().__init__(model, "SummaryAgent")
        self.logger = logging.getLogger("interview.agents.summary_agent")

    # ------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------

    async def aprocess(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步生成总结。
        input_data:
          candidate_name, resume_data, qa_history, average_score, security_summary,
          [security_termination], [termination_reason]
        """
        candidate_name = input_data.get("candidate_name", "")
        resume_data = input_data.get("resume_data", {})
        qa_history: List[Dict[str, Any]] = input_data.get("qa_history", [])
        average_score = input_data.get("average_score", 0.0)
        security_summary = input_data.get("security_summary", {})
        is_security_termination = bool(input_data.get("security_termination"))

        # 安全终止：直接走专用降级（避开 LLM 调用，因为输入数据少）
        if is_security_termination:
            return self._security_termination_summary(
                candidate_name, input_data.get("termination_reason", ""), qa_history
            )

        # 构建详细面试报告（注入 human_template）
        interview_report = self._build_interview_report(
            candidate_name, resume_data, qa_history, average_score, security_summary
        )
        dimension_history = _extract_dim_history_text(qa_history)
        avg_agreement = _avg_agreement(qa_history)
        any_fallback = _any_fallback(qa_history)
        pre_detected_boundary = _is_boundary_score(float(average_score))

        human_text = self.prompt.format_human(
            interview_report=interview_report,
            dimension_history=dimension_history,
            avg_agreement=f"{avg_agreement:.2f}",
            any_fallback=str(any_fallback),
            pre_detected_boundary=str(pre_detected_boundary),
        )

        try:
            result: SummaryOutput = await self.ainvoke_structured(human_text)
            data = result.model_dump(mode="json")
        except Exception as e:
            self.logger.error(f"SummaryAgent 异常，使用降级总结: {e}")
            return self._generate_fallback_summary(candidate_name, average_score, qa_history)

        # ----- post-validation: 强制 boundary / review 一致性 -----
        data = self._validate_summary_result(data, average_score, qa_history)
        data["generated_at"] = datetime.now().isoformat()
        data["candidate_name"] = candidate_name
        return data

    # ------------------------------------------------------------
    # 报告构造
    # ------------------------------------------------------------

    def _build_interview_report(
        self,
        candidate_name: str,
        resume_data: Dict[str, Any],
        qa_history: List[Dict[str, Any]],
        average_score: float,
        security_summary: Dict[str, Any],
    ) -> str:
        """构建详细的面试报告（兼容 v2 / v3 score_details）"""
        report_parts: List[str] = []

        report_parts.append(f"候选人: {candidate_name}")
        report_parts.append(f"面试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_parts.append(f"总题目数: {len(qa_history)}")
        report_parts.append(f"平均分: {average_score:.2f}/10")

        if resume_data:
            report_parts.append("\n=== 候选人背景 ===")
            try:
                resume_text = json.dumps(resume_data, ensure_ascii=False, indent=2)[:2000]
            except Exception:
                resume_text = str(resume_data)[:2000]
            report_parts.append(f"简历信息: {resume_text}")

        report_parts.append("\n=== 面试问答记录 ===")
        for i, qa in enumerate(qa_history):
            report_parts.append(f"\n--- 第{i + 1}题 (turn_index={i}) ---")
            report_parts.append(f"问题: {qa.get('question', '未记录')}")

            qd = qa.get("question_data")
            if qd:
                if isinstance(qd, dict):
                    report_parts.append(f"问题类型: {qd.get('type', 'N/A')}")
                    report_parts.append(f"难度等级: {qd.get('difficulty', 'N/A')}")
                    if "reasoning" in qd:
                        report_parts.append(f"选题原因: {qd['reasoning']}")

            report_parts.append(f"回答: {qa.get('answer', '未记录')}")

            sd = qa.get("score_details") or {}
            score = sd.get("score", 0)
            report_parts.append(f"得分: {score}/10")

            # v3：dimensions 数组
            dims = sd.get("dimensions") or []
            if dims:
                report_parts.append("维度评分:")
                for d in dims:
                    if isinstance(d, dict):
                        report_parts.append(
                            f"  - {d.get('dimension')}: {d.get('level')} "
                            f"({d.get('score')}, conf={d.get('confidence')})"
                        )
            else:
                # v2 兼容
                bd = sd.get("breakdown", {})
                if bd:
                    report_parts.append(f"维度分（legacy）: {bd}")

            if "reasoning" in sd:
                report_parts.append(f"评分理由: {sd['reasoning']}")

        if security_summary:
            report_parts.append("\n=== 安全检测摘要 ===")
            report_parts.append(f"总体风险等级: {security_summary.get('overall_risk', 'unknown')}")
            report_parts.append(f"安全警报数量: {security_summary.get('total_alerts', 0)}")
            if security_summary.get("security_alerts"):
                report_parts.append("安全问题详情:")
                for alert in security_summary["security_alerts"]:
                    report_parts.append(
                        f"  - 问题{alert.get('question_id', '?')}: {alert.get('issues', [])}"
                    )

        # 分数统计（保留 v2 行为）
        scores = []
        for qa in qa_history:
            sd = qa.get("score_details") or {}
            s = sd.get("score")
            if isinstance(s, (int, float)) and s > 0:
                scores.append(int(s))
        if scores:
            report_parts.append("\n=== 分数统计 ===")
            report_parts.append(f"最高分: {max(scores)}/10")
            report_parts.append(f"最低分: {min(scores)}/10")
            report_parts.append(f"平均分: {sum(scores)/len(scores):.2f}/10")
            high_scores = sum(1 for s in scores if s >= 7)
            medium_scores = sum(1 for s in scores if 4 <= s < 7)
            low_scores = sum(1 for s in scores if s < 4)
            report_parts.append(f"高分题目(≥7分): {high_scores}题")
            report_parts.append(f"中等题目(4-6分): {medium_scores}题")
            report_parts.append(f"低分题目(<4分): {low_scores}题")

        return "\n".join(report_parts)

    # ------------------------------------------------------------
    # Post-validation：强制 boundary / review 一致性
    # ------------------------------------------------------------

    def _validate_summary_result(
        self,
        data: Dict[str, Any],
        average_score: float,
        qa_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """对齐分数与等级，自动校正 boundary_case / requires_human_review

        v3.1 新增：
        - P0-2: overall_score 必须 ≈ mean(qa scores)，超过容忍度则强制覆盖
        - P0-3: decision_evidence.turn_index 必须在 [0, len(qa_history)) 范围内
        - P0-4: decision_evidence.answer_snippet 必须 fuzzy match 该轮的 answer
        """
        n_turns = len(qa_history)

        # ============================================================
        # P0-2: overall_score 与 qa mean 一致性
        # ============================================================
        actual_mean = _compute_actual_mean(qa_history)
        if actual_mean is None:
            # 无有效轮分数 → fallback 到 input 的 average_score
            actual_mean = float(average_score) if average_score else 0.0

        llm_score = data.get("overall_score")
        if llm_score is None:
            data["overall_score"] = round(actual_mean, 1)
        else:
            try:
                llm_score_f = float(llm_score)
            except (TypeError, ValueError):
                llm_score_f = actual_mean
            if abs(llm_score_f - actual_mean) > _OVERALL_SCORE_TOLERANCE:
                self.logger.warning(
                    "P0-2 修正：LLM overall_score=%.2f 与 qa 实际 mean=%.2f 偏差 > %.1f，覆盖",
                    llm_score_f, actual_mean, _OVERALL_SCORE_TOLERANCE,
                )
                data["overall_score"] = round(actual_mean, 1)
                data["_overall_score_corrected"] = True
            else:
                data["overall_score"] = round(llm_score_f, 1)

        score = float(data["overall_score"])

        # ============================================================
        # grade ↔ score 一致性（v2 行为保留）
        # ============================================================
        expected_grade = self._score_to_grade(score)
        data["final_grade"] = expected_grade
        data["final_decision"] = self._decision_by_grade(expected_grade)

        # ============================================================
        # P0-3 + P0-4: decision_evidence 校验
        # ============================================================
        raw_evidence = data.get("decision_evidence", []) or []
        invalid_turn_count = 0
        invalid_snippet_count = 0
        valid_evidence: List[Dict[str, Any]] = []
        for ev in raw_evidence:
            if not isinstance(ev, dict):
                invalid_turn_count += 1
                continue

            # P0-3: turn_index 越界检查
            ti = ev.get("turn_index")
            if not isinstance(ti, int) or ti < 0 or (n_turns > 0 and ti >= n_turns):
                invalid_turn_count += 1
                continue

            # P0-4: answer_snippet 必须出现在该轮的 answer 中
            snippet = ev.get("answer_snippet") or ""
            if n_turns > 0:
                actual_answer = qa_history[ti].get("answer", "") or ""
                if not validate_quote_in_answer(snippet, actual_answer):
                    invalid_snippet_count += 1
                    continue

            valid_evidence.append(ev)

        if invalid_turn_count + invalid_snippet_count > 0:
            self.logger.warning(
                "decision_evidence 过滤：%d 条 turn_index 越界，%d 条 answer_snippet 不在 answer 中",
                invalid_turn_count, invalid_snippet_count,
            )

        # 过滤后 < 3 → 从 qa_history 自动补占位（保持 schema min_length=3 不破）
        if len(valid_evidence) < 3 and n_turns > 0:
            valid_evidence = self._pad_evidence_with_placeholders(valid_evidence, qa_history)

        data["decision_evidence"] = valid_evidence

        # ============================================================
        # boundary_case + requires_human_review（基于校正后的 score）
        # ============================================================
        boundary = _is_boundary_score(score)
        data["boundary_case"] = boundary

        avg_ag = _avg_agreement(qa_history)
        any_fb = _any_fallback(qa_history)
        any_low_conf = _any_low_confidence(qa_history)
        forced_review = boundary or any_fb or avg_ag < 0.6 or any_low_conf
        if forced_review:
            data["requires_human_review"] = True

        if data.get("requires_human_review") and not data.get("abstain_reason"):
            reasons = []
            if boundary:
                reasons.append(f"overall_score={score:.1f} 落在边界带")
            if any_fb:
                reasons.append("某轮评分使用了 fallback")
            if avg_ag < 0.6:
                reasons.append(f"多模型平均一致性={avg_ag:.2f} < 0.6")
            if any_low_conf:
                reasons.append("某轮 confidence_level=low")
            if data.get("_overall_score_corrected"):
                reasons.append("LLM 的 overall_score 与实际 mean 偏差较大已被覆盖")
            data["abstain_reason"] = "建议人工复核：" + "；".join(reasons)

        # decision_confidence 推导
        if forced_review:
            data["decision_confidence"] = "low"
        elif avg_ag >= 0.8 and not boundary:
            data["decision_confidence"] = "high"
        else:
            data["decision_confidence"] = data.get("decision_confidence", "medium")

        # 清理内部临时标记
        data.pop("_overall_score_corrected", None)
        return data

    def _pad_evidence_with_placeholders(
        self,
        existing: List[Dict[str, Any]],
        qa_history: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """过滤后 evidence < 3 时，从 qa_history 中分数最低的轮挑出来补占位。

        占位 evidence 的特点：
        - turn_index 合法（来自真实 qa_history）
        - dimension/level/rubric_clause 来自该轮的实际 score_details.dimensions（v3）
        - answer_snippet 用该轮 answer 的前 80 字符（保证 fuzzy match 必过）
        - impact = neutral（占位，不主张方向）
        """
        used_turns = {ev["turn_index"] for ev in existing}
        # 按分数升序（先补低分轮，更可能是问题点）
        sorted_qa = sorted(
            enumerate(qa_history),
            key=lambda p: (p[1].get("score_details") or {}).get("score", 5),
        )

        result = list(existing)
        for idx, qa in sorted_qa:
            if len(result) >= 3:
                break
            if idx in used_turns:
                continue

            sd = qa.get("score_details") or {}
            dims = sd.get("dimensions") or []
            chosen_dim = dims[0] if dims and isinstance(dims[0], dict) else None

            if chosen_dim:
                dimension = chosen_dim.get("dimension", "math_logic")
                level = chosen_dim.get("level", "MEDIUM")
                rubric = chosen_dim.get("rubric_clause") or "(auto-filled placeholder)"
            else:
                dimension = "math_logic"
                level = "MEDIUM"
                rubric = "(auto-filled placeholder)"

            answer_text = qa.get("answer") or ""
            # 选 answer 的前 80 字作为 snippet（保证 fuzzy 校验过）
            snippet = answer_text[:80] if answer_text else "(no answer)"

            result.append({
                "turn_index": idx,
                "dimension": dimension,
                "observed_level": level,
                "rubric_clause": rubric,
                "answer_snippet": snippet,
                "impact": "neutral",
            })
            used_turns.add(idx)

        # 极端情况：qa_history 全用过仍 < 3 → 重复使用 turn_index=0 占位
        # （保证 schema min_length=3 不破，但前端会展示重复 turn）
        while len(result) < 3:
            if qa_history:
                result.append({
                    "turn_index": 0,
                    "dimension": "math_logic",
                    "observed_level": "MEDIUM",
                    "rubric_clause": "(auto-filled placeholder)",
                    "answer_snippet": (qa_history[0].get("answer") or "(no answer)")[:80],
                    "impact": "neutral",
                })
            else:
                # qa_history 空 — 这是 fallback 路径，保留原占位风格
                result.append({
                    "turn_index": 0,
                    "dimension": "math_logic",
                    "observed_level": "MEDIUM",
                    "rubric_clause": "(no qa_history)",
                    "answer_snippet": "(no answer)",
                    "impact": "neutral",
                })
        return result

    def _score_to_grade(self, score: float) -> str:
        if score >= 8.5:
            return "A"
        elif score >= 7.0:
            return "B"
        elif score >= 5.0:
            return "C"
        else:
            return "D"

    def _decision_by_grade(self, grade: str) -> str:
        if grade == "A":
            return "accept"
        elif grade == "B":
            return "conditional"
        else:
            return "reject"

    # ------------------------------------------------------------
    # Fallback / 安全终止
    # ------------------------------------------------------------

    def _generate_fallback_summary(
        self,
        candidate_name: str,
        average_score: float,
        qa_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """LLM 调用失败时的降级总结（仍输出合法的 v3 schema）"""
        score = float(max(0, average_score))
        grade = self._score_to_grade(score)
        # 至少 3 条 decision_evidence 占位（标 confidence=low）
        evidence_list: List[DecisionEvidence] = []
        # 优先用真实 qa_history 的低分项
        sorted_qa = sorted(
            enumerate(qa_history),
            key=lambda p: (p[1].get("score_details") or {}).get("score", 5),
        )
        for idx, qa in sorted_qa[: min(3, len(qa_history))]:
            sd = qa.get("score_details") or {}
            dims = sd.get("dimensions") or []
            chosen_dim = dims[0] if dims else None
            if isinstance(chosen_dim, dict):
                evidence_list.append(
                    DecisionEvidence(
                        turn_index=idx,
                        dimension=chosen_dim.get("dimension", "math_logic"),
                        observed_level=chosen_dim.get("level", "MEDIUM"),
                        rubric_clause=chosen_dim.get("rubric_clause", "(fallback)"),
                        answer_snippet=chosen_dim.get("evidence_quote", "(fallback)")[:80] or "(fallback)",
                        impact="neutral",
                    )
                )
            else:
                evidence_list.append(
                    DecisionEvidence(
                        turn_index=idx,
                        dimension="math_logic",
                        observed_level="MEDIUM",
                        rubric_clause="(fallback: 降级总结)",
                        answer_snippet="(fallback)",
                        impact="neutral",
                    )
                )
        # 不够 3 条 → 补占位
        while len(evidence_list) < 3:
            evidence_list.append(
                DecisionEvidence(
                    turn_index=0,
                    dimension="reasoning_rigor",
                    observed_level="MEDIUM",
                    rubric_clause="(fallback: 降级总结)",
                    answer_snippet="(fallback)",
                    impact="neutral",
                )
            )

        try:
            output = SummaryOutput(
                final_grade=grade,
                final_decision=self._decision_by_grade(grade),
                overall_score=round(score, 1),
                summary="由于系统问题，详细总结生成失败，建议人工复核面试记录。",
                strengths=[],
                weaknesses=["系统评估异常"],
                decision_evidence=evidence_list,
                boundary_case=_is_boundary_score(score),
                decision_confidence="low",
                requires_human_review=True,
                abstain_reason="SummaryAgent 调用失败，已使用降级总结。",
            )
            data = output.model_dump(mode="json")
        except Exception as e:
            self.logger.error(f"Fallback SummaryOutput 校验失败: {e}")
            data = {
                "final_grade": grade,
                "final_decision": self._decision_by_grade(grade),
                "overall_score": round(score, 1),
                "summary": "系统问题，无法生成总结。建议人工复核。",
                "strengths": [],
                "weaknesses": ["系统评估异常"],
                "decision_evidence": [e.model_dump(mode="json") for e in evidence_list],
                "boundary_case": _is_boundary_score(score),
                "decision_confidence": "low",
                "requires_human_review": True,
                "abstain_reason": "SummaryAgent 双重降级",
            }
        data["generated_at"] = datetime.now().isoformat()
        data["candidate_name"] = candidate_name
        data["note"] = "Fallback summary"
        return data

    def _security_termination_summary(
        self,
        candidate_name: str,
        termination_reason: str,
        qa_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """安全终止专用降级总结"""
        last_turn_idx = max(0, len(qa_history) - 1)
        evidence = [
            DecisionEvidence(
                turn_index=last_turn_idx,
                dimension="reasoning_rigor",
                observed_level="LOW",
                rubric_clause="安全违规终止：候选人在面试中触发了安全策略",
                answer_snippet=(qa_history[-1].get("answer", "") if qa_history else "")[:80]
                or "(security_violation)",
                impact="negative",
            ),
            DecisionEvidence(
                turn_index=last_turn_idx,
                dimension="communication",
                observed_level="LOW",
                rubric_clause="安全违规：违反面试规则",
                answer_snippet="(security_violation)",
                impact="negative",
            ),
            DecisionEvidence(
                turn_index=last_turn_idx,
                dimension="growth_potential",
                observed_level="LOW",
                rubric_clause="安全违规：缺乏诚信",
                answer_snippet="(security_violation)",
                impact="negative",
            ),
        ]
        try:
            output = SummaryOutput(
                final_grade="D",
                final_decision="reject",
                overall_score=0.0,
                summary=f"面试因安全违规提前终止。{termination_reason}",
                strengths=[],
                weaknesses=["违反面试规则", "诚信问题"],
                decision_evidence=evidence,
                boundary_case=False,
                decision_confidence="high",
                requires_human_review=False,
                abstain_reason=None,
            )
            data = output.model_dump(mode="json")
        except Exception as e:
            self.logger.error(f"安全终止 SummaryOutput 校验失败: {e}")
            data = {
                "final_grade": "D",
                "final_decision": "reject",
                "overall_score": 0.0,
                "summary": f"面试因安全违规提前终止。{termination_reason}",
                "decision_evidence": [e.model_dump(mode="json") for e in evidence],
                "boundary_case": False,
                "decision_confidence": "high",
                "requires_human_review": False,
            }
        data["generated_at"] = datetime.now().isoformat()
        data["candidate_name"] = candidate_name
        data["security_termination"] = True
        return data
