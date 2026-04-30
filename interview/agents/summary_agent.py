"""
SummaryAgent — async + structured output (S1 + S2)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from .base_agent import BaseAgent
from .schemas import SummaryOutput


class SummaryAgent(BaseAgent):
    """总结智能体 — 仅生成总结，不直接持久化（由协调器统一保存）"""

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
        input_data: { candidate_name, resume_data, qa_history, average_score, security_summary,
                      [security_termination], [termination_reason] }
        """
        candidate_name = input_data.get("candidate_name", "")
        resume_data = input_data.get("resume_data", {})
        qa_history = input_data.get("qa_history", [])
        average_score = input_data.get("average_score", 0)
        security_summary = input_data.get("security_summary", {})

        # 构建详细面试报告（注入到 human_template）
        interview_report = self._build_interview_report(
            candidate_name, resume_data, qa_history, average_score, security_summary
        )
        human_text = self.prompt.format_human(interview_report=interview_report)

        try:
            result: SummaryOutput = await self.ainvoke_structured(human_text)
            data = result.model_dump(mode="json")

            # 校准：分数与等级一致性
            data = self._validate_summary_result(data, average_score)
            data["generated_at"] = datetime.now().isoformat()
            data["candidate_name"] = candidate_name
            return data

        except Exception as e:
            self.logger.error(f"SummaryAgent 异常，使用降级总结: {e}")
            return self._generate_fallback_summary(candidate_name, average_score)

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
        """构建详细的面试报告供 LLM 总结"""
        report_parts: List[str] = []

        report_parts.append(f"候选人: {candidate_name}")
        report_parts.append(f"面试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_parts.append(f"总题目数: {len(qa_history)}")
        report_parts.append(f"平均分: {average_score:.2f}/10")

        if resume_data:
            report_parts.append("\n=== 候选人背景 ===")
            report_parts.append(f"简历信息: {json.dumps(resume_data, ensure_ascii=False, indent=2)[:2000]}")

        report_parts.append("\n=== 面试问答记录 ===")
        for i, qa in enumerate(qa_history, 1):
            report_parts.append(f"\n--- 第{i}题 ---")
            report_parts.append(f"问题: {qa.get('question', '未记录')}")

            if qa.get("question_data"):
                qd = qa["question_data"]
                report_parts.append(f"问题类型: {qd.get('type', 'N/A')}")
                report_parts.append(f"难度等级: {qd.get('difficulty', 'N/A')}")
                if "reasoning" in qd:
                    report_parts.append(f"选题原因: {qd['reasoning']}")

            report_parts.append(f"回答: {qa.get('answer', '未记录')}")

            if qa.get("score_details"):
                sd = qa["score_details"]
                report_parts.append(f"得分: {sd.get('score', 0)}/10")
                if "reasoning" in sd:
                    report_parts.append(f"评分理由: {sd['reasoning']}")

        if security_summary:
            report_parts.append("\n=== 安全检测摘要 ===")
            report_parts.append(f"总体风险等级: {security_summary.get('overall_risk', 'unknown')}")
            report_parts.append(f"安全警报数量: {security_summary.get('total_alerts', 0)}")
            if security_summary.get("security_alerts"):
                report_parts.append("安全问题详情:")
                for alert in security_summary["security_alerts"]:
                    report_parts.append(f"  - 问题{alert.get('question_id', '?')}: {alert.get('issues', [])}")

        scores = [
            qa.get("score_details", {}).get("score", 0)
            for qa in qa_history
            if qa.get("score_details")
        ]
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
    # 校准与降级
    # ------------------------------------------------------------

    def _validate_summary_result(self, result: Dict[str, Any], average_score: float) -> Dict[str, Any]:
        """对齐分数与等级，避免 LLM 输出的不一致"""
        if "overall_score" not in result or result["overall_score"] is None:
            result["overall_score"] = round(average_score, 1)

        score = result["overall_score"]
        expected_grade = self._score_to_grade(score)
        result["final_grade"] = expected_grade
        result["final_decision"] = self._decision_by_grade(expected_grade)
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

    def _generate_fallback_summary(self, candidate_name: str, average_score: float) -> Dict[str, Any]:
        grade = self._score_to_grade(average_score)
        return {
            "candidate_name": candidate_name,
            "final_grade": grade,
            "final_decision": self._decision_by_grade(grade),
            "overall_score": round(max(0, average_score), 1),
            "summary": "由于系统问题，详细总结生成失败，建议人工复核面试记录。",
            "strengths": [],
            "weaknesses": ["系统评估异常"],
            "confidence_level": "low",
            "recommendations": {
                "for_candidate": "建议结合面试记录人工复核",
                "for_program": "建议结合面试目标与培养方向综合判断",
            },
            "detailed_analysis": {
                "math_logic": "由于系统问题，详细分析不可用",
                "reasoning_rigor": "由于系统问题，详细分析不可用",
                "communication": "由于系统问题，详细分析不可用",
                "collaboration": "由于系统问题，详细分析不可用",
                "growth_potential": "由于系统问题，详细分析不可用",
            },
            "generated_at": datetime.now().isoformat(),
            "note": "Fallback summary",
        }
