"""
多智能体协调器
协调各个智能体的工作流程，管理面试的整个生命周期
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import asyncio

from .base_agent import BaseAgent, InterviewState
from .memory import MemoryManager, InterviewMemory
from .retrieval import RetrievalSystem
from .question_generator import QuestionGeneratorAgent
from .scoring_agent import ScoringAgent
from .security_agent import SecurityAgent
from .summary_agent import SummaryAgent


class MultiAgentCoordinator:
    """多智能体协调器"""
    
    def __init__(self, models: Dict[str, Any]):
        """
        初始化协调器
        models: 包含不同模型配置的字典
        """
        # 初始化各个组件
        self.retrieval_system = RetrievalSystem()
        self.memory_manager = MemoryManager()
        
        # 初始化各个智能体
        self.question_generator = QuestionGeneratorAgent(
            models.get("question_model"), self.retrieval_system
        )
        self.scoring_agent = ScoringAgent(models.get("scoring_model"))
        self.security_agent = SecurityAgent(models.get("security_model"))
        self.summary_agent = SummaryAgent(models.get("summary_model"))
        
        # 面试会话管理
        self.active_sessions = {}  # session_id -> InterviewSession
    
    def start_interview(self, session_id: str, candidate_name: str) -> Dict[str, Any]:
        """开始面试"""
        try:
            print(f"开始面试会话: {session_id}, 候选人: {candidate_name}")
            
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
            
            # 创建记忆实例
            memory = self.memory_manager.create_memory(session_id, candidate_name)
            memory.set_context("resume_data", resume_data)
            memory.set_context("session_start", datetime.now())
            
            # 生成开场问题
            first_question = self.question_generator.process({
                "resume_data": resume_data,
                "interview_stage": "opening",
                "previous_qa": [],
                "current_score": 0
            })
            
            session.current_question = first_question
            
            return {
                "success": True,
                "session_id": session_id,
                "first_question": first_question["question"],
                "question_type": first_question.get("type", "opening"),
                "message": f"面试开始，欢迎 {candidate_name}！"
            }
            
        except Exception as e:
            print(f"启动面试时发生错误: {e}")
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
            
            memory = self.memory_manager.get_memory(session_id)
            if not memory:
                return {
                    "success": False,
                    "error": "Memory not found", 
                    "message": "面试记忆不存在"
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
            
            # 如果检测到高风险，直接返回警告
            if security_check["risk_level"] == "high":
                return {
                    "success": False,
                    "security_alert": True,
                    "message": "检测到不当输入，请重新回答。",
                    "details": security_check["reasoning"]
                }
            
            # 2. 记录问答
            current_qa = {
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
                "difficulty": current_qa["difficulty"],
                "resume_data": session.resume_data
            })
            
            current_qa["score_details"] = scoring_result
            
            # 4. 更新记忆
            memory.add_question_answer(
                current_qa["question"], 
                user_answer, 
                current_qa["timestamp"]
            )
            memory.add_score(
                len(memory.qa_history) - 1,  # 最新问题的ID
                scoring_result["score"],
                scoring_result.get("reasoning", "")
            )
            
            session.qa_history.append(current_qa)
            
            # 5. 检查是否应该结束面试
            readiness_check = self.scoring_agent.evaluate_interview_readiness(
                session.qa_history, 
                min_questions=3
            )
            
            if readiness_check["ready"]:
                # 生成最终总结
                return self._finalize_interview(session_id)
            
            # 6. 生成下一个问题
            next_question = self.question_generator.process({
                "resume_data": session.resume_data,
                "interview_stage": "technical",
                "previous_qa": session.qa_history,
                "current_score": memory.get_average_score()
            })
            
            session.current_question = next_question
            
            return {
                "success": True,
                "score": scoring_result["score"],
                "next_question": next_question["question"],
                "question_type": next_question.get("type", "technical"),
                "current_average": memory.get_average_score(),
                "total_questions": len(session.qa_history),
                "security_warning": security_check["risk_level"] == "medium"
            }
            
        except Exception as e:
            print(f"处理回答时发生错误: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "处理回答时发生系统错误"
            }
    
    def _finalize_interview(self, session_id: str) -> Dict[str, Any]:
        """结束面试并生成总结"""
        try:
            session = self.active_sessions.get(session_id)
            memory = self.memory_manager.get_memory(session_id)
            
            if not session or not memory:
                return {
                    "success": False,
                    "error": "Session or memory not found"
                }
            
            # 生成安全总结
            security_summary = self.security_agent.analyze_session_security(session.qa_history)
            
            # 生成最终总结
            summary_result = self.summary_agent.process({
                "candidate_name": session.candidate_name,
                "resume_data": session.resume_data,
                "qa_history": session.qa_history,
                "average_score": memory.get_average_score(),
                "security_summary": security_summary
            })
            
            # 保存面试结果到数据库
            result_data = {
                "summary": summary_result.get("summary", ""),
                "final_decision": summary_result.get("final_decision") == "accept",
                "scores": [qa.get("score_details", {}).get("score", 0) for qa in session.qa_history],
                "average_score": memory.get_average_score(),
                "total_questions": len(session.qa_history),
                "timestamp": datetime.now(),
                "security_alerts": security_summary.get("security_alerts", []),
                "qa_history": session.qa_history,
                "detailed_summary": summary_result
            }
            
            save_success = self.retrieval_system.save_interview_result(
                session.candidate_name, result_data
            )
            
            # 清理会话
            self.cleanup_session(session_id)
            
            return {
                "success": True,
                "interview_complete": True,
                "final_decision": summary_result.get("final_decision", "conditional"),
                "overall_score": summary_result.get("overall_score", memory.get_average_score()),
                "summary": summary_result.get("summary", ""),
                "total_questions": len(session.qa_history),
                "average_score": memory.get_average_score(),
                "save_success": save_success,
                "message": "面试已完成，感谢您的参与！"
            }
            
        except Exception as e:
            print(f"结束面试时发生错误: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "结束面试时发生系统错误"
            }
    
    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """获取会话状态"""
        session = self.active_sessions.get(session_id)
        memory = self.memory_manager.get_memory(session_id)
        
        if not session:
            return {"exists": False}
        
        return {
            "exists": True,
            "candidate_name": session.candidate_name,
            "total_questions": len(session.qa_history),
            "average_score": memory.get_average_score() if memory else 0,
            "current_question": session.current_question,
            "session_duration": (datetime.now() - session.start_time).total_seconds() / 60  # 分钟
        }
    
    def cleanup_session(self, session_id: str):
        """清理会话资源"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
        
        self.memory_manager.remove_memory(session_id)
        print(f"已清理会话: {session_id}")
    
    def cleanup_all_sessions(self):
        """清理所有会话"""
        session_ids = list(self.active_sessions.keys())
        for session_id in session_ids:
            self.cleanup_session(session_id)
    
    def __del__(self):
        """析构函数，清理资源"""
        try:
            self.cleanup_all_sessions()
            if hasattr(self.retrieval_system, 'close_connection'):
                self.retrieval_system.close_connection()
        except:
            pass


class InterviewSession:
    """面试会话类"""
    
    def __init__(self, session_id: str, candidate_name: str, resume_data: Dict[str, Any], coordinator):
        self.session_id = session_id
        self.candidate_name = candidate_name
        self.resume_data = resume_data
        self.coordinator = coordinator
        self.start_time = datetime.now()
        self.qa_history = []
        self.current_question = None
        self.is_active = True
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "session_id": self.session_id,
            "candidate_name": self.candidate_name,
            "start_time": self.start_time.isoformat(),
            "total_questions": len(self.qa_history),
            "is_active": self.is_active,
            "current_question": self.current_question
        }