"""
评分智能体
对候选人的回答进行评分和评价
"""

import json
import logging
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage
from .base_agent import BaseAgent
from .qa_models import get_score


class ScoringAgent(BaseAgent):
    """评分智能体"""
    
    def __init__(self, model):
        super().__init__(model, "ScoringAgent")
        self.logger = logging.getLogger("interview.agents.scoring_agent")
        self.system_prompt = """
You are a scoring expert for interviews at a university's advanced computer science class (research track). The interviewees are first-year university students. You need to focus on assessing their mathematical and logical foundations, while also considering basic qualities and social skills.

Scoring Dimensions and Suggested Weights (Total 10 points):
1. Mathematical/Logical Foundation (1-4): Conceptual understanding, reasoning rigor, abstraction, and formalization skills.
2. Reasoning Rigor and Problem Solving (1-2): Quality of multi-step reasoning, awareness of boundaries/conditions, and counter-examples.
3. Expression and Communication (1-2): Clarity of language, structured expression, listening, and responsiveness.
4. Collaboration and Social Baseline (0-1): Respect for others, teamwork awareness, emotional stability.
5. Growth Potential (0-1): Self-motivation, reflective learning, and attitude towards exploring unknown problems.

Letter Grades (for final result reference):
- A: Strongly recommend (usually corresponds to an average score >= 8.5)
- B: Can be considered (usually corresponds to an average score of 7.0-8.4)
- C: Not recommended (usually corresponds to an average score of 5.0-6.9)
- D: Basically unacceptable (usually corresponds to an average score < 5.0)

Important Constraints (Scoring Triggers):
- The system will not encounter any network or "review delay" issues; if they occur, the call will be interrupted directly, and you will not receive any prompts.
- You should only give a score when and only when you "see a valid solution." A valid solution means: providing the correct answer, or the thought process.
- If there is no valid solution (e.g., only discussion, questioning, no conclusion), give a score of 0 directly.

Scoring Principles:
- Tailored for first-year university students, focusing on the quality of thinking rather than an accumulation of terminology.
- A correct answer should receive at least 8 points, with the remaining points awarded based on the problem-solving process.
- Avoid giving excessively low scores unless the performance is extremely poor.
- Moderately increase expectations for self-declared learned content.
- For uncertain questions, look at the approach, assumptions, decomposition, and verification methods.
- Focus on logical consistency and verifiability.

When a valid solution exists, please return the scoring result in strict JSON format:
{
    "score": Total score (1-10),
    "letter": "A/B/C/D",
    "breakdown": {
        "math_logic": Math and Logic (1-4),
        "reasoning_rigor": Reasoning Rigor (1-2),
        "communication": Expression and Communication (1-2),
        "collaboration": Collaboration and Social Baseline (0-1),
        "potential": Growth Potential (0-1)
    },
    "reasoning": "Reasoning for the score (pointing out differentiators and areas for improvement)",
    "strengths": ["Strength 1", "Strength 2"],
    "weaknesses": ["Weakness 1", "Weakness 2"],
    "suggestions": ["Suggestion for improvement 1", "Suggestion for improvement 2"]
}

**Strict Formatting Requirements**:
1. Must return a complete and valid JSON; all braces and quotes must be paired.
2. Do not add any explanatory text or markdown tags outside the JSON.
3. Pay special attention to correctly closing the nested `breakdown` object.
4. Array fields (strengths, weaknesses, suggestions) must be correctly formatted.
5. Must end with a '}' brace; check for any missing closing symbols.

All outputs must be in Chinese.
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
        - resume_data: 简历信息（不参与评分，仅为兼容字段，将被忽略）
        """
        self.logger.debug("===== ScoringAgent.process() 开始执行 =====")
        try:
            question = input_data.get("question", "")
            answer = input_data.get("answer", "")
            question_type = input_data.get("question_type", "general")
            difficulty = input_data.get("difficulty", "medium")
            # 为保持接口兼容接收，但评分不使用简历信息
            _ = input_data.get("resume_data", {})
            
            # 构建评分prompt
            prompt_content = f"""
Please score the following interview Q&A:

Question Type: {question_type}
Question Difficulty: {difficulty}
Question: {question}
Candidate's Answer: {answer}

Important: Base the score solely on the performance in the answer itself, without considering any resume or background information.
 If no valid solution is seen (no correct result), give a score of 0 directly.
Please provide a detailed scoring result according to the scoring criteria.
"""
            
            messages = [
                SystemMessage(content=self.get_system_prompt()),
                HumanMessage(content=prompt_content)
            ]
            
            response = self._invoke_model(messages)
            
            # 输出原始响应内容
            self.logger.debug("===== ScoringAgent 原始响应 =====")
            self.logger.debug(response)
            self.logger.debug("=================================\n")
            
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
                self.logger.error(f"Failed to parse JSON response from ScoringAgent: {e}")
                self.logger.debug(f"Raw response: {response}")
                
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
            self.logger.error(f"Error in ScoringAgent: {e}")
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
        
        # 计算平均分（统一从 score_details.score 读取，兼容旧顶层 score）
        scores = [get_score(qa) for qa in qa_history]
        scores = [s for s in scores if s > 0]
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

            