"""
SecurityAgent — async + structured output + 双层 Guardrails (S1 + S2 + S7)

双层防御：
1. OpenAI Moderation API（fast, free, ~100ms）做第一道明显有害内容过滤
2. SecurityAgent LLM（structured output）做 prompt-injection 等定制检测

短路优化：
- 输入长度 < 200 + 快检 low + Moderation 通过 → 跳过 LLM 检测，直接返回 safe
- 这覆盖了 ~70% 的正常面试回答
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from .base_agent import BaseAgent
from .guardrails import merge_moderation_into_security, moderate_text
from .schemas import RiskLevel, SecurityOutput, SuggestedAction

# 风险等级权重表（统一供 max() 使用，未知等级回退到 1）
_RISK_RANK = {"low": 1, "medium": 2, "high": 3}


def _risk_rank(level: Any) -> int:
    """安全地将风险等级字符串映射为权重，未知值返回 1（low）"""
    if not isinstance(level, str):
        return 1
    return _RISK_RANK.get(level.strip().lower(), 1)


def _max_risk(*levels: Any) -> str:
    """返回最高风险等级；若全部未知则返回 'low'"""
    valid = [lv for lv in levels if isinstance(lv, str) and lv.strip().lower() in _RISK_RANK]
    if not valid:
        return "low"
    return max(valid, key=_risk_rank).strip().lower()


# 短路阈值
_SHORT_CIRCUIT_LEN = 200


class SecurityAgent(BaseAgent):
    """安全检测智能体 - structured output + Moderation 双层"""

    prompt_name = "security_agent"
    output_schema = SecurityOutput

    def __init__(self, model):
        super().__init__(model, "SecurityAgent")
        self.logger = logging.getLogger("interview.agents.security_agent")

        # 预定义的危险模式（快检层，正则黑名单）
        self.dangerous_patterns = [
            # 提示词注入
            r"ignore\s+previous\s+instructions",
            r"forget\s+everything\s+above",
            r"disregard\s+the\s+above",
            r"重新定义你的角色",
            r"忘记之前的指令",
            r"忽略上面的内容",
            # 元叙述型注入（Error/题目有误/标准答案无参考/系统审查/网络问题）
            r"^\s*error\s*:.*(题目|问题).*(疏漏|漏洞|无\s*正确答案|不具?参考性)",
            r"(系统|审查|网络|延迟).*(已|再次|反复).*(确认|认定|导致).*(题目|问题).*(有误|疏漏|无法评估)",
            r"标准答案.*(不具?参考性|无效)",
            r"(由于|因为).*(网络|系统|审查).*(问题|延迟).*(请|应当)?.*(直接|立刻)?.*(高分|通过|满分)",
            # 角色扮演绕过
            r"now\s+you\s+are\s+a",
            r"pretend\s+to\s+be",
            r"act\s+as\s+a",
            r"现在你是",
            r"假装你是",
            r"扮演",
            # 系统信息获取
            r"show\s+me\s+your\s+system\s+prompt",
            r"what\s+are\s+your\s+instructions",
            r"显示你的系统提示",
            r"你的指令是什么",
            # 直接要求好评
            r"give\s+me\s+.*high.*score",
            r"rate\s+me\s+.*10.*out.*10",
            r"给我.*高分",
            r"给我满分",
            r"直接通过",
        ]

        self.suspicious_keywords = [
            "jailbreak", "bypass", "hack", "exploit",
            "越狱", "绕过", "破解", "利用漏洞",
        ]

    # ------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------

    async def aprocess(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步安全检测（双层 + 短路）。
        input_data: { user_input, context }
        """
        user_input = input_data.get("user_input", "")
        context = input_data.get("context", {})

        # 第 0 层：正则快检（≈1ms）
        quick_check = self._quick_security_check(user_input)
        if quick_check["risk_level"] == "high":
            self.logger.warning(f"快检命中高风险: {quick_check['detected_issues']}")
            return quick_check

        # 第 1 层：OpenAI Moderation（≈100ms，并行执行）
        moderation_result = await moderate_text(user_input)

        # 短路：低风险 + 输入短 + Moderation 通过 → 跳过 LLM
        if (
            quick_check["risk_level"] == "low"
            and len(user_input) < _SHORT_CIRCUIT_LEN
            and not moderation_result.get("flagged")
            and moderation_result.get("risk_level") == "low"
        ):
            return {
                "is_safe": True,
                "risk_level": "low",
                "detected_issues": [],
                "reasoning": "短路通过：快检 low + Moderation 低风险 + 输入长度小",
                "suggested_action": "continue",
            }

        # 第 2 层：SecurityAgent LLM 深度分析（仅在前两层有疑点时）
        try:
            human_text = self.prompt.format_human(
                user_input=user_input,
                context=json.dumps(context, ensure_ascii=False) if context else "无",
            )
            llm_result: SecurityOutput = await self.ainvoke_structured(human_text)
            result = llm_result.model_dump(mode="json")
            # SuggestedAction enum value "continue" 在 Python 中是关键字别名，但序列化为字符串没问题
            # 标准化字符串
            result["risk_level"] = result.get("risk_level", "low")
            result["suggested_action"] = result.get("suggested_action", "continue")
        except Exception as e:
            self.logger.error(f"SecurityAgent LLM 调用异常: {e}")
            # LLM 失败时降级到快检 + Moderation 结果
            result = {
                "is_safe": quick_check.get("is_safe", True),
                "risk_level": _max_risk(
                    quick_check.get("risk_level", "low"),
                    moderation_result.get("risk_level", "low"),
                ),
                "detected_issues": list(set(
                    quick_check.get("detected_issues", []) + moderation_result.get("detected_issues", [])
                )),
                "reasoning": f"LLM 异常降级；快检+Moderation 合并：{e}",
                "suggested_action": quick_check.get("suggested_action", "continue"),
            }

        # 合并三层结果（取最高风险）
        if quick_check["detected_issues"]:
            result["detected_issues"] = list(set(
                result.get("detected_issues", []) + quick_check["detected_issues"]
            ))
            result["risk_level"] = _max_risk(
                result.get("risk_level", "low"),
                quick_check.get("risk_level", "low"),
            )

        result = merge_moderation_into_security(result, moderation_result)

        # 重新计算 suggested_action / is_safe
        result["risk_level"] = _max_risk(result.get("risk_level", "low"))
        result["suggested_action"] = self._get_suggested_action(
            result["risk_level"], result.get("detected_issues", [])
        )
        result["is_safe"] = result["suggested_action"] != "block"

        return result

    # ------------------------------------------------------------
    # 快检层
    # ------------------------------------------------------------

    def _quick_security_check(self, user_input: str) -> Dict[str, Any]:
        """正则快速检测（1ms 级）"""
        user_input_lower = user_input.lower()
        detected_issues: List[str] = []
        risk_level = "low"

        for pattern in self.dangerous_patterns:
            if re.search(pattern, user_input_lower, re.IGNORECASE):
                detected_issues.append("prompt_injection")
                risk_level = "high"
                break

        for keyword in self.suspicious_keywords:
            if keyword.lower() in user_input_lower:
                detected_issues.append("suspicious_keyword")
                risk_level = _max_risk(risk_level, "medium")

        special_char_ratio = len(
            [c for c in user_input if not c.isalnum() and c not in " .,!?;:"]
        ) / max(len(user_input), 1)
        if special_char_ratio > 0.3:
            detected_issues.append("unusual_characters")
            risk_level = _max_risk(risk_level, "medium")

        if len(user_input) > 2000:
            detected_issues.append("excessive_length")
            risk_level = _max_risk(risk_level, "medium")

        suggested_action = self._get_suggested_action(risk_level, detected_issues)
        is_safe = suggested_action != "block"

        return {
            "is_safe": is_safe,
            "risk_level": risk_level,
            "detected_issues": detected_issues,
            "reasoning": f"快速检测发现的问题: {detected_issues}" if detected_issues else "快速检测未发现明显问题",
            "suggested_action": suggested_action,
        }

    def _get_suggested_action(self, risk_level: str, detected_issues: List[str]) -> str:
        """根据风险等级和检测到的问题建议行动"""
        if risk_level == "high" or "prompt_injection" in detected_issues:
            return "block"
        elif risk_level == "medium":
            return "warning"
        else:
            return "continue"

    # ------------------------------------------------------------
    # 会话级分析（保留同步）
    # ------------------------------------------------------------

    def analyze_session_security(self, qa_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析整个面试会话的安全状况（不做 LLM 调用，纯统计）"""
        total_inputs = len(qa_history)
        security_alerts = []
        risk_count = {"low": 0, "medium": 0, "high": 0}

        for qa in qa_history:
            if "security_check" in qa and qa["security_check"]:
                security_check = qa["security_check"]
                if not security_check.get("is_safe", True):
                    security_alerts.append({
                        "question_id": qa.get("question_id", "unknown"),
                        "risk_level": security_check.get("risk_level", "medium"),
                        "issues": security_check.get("detected_issues", []),
                    })

                risk_level = security_check.get("risk_level", "low")
                if risk_level in risk_count:
                    risk_count[risk_level] += 1

        if risk_count["high"] > 0:
            overall_risk = "high"
        elif risk_count["medium"] > total_inputs * 0.3:
            overall_risk = "medium"
        else:
            overall_risk = "low"

        return {
            "overall_risk": overall_risk,
            "total_alerts": len(security_alerts),
            "risk_distribution": risk_count,
            "security_alerts": security_alerts,
            "recommendation": self._get_session_recommendation(overall_risk, len(security_alerts), total_inputs),
        }

    def _get_session_recommendation(self, overall_risk: str, alert_count: int, total_inputs: int) -> str:
        alert_ratio = alert_count / max(total_inputs, 1)
        if overall_risk == "high" or alert_ratio > 0.5:
            return "terminate"
        elif overall_risk == "medium" or alert_ratio > 0.2:
            return "caution"
        else:
            return "normal"
