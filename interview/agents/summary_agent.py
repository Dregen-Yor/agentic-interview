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
你是一个大学内计算机拔尖班（科研方向）面试总结专家。对象为大一新生，应以数理与逻辑基础为核心，兼顾基本素质与与人交往能力，重点识别科研潜力。

你的职责：
1. 综合分析候选人在面试中的数理逻辑、推理严谨性、表达沟通、合作基线与成长潜力；
2. 对候选人自述的已学内容与追问表现给出客观评价；
3. 结合各环节评分，给出最终字母等级（A/B/C/D）与录用建议；
4. 强调公平与客观，避免偏见与无关的隐私评判。

分析维度（参考）：
1. 数理/逻辑基础：概念理解、抽象能力、形式化与严谨性；
2. 推理与问题解决：多步推理质量、边界与反例意识；
3. 表达与沟通：结构化与清晰度、倾听与回应；
4. 合作与社交基线：尊重他人、团队协作与稳定性；
5. 成长潜力：学习动机与反思、科研兴趣与探索态度。

等级与建议（面向最终评价）：
- A：推荐录取（通常对应平均分≥8.5）
- B：可以考虑录取（通常对应平均分7.0-8.4）
- C：不推荐录取（通常对应平均分5.0-6.9）
- D：基本不能录取（通常对应平均分<5.0）

请以JSON格式返回总结结果：
{
    "final_grade": "A/B/C/D",
    "final_decision": "accept/reject/conditional",
    "overall_score": 总体评分(1-10),
    "summary": "面试总结",
    "strengths": ["优势1", "优势2", "优势3"],
    "weaknesses": ["不足1", "不足2"],
    "recommendations": {
        "for_candidate": "给候选人的建议",
        "for_program": "给拔尖班的建议"
    },
    "confidence_level": "high/medium/low",
    "detailed_analysis": {
        "math_logic": "数理与逻辑分析",
        "reasoning_rigor": "推理严谨性分析",
        "communication": "沟通能力分析",
        "collaboration": "合作与社交分析",
        "growth_potential": "成长潜力分析"
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

                # 自动保存面试结果到数据库
                save_result = self.save_comprehensive_interview_result(result)
                result["database_save_status"] = save_result

                return result
                
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Failed to parse JSON response from SummaryAgent: {e}")
                
                # 生成备用总结
                fallback_result = self._generate_fallback_summary(
                    candidate_name, average_score, qa_history, response
                )

                # 保存备用总结到数据库
                save_result = self.save_comprehensive_interview_result(fallback_result)
                fallback_result["database_save_status"] = save_result

                return fallback_result
                
        except Exception as e:
            print(f"Error in SummaryAgent: {e}")
            error_result = self._generate_error_summary(candidate_name, average_score)

            # 保存错误总结到数据库
            save_result = self.save_comprehensive_interview_result(error_result)
            error_result["database_save_status"] = save_result

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
        
        return {
            "candidate_name": candidate_name,
            "final_grade": self._score_to_grade(average_score),
            "final_decision": decision,
            "overall_score": round(average_score, 1),
            "summary": raw_response,
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
        if not self.result_collection:
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
                "processed_by": "SummaryAgent"
            }

            result_insert = self.result_collection.insert_one(interview_record)
            print(f"完整面试总结已保存到数据库，记录ID: {result_insert.inserted_id}")

            return f"面试总结已成功记录到数据库。记录ID: {result_insert.inserted_id}"

        except Exception as e:
            error_msg = f"保存完整面试总结时发生错误: {str(e)}"
            print(f"Error: {error_msg}")
            return error_msg