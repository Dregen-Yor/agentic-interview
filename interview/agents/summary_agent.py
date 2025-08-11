"""
总结智能体
对面试过程进行总结并做出最终决定
"""

import json
from typing import Dict, Any, List
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage
from .base_agent import BaseAgent


class SummaryAgent(BaseAgent):
    """总结智能体"""
    
    def __init__(self, model):
        super().__init__(model, "SummaryAgent")
        self.system_prompt = """
你是一个专业的面试总结专家，负责对整个面试过程进行全面分析和总结，并做出最终的录用决定。

你的职责：
1. 综合分析候选人在整个面试过程中的表现
2. 评估候选人与职位要求的匹配度
3. 考虑各个环节的评分情况
4. 识别候选人的优势和不足
5. 做出客观的录用建议

分析维度：
1. 技术能力：专业技能掌握程度和深度
2. 经验匹配：工作经验与职位要求的契合度
3. 学习能力：接受新知识和适应变化的能力
4. 沟通表达：思路清晰度和表达能力
5. 问题解决：分析和解决问题的能力
6. 团队合作：协作意识和团队精神
7. 发展潜力：职业发展前景和成长空间

决策标准：
- 推荐录用：平均分≥7分，核心技能突出，无重大短板
- 谨慎录用：平均分6-7分，基本符合要求，有成长潜力
- 不推荐录用：平均分<6分，关键技能不足或存在严重问题

请以JSON格式返回总结结果：
{
    "final_decision": "accept/reject/conditional",
    "overall_score": 总体评分(1-10),
    "summary": "面试总结",
    "strengths": ["优势1", "优势2", "优势3"],
    "weaknesses": ["不足1", "不足2"],
    "recommendations": {
        "for_candidate": "给候选人的建议",
        "for_company": "给公司的建议"
    },
    "confidence_level": "high/medium/low",
    "detailed_analysis": {
        "technical_skills": "技术能力分析",
        "experience_match": "经验匹配分析", 
        "communication": "沟通能力分析",
        "problem_solving": "问题解决能力分析",
        "growth_potential": "发展潜力分析"
    }
}
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
            
            try:
                result = json.loads(response)
                
                # 验证和标准化结果
                result = self._validate_summary_result(result, average_score)
                
                # 添加时间戳
                result["generated_at"] = datetime.now().isoformat()
                result["candidate_name"] = candidate_name
                
                return result
                
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Failed to parse JSON response from SummaryAgent: {e}")
                
                # 生成备用总结
                return self._generate_fallback_summary(
                    candidate_name, average_score, qa_history, response
                )
                
        except Exception as e:
            print(f"Error in SummaryAgent: {e}")
            return self._generate_error_summary(candidate_name, average_score)
    
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
        if "final_decision" not in result:
            result["final_decision"] = self._make_decision_by_score(average_score)
        
        if "overall_score" not in result:
            result["overall_score"] = round(average_score, 1)
        
        # 验证决策与分数的一致性
        decision = result["final_decision"]
        score = result["overall_score"]
        
        # 如果决策与分数不匹配，以分数为准
        if score >= 7 and decision == "reject":
            result["final_decision"] = "accept"
        elif score < 4 and decision == "accept":
            result["final_decision"] = "reject"
        elif 4 <= score < 7 and decision not in ["conditional", "accept"]:
            result["final_decision"] = "conditional"
        
        # 确保其他必要字段存在
        default_values = {
            "summary": "面试总结生成中出现问题",
            "strengths": [],
            "weaknesses": [],
            "confidence_level": "medium",
            "recommendations": {
                "for_candidate": "建议继续提升相关技能",
                "for_company": "建议根据具体情况决定"
            },
            "detailed_analysis": {
                "technical_skills": "技能分析待补充",
                "experience_match": "经验匹配分析待补充",
                "communication": "沟通能力分析待补充",
                "problem_solving": "问题解决能力分析待补充",
                "growth_potential": "发展潜力分析待补充"
            }
        }
        
        for key, default_value in default_values.items():
            if key not in result:
                result[key] = default_value
        
        return result
    
    def _make_decision_by_score(self, average_score: float) -> str:
        """根据平均分做决定"""
        if average_score >= 7:
            return "accept"
        elif average_score >= 5:
            return "conditional"
        else:
            return "reject"
    
    def _generate_fallback_summary(self, candidate_name: str, average_score: float, 
                                  qa_history: List[Dict[str, Any]], raw_response: str) -> Dict[str, Any]:
        """生成备用总结（当JSON解析失败时）"""
        decision = self._make_decision_by_score(average_score)
        
        return {
            "candidate_name": candidate_name,
            "final_decision": decision,
            "overall_score": round(average_score, 1),
            "summary": raw_response,
            "strengths": [],
            "weaknesses": [],
            "confidence_level": "low",
            "recommendations": {
                "for_candidate": "建议继续提升相关技能",
                "for_company": "建议结合其他评估方式综合考虑"
            },
            "detailed_analysis": {
                "technical_skills": "由于系统问题，详细分析不可用",
                "experience_match": "由于系统问题，详细分析不可用",
                "communication": "由于系统问题，详细分析不可用",
                "problem_solving": "由于系统问题，详细分析不可用",
                "growth_potential": "由于系统问题，详细分析不可用"
            },
            "generated_at": datetime.now().isoformat(),
            "note": "此总结由于系统问题生成，建议人工复核"
        }
    
    def _generate_error_summary(self, candidate_name: str, average_score: float) -> Dict[str, Any]:
        """生成错误情况下的总结"""
        return {
            "candidate_name": candidate_name,
            "final_decision": "conditional",
            "overall_score": max(0, average_score),
            "summary": "由于系统错误，无法生成完整的面试总结。建议人工审核面试记录。",
            "strengths": [],
            "weaknesses": ["系统评估异常"],
            "confidence_level": "low",
            "recommendations": {
                "for_candidate": "建议重新安排面试",
                "for_company": "建议人工审核面试过程"
            },
            "detailed_analysis": {
                "technical_skills": "系统错误，无法分析",
                "experience_match": "系统错误，无法分析",
                "communication": "系统错误，无法分析", 
                "problem_solving": "系统错误，无法分析",
                "growth_potential": "系统错误，无法分析"
            },
            "generated_at": datetime.now().isoformat(),
            "error": "SummaryAgent processing error"
        }