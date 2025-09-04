"""
评分智能体
对候选人的回答进行评分和评价
"""

import json
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage
from .base_agent import BaseAgent


class ScoringAgent(BaseAgent):
    """评分智能体"""
    
    def __init__(self, model):
        super().__init__(model, "ScoringAgent")
        self.system_prompt = """
你是一个大学内计算机拔尖班（科研方向）面试评分专家。面试对象为大一新生，需突出评估其数理与逻辑基础，同时兼顾基本素质与社交能力。

评分维度与建议权重（总分10）：
1. 数理/逻辑基础 (1-4)：概念理解、推理严谨性、抽象与形式化能力
2. 推理严谨与问题求解 (1-2)：多步推理质量、边界/条件意识、反例意识
3. 表达与沟通 (1-2)：语言清晰度、结构化表达、倾听与回应
4. 合作与社交基线 (0-1)：尊重他人、团队协作意识、情绪稳定
5. 成长潜力 (0-1)：自我驱动、学习反思、对未知问题的探索态度

字母等级（用于最终结果参考）：
- A：强烈推荐（通常对应平均分≥8.5）
- B：可以考虑（通常对应平均分7.0-8.4）
- C：不推荐（通常对应平均分5.0-6.9）
- D：基本不能录取（通常对应平均分<5.0）

评分原则：
- 面向大一新生的起点，不以术语堆砌为主，重在思维质量；
- 对自述已学内容可适度提高期望；
- 对不确定题可看思路、假设、拆解与验证方法；
- 关注逻辑一致性与可检验性。

请以严格的JSON格式返回评分结果：
{
    "score": 总分(1-10),
    "letter": "A/B/C/D",
    "breakdown": {
        "math_logic": 数理与逻辑(1-4),
        "reasoning_rigor": 推理严谨(1-2),
        "communication": 表达与沟通(1-2),
        "collaboration": 合作与社交基线(0-1),
        "potential": 成长潜力(0-1)
    },
    "reasoning": "评分理由（指出区分度与改进方向）",
    "strengths": ["优势点1", "优势点2"],
    "weaknesses": ["不足点1", "不足点2"],
    "suggestions": ["改进建议1", "改进建议2"]
}

**严格格式要求**：
1. 必须返回完整有效的JSON，所有大括号和引号必须配对
2. 不要在JSON外添加任何说明文字或markdown标记
3. 特别注意嵌套的 breakdown 对象要正确闭合
4. 数组字段（strengths, weaknesses, suggestions）格式要正确
5. 最后必须以 '}' 结尾，检查是否遗漏闭合符号
"""
    
    def get_system_prompt(self) -> str:
        return self.system_prompt
    
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        对回答进行评分
        input_data包含:
        - question: 面试问题
        - answer: 候选人回答
        - question_type: 问题类型
        - difficulty: 问题难度
        - resume_data: 简历信息（用于经验匹配评估）
        """
        print(f"===== ScoringAgent.process() 开始执行 =====")
        try:
            question = input_data.get("question", "")
            answer = input_data.get("answer", "")
            question_type = input_data.get("question_type", "general")
            difficulty = input_data.get("difficulty", "medium")
            resume_data = input_data.get("resume_data", {})
            
            # 构建评分prompt
            prompt_content = f"""
请对以下面试问答进行评分：

问题类型: {question_type}
问题难度: {difficulty}
问题: {question}
候选人回答: {answer}

候选人简历背景: {json.dumps(resume_data, ensure_ascii=False, indent=2) if resume_data else '无'}

请根据评分标准给出详细的评分结果。
"""
            
            messages = [
                SystemMessage(content=self.get_system_prompt()),
                HumanMessage(content=prompt_content)
            ]
            
            response = self._invoke_model(messages)
            
            # 输出原始响应内容
            print(f"===== ScoringAgent 原始响应 =====")
            print(response)
            print("=================================\n")
            
            # 尝试解析JSON响应
            try:
                # 首先尝试修复常见的JSON问题
                fixed_response = self._fix_common_json_issues(response)
                result = json.loads(fixed_response)
                
                # 验证必要字段
                if "score" not in result:
                    result["score"] = 5  # 默认分数
                
                # 确保分数在合理范围内
                result["score"] = max(1, min(10, result["score"]))

                # 计算字母等级（如缺失）
                if "letter" not in result:
                    result["letter"] = self._score_to_letter(result["score"]) 
                
                return result
                
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Failed to parse JSON response from ScoringAgent: {e}")
                print(f"Raw response: {response}")
                
                # 尝试从文本中提取分数
                score = self._extract_score_from_text(response)
                
                return {
                    "score": score,
                    "letter": self._score_to_letter(score),
                    "breakdown": {
                        "math_logic": max(1, min(4, score - 6)) if score >= 7 else max(1, min(4, score // 2)),
                        "reasoning_rigor": max(0, min(2, (score - 4) // 3)),
                        "communication": max(0, min(2, (score + 1) // 4)),
                        "collaboration": 1 if score >= 7 else 0,
                        "potential": 1 if score >= 8 else 0
                    },
                    "reasoning": response,
                    "strengths": [],
                    "weaknesses": [],
                    "suggestions": []
                }
                
        except Exception as e:
            print(f"Error in ScoringAgent: {e}")
            return {
                "score": 5,
                "letter": self._score_to_letter(5),
                "breakdown": {
                    "math_logic": 2,
                    "reasoning_rigor": 1,
                    "communication": 1,
                    "collaboration": 0,
                    "potential": 1
                },
                "reasoning": f"评分过程中出现错误: {str(e)}",
                "strengths": [],
                "weaknesses": [],
                "suggestions": []
            }
    
    def _fix_common_json_issues(self, response: str) -> str:
        """
        修复常见的JSON格式问题
        """
        # 清理响应
        cleaned = response.strip()
        
        # 移除markdown代码块标记
        if cleaned.startswith('```json'):
            cleaned = cleaned[7:]
        elif cleaned.startswith('```'):
            cleaned = cleaned[3:]
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        
        # 检查是否缺少结尾大括号
        open_braces = cleaned.count('{')
        close_braces = cleaned.count('}')
        
        if open_braces > close_braces:
            # 添加缺少的结尾大括号
            missing_braces = open_braces - close_braces
            cleaned += '}' * missing_braces
        
        # 移除可能的多余逗号（在大括号前的逗号）
        import re
        cleaned = re.sub(r',\s*}', '}', cleaned)
        cleaned = re.sub(r',\s*]', ']', cleaned)
        
        return cleaned
    
    def _extract_score_from_text(self, text: str) -> int:
        """从文本中提取分数，JSON解析失败时返回默认分数"""
        # 简化处理，直接返回默认分数
        return 5

    def _score_to_letter(self, score: int) -> str:
        """根据数值分映射字母等级"""
        if score >= 9:
            return "A"
        elif score >= 7:
            return "B"
        elif score >= 5:
            return "C"
        else:
            return "D"
    
    def evaluate_interview_readiness(self, qa_history: List[Dict[str, Any]], min_questions: int = 4) -> Dict[str, Any]:
        """评估是否有足够信息做出面试决定（优化为5-6轮面试）"""
        total_questions = len(qa_history)
        
        if total_questions < min_questions:
            return {
                "ready": False,
                "reason": f"问题数量不足，当前{total_questions}题，建议至少{min_questions}题",
                "recommendation": "continue"
            }
        
        # 计算平均分
        scores = [qa.get("score", 0) for qa in qa_history if "score" in qa]
        if not scores:
            return {
                "ready": False,
                "reason": "缺少评分信息",
                "recommendation": "continue"
            }
        
        avg_score = sum(scores) / len(scores)
        
        # 检查分数分布
        high_scores = sum(1 for s in scores if s >= 7)
        low_scores = sum(1 for s in scores if s <= 4)
        
        # 决策逻辑
        if avg_score >= 7 and high_scores >= total_questions * 0.6:
            return {
                "ready": True,
                "reason": f"候选人表现优秀，平均分{avg_score:.1f}",
                "recommendation": "accept"
            }
        elif avg_score <= 4 or low_scores >= total_questions * 0.5:
            return {
                "ready": True,
                "reason": f"候选人表现不佳，平均分{avg_score:.1f}",
                "recommendation": "reject"
            }
        elif total_questions >= 5:
            # 如果已经问了5题或更多，基于当前分数做决定
            decision = "accept" if avg_score >= 6 else "reject"
            return {
                "ready": True,
                "reason": f"已完成{total_questions}题评估，平均分{avg_score:.1f}",
                "recommendation": decision
            }
        else:
            return {
                "ready": False,
                "reason": f"需要更多信息，当前平均分{avg_score:.1f}，建议继续面试",
                "recommendation": "continue"
            }

            