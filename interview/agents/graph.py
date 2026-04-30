"""
LangGraph 状态机 (S6) — 替换原 coordinator 中的 if/else 编排

核心改进：
1. 显式声明状态图（process_answer 拓扑）
2. security_check 与 score 通过 asyncio.gather 在 process_turn_node 内部并行
3. MongoDB checkpointer 实现跨进程状态恢复（崩溃安全）
4. 节点级条件路由替代散落的 if 分支

拓扑：
  START → process_turn_node ──┬─→ finalize_security  → END
                              ├─→ finalize_normal    → END
                              └─→ next_question_node → END (单轮回合)

每轮 process_answer 是一次完整的 graph.ainvoke，状态从 MongoDB 恢复并保存。
首轮（start_interview）由独立的 start_node 处理。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.graph import END, START, StateGraph
from pymongo import MongoClient

from interview.tools.db import get_mongo_client

from .qa_models import QATurn, get_question_type, get_score

logger = logging.getLogger("interview.agents.graph")


# ============================================================
# State 定义
# ============================================================

class InterviewGraphState(TypedDict, total=False):
    """LangGraph 共享状态 — 单轮 process_answer 的完整上下文"""

    session_id: str
    candidate_name: str
    resume_data: Dict[str, Any]
    parsed_profile: Optional[Dict[str, Any]]
    qa_history: List[Dict[str, Any]]

    # 当前轮
    current_question: Optional[Dict[str, Any]]
    user_answer: str

    # 节点产出
    security_check: Optional[Dict[str, Any]]
    score_details: Optional[Dict[str, Any]]
    similar_cases_context: str
    next_question: Optional[Dict[str, Any]]

    # 控制流
    should_block: bool
    interview_complete: bool
    finalize_reason: str  # "security" | "normal" | "continue"
    final_summary: Optional[Dict[str, Any]]
    average_score: float
    total_questions: int

    # 出口数据（提供给 coordinator 返回前端）
    output: Dict[str, Any]


# ============================================================
# 节点工厂（依赖注入式）
# ============================================================

def build_interview_graph(
    *,
    security_agent,
    scoring_agent,
    question_generator,
    summary_agent,
    memory_store,
    memory_retriever,
    retrieval_system,
    interview_session_provider,
    checkpointer=None,
):
    """
    构造 process_answer 的状态图。
    interview_session_provider: 给定 session_id 返回 InterviewSession（供 coordinator 共享内存态）
    """

    # ---------------- 节点：处理一轮回合 ----------------
    async def process_turn_node(state: InterviewGraphState) -> Dict[str, Any]:
        """
        核心并行节点：security_check 与 scoring 同时执行（asyncio.gather）。
        内部完成：安全检测 + 评分 + 持久化 + readiness 判定。
        """
        session_id = state["session_id"]
        user_answer = state.get("user_answer", "")
        session = interview_session_provider(session_id)
        if not session:
            return {
                "should_block": False,
                "interview_complete": True,
                "finalize_reason": "error",
                "output": {"success": False, "error": "Session not found"},
            }

        current_question = session.current_question or {}

        # 并行执行：security + scoring（最大瓶颈优化点）
        security_task = security_agent.aprocess({
            "user_input": user_answer,
            "context": {
                "session_id": session_id,
                "candidate_name": session.candidate_name,
                "current_question": current_question,
            },
        })
        scoring_task = scoring_agent.aprocess({
            "question": current_question.get("question", "") if current_question else "",
            "answer": user_answer,
            "question_type": get_question_type(current_question),
            "difficulty": (current_question or {}).get("difficulty", "medium"),
        })
        security_check, scoring_result = await asyncio.gather(
            security_task, scoring_task, return_exceptions=False
        )

        logger.debug(
            "[graph] security risk=%s action=%s | score=%s",
            security_check.get("risk_level"),
            security_check.get("suggested_action"),
            scoring_result.get("score"),
        )

        # 1. 安全短路 — block 时立即终止
        should_block = (
            security_check.get("suggested_action") == "block"
            or security_check.get("risk_level") == "high"
        )
        if should_block:
            malicious_turn = QATurn(
                question=current_question.get("question", "") if current_question else "未知问题",
                answer=user_answer,
                question_type="security_violation",
                difficulty="N/A",
                question_data=session.question_data or {"question": "未知问题", "type": "security_violation"},
                score_details={"score": 0, "reasoning": "因安全违规终止面试"},
                security_check=security_check,
            )
            session.qa_history.append(malicious_turn.to_dict())
            session.add_score(0)
            return {
                "security_check": security_check,
                "score_details": {"score": 0},
                "should_block": True,
                "interview_complete": True,
                "finalize_reason": "security",
            }

        # 2. 正常记录 + 持久化
        current_turn = QATurn(
            question=current_question.get("question", "") if current_question else "",
            answer=user_answer,
            question_type=get_question_type(current_question),
            difficulty=(current_question or {}).get("difficulty", "medium"),
            question_data=session.question_data,
            security_check=security_check,
            score_details=scoring_result,
        )
        session.qa_history.append(current_turn.to_dict())
        session.add_score(scoring_result["score"])

        # 持久化 turn（同步 MongoDB 写）
        turn_index = len(session.qa_history) - 1
        state_snapshot = {
            "turn_number": turn_index + 1,
            "cumulative_avg_score": session.get_average_score(),
            "previous_scores": session.score_list[:-1],
            "question_types_so_far": [get_question_type(qa) for qa in session.qa_history[:-1]],
        }
        action_data = {
            "question_text": current_turn.question,
            "question_data": session.question_data,
            "answer_text": user_answer,
            "security_check": security_check,
        }

        await asyncio.to_thread(
            memory_store.save_turn,
            session_id, session.candidate_name, turn_index,
            state_snapshot, action_data, scoring_result, security_check,
        )

        # 3. 终止判定
        total_questions = len(session.qa_history)
        if total_questions >= 6:
            return {
                "security_check": security_check,
                "score_details": scoring_result,
                "should_block": False,
                "interview_complete": True,
                "finalize_reason": "normal",
                "total_questions": total_questions,
            }

        readiness = scoring_agent.evaluate_interview_readiness(session.qa_history, min_questions=4)
        if readiness["ready"]:
            return {
                "security_check": security_check,
                "score_details": scoring_result,
                "should_block": False,
                "interview_complete": True,
                "finalize_reason": "normal",
                "total_questions": total_questions,
            }

        # 4. 触发 Memento 检索（在 thread 中跑同步检索 + embedding 生成）
        retrieval_query = f"{current_turn.question} {user_answer}"
        similar_cases = await asyncio.to_thread(
            memory_retriever.retrieve_similar_cases,
            retrieval_query, 4, session_id, None, 0.3,
        )
        cases_context = memory_retriever.format_cases_for_question_generation(similar_cases)

        return {
            "security_check": security_check,
            "score_details": scoring_result,
            "similar_cases_context": cases_context,
            "should_block": False,
            "interview_complete": False,
            "finalize_reason": "continue",
            "total_questions": total_questions,
            "average_score": session.get_average_score(),
        }

    # ---------------- 节点：生成下一题 ----------------
    async def next_question_node(state: InterviewGraphState) -> Dict[str, Any]:
        session_id = state["session_id"]
        session = interview_session_provider(session_id)
        if not session:
            return {"output": {"success": False, "error": "Session not found"}}

        next_q = await question_generator.aprocess({
            "interview_stage": "technical",
            "previous_qa": session.qa_history,
            "current_score": session.get_average_score(),
            "similar_cases_context": state.get("similar_cases_context", ""),
            "parsed_profile": session.parsed_profile,
        })

        session.current_question = next_q
        session.question_data = next_q

        next_question_text = (
            next_q.get("question", str(next_q)) if isinstance(next_q, dict) else str(next_q)
        )

        output = {
            "success": True,
            "score": state.get("score_details", {}).get("score", 0),
            "question_data": next_q,
            "next_question": next_question_text,
            "question_type": next_q.get("type", "technical") if isinstance(next_q, dict) else "technical",
            "current_average": session.get_average_score(),
            "total_questions": len(session.qa_history),
            "security_warning": (state.get("security_check") or {}).get("risk_level") == "medium",
        }
        return {"next_question": next_q, "output": output}

    # ---------------- 节点：正常结束 ----------------
    async def finalize_normal_node(state: InterviewGraphState) -> Dict[str, Any]:
        session_id = state["session_id"]
        session = interview_session_provider(session_id)
        if not session:
            return {"output": {"success": False, "error": "Session not found"}}

        avg_score = session.get_average_score()
        security_summary = security_agent.analyze_session_security(session.qa_history)

        summary_result = await summary_agent.aprocess({
            "candidate_name": session.candidate_name,
            "resume_data": session.resume_data,
            "qa_history": session.qa_history,
            "average_score": avg_score,
            "security_summary": security_summary,
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
            "scores": [get_score(qa) for qa in session.qa_history],
            "average_score": avg_score,
            "total_questions": len(session.qa_history),
            "qa_history": session.qa_history,
            "detailed_summary": summary_result,
            "security_summary": security_summary,
            "security_alerts": security_summary.get("security_alerts", []),
            "session_duration": (timestamp - session.start_time).total_seconds(),
            "termination_reason": "normal_completion",
        }

        save_success = await asyncio.to_thread(
            retrieval_system.save_interview_result,
            session.candidate_name, comprehensive_result,
        )
        await asyncio.to_thread(
            memory_store.update_session_status,
            session_id, "completed", {
                "final_summary": summary_result,
                "security_summary": security_summary,
                "final_decision": summary_result.get("final_decision", "conditional"),
                "final_grade": summary_result.get("final_grade", "C"),
                "overall_score": summary_result.get("overall_score", avg_score),
                "session_duration": comprehensive_result["session_duration"],
                "termination_reason": "normal_completion",
            },
        )

        output = {
            "success": True,
            "interview_complete": True,
            "final_decision": summary_result.get("final_decision", "conditional"),
            "final_grade": summary_result.get("final_grade", "C"),
            "overall_score": summary_result.get("overall_score", avg_score),
            "summary": summary_result.get("summary", ""),
            "total_questions": len(session.qa_history),
            "average_score": avg_score,
            "save_success": save_success,
            "message": "面试已完成，感谢您的参与！",
        }
        return {"final_summary": summary_result, "output": output}

    # ---------------- 节点：安全终止 ----------------
    async def finalize_security_node(state: InterviewGraphState) -> Dict[str, Any]:
        session_id = state["session_id"]
        session = interview_session_provider(session_id)
        if not session:
            return {"output": {"success": False, "error": "Session not found"}}

        security_check = state.get("security_check", {})
        security_summary = security_agent.analyze_session_security(session.qa_history)

        summary_result = await summary_agent.aprocess({
            "candidate_name": session.candidate_name,
            "resume_data": session.resume_data,
            "qa_history": session.qa_history,
            "average_score": 0,
            "security_summary": security_summary,
            "security_termination": True,
            "termination_reason": "安全违规：" + ", ".join(security_check.get("detected_issues", [])),
        })

        termination_summary = {
            "termination_reason": "security_violation",
            "violation_details": {
                "detected_issues": security_check.get("detected_issues", []),
                "risk_level": security_check.get("risk_level", "high"),
                "reasoning": security_check.get("reasoning", ""),
                "malicious_input": session.qa_history[-1]["answer"] if session.qa_history else "未知输入",
            },
            "interview_summary": (
                f"面试因安全违规而提前终止。候选人 {session.candidate_name} 在面试过程中尝试进行不当操作。"
            ),
            "final_decision": "reject",
            "final_grade": "F",
            "termination_time": datetime.now().isoformat(),
        }

        final_summary = {
            **summary_result,
            **termination_summary,
            "summary": f"面试因安全违规提前终止。{summary_result.get('summary', '')}",
            "final_decision": "reject",
            "overall_score": 0,
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
            "scores": [get_score(qa) for qa in session.qa_history],
            "average_score": 0,
            "total_questions": len(session.qa_history),
            "qa_history": session.qa_history,
            "detailed_summary": final_summary,
            "security_summary": security_summary,
            "security_alerts": security_summary.get("security_alerts", []),
            "security_violation": security_check,
            "violation_details": termination_summary["violation_details"],
            "session_duration": (timestamp - session.start_time).total_seconds(),
            "termination_reason": "security_violation",
        }

        save_success = await asyncio.to_thread(
            retrieval_system.save_interview_result,
            session.candidate_name, comprehensive_result,
        )
        await asyncio.to_thread(
            memory_store.update_session_status,
            session_id, "terminated_security", {
                "final_summary": final_summary,
                "security_summary": security_summary,
                "final_decision": "reject",
                "final_grade": "F",
                "overall_score": 0,
                "session_duration": comprehensive_result["session_duration"],
                "termination_reason": "security_violation",
            },
        )

        output = {
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
            "violation_details": termination_summary["violation_details"],
            "message": (
                f"面试已因安全违规终止。检测到：{', '.join(security_check.get('detected_issues', []))}。"
                f"所有数据已保存。"
            ),
        }
        return {"final_summary": final_summary, "output": output}

    # ---------------- 路由函数 ----------------
    def route_after_turn(state: InterviewGraphState) -> str:
        reason = state.get("finalize_reason", "continue")
        if reason == "security":
            return "finalize_security"
        if reason == "normal":
            return "finalize_normal"
        return "next_question"

    # ---------------- 图构建 ----------------
    builder = StateGraph(InterviewGraphState)
    builder.add_node("process_turn", process_turn_node)
    builder.add_node("next_question", next_question_node)
    builder.add_node("finalize_normal", finalize_normal_node)
    builder.add_node("finalize_security", finalize_security_node)

    builder.add_edge(START, "process_turn")
    builder.add_conditional_edges(
        "process_turn",
        route_after_turn,
        {
            "next_question": "next_question",
            "finalize_normal": "finalize_normal",
            "finalize_security": "finalize_security",
        },
    )
    builder.add_edge("next_question", END)
    builder.add_edge("finalize_normal", END)
    builder.add_edge("finalize_security", END)

    return builder.compile(checkpointer=checkpointer)


# ============================================================
# Checkpointer 工厂
# ============================================================

def create_mongo_checkpointer(db_name: str = "interview", collection: str = "langgraph_checkpoints") -> MongoDBSaver:
    """构造基于现有 MongoDB 共享连接的 LangGraph checkpointer"""
    client: MongoClient = get_mongo_client()
    return MongoDBSaver(
        client=client,
        db_name=db_name,
        checkpoint_collection_name=collection,
        writes_collection_name=f"{collection}_writes",
    )
