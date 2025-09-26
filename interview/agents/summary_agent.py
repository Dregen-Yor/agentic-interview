"""
总结智能体
对面试过程进行总结并做出最终决定
"""

import json
import os
import datetime
import pymongo
from typing import Dict, Any, List
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage
from .base_agent import BaseAgent


class SummaryAgent(BaseAgent):
    """总结智能体"""
    
    def __init__(self, model):
        super().__init__(model, "SummaryAgent")

        # MongoDB连接初始化
        try:
            self.client = pymongo.MongoClient(os.getenv("MONGODB_URI"))
            self.db = self.client[os.getenv("MONGODB_DB")]
            self.result_collection = self.db["result"]
            print("SummaryAgent: MongoDB连接成功")
        except Exception as e:
            print(f"SummaryAgent: MongoDB连接失败: {e}")
            self.client = None
            self.db = None
            self.result_collection = None

        self.system_prompt = """
You are an interview summary expert for a university's advanced computer science class (research track). The interviewees are first-year university students. The evaluation should focus on mathematical and logical foundations, while also considering basic qualities and interpersonal skills, with an emphasis on identifying research potential.
The interview uses a 5-6 round high-efficiency Q&A model, requiring an accurate assessment based on limited information.

Your Responsibilities:
1. Comprehensively analyze the candidate's performance in mathematical logic, reasoning rigor, expression, communication, collaborative baseline, and growth potential during the interview.
2. Provide an objective evaluation of the candidate's self-declared knowledge and their performance on follow-up questions.
3. Based on the scores from each segment, provide a final letter grade (A/B/C/D) and a hiring recommendation.
4. Emphasize fairness and objectivity, avoiding bias and irrelevant personal judgments.
5. Fully utilize the high-quality Q&A in the limited rounds to deeply explore the candidate's potential.

Analysis Dimensions (for reference):
1. Mathematical/Logical Foundation: Conceptual understanding, abstraction ability, formalization, and rigor.
2. Reasoning and Problem Solving: Quality of multi-step reasoning, awareness of boundaries and counter-examples.
3. Expression and Communication: Structure and clarity, listening and responsiveness.
4. Collaboration and Social Baseline: Respect for others, teamwork, and stability.
5. Growth Potential: Learning motivation and reflection, research interest, and exploratory attitude.

Grades and Recommendations (for final evaluation):
- A: Recommended for admission (usually corresponds to an average score >= 8.5)
- B: Can be considered for admission (usually corresponds to an average score of 7.0-8.4)
- C: Not recommended for admission (usually corresponds to an average score of 5.0-6.9)
- D: Basically unacceptable for admission (usually corresponds to an average score < 5.0)

Please return the summary result in strict JSON format:
{
    "final_grade": "A/B/C/D",
    "final_decision": "accept/reject/conditional",
    "overall_score": Overall score (1-10),
    "summary": "Interview summary",
    "strengths": ["Strength 1", "Strength 2", "Strength 3"],
    "weaknesses": ["Weakness 1", "Weakness 2"],
    "recommendations": {
        "for_candidate": "Suggestions for the candidate",
        "for_program": "Suggestions for the advanced class"
    },
    "confidence_level": "high/medium/low",
    "detailed_analysis": {
        "math_logic": "Mathematical and logical analysis",
        "reasoning_rigor": "Reasoning rigor analysis",
        "communication": "Communication skills analysis",
        "collaboration": "Collaboration and social skills analysis",
        "growth_potential": "Growth potential analysis"
    }
}

**Key Formatting Requirements**:
1. Must return a complete JSON; all curly braces {} must be correctly paired.
2. Do not add markdown code blocks, additional explanations, or other non-JSON content.
3. Carefully check if the curly braces of nested objects are complete.
4. Ensure that it ends with a '}' brace and no closing symbols are missing.
5. All string values must be enclosed in double quotes.

All outputs must be in Chinese.
"""
    
    def get_system_prompt(self) -> str:
        return self.system_prompt
    
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成面试总结和最终决定
        input_data包含:
        - candidate_name: 候选人姓名
        - resume_data: 简历信息
        - qa_history: 完整的问答历史
        - average_score: 平均分
        - security_summary: 安全检测总结
        """
        try:
            candidate_name = input_data.get("candidate_name", "")
            resume_data = input_data.get("resume_data", {})
            qa_history = input_data.get("qa_history", [])
            average_score = input_data.get("average_score", 0)
            security_summary = input_data.get("security_summary", {})
            
            # 构建详细的面试报告
            interview_report = self._build_interview_report(
                candidate_name, resume_data, qa_history, average_score, security_summary
            )
            
            messages = [
                SystemMessage(content=self.get_system_prompt()),
                HumanMessage(content=interview_report)
            ]
            
            response = self._invoke_model(messages)
            
            # 输出原始响应内容
            print(f"===== SummaryAgent 原始响应 =====")
            print(response)
            print("=================================\n")
            
            try:
                # 首先尝试修复常见的JSON问题
                fixed_response = self._fix_common_json_issues(response)
                result = json.loads(fixed_response)
                
                # 验证和标准化结果
                result = self._validate_summary_result(result, average_score)
                
                # 添加时间戳
                result["generated_at"] = datetime.now().isoformat()
                result["candidate_name"] = candidate_name

                # 注意：不在这里自动保存，由协调器统一保存数据
                # 这避免了重复保存和数据不一致问题
                return result
                
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Failed to parse JSON response from SummaryAgent: {e}")
                
                # 生成备用总结
                fallback_result = self._generate_fallback_summary(
                    candidate_name, average_score, qa_history, response
                )

                # 注意：不在这里保存，由协调器统一保存
                return fallback_result
                
        except Exception as e:
            print(f"Error in SummaryAgent: {e}")
            error_result = self._generate_error_summary(candidate_name, average_score)

            # 注意：不在这里保存，由协调器统一保存
            return error_result
    
    def _build_interview_report(self, candidate_name: str, resume_data: Dict[str, Any], 
                               qa_history: List[Dict[str, Any]], average_score: float,
                               security_summary: Dict[str, Any]) -> str:
        """构建详细的面试报告"""
        report_parts = []
        
        # 候选人基本信息
        report_parts.append(f"候选人: {candidate_name}")
        report_parts.append(f"面试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_parts.append(f"总题目数: {len(qa_history)}")
        report_parts.append(f"平均分: {average_score:.2f}/10")
        
        # 简历信息摘要
        if resume_data:
            report_parts.append("\n=== 候选人背景 ===")
            report_parts.append(f"简历信息: {json.dumps(resume_data, ensure_ascii=False, indent=2)}")
        
        # 面试问答详情
        report_parts.append("\n=== 面试问答记录 ===")
        for i, qa in enumerate(qa_history, 1):
            report_parts.append(f"\n--- 第{i}题 ---")
            report_parts.append(f"问题: {qa.get('question', '未记录')}")
            
            # 如果有完整的问题数据，显示更多元信息
            if 'question_data' in qa and qa['question_data']:
                question_data = qa['question_data']
                report_parts.append(f"问题类型: {question_data.get('type', 'N/A')}")
                report_parts.append(f"难度等级: {question_data.get('difficulty', 'N/A')}")
                if 'reasoning' in question_data:
                    report_parts.append(f"选题原因: {question_data['reasoning']}")
            
            report_parts.append(f"回答: {qa.get('answer', '未记录')}")
            
            if 'score_details' in qa:
                score_details = qa['score_details']
                report_parts.append(f"得分: {score_details.get('score', 0)}/10")
                if 'reasoning' in score_details:
                    report_parts.append(f"评分理由: {score_details['reasoning']}")
        
        # 安全检测摘要
        if security_summary:
            report_parts.append(f"\n=== 安全检测摘要 ===")
            report_parts.append(f"总体风险等级: {security_summary.get('overall_risk', 'unknown')}")
            report_parts.append(f"安全警报数量: {security_summary.get('total_alerts', 0)}")
            if security_summary.get('security_alerts'):
                report_parts.append("安全问题详情:")
                for alert in security_summary['security_alerts']:
                    report_parts.append(f"  - 问题{alert.get('question_id', '?')}: {alert.get('issues', [])}")
        
        # 统计分析
        scores = [qa.get('score_details', {}).get('score', 0) for qa in qa_history 
                 if qa.get('score_details')]
        if scores:
            report_parts.append(f"\n=== 分数统计 ===")
            report_parts.append(f"最高分: {max(scores)}/10")
            report_parts.append(f"最低分: {min(scores)}/10")
            report_parts.append(f"平均分: {sum(scores)/len(scores):.2f}/10")
            
            # 分数分布
            high_scores = sum(1 for s in scores if s >= 7)
            medium_scores = sum(1 for s in scores if 4 <= s < 7)
            low_scores = sum(1 for s in scores if s < 4)
            
            report_parts.append(f"高分题目(≥7分): {high_scores}题")
            report_parts.append(f"中等题目(4-6分): {medium_scores}题") 
            report_parts.append(f"低分题目(<4分): {low_scores}题")
        
        report_parts.append("\n请基于以上信息生成全面的面试总结和录用建议。")
        
        return "\n".join(report_parts)
    
    def _validate_summary_result(self, result: Dict[str, Any], average_score: float) -> Dict[str, Any]:
        """验证和标准化总结结果"""
        # 确保必要字段存在
        if "overall_score" not in result:
            result["overall_score"] = round(average_score, 1)

        # 计算字母等级
        if "final_grade" not in result:
            result["final_grade"] = self._score_to_grade(result["overall_score"]) 

        # 根据字母等级给出默认决策
        if "final_decision" not in result:
            result["final_decision"] = self._decision_by_grade(result["final_grade"]) 
        
        # 验证决策与分数的一致性
        decision = result["final_decision"]
        score = result["overall_score"]
        grade = result.get("final_grade", self._score_to_grade(score))
        
        # 若分数与决策/等级冲突，优先以等级与分数区间规则为准
        expected_grade = self._score_to_grade(score)
        if grade != expected_grade:
            result["final_grade"] = expected_grade
        result["final_decision"] = self._decision_by_grade(result["final_grade"]) 
        
        # 确保其他必要字段存在
        default_values = {
            "summary": "面试总结生成中出现问题",
            "strengths": [],
            "weaknesses": [],
            "confidence_level": "medium",
            "recommendations": {
                "for_candidate": "建议继续提升相关技能",
                "for_program": "建议结合面试目标与培养方向综合判断"
            },
            "detailed_analysis": {
                "math_logic": "数理与逻辑分析待补充",
                "reasoning_rigor": "推理严谨性分析待补充",
                "communication": "沟通能力分析待补充",
                "collaboration": "合作与社交分析待补充",
                "growth_potential": "成长潜力分析待补充"
            }
        }
        
        for key, default_value in default_values.items():
            if key not in result:
                result[key] = default_value
        
        return result
    
    def _make_decision_by_score(self, average_score: float) -> str:
        """根据平均分做决定（兼容旧逻辑）"""
        grade = self._score_to_grade(average_score)
        return self._decision_by_grade(grade)

    def _score_to_grade(self, score: float) -> str:
        """将分数映射为A/B/C/D等级（平均分使用≥8.5阈值）"""
        if score >= 8.5:
            return "A"
        elif score >= 7.0:
            return "B"
        elif score >= 5.0:
            return "C"
        else:
            return "D"

    def _decision_by_grade(self, grade: str) -> str:
        """根据等级映射录用建议"""
        if grade == "A":
            return "accept"
        elif grade == "B":
            return "conditional"
        else:
            return "reject"
    
    def _generate_fallback_summary(self, candidate_name: str, average_score: float,
                                  qa_history: List[Dict[str, Any]], raw_response: str) -> Dict[str, Any]:
        """生成备用总结（当JSON解析失败时）"""
        decision = self._make_decision_by_score(average_score)

        # 从原始响应中提取有意义的总结文本
        summary_text = self._extract_summary_from_raw_response(raw_response)

        return {
            "candidate_name": candidate_name,
            "final_grade": self._score_to_grade(average_score),
            "final_decision": decision,
            "overall_score": round(average_score, 1),
            "summary": summary_text,
            "strengths": [],
            "weaknesses": [],
            "confidence_level": "low",
            "recommendations": {
                "for_candidate": "建议继续提升相关技能",
                "for_program": "建议结合其他评估方式综合考虑"
            },
            "detailed_analysis": {
                "math_logic": "由于系统问题，详细分析不可用",
                "reasoning_rigor": "由于系统问题，详细分析不可用",
                "communication": "由于系统问题，详细分析不可用",
                "collaboration": "由于系统问题，详细分析不可用",
                "growth_potential": "由于系统问题，详细分析不可用"
            },
            "generated_at": datetime.now().isoformat(),
            "note": "此总结由于系统问题生成，建议人工复核"
        }
    
    def _generate_error_summary(self, candidate_name: str, average_score: float) -> Dict[str, Any]:
        """生成错误情况下的总结"""
        return {
            "candidate_name": candidate_name,
            "final_grade": self._score_to_grade(average_score),
            "final_decision": "conditional",
            "overall_score": max(0, average_score),
            "summary": "由于系统错误，无法生成完整的面试总结。建议人工审核面试记录。",
            "strengths": [],
            "weaknesses": ["系统评估异常"],
            "confidence_level": "low",
            "recommendations": {
                "for_candidate": "建议重新安排面试",
                "for_program": "建议人工审核面试过程"
            },
            "detailed_analysis": {
                "math_logic": "系统错误，无法分析",
                "reasoning_rigor": "系统错误，无法分析",
                "communication": "系统错误，无法分析", 
                "collaboration": "系统错误，无法分析",
                "growth_potential": "系统错误，无法分析"
            },
            "generated_at": datetime.now().isoformat(),
            "error": "SummaryAgent processing error"
        }

    def save_comprehensive_interview_result(self, summary_result: Dict[str, Any]) -> str:
        """
        保存完整的面试总结结果到数据库

        Args:
            summary_result (Dict[str, Any]): 完整的面试总结结果

        Returns:
            str: 操作结果信息
        """
        if self.result_collection is None:
            error_msg = "数据库连接未建立，无法保存面试结果"
            print(f"Error: {error_msg}")
            return error_msg

        try:
            # 构建完整的面试记录
            interview_record = {
                "candidate_name": summary_result.get("candidate_name", ""),
                "final_decision": summary_result.get("final_decision", ""),
                "overall_score": summary_result.get("overall_score", 0),
                "summary": summary_result.get("summary", ""),
                "strengths": summary_result.get("strengths", []),
                "weaknesses": summary_result.get("weaknesses", []),
                "recommendations": summary_result.get("recommendations", {}),
                "confidence_level": summary_result.get("confidence_level", ""),
                "detailed_analysis": summary_result.get("detailed_analysis", {}),
                "generated_at": summary_result.get("generated_at", ""),
                "timestamp": datetime.datetime.now(),
                "processed_by": "SummaryAgent",
                "database_save_status": summary_result.get("database_save_status", "")
            }

            result_insert = self.result_collection.insert_one(interview_record)
            print(f"完整面试总结已保存到数据库，记录ID: {result_insert.inserted_id}")

            return f"面试总结已成功记录到数据库。记录ID: {result_insert.inserted_id}"

        except Exception as e:
            error_msg = f"保存完整面试总结时发生错误: {str(e)}"
            print(f"Error: {error_msg}")
            return error_msg

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
    
    def _extract_summary_from_raw_response(self, raw_response: str) -> str:
        """
        从原始AI响应中提取总结文本
        JSON解析失败时直接返回整个字符串
        """
        return raw_response.strip()