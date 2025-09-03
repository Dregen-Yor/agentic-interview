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

请以JSON格式返回评分结果，包含：
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
            
            # 尝试解析JSON响应
            try:
                result = json.loads(response)
                
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
    
    def _extract_score_from_text(self, text: str) -> int:
        """从文本中提取分数"""
        import re
        
        # 寻找数字模式
        patterns = [
            r'(\d+)分',
            r'分数[：:](\d+)',
            r'得分[：:](\d+)',
            r'总分[：:](\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                score = int(match.group(1))
                return max(1, min(10, score))
        
        # 如果找不到明确的分数，根据关键词判断
        if any(word in text for word in ['优秀', '很好', '出色']):
            return 8
        elif any(word in text for word in ['良好', '不错', '可以']):
            return 6
        elif any(word in text for word in ['一般', '普通']):
            return 5
        elif any(word in text for word in ['较差', '不够']):
            return 3
        
        return 5  # 默认分数

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
    
    def evaluate_interview_readiness(self, qa_history: List[Dict[str, Any]], min_questions: int = 5) -> Dict[str, Any]:
        """评估是否有足够信息做出面试决定"""
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
        elif total_questions >= min_questions + 2:
            # 如果已经问了足够多的问题，基于当前分数做决定
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

            