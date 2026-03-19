"""
Multi-Agent Coordinator
Coordinates the workflow of various agents and manages the entire lifecycle of interviews
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import asyncio
import logging

from .base_agent import BaseAgent, InterviewState
from .memory import MemoryStore, MemoryRetriever
from .session import InterviewSession
from interview.tools.rag_tools import RetrievalSystem
from .question_generator import QuestionGeneratorAgent
from .scoring_agent import ScoringAgent
from .security_agent import SecurityAgent
from .summary_agent import SummaryAgent
from .resume_parser import ResumeParser


class MultiAgentCoordinator:
    """Multi-Agent Coordinator"""

    def __init__(self, models: Dict[str, Any]):
        """
        Initialize the coordinator
        models: Dictionary containing different model configurations
        """
        # Initialize logger
        self.logger = logging.getLogger("interview.agents.coordinator")

        # Initialize components
        self.retrieval_system = RetrievalSystem()
        self.memory_store = MemoryStore(self.retrieval_system)
        self.memory_retriever = MemoryRetriever(self.retrieval_system)

        # Initialize agents
        self.question_generator = QuestionGeneratorAgent(
            models.get("question_model"), self.retrieval_system
        )
        self.scoring_agent = ScoringAgent(models.get("scoring_model"))
        self.security_agent = SecurityAgent(models.get("security_model"))
        self.summary_agent = SummaryAgent(models.get("summary_model"))
        self.resume_parser = ResumeParser(models.get("question_model"))

        # Interview session management
        self.active_sessions = {}  # session_id -> InterviewSession
    
    def start_interview(self, session_id: str, candidate_name: str) -> Dict[str, Any]:
        """开始面试"""
        try:
            self.logger.debug(f"开始面试会话: {session_id}, 候选人: {candidate_name}")
            
            # 获取候选人简历
            resume_data = self.retrieval_system.get_resume_by_name(candidate_name)
            if "error" in resume_data:
                return {
                    "success": False,
                    "error": resume_data["error"],
                    "message": "无法获取候选人简历信息"
                }
            
            # 创建面试会话
            session = InterviewSession(
                session_id=session_id,
                candidate_name=candidate_name,
                resume_data=resume_data,
                coordinator=self
            )
            
            self.active_sessions[session_id] = session

            # 简历结构化解析 — 生成 parsed_profile 供下游锚定出题
            parsed_profile = self.resume_parser.parse(resume_data)
            session.parsed_profile = parsed_profile
            self.logger.debug(f"简历解析完成，提取 {len(parsed_profile.get('items', []))} 个条目")

            # 在 MongoDB 中创建 session_meta 文档（增量持久化起点）
            self.memory_store.create_session(session_id, candidate_name, resume_data, parsed_profile=parsed_profile)

            # 生成开场问题
            first_question = self.question_generator.process({
                "interview_stage": "opening",
                "previous_qa": [],
                "current_score": 0,
                "parsed_profile": session.parsed_profile,
            })
            
            session.current_question = first_question
            session.question_data = first_question
            
            # 安全提取问题文本
            question_text = first_question.get("question", str(first_question)) if isinstance(first_question, dict) else str(first_question)
            
            return {
                "success": True,
                "session_id": session_id,
                "question_data": first_question,
                "first_question": question_text,
                "question_type": first_question.get("type", "opening") if isinstance(first_question, dict) else "opening",
                "message": f"面试开始，欢迎 {candidate_name}！"
            }
            
        except Exception as e:
            self.logger.error(f"启动面试时发生错误: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "启动面试时发生系统错误"
            }
    
    def process_answer(self, session_id: str, user_answer: str) -> Dict[str, Any]:
        """处理候选人的回答"""
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                return {
                    "success": False,
                    "error": "Session not found",
                    "message": "面试会话不存在"
                }

            # 1. 安全检测
            security_check = self.security_agent.process({
                "user_input": user_answer,
                "context": {
                    "session_id": session_id,
                    "candidate_name": session.candidate_name,
                    "current_question": session.current_question
                }
            })

            # 记录安全检查结果用于调试
            self.logger.debug("===== 安全检查结果 =====")
            self.logger.debug(f"风险等级: {security_check.get('risk_level', 'unknown')}")
            self.logger.debug(f"建议操作: {security_check.get('suggested_action', 'unknown')}")
            self.logger.debug(f"是否安全: {security_check.get('is_safe', True)}")
            self.logger.debug(f"检测问题: {security_check.get('detected_issues', [])}")
            self.logger.debug("========================")

            # 如果检测到高风险或建议阻止，直接结束面试
            if (security_check.get("risk_level") == "high" or
                security_check.get("suggested_action") == "block" or
                security_check.get("is_safe") == False):

                self.logger.warning("⚠️ 安全警报：检测到恶意输入，直接终止面试")

                # 记录这次恶意输入到问答历史
                malicious_qa = {
                    "question_data": session.question_data if session.question_data else {"question": "未知问题", "type": "security_violation"},
                    "question": session.current_question.get("question", "") if session.current_question else "未知问题",
                    "answer": user_answer,
                    "question_type": "security_violation",
                    "difficulty": "N/A",
                    "security_check": security_check,
                    "score_details": {"score": 0, "reasoning": "因安全违规终止面试"},
                    "timestamp": datetime.now()
                }
                session.qa_history.append(malicious_qa)
                session.add_score(0)

                # 直接调用面试终止逻辑
                return self._finalize_interview_with_security_termination(session_id, security_check)

            # 2. 记录问答
            current_qa = {
                "question_data": session.question_data,
                "question": session.current_question.get("question", ""),
                "answer": user_answer,
                "question_type": session.current_question.get("type", "general"),
                "difficulty": session.current_question.get("difficulty", "medium"),
                "security_check": security_check,
                "timestamp": datetime.now()
            }

            # 3. 评分
            scoring_result = self.scoring_agent.process({
                "question": current_qa["question"],
                "answer": user_answer,
                "question_type": current_qa["question_type"],
                "difficulty": current_qa["difficulty"]
            })

            current_qa["score_details"] = scoring_result

            # 4. 更新 session 评分追踪
            session.add_score(scoring_result["score"])
            session.qa_history.append(current_qa)

            # 4.5 增量持久化 — 将本轮 Memento 三元组写入 MongoDB
            turn_index = len(session.qa_history) - 1
            state_snapshot = {
                "turn_number": turn_index + 1,
                "cumulative_avg_score": session.get_average_score(),
                "previous_scores": session.score_list[:-1],
                "question_types_so_far": [qa.get("question_type", "general") for qa in session.qa_history[:-1]],
            }
            action_data = {
                "question_text": current_qa["question"],
                "question_data": session.question_data,
                "answer_text": user_answer,
                "security_check": security_check,
            }
            reward_data = scoring_result

            self.memory_store.save_turn(
                session_id, session.candidate_name, turn_index,
                state_snapshot, action_data, reward_data, security_check
            )

            # 5. 检查是否应该结束面试（调整为5-6轮）
            total_questions = len(session.qa_history)

            # 强制终止条件：超过6轮必须结束
            if total_questions >= 6:
                return self._finalize_interview(session_id)

            readiness_check = self.scoring_agent.evaluate_interview_readiness(
                session.qa_history,
                min_questions=4
            )

            if readiness_check["ready"]:
                return self._finalize_interview(session_id)

            # 6. 生成下一个问题
            # Memento 检索 — 从历史面试中获取相似高价值案例注入 prompt
            retrieval_query = f"{current_qa['question']} {user_answer}"
            similar_cases = self.memory_retriever.retrieve_similar_cases(
                query_text=retrieval_query, top_k=4,
                exclude_session_id=session_id, min_importance=0.3
            )
            cases_context = self.memory_retriever.format_cases_for_question_generation(similar_cases)

            next_question = self.question_generator.process({
                "interview_stage": "technical",
                "previous_qa": session.qa_history,
                "current_score": session.get_average_score(),
                "similar_cases_context": cases_context,
                "parsed_profile": session.parsed_profile,
            })

            session.current_question = next_question
            session.question_data = next_question

            # 安全提取问题文本
            next_question_text = next_question.get("question", str(next_question)) if isinstance(next_question, dict) else str(next_question)

            return {
                "success": True,
                "score": scoring_result["score"],
                "question_data": next_question,
                "next_question": next_question_text,
                "question_type": next_question.get("type", "technical") if isinstance(next_question, dict) else "technical",
                "current_average": session.get_average_score(),
                "total_questions": len(session.qa_history),
                "security_warning": security_check["risk_level"] == "medium"
            }

        except Exception as e:
            self.logger.error(f"处理回答时发生错误: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "处理回答时发生系统错误"
            }
    
    def _finalize_interview_with_security_termination(self, session_id: str, security_check: Dict[str, Any]) -> Dict[str, Any]:
        """因安全违规终止面试并生成总结"""
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                return {
                    "success": False,
                    "error": "Session not found"
                }

            self.logger.warning(f"🚨 执行安全终止面试流程: {session_id}")

            # 生成安全总结（包含此次违规）
            security_summary = self.security_agent.analyze_session_security(session.qa_history)

            # 创建专门的安全终止总结
            security_termination_summary = {
                "termination_reason": "security_violation",
                "violation_details": {
                    "detected_issues": security_check.get("detected_issues", []),
                    "risk_level": security_check.get("risk_level", "high"),
                    "reasoning": security_check.get("reasoning", ""),
                    "malicious_input": session.qa_history[-1]["answer"] if session.qa_history else "未知输入"
                },
                "interview_summary": f"面试因安全违规而提前终止。候选人 {session.candidate_name} 在面试过程中尝试进行不当操作。",
                "final_decision": "reject",
                "final_grade": "F",
                "termination_time": datetime.now().isoformat()
            }

            # 生成正式的面试总结（标记为安全终止）
            summary_result = self.summary_agent.process({
                "candidate_name": session.candidate_name,
                "resume_data": session.resume_data,
                "qa_history": session.qa_history,
                "average_score": 0,
                "security_summary": security_summary,
                "security_termination": True,
                "termination_reason": "安全违规：" + ", ".join(security_check.get("detected_issues", []))
            })

            final_summary = {
                **summary_result,
                **security_termination_summary,
                "summary": f"面试因安全违规提前终止。{summary_result.get('summary', '')}",
                "final_decision": "reject",
                "overall_score": 0
            }

            timestamp = datetime.now()
            comprehensive_result = {
                "candidate_name": session.candidate_name,
                "session_id": session_id,
                "timestamp": timestamp,
                "final_decision": "reject",
                "final_grade": "F",
                "overall_score": 0,
                "summary": final_summary.get("summary", ""),
                "scores": [qa.get("score_details", {}).get("score", 0) for qa in session.qa_history],
                "average_score": 0,
                "total_questions": len(session.qa_history),
                "qa_history": session.qa_history,
                "detailed_summary": final_summary,
                "security_summary": security_summary,
                "security_alerts": security_summary.get("security_alerts", []),
                "security_violation": security_check,
                "violation_details": security_termination_summary["violation_details"],
                "session_duration": (timestamp - session.start_time).total_seconds(),
                "termination_reason": "security_violation"
            }

            save_success = self.retrieval_system.save_interview_result(
                session.candidate_name, comprehensive_result
            )

            # 更新 conversation_memories 中的 session_meta 状态
            self.memory_store.update_session_status(session_id, "terminated_security", final_data={
                "final_summary": final_summary,
                "security_summary": security_summary,
                "final_decision": "reject",
                "final_grade": "F",
                "overall_score": 0,
                "session_duration": comprehensive_result["session_duration"],
                "termination_reason": "security_violation",
            })

            # 清理会话
            self.cleanup_session(session_id)

            return {
                "success": True,
                "interview_complete": True,
                "security_termination": True,
                "final_decision": "reject",
                "final_grade": "F",
                "overall_score": 0,
                "summary": final_summary.get("summary", ""),
                "total_questions": len(session.qa_history),
                "average_score": 0,
                "save_success": save_success,
                "termination_reason": "security_violation",
                "violation_details": security_termination_summary["violation_details"],
                "message": f"面试已因安全违规终止。检测到：{', '.join(security_check.get('detected_issues', []))}。所有数据已保存。"
            }

        except Exception as e:
            self.logger.error(f"安全终止面试时发生错误: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "安全终止面试时发生系统错误"
            }
    
    def _finalize_interview(self, session_id: str) -> Dict[str, Any]:
        """结束面试并生成总结"""
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                return {
                    "success": False,
                    "error": "Session not found"
                }

            avg_score = session.get_average_score()

            # 生成安全总结
            security_summary = self.security_agent.analyze_session_security(session.qa_history)

            # 生成最终总结
            summary_result = self.summary_agent.process({
                "candidate_name": session.candidate_name,
                "resume_data": session.resume_data,
                "qa_history": session.qa_history,
                "average_score": avg_score,
                "security_summary": security_summary
            })

            timestamp = datetime.now()
            comprehensive_result = {
                "candidate_name": session.candidate_name,
                "session_id": session_id,
                "timestamp": timestamp,
                "final_decision": summary_result.get("final_decision", "conditional"),
                "final_grade": summary_result.get("final_grade", "C"),
                "overall_score": summary_result.get("overall_score", avg_score),
                "summary": summary_result.get("summary", ""),
                "scores": [qa.get("score_details", {}).get("score", 0) for qa in session.qa_history],
                "average_score": avg_score,
                "total_questions": len(session.qa_history),
                "qa_history": session.qa_history,
                "detailed_summary": summary_result,
                "security_summary": security_summary,
                "security_alerts": security_summary.get("security_alerts", []),
                "session_duration": (timestamp - session.start_time).total_seconds(),
                "termination_reason": "normal_completion"
            }

            save_success = self.retrieval_system.save_interview_result(
                session.candidate_name, comprehensive_result
            )

            # 更新 conversation_memories 中的 session_meta 状态
            self.memory_store.update_session_status(session_id, "completed", final_data={
                "final_summary": summary_result,
                "security_summary": security_summary,
                "final_decision": summary_result.get("final_decision", "conditional"),
                "final_grade": summary_result.get("final_grade", "C"),
                "overall_score": summary_result.get("overall_score", avg_score),
                "session_duration": comprehensive_result["session_duration"],
                "termination_reason": "normal_completion",
            })

            # 清理会话
            self.cleanup_session(session_id)

            return {
                "success": True,
                "interview_complete": True,
                "final_decision": summary_result.get("final_decision", "conditional"),
                "final_grade": summary_result.get("final_grade", "C"),
                "overall_score": summary_result.get("overall_score", avg_score),
                "summary": summary_result.get("summary", ""),
                "total_questions": len(session.qa_history),
                "average_score": avg_score,
                "save_success": save_success,
                "message": "面试已完成，感谢您的参与！"
            }

        except Exception as e:
            self.logger.error(f"结束面试时发生错误: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "结束面试时发生系统错误"
            }
    
    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """获取会话状态"""
        session = self.active_sessions.get(session_id)

        if not session:
            return {"exists": False}

        return {
            "exists": True,
            "candidate_name": session.candidate_name,
            "total_questions": len(session.qa_history),
            "average_score": session.get_average_score(),
            "current_question": session.current_question,
            "session_duration": (datetime.now() - session.start_time).total_seconds() / 60
        }

    def cleanup_session(self, session_id: str):
        """清理会话资源"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
        self.logger.info(f"已清理会话: {session_id}")
    
    def cleanup_all_sessions(self):
        """清理所有会话"""
        session_ids = list(self.active_sessions.keys())
        for session_id in session_ids:
            self.cleanup_session(session_id)

    def resume_interview(self, session_id: str) -> Dict[str, Any]:
        """恢复历史面试会话 — 从 conversation_memories 恢复"""
        try:
            session_meta = self.memory_store.get_session_meta(session_id)
            if not session_meta:
                return {
                    "success": False,
                    "error": "Memory not found",
                    "message": "未找到该面试会话的记忆数据"
                }

            return self._resume_from_conversation_memories(session_id, session_meta)

        except Exception as e:
            self.logger.error(f"恢复面试会话时发生错误: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "恢复面试会话时发生系统错误"
            }

    def _resume_from_conversation_memories(self, session_id: str, session_meta: Dict[str, Any]) -> Dict[str, Any]:
        """从 conversation_memories 恢复面试会话"""
        candidate_name = session_meta.get("candidate_name", "unknown")
        context = session_meta.get("context", {})
        resume_data = context.get("resume_data", {})

        if not resume_data:
            return {
                "success": False,
                "error": "Resume data not found",
                "message": "记忆数据中缺少简历信息"
            }

        session = InterviewSession(
            session_id=session_id,
            candidate_name=candidate_name,
            resume_data=resume_data,
            coordinator=self
        )

        # 恢复 parsed_profile（从 context 中读取）
        session.parsed_profile = context.get("parsed_profile")

        # 从 turn 文档重建 qa_history + score_list
        turns = self.memory_store.get_session_turns(session_id)
        for turn in turns:
            action = turn.get("action", {})
            reward = turn.get("reward", {})
            question_data = action.get("question_data", {})
            question_text = action.get("question_text", "")

            session.qa_history.append({
                "question_data": question_data,
                "question": question_text,
                "answer": action.get("answer_text", ""),
                "question_type": question_data.get("type", "general") if isinstance(question_data, dict) else "general",
                "difficulty": question_data.get("difficulty", "medium") if isinstance(question_data, dict) else "medium",
                "score_details": reward,
                "security_check": action.get("security_check", {}),
                "timestamp": turn.get("timestamp", datetime.now()),
            })
            session.add_score(reward.get("score", 0))

        self.active_sessions[session_id] = session

        # 恢复当前问题
        if session.qa_history:
            last_qa = session.qa_history[-1]
            session.current_question = last_qa.get("question_data") or {
                "question": last_qa["question"],
                "type": last_qa.get("question_type", "general"),
                "difficulty": last_qa.get("difficulty", "medium"),
                "reasoning": "历史问题（无生成理由记录）"
            }
            session.question_data = session.current_question

        avg_score = session_meta.get("stats", {}).get("average_score", 0.0)

        return {
            "success": True,
            "session_id": session_id,
            "candidate_name": candidate_name,
            "total_questions": len(turns),
            "average_score": avg_score,
            "last_question": session.qa_history[-1]["question"] if session.qa_history else None,
            "message": f"已恢复面试会话: {candidate_name}，共{len(turns)}个问题",
        }

    def get_candidate_memory_history(self, candidate_name: str) -> List[Dict[str, Any]]:
        """获取候选人的记忆历史记录"""
        try:
            memories = self.retrieval_system.get_candidate_memories(candidate_name)
            memory_summaries = []

            for memory_record in memories:
                memory_data = memory_record.get("memory_data", {})
                metadata = memory_record.get("metadata", {})

                summary = {
                    "session_id": memory_record.get("session_id"),
                    "candidate_name": memory_data.get("candidate_name"),
                    "created_at": memory_data.get("created_at"),
                    "saved_at": memory_record.get("saved_at"),
                    "total_questions": metadata.get("total_questions", 0),
                    "average_score": metadata.get("average_score", 0),
                    "has_context": metadata.get("has_context", False)
                }
                memory_summaries.append(summary)

            return memory_summaries

        except Exception as e:
            self.logger.error(f"获取候选人记忆历史时发生错误: {e}")
            return []

    def export_memory_to_file(self, session_id: str, file_path: str = None) -> Dict[str, Any]:
        """将面试记忆导出到文件"""
        try:
            meta = self.memory_store.get_session_meta(session_id)
            if not meta:
                return {
                    "success": False,
                    "error": "Memory not found",
                    "message": "未找到该面试会话的记忆数据"
                }

            turns = self.memory_store.get_session_turns(session_id)

            export_data = {
                "session_id": session_id,
                "export_time": datetime.now().isoformat(),
                "session_meta": meta,
                "turns": turns,
            }

            if file_path:
                import json

                def _default_serializer(obj):
                    if isinstance(obj, datetime):
                        return obj.isoformat()
                    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2, default=_default_serializer)

            return {
                "success": True,
                "export_data": export_data,
                "message": f"记忆已导出: {session_id}"
            }

        except Exception as e:
            self.logger.error(f"导出记忆时发生错误: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "导出记忆时发生系统错误"
            }

    def _extract_skill_tags(self, resume_data: Dict[str, Any]) -> List[str]:
        """从简历数据中提取技能标签，用于 Memento 检索过滤"""
        tags = []
        if not resume_data or not isinstance(resume_data, dict):
            return tags

        # 尝试从常见字段提取
        skills = resume_data.get("skills", [])
        if isinstance(skills, list):
            tags.extend(skills)
        elif isinstance(skills, str):
            tags.extend([s.strip() for s in skills.split(",") if s.strip()])

        # 从 personal_statement 中提取关键词（简单实现）
        statement = resume_data.get("personal_statement", "")
        if isinstance(statement, str) and len(statement) > 0:
            # 取前几个有意义的词作为 tag
            keywords = [w for w in statement.split() if len(w) > 2][:5]
            tags.extend(keywords)

        return tags[:20]  # 限制标签数量

    def __del__(self):
        """析构函数，清理资源"""
        try:
            self.cleanup_all_sessions()
            if hasattr(self.retrieval_system, 'close_connection'):
                self.retrieval_system.close_connection()
        except:
            pass