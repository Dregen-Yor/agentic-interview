"""
MemoryStore — MongoDB 增量持久化层
每轮实时写入 conversation_memories 集合，确保崩溃安全。
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import logging


class MemoryStore:
    """MongoDB 增量持久化层 — 每轮实时写入 conversation_memories 集合"""

    def __init__(self, retrieval_system):
        """
        Args:
            retrieval_system: RetrievalSystem 实例，提供 MongoDB 操作和 embedding 生成
        """
        self.rs = retrieval_system
        self.logger = logging.getLogger("interview.agents.memory.MemoryStore")

    # -------------------- 会话生命周期 --------------------

    def create_session(self, session_id: str, candidate_name: str, resume_data: Dict[str, Any] = None, parsed_profile: Dict[str, Any] = None) -> bool:
        """创建新的 session_meta 文档"""
        now = datetime.now()
        context = {
            "resume_data": resume_data or {},
        }
        if parsed_profile:
            context["parsed_profile"] = parsed_profile
        meta_doc = {
            "doc_type": "session_meta",
            "session_id": session_id,
            "candidate_name": candidate_name,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "context": context,
            "stats": {
                "total_turns": 0,
                "average_score": 0.0,
                "score_list": [],
                "question_type_counts": {},
                "security_alert_count": 0,
            },
            "final_summary": None,
            "security_summary": None,
            "final_decision": None,
            "final_grade": None,
            "overall_score": None,
            "session_duration": None,
            "termination_reason": None,
            "version": "2.0",
        }
        return self.rs.save_session_meta(meta_doc)

    def update_session_status(self, session_id: str, status: str, final_data: Dict[str, Any] = None) -> bool:
        """更新会话状态（completed / terminated_security）"""
        now = datetime.now()
        set_fields = {
            "status": status,
            "updated_at": now,
            "completed_at": now,
        }
        if final_data:
            for key in ("final_summary", "security_summary", "final_decision",
                        "final_grade", "overall_score", "session_duration", "termination_reason"):
                if key in final_data:
                    set_fields[key] = final_data[key]

        return self.rs.update_session_meta(session_id, {"$set": set_fields})

    def get_session_meta(self, session_id: str) -> Optional[Dict[str, Any]]:
        """查询 session_meta"""
        return self.rs.find_session_meta(session_id)

    # -------------------- 逐轮持久化（核心方法） --------------------

    def save_turn(
        self,
        session_id: str,
        candidate_name: str,
        turn_index: int,
        state: Dict[str, Any],
        action: Dict[str, Any],
        reward: Dict[str, Any],
        security_check: Dict[str, Any] = None,
        baseline_score: float = 5.0,
    ) -> bool:
        """
        保存一轮 Memento 三元组 (state, action, reward) 到 MongoDB，
        同时增量更新 session_meta 的统计信息。

        W3.3：新增 baseline_score 参数（PER importance 计算用）。默认 5.0 兼容旧调用。
        """
        try:
            # 构建 combined_text 用于向量检索
            question_text = action.get("question_text", "")
            answer_text = action.get("answer_text", "")
            reasoning = reward.get("reasoning", "")
            combined_text = self._build_combined_text(question_text, answer_text, reasoning)

            # 生成 embedding
            embedding = self.rs.get_embedding(combined_text)

            # 计算 importance（W3.3 改为 PER 风格）
            score = reward.get("score", 5)
            difficulty = action.get("question_data", {}).get("difficulty", "medium") if isinstance(action.get("question_data"), dict) else "medium"
            is_security_event = (
                security_check is not None
                and security_check.get("risk_level") in ("medium", "high")
            )
            importance = self._compute_importance(
                score, difficulty, is_security_event, baseline_score=baseline_score
            )

            # 构建 turn 文档
            now = datetime.now()
            turn_doc = {
                "doc_type": "turn",
                "session_id": session_id,
                "turn_index": turn_index,
                "candidate_name": candidate_name,
                "timestamp": now,
                "state": state,
                "action": action,
                "reward": reward,
                "importance": importance,
                "combined_text": combined_text,
            }

            # embedding 可能因 API 异常为 None，允许写入但不带向量
            if embedding:
                turn_doc["embedding"] = embedding

            # 写入 turn 文档
            success = self.rs.save_turn_document(turn_doc)
            if not success:
                self.logger.error(f"保存 turn 文档失败: session={session_id}, turn={turn_index}")
                return False

            # 增量更新 session_meta 统计
            question_type = action.get("question_data", {}).get("type", "general") if isinstance(action.get("question_data"), dict) else "general"
            security_alert_inc = 1 if is_security_event else 0

            update_ops = {
                "$set": {"updated_at": now},
                "$inc": {
                    "stats.total_turns": 1,
                    "stats.security_alert_count": security_alert_inc,
                    f"stats.question_type_counts.{question_type}": 1,
                },
                "$push": {"stats.score_list": score},
            }
            self.rs.update_session_meta(session_id, update_ops)

            # 重新计算平均分（使用 $set 而非 $inc 避免精度漂移）
            meta = self.rs.find_session_meta(session_id)
            if meta:
                score_list = meta.get("stats", {}).get("score_list", [])
                if score_list:
                    avg = sum(score_list) / len(score_list)
                    self.rs.update_session_meta(session_id, {"$set": {"stats.average_score": round(avg, 2)}})

            self.logger.debug(f"Turn 已持久化: session={session_id}, turn={turn_index}, importance={importance:.2f}")
            return True

        except Exception as e:
            self.logger.error(f"save_turn 异常: {e}")
            return False

    # -------------------- 会话内读取 --------------------

    def get_session_turns(self, session_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取某会话的所有 turn 文档（按 turn_index 升序）"""
        return self.rs.find_turns_by_session(session_id, limit)

    def get_recent_turns(self, session_id: str, count: int = 5) -> List[Dict[str, Any]]:
        """获取最近 N 轮 turn"""
        all_turns = self.rs.find_turns_by_session(session_id)
        return all_turns[-count:] if len(all_turns) > count else all_turns

    # -------------------- 清理 --------------------

    def delete_session(self, session_id: str) -> int:
        """删除某会话的全部文档"""
        return self.rs.delete_conversation_memories(session_id)

    def cleanup_old_sessions(self, days_old: int = 30) -> int:
        """清理指定天数之前的已完成会话"""
        try:
            cutoff = datetime.now() - timedelta(days=days_old)
            result = self.rs.conversation_memory_collection.delete_many({
                "doc_type": "session_meta",
                "status": {"$in": ["completed", "terminated_security"]},
                "created_at": {"$lt": cutoff}
            })
            deleted_meta = result.deleted_count

            # 同时清理对应的 turn 文档
            if deleted_meta > 0:
                self.rs.conversation_memory_collection.delete_many({
                    "doc_type": "turn",
                    "timestamp": {"$lt": cutoff}
                })

            self.logger.info(f"已清理 {deleted_meta} 个过期会话")
            return deleted_meta
        except Exception as e:
            self.logger.error(f"清理过期会话失败: {e}")
            return 0

    # -------------------- 私有方法 --------------------

    def _compute_importance(
        self,
        score: int,
        difficulty: str,
        is_security_event: bool,
        baseline_score: float = 5.0,
    ) -> float:
        """
        PER (Prioritized Experience Replay, Schaul 2015, arXiv:1511.05952) 风格 importance。

        priority = (|TD-error| + ε) ** α
          - TD-error 近似：|score - baseline_score|
          - baseline_score：候选人当前历史均分（首轮默认 5.0）
          - α=0.6（PER 论文 rank-based variant 推荐值）
          - ε=0.01 避免 0 分时 importance=0

        difficulty_bonus + security_bonus 作为 PER 公式之外的加性奖励项
        （论文未涵盖，但与教育评估场景契合：难题/安全事件价值更高）。
        """
        EPSILON = 0.01
        ALPHA = 0.6
        # 归一化：5 是 score 与 baseline 最大可能距离（baseline∈[0,10]，score∈[0,10]）
        # 实际取 max(score-baseline) ≈ 5 时的 priority 作为分母，让 base_priority 落在 [0, 1]
        NORM_DIVISOR = (5.0 + EPSILON) ** ALPHA  # ≈ 2.626

        td_error = abs(float(score) - float(baseline_score))
        base_priority = ((td_error + EPSILON) ** ALPHA) / NORM_DIVISOR
        base_priority = min(base_priority, 1.0)

        difficulty_bonus = {"hard": 0.20, "medium": 0.10, "easy": 0.0}.get(difficulty, 0.10)
        security_bonus = 0.30 if is_security_event else 0.0

        importance = base_priority + difficulty_bonus + security_bonus
        return round(min(importance, 1.0), 4)

    def _build_combined_text(self, question: str, answer: str, reasoning: str) -> str:
        """拼接 question + answer + reasoning 作为向量检索的源文本"""
        parts = []
        if question:
            parts.append(f"问题: {question}")
        if answer:
            parts.append(f"回答: {answer}")
        if reasoning:
            parts.append(f"评分理由: {reasoning}")
        return "\n".join(parts)
