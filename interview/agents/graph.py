"""
LangGraph 状态机 v3 — 6 节点 pure-function 拓扑（W3.1 重构）

论文锚点：
- LangGraph Best Practices: 节点 pure function，返回 partial state update，避免 mutate
- LLMs Cannot Self-Correct (ICLR 2024): 不要把所有逻辑塞一个节点，应该单职责拆分

核心改动 vs v2：
- 旧 process_turn_node 巨石节点 → 拆为 4 个节点
- 仅 persist_node 和 next_question_node 允许 mutate InterviewSession
  （这是 LangGraph 中 session 写入的唯一合法位置）
- 每个节点的 partial state update 仅返回该节点产出，不修改其他字段
- Memento PER importance（W3.3）由 persist_node 调用 save_turn 时传入 baseline_score
- CoVe verifier 由 next_question_node 调用（W3.2 接入）

拓扑：
  START → security_node ──┬─→ finalize_security_node → END
                          └─→ scoring_node → persist_node → readiness_node
                                                                ├─→ finalize_normal_node → END
                                                                └─→ retrieval_node → next_question_node → END

每个节点的契约：
  security_node    : 输入 user_answer + current_question，输出 security_check + finalize_reason
  scoring_node     : 输入 question/answer/session_id，输出 scoring_result（ScoringOutput dict）
  persist_node     : 唯一允许 mutate session.qa_history + 写 MongoDB；输出 persisted=True
  readiness_node   : 输入 session 状态，输出 is_ready + finalize_reason
  retrieval_node   : 输入 question+answer，输出 similar_cases_context（Memento）
  next_question_node: 调用 question_generator + (W3.2) CoVe verifier，mutate session.current_question
  finalize_normal  : 生成总结 + 持久化结果，输出 final_summary
  finalize_security: 安全终止专用 finalize
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, TypedDict

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

    # 输入
    session_id: str
    candidate_name: str
    resume_data: Dict[str, Any]
    parsed_profile: Optional[Dict[str, Any]]
    qa_history: List[Dict[str, Any]]
    current_question: Optional[Dict[str, Any]]
    user_answer: str

    # 节点产出（按拓扑顺序）
    security_check: Optional[Dict[str, Any]]      # security_node
    scoring_result: Optional[Dict[str, Any]]      # scoring_node — ScoringOutput dict (含 dimensions)
    persisted: bool                                # persist_node
    is_ready: bool                                 # readiness_node
    similar_cases_context: str                     # retrieval_node
    next_question: Optional[Dict[str, Any]]        # next_question_node
    final_summary: Optional[Dict[str, Any]]        # finalize_*

    # 控制流
    should_block: bool
    interview_complete: bool
    finalize_reason: str  # "security" | "normal" | "continue" | "error"
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
    question_verifier=None,        # W3.2 可选注入
    checkpointer=None,
):
    """
    构造 process_answer 的状态图（6 节点拓扑）。

    interview_session_provider: 给定 session_id 返回 InterviewSession（供 persist/next_q 节点 mutate）

    persist_node 与 next_question_node 是仅有的两个允许 mutate session 的节点；
    其他节点只读访问 session（用于读取 qa_history / parsed_profile 等）。
    """

    # ============================================================
    # 节点 1：security_node — 安全检测
    # ============================================================
    async def security_node(state: InterviewGraphState) -> Dict[str, Any]:
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
        security_check = await security_agent.aprocess({
            "user_input": user_answer,
            "context": {
                "session_id": session_id,
                "candidate_name": session.candidate_name,
                "current_question": current_question,
            },
        })

        should_block = (
            security_check.get("suggested_action") == "block"
            or security_check.get("risk_level") == "high"
        )
        logger.debug(
            "[security_node] risk=%s action=%s block=%s",
            security_check.get("risk_level"),
            security_check.get("suggested_action"),
            should_block,
        )

        if should_block:
            # 安全终止：mutate session（这是 security 路径的合法 mutation 点）
            malicious_turn = QATurn(
                question=current_question.get("question", "") if current_question else "未知问题",
                answer=user_answer,
                question_type="security_violation",
                difficulty="N/A",
                question_data=session.question_data
                or {"question": "未知问题", "type": "security_violation"},
                score_details={"score": 0, "reasoning": "因安全违规终止面试"},
                security_check=security_check,
            )
            session.qa_history.append(malicious_turn.to_dict())
            session.add_score(0)
            return {
                "security_check": security_check,
                "should_block": True,
                "interview_complete": True,
                "finalize_reason": "security",
            }

        return {
            "security_check": security_check,
            "should_block": False,
            "finalize_reason": "continue",
        }

    # ============================================================
    # 节点 2：scoring_node — MTS 多维度评分（W1 + W2 接入）
    # ============================================================
    async def scoring_node(state: InterviewGraphState) -> Dict[str, Any]:
        session_id = state["session_id"]
        session = interview_session_provider(session_id)
        if not session:
            return {"finalize_reason": "error", "output": {"success": False, "error": "Session not found"}}

        current_question = session.current_question or {}
        scoring_result = await scoring_agent.aprocess({
            "question": current_question.get("question", "") if current_question else "",
            "answer": state.get("user_answer", ""),
            "question_type": get_question_type(current_question),
            "difficulty": (current_question or {}).get("difficulty", "medium"),
            "session_id": session_id,  # 用于 RAG anchors exclude_session_id（避免 self-leak）
        })
        logger.debug(
            "[scoring_node] score=%s agreement=%s conf=%s review=%s",
            scoring_result.get("score"),
            scoring_result.get("agreement"),
            scoring_result.get("confidence_level"),
            scoring_result.get("requires_human_review"),
        )
        return {"scoring_result": scoring_result}

    # ============================================================
    # 节点 3：persist_node — 唯一允许 mutate session + 写 MongoDB
    # ============================================================
    async def persist_node(state: InterviewGraphState) -> Dict[str, Any]:
        session_id = state["session_id"]
        session = interview_session_provider(session_id)
        if not session:
            return {"persisted": False, "finalize_reason": "error",
                    "output": {"success": False, "error": "Session not found"}}

        scoring_result = state.get("scoring_result") or {}
        security_check = state.get("security_check") or {}
        current_question = session.current_question or {}
        user_answer = state.get("user_answer", "")

        # 1. 内存 session.qa_history 追加（合法 mutate 点）
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
        session.add_score(scoring_result.get("score", 0))

        # 2. 准备 turn 持久化的元数据
        turn_index = len(session.qa_history) - 1
        state_snapshot = {
            "turn_number": turn_index + 1,
            "cumulative_avg_score": session.get_average_score(),
            "previous_scores": session.score_list[:-1],
            "question_types_so_far": [
                get_question_type(qa) for qa in session.qa_history[:-1]
            ],
        }
        action_data = {
            "question_text": current_turn.question,
            "question_data": session.question_data,
            "answer_text": user_answer,
            "security_check": security_check,
        }

        # 3. PER importance（W3.3）：传入 baseline_score = 候选人当前历史均分
        # 首次（无历史）默认 5.0；之后用 session.get_average_score()
        baseline = session.get_average_score() if turn_index > 0 else 5.0
        await asyncio.to_thread(
            memory_store.save_turn,
            session_id, session.candidate_name, turn_index,
            state_snapshot, action_data, scoring_result, security_check,
            baseline,
        )
        logger.debug(
            "[persist_node] turn=%d total=%d avg=%.2f baseline=%.2f",
            turn_index + 1,
            len(session.qa_history),
            session.get_average_score(),
            baseline,
        )
        return {"persisted": True, "total_questions": len(session.qa_history),
                "average_score": session.get_average_score()}

    # ============================================================
    # 节点 4：readiness_node — 决定 finalize_normal vs continue
    # ============================================================
    async def readiness_node(state: InterviewGraphState) -> Dict[str, Any]:
        session_id = state["session_id"]
        session = interview_session_provider(session_id)
        if not session:
            return {"finalize_reason": "error",
                    "output": {"success": False, "error": "Session not found"}}

        total = len(session.qa_history)
        # 强制终止：≥ 6 题
        if total >= 6:
            return {
                "is_ready": True,
                "finalize_reason": "normal",
                "total_questions": total,
            }
        # 提前终止：readiness 判定
        readiness = scoring_agent.evaluate_interview_readiness(
            session.qa_history, min_questions=4
        )
        is_ready = readiness["ready"]
        return {
            "is_ready": is_ready,
            "finalize_reason": "normal" if is_ready else "continue",
            "total_questions": total,
        }

    # ============================================================
    # 节点 5：retrieval_node — Memento 检索相似案例供下题
    # ============================================================
    async def retrieval_node(state: InterviewGraphState) -> Dict[str, Any]:
        session_id = state["session_id"]
        session = interview_session_provider(session_id)
        if not session or not session.qa_history:
            return {"similar_cases_context": ""}

        last_qa = session.qa_history[-1]
        retrieval_query = f"{last_qa.get('question', '')} {last_qa.get('answer', '')}"
        try:
            similar_cases = await asyncio.to_thread(
                memory_retriever.retrieve_similar_cases,
                retrieval_query, 4, session_id, None, 0.3,
            )
            cases_context = memory_retriever.format_cases_for_question_generation(similar_cases)
        except Exception as e:
            logger.warning(f"[retrieval_node] 检索失败（不阻塞下题）: {e}")
            cases_context = ""
        return {"similar_cases_context": cases_context}

    # ============================================================
    # 节点 6：next_question_node — 生成下一题（含 CoVe verifier W3.2）
    # ============================================================
    async def next_question_node(state: InterviewGraphState) -> Dict[str, Any]:
        session_id = state["session_id"]
        session = interview_session_provider(session_id)
        if not session:
            return {"output": {"success": False, "error": "Session not found"}}

        gen_input = {
            "interview_stage": "technical",
            "previous_qa": session.qa_history,
            "current_score": session.get_average_score(),
            "similar_cases_context": state.get("similar_cases_context", ""),
            "parsed_profile": session.parsed_profile,
        }
        next_q = await question_generator.aprocess(gen_input)

        # CoVe verifier (W3.2)：可选，失败/未注入时直接放行
        if question_verifier is not None:
            try:
                verification = await question_verifier.averify(
                    candidate_question=next_q,
                    parsed_profile=session.parsed_profile,
                    qa_history=session.qa_history,
                )
                if not verification.is_valid:
                    logger.info(
                        "[next_question_node] CoVe 不通过，触发 revise: %s",
                        verification.violations,
                    )
                    revise_input = {
                        **gen_input,
                        "verifier_feedback": verification.violations,
                    }
                    revised = await question_generator.aprocess(revise_input)
                    next_q = revised
            except Exception as e:
                logger.warning(f"[next_question_node] CoVe verifier 异常（沿用原题）: {e}")

        # mutate session（next_q 是合法 mutation 点）
        session.current_question = next_q
        session.question_data = next_q

        next_question_text = (
            next_q.get("question", str(next_q)) if isinstance(next_q, dict) else str(next_q)
        )
        scoring_result = state.get("scoring_result") or {}
        security_check = state.get("security_check") or {}

        output = {
            "success": True,
            "score": scoring_result.get("score", 0),
            "question_data": next_q,
            "next_question": next_question_text,
            "question_type": next_q.get("type", "technical")
            if isinstance(next_q, dict)
            else "technical",
            "current_average": session.get_average_score(),
            "total_questions": len(session.qa_history),
            "security_warning": security_check.get("risk_level") == "medium",
            # v3：暴露 confidence 信号给前端
            "scoring_confidence": scoring_result.get("confidence_level", "medium"),
            "scoring_agreement": scoring_result.get("agreement", 1.0),
            "requires_human_review": scoring_result.get("requires_human_review", False),
        }
        return {"next_question": next_q, "output": output}

    # ============================================================
    # 节点 7：finalize_normal_node — 正常结束
    # ============================================================
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
            # v3：决策置信度信号
            "decision_confidence": summary_result.get("decision_confidence", "medium"),
            "boundary_case": summary_result.get("boundary_case", False),
            "requires_human_review": summary_result.get("requires_human_review", False),
            "abstain_reason": summary_result.get("abstain_reason"),
            "decision_evidence": summary_result.get("decision_evidence", []),
            "message": "面试已完成，感谢您的参与！",
        }
        return {"final_summary": summary_result, "output": output}

    # ============================================================
    # 节点 8：finalize_security_node — 安全终止
    # ============================================================
    async def finalize_security_node(state: InterviewGraphState) -> Dict[str, Any]:
        session_id = state["session_id"]
        session = interview_session_provider(session_id)
        if not session:
            return {"output": {"success": False, "error": "Session not found"}}

        security_check = state.get("security_check", {}) or {}
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
                "malicious_input": session.qa_history[-1]["answer"]
                if session.qa_history else "未知输入",
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

    # ============================================================
    # 路由函数
    # ============================================================
    def route_after_security(state: InterviewGraphState) -> str:
        if state.get("finalize_reason") == "security":
            return "finalize_security"
        if state.get("finalize_reason") == "error":
            return END
        return "scoring"

    def route_after_readiness(state: InterviewGraphState) -> str:
        reason = state.get("finalize_reason", "continue")
        if reason == "normal":
            return "finalize_normal"
        if reason == "error":
            return END
        return "retrieval"

    # ============================================================
    # 图构建
    # ============================================================
    builder = StateGraph(InterviewGraphState)
    builder.add_node("security", security_node)
    builder.add_node("scoring", scoring_node)
    builder.add_node("persist", persist_node)
    builder.add_node("readiness", readiness_node)
    builder.add_node("retrieval", retrieval_node)
    builder.add_node("next_question", next_question_node)
    builder.add_node("finalize_normal", finalize_normal_node)
    builder.add_node("finalize_security", finalize_security_node)

    builder.add_edge(START, "security")
    builder.add_conditional_edges(
        "security",
        route_after_security,
        {
            "finalize_security": "finalize_security",
            "scoring": "scoring",
            END: END,
        },
    )
    builder.add_edge("scoring", "persist")
    builder.add_edge("persist", "readiness")
    builder.add_conditional_edges(
        "readiness",
        route_after_readiness,
        {
            "finalize_normal": "finalize_normal",
            "retrieval": "retrieval",
            END: END,
        },
    )
    builder.add_edge("retrieval", "next_question")
    builder.add_edge("next_question", END)
    builder.add_edge("finalize_normal", END)
    builder.add_edge("finalize_security", END)

    return builder.compile(checkpointer=checkpointer)


# ============================================================
# Checkpointer 工厂
# ============================================================

def create_mongo_checkpointer(
    db_name: str = "interview",
    collection: str = "langgraph_checkpoints_v3",  # v3 新 collection，老的弃用
) -> MongoDBSaver:
    """构造基于现有 MongoDB 共享连接的 LangGraph checkpointer"""
    client: MongoClient = get_mongo_client()
    return MongoDBSaver(
        client=client,
        db_name=db_name,
        checkpoint_collection_name=collection,
        writes_collection_name=f"{collection}_writes",
    )
