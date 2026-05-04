"""
Multi-Agent Coordinator (S6 升级版)

变更要点：
- 提供 async 主入口 astart_interview / aprocess_answer
- aprocess_answer 委托给 LangGraph 状态机执行（process_turn → 并行 security/scoring → 路由）
- 保留同步 start_interview / process_answer 兼容旧调用
- MongoDB checkpointer 自动恢复跨进程状态
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from interview.tools.rag_tools import RetrievalSystem

from .graph import build_interview_graph, create_mongo_checkpointer
from .memory import MemoryRetriever, MemoryStore
from .qa_models import QATurn, get_question_type, get_score
from .question_generator import QuestionGeneratorAgent
from .question_verifier import QuestionVerifier
from .resume_parser import ResumeParser
from .scoring_agent import ScoringAgent
from .security_agent import SecurityAgent
from .session import InterviewSession
from .summary_agent import SummaryAgent


class MultiAgentCoordinator:
    """Multi-Agent Coordinator — LangGraph 编排版"""

    def __init__(self, models: Dict[str, Any]):
        self.logger = logging.getLogger("interview.agents.coordinator")

        # 组件
        self.retrieval_system = RetrievalSystem()
        self.memory_store = MemoryStore(self.retrieval_system)
        self.memory_retriever = MemoryRetriever(self.retrieval_system)

        # Agent 实例
        self.question_generator = QuestionGeneratorAgent(
            models.get("question_model"), self.retrieval_system
        )
        # ScoringAgent v3：支持多模型 ensemble + RAG anchors（W2.1）
        # 优先 scoring_models（List），向后兼容 scoring_model（single）
        scoring_models = models.get("scoring_models")
        if scoring_models is None:
            single = models.get("scoring_model")
            scoring_models = [single] if single is not None else []
        if not scoring_models:
            raise ValueError(
                "MultiAgentCoordinator: 必须提供 scoring_models (List) 或 scoring_model (single)"
            )
        self.scoring_agent = ScoringAgent(scoring_models, memory_retriever=self.memory_retriever)
        self.security_agent = SecurityAgent(models.get("security_model"))
        self.summary_agent = SummaryAgent(models.get("summary_model"))
        self.resume_parser = ResumeParser(models.get("question_model"))
        # W3.2 CoVe verifier：默认用 question_model（与出题模型一致，避免增加 API 来源）
        # 若提供 verifier_model 则用专用模型；若显式禁用 (verifier_model=False) 则跳过
        verifier_model = models.get("verifier_model", models.get("question_model"))
        if verifier_model:
            self.question_verifier = QuestionVerifier(verifier_model)
        else:
            self.question_verifier = None
            self.logger.info("CoVe verifier 已禁用（verifier_model=None）")

        # 会话管理
        self.active_sessions: Dict[str, InterviewSession] = {}

        # LangGraph 编译（懒加载 checkpointer，连接失败时降级为无 checkpoint）
        self._graph = None
        self._checkpointer = None

    # ------------------------------------------------------------
    # 内部：图构建
    # ------------------------------------------------------------

    def _ensure_graph(self):
        """懒加载 LangGraph，避免在 import 时就连 MongoDB"""
        if self._graph is not None:
            return self._graph

        try:
            self._checkpointer = create_mongo_checkpointer()
            self.logger.info("LangGraph MongoDB checkpointer 已初始化")
        except Exception as e:
            self.logger.warning(f"MongoDB checkpointer 初始化失败，降级为无 checkpoint: {e}")
            self._checkpointer = None

        self._graph = build_interview_graph(
            security_agent=self.security_agent,
            scoring_agent=self.scoring_agent,
            question_generator=self.question_generator,
            summary_agent=self.summary_agent,
            memory_store=self.memory_store,
            memory_retriever=self.memory_retriever,
            retrieval_system=self.retrieval_system,
            interview_session_provider=lambda sid: self.active_sessions.get(sid),
            question_verifier=getattr(self, "question_verifier", None),  # W3.2 注入点
            checkpointer=self._checkpointer,
        )
        return self._graph

    # ------------------------------------------------------------
    # async 主入口
    # ------------------------------------------------------------

    async def astart_interview(self, session_id: str, candidate_name: str) -> Dict[str, Any]:
        """异步启动面试"""
        try:
            self.logger.debug(f"开始面试会话: {session_id}, 候选人: {candidate_name}")

            # 拉取简历（同步阻塞调用 → 放入 thread）
            resume_data = await asyncio.to_thread(
                self.retrieval_system.get_resume_by_name, candidate_name
            )
            if "error" in resume_data:
                return {
                    "success": False,
                    "error": resume_data["error"],
                    "message": "无法获取候选人简历信息",
                }

            session = InterviewSession(
                session_id=session_id,
                candidate_name=candidate_name,
                resume_data=resume_data,
                coordinator=self,
            )
            self.active_sessions[session_id] = session

            # 简历解析（async）
            parsed_profile = await self.resume_parser.aparse(resume_data)
            session.parsed_profile = parsed_profile
            self.logger.debug(
                f"简历解析完成，提取 {len(parsed_profile.get('items', []))} 个条目"
            )

            # 创建 session_meta（同步 → thread）
            await asyncio.to_thread(
                self.memory_store.create_session,
                session_id, candidate_name, resume_data, parsed_profile,
            )

            # 生成首题（async）
            first_question = await self.question_generator.aprocess({
                "interview_stage": "opening",
                "previous_qa": [],
                "current_score": 0,
                "parsed_profile": parsed_profile,
            })

            session.current_question = first_question
            session.question_data = first_question

            question_text = (
                first_question.get("question", str(first_question))
                if isinstance(first_question, dict) else str(first_question)
            )

            return {
                "success": True,
                "session_id": session_id,
                "question_data": first_question,
                "first_question": question_text,
                "question_type": (
                    first_question.get("type", "opening")
                    if isinstance(first_question, dict) else "opening"
                ),
                "message": f"面试开始，欢迎 {candidate_name}！",
            }

        except Exception as e:
            self.logger.exception(f"启动面试时发生错误: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "启动面试时发生系统错误",
            }

    async def aprocess_answer(self, session_id: str, user_answer: str) -> Dict[str, Any]:
        """异步处理回答 — 通过 LangGraph 执行"""
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                return {
                    "success": False,
                    "error": "Session not found",
                    "message": "面试会话不存在",
                }

            graph = self._ensure_graph()

            # graph 配置：thread_id 用于 checkpoint 路由（每个 session 一个 thread）
            config = {"configurable": {"thread_id": session_id}}
            initial_state = {
                "session_id": session_id,
                "candidate_name": session.candidate_name,
                "user_answer": user_answer,
                "qa_history": session.qa_history,
                "current_question": session.current_question,
                "parsed_profile": session.parsed_profile,
            }

            final_state = await graph.ainvoke(initial_state, config=config)
            output = final_state.get("output") or {}

            # 终止状态时清理内存 session
            if final_state.get("interview_complete"):
                self.cleanup_session(session_id)

            return output if output else {
                "success": False,
                "error": "Graph returned empty output",
                "message": "处理回答时返回为空",
            }

        except Exception as e:
            self.logger.exception(f"处理回答时发生错误: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "处理回答时发生系统错误",
            }

    # ------------------------------------------------------------
    # 同步兼容入口（旧调用方）
    # ------------------------------------------------------------

    def start_interview(self, session_id: str, candidate_name: str) -> Dict[str, Any]:
        return _run_async(self.astart_interview(session_id, candidate_name))

    def process_answer(self, session_id: str, user_answer: str) -> Dict[str, Any]:
        return _run_async(self.aprocess_answer(session_id, user_answer))

    # ------------------------------------------------------------
    # 会话管理 / 历史 / 工具方法（保持原有同步接口）
    # ------------------------------------------------------------

    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        session = self.active_sessions.get(session_id)
        if not session:
            return {"exists": False}
        return {
            "exists": True,
            "candidate_name": session.candidate_name,
            "total_questions": len(session.qa_history),
            "average_score": session.get_average_score(),
            "current_question": session.current_question,
            "session_duration": (datetime.now() - session.start_time).total_seconds() / 60,
        }

    def cleanup_session(self, session_id: str):
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
        self.logger.info(f"已清理会话: {session_id}")

    def cleanup_all_sessions(self):
        for sid in list(self.active_sessions.keys()):
            self.cleanup_session(sid)

    def resume_interview(self, session_id: str) -> Dict[str, Any]:
        try:
            session_meta = self.memory_store.get_session_meta(session_id)
            if not session_meta:
                return {
                    "success": False,
                    "error": "Memory not found",
                    "message": "未找到该面试会话的记忆数据",
                }
            return self._resume_from_conversation_memories(session_id, session_meta)
        except Exception as e:
            self.logger.error(f"恢复面试会话时发生错误: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "恢复面试会话时发生系统错误",
            }

    def _resume_from_conversation_memories(
        self, session_id: str, session_meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        candidate_name = session_meta.get("candidate_name", "unknown")
        context = session_meta.get("context", {})
        resume_data = context.get("resume_data", {})

        if not resume_data:
            return {
                "success": False,
                "error": "Resume data not found",
                "message": "记忆数据中缺少简历信息",
            }

        session = InterviewSession(
            session_id=session_id,
            candidate_name=candidate_name,
            resume_data=resume_data,
            coordinator=self,
        )
        session.parsed_profile = context.get("parsed_profile")

        turns = self.memory_store.get_session_turns(session_id)
        for turn in turns:
            action = turn.get("action", {})
            reward = turn.get("reward", {}) or {}
            question_data = action.get("question_data") or {}

            qa_turn = QATurn(
                question=action.get("question_text", ""),
                answer=action.get("answer_text", ""),
                question_type=get_question_type(question_data),
                difficulty=question_data.get("difficulty", "medium")
                if isinstance(question_data, dict) else "medium",
                question_data=question_data,
                score_details=reward,
                security_check=action.get("security_check", {}),
                timestamp=turn.get("timestamp", datetime.now()),
            )
            session.qa_history.append(qa_turn.to_dict())
            session.add_score(reward.get("score", 0))

        self.active_sessions[session_id] = session

        if session.qa_history:
            last_qa = session.qa_history[-1]
            session.current_question = last_qa.get("question_data") or {
                "question": last_qa["question"],
                "type": last_qa.get("question_type", "general"),
                "difficulty": last_qa.get("difficulty", "medium"),
                "reasoning": "历史问题（无生成理由记录）",
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
        try:
            memories = self.retrieval_system.get_candidate_memories(candidate_name)
            summaries = []
            for record in memories:
                memory_data = record.get("memory_data", {})
                metadata = record.get("metadata", {})
                summaries.append({
                    "session_id": record.get("session_id"),
                    "candidate_name": memory_data.get("candidate_name"),
                    "created_at": memory_data.get("created_at"),
                    "saved_at": record.get("saved_at"),
                    "total_questions": metadata.get("total_questions", 0),
                    "average_score": metadata.get("average_score", 0),
                    "has_context": metadata.get("has_context", False),
                })
            return summaries
        except Exception as e:
            self.logger.error(f"获取候选人记忆历史时发生错误: {e}")
            return []

    def export_memory_to_file(self, session_id: str, file_path: str = None) -> Dict[str, Any]:
        try:
            meta = self.memory_store.get_session_meta(session_id)
            if not meta:
                return {
                    "success": False,
                    "error": "Memory not found",
                    "message": "未找到该面试会话的记忆数据",
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

                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2, default=_default_serializer)

            return {
                "success": True,
                "export_data": export_data,
                "message": f"记忆已导出: {session_id}",
            }
        except Exception as e:
            self.logger.error(f"导出记忆时发生错误: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "导出记忆时发生系统错误",
            }

    def __del__(self):
        try:
            self.cleanup_all_sessions()
        except Exception:
            pass


# ============================================================
# 同步 ↔ async 桥接工具
# ============================================================

def _run_async(coro):
    """在已运行 / 未运行 event loop 下都能跑 coroutine 到结果"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        pass
    return asyncio.run(coro)
