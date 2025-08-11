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
你是一个专业的面试评分专家，负责对候选人的面试回答进行客观、公正的评分。

评分标准：
1. 技术能力 (1-3分)：回答的技术准确性和深度
2. 表达能力 (1-3分)：回答的清晰度和逻辑性  
3. 经验匹配 (1-2分)：回答与职位要求的匹配度
4. 创新思维 (1-2分)：回答中体现的创新性和解决问题的能力

总分范围：1-10分
- 9-10分：优秀，完全符合或超出期望
- 7-8分：良好，基本符合期望
- 5-6分：一般，部分符合期望
- 3-4分：较差，不太符合期望
- 1-2分：很差，完全不符合期望

评分原则：
- 客观公正，基于事实
- 考虑问题的难度和候选人的经验水平
- 重点关注回答的质量而不是长度
- 识别候选人的优势和不足

请以JSON格式返回评分结果，包含：
{
    "score": 总分(1-10),
    "breakdown": {
        "technical": 技术能力分数(1-3),
        "communication": 表达能力分数(1-3), 
        "experience": 经验匹配分数(1-2),
        "innovation": 创新思维分数(1-2)
    },
    "reasoning": "详细的评分理由",
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
                
                return result
                
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Failed to parse JSON response from ScoringAgent: {e}")
                print(f"Raw response: {response}")
                
                # 尝试从文本中提取分数
                score = self._extract_score_from_text(response)
                
                return {
                    "score": score,
                    "breakdown": {
                        "technical": score // 3,
                        "communication": score // 3,
                        "experience": score // 5,
                        "innovation": score // 5
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
                "breakdown": {
                    "technical": 2,
                    "communication": 2,
                    "experience": 1,
                    "innovation": 0
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