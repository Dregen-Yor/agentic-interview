"""
MemoryRetriever — Memento 风格 Case-Based Reasoning 检索层
通过向量检索 + importance 重排获取历史高价值案例。
"""

from typing import Dict, List, Any, Optional
import logging


class MemoryRetriever:
    """Memento 风格 Case-Based Reasoning 检索层"""

    DEFAULT_TOP_K = 4  # Memento 论文最优 K

    def __init__(self, retrieval_system):
        """
        Args:
            retrieval_system: RetrievalSystem 实例
        """
        self.rs = retrieval_system
        self.logger = logging.getLogger("interview.agents.memory.MemoryRetriever")

    # -------------------- 核心检索 --------------------

    def retrieve_similar_cases(
        self,
        query_text: str,
        top_k: int = 4,
        exclude_session_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        min_importance: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        跨会话向量检索 + importance 重排。

        Args:
            query_text: 查询文本（通常是 question + answer 拼接）
            top_k: 返回数量
            exclude_session_id: 排除当前会话
            filters: 额外的 MongoDB 过滤条件
            min_importance: 最低 importance 阈值

        Returns:
            按 combined_score 降序排列的 turn 文档列表
        """
        try:
            # 生成查询向量
            query_embedding = self.rs.get_embedding(query_text)
            if not query_embedding:
                self.logger.warning("检索查询向量生成失败，返回空结果")
                return []

            # 构建 pre_filter
            pre_filter = {"doc_type": "turn"}
            if exclude_session_id:
                pre_filter["session_id"] = {"$ne": exclude_session_id}
            if filters:
                pre_filter.update(filters)

            # 多取一些候选，后续做 importance 重排
            num_candidates = max(top_k * 10, 50)
            fetch_limit = max(top_k * 3, 15)

            raw_results = self.rs.vector_search_memories(
                query_embedding=query_embedding,
                num_candidates=num_candidates,
                limit=fetch_limit,
                pre_filter=pre_filter,
            )

            # importance 重排: combined_score = 0.6 * similarity + 0.4 * importance
            scored = []
            for doc in raw_results:
                importance = doc.get("importance", 0.0)
                if importance < min_importance:
                    continue
                similarity = doc.get("similarity_score", 0.0)
                combined_score = 0.6 * similarity + 0.4 * importance
                doc["combined_score"] = round(combined_score, 4)
                scored.append(doc)

            # 按 combined_score 降序
            scored.sort(key=lambda x: x["combined_score"], reverse=True)

            results = scored[:top_k]
            self.logger.debug(f"检索到 {len(results)} 条相似案例 (query_len={len(query_text)}, top_k={top_k})")
            return results

        except Exception as e:
            self.logger.error(f"retrieve_similar_cases 异常: {e}")
            return []

    def retrieve_within_session(self, session_id: str, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """当前会话内的相关历史轮次检索"""
        try:
            query_embedding = self.rs.get_embedding(query_text)
            if not query_embedding:
                return []

            pre_filter = {
                "doc_type": "turn",
                "session_id": session_id,
            }

            results = self.rs.vector_search_memories(
                query_embedding=query_embedding,
                num_candidates=max(top_k * 5, 20),
                limit=top_k,
                pre_filter=pre_filter,
            )
            return results

        except Exception as e:
            self.logger.error(f"retrieve_within_session 异常: {e}")
            return []

    def get_candidate_case_history(self, candidate_name: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """获取某候选人的历史高价值案例（按 importance 降序）"""
        try:
            cursor = self.rs.conversation_memory_collection.find(
                {"doc_type": "turn", "candidate_name": candidate_name}
            ).sort("importance", -1).limit(top_k)

            results = []
            for doc in cursor:
                doc.pop("_id", None)
                doc.pop("embedding", None)  # 不返回大向量
                results.append(doc)
            return results

        except Exception as e:
            self.logger.error(f"get_candidate_case_history 异常: {e}")
            return []

    # -------------------- 格式化为 LLM Prompt --------------------

    def format_cases_for_question_generation(self, cases: List[Dict[str, Any]]) -> str:
        """
        格式化案例供 QuestionGeneratorAgent 参考。
        重点信息: 题型、难度、得分 -> 帮助出题器避重复、调难度。
        """
        if not cases:
            return ""

        lines = ["=== 历史面试参考案例 ==="]
        for i, case in enumerate(cases, 1):
            action = case.get("action", {})
            reward = case.get("reward", {})
            state = case.get("state", {})
            q_data = action.get("question_data", {})

            q_type = q_data.get("type", "unknown") if isinstance(q_data, dict) else "unknown"
            difficulty = q_data.get("difficulty", "unknown") if isinstance(q_data, dict) else "unknown"
            score = reward.get("score", "N/A")
            question = action.get("question_text", "")[:100]  # 截断避免 prompt 过长
            avg_score = state.get("cumulative_avg_score", "N/A")

            lines.append(
                f"案例{i}: 题型={q_type}, 难度={difficulty}, 得分={score}/10, "
                f"当时平均分={avg_score}, 问题摘要=\"{question}\""
            )

        lines.append("=== 参考案例结束 ===")
        return "\n".join(lines)

    def format_cases_for_scoring(self, cases: List[Dict[str, Any]]) -> str:
        """
        格式化案例供 ScoringAgent 参考（评分一致性）。
        重点信息: 问题、回答、评分详情。
        """
        if not cases:
            return ""

        lines = ["=== 评分参考案例 ==="]
        for i, case in enumerate(cases, 1):
            action = case.get("action", {})
            reward = case.get("reward", {})

            question = action.get("question_text", "")[:80]
            answer = action.get("answer_text", "")[:120]
            score = reward.get("score", "N/A")
            reasoning = reward.get("reasoning", "")[:100]

            lines.append(f"案例{i}:")
            lines.append(f"  问题: {question}")
            lines.append(f"  回答: {answer}")
            lines.append(f"  得分: {score}/10")
            lines.append(f"  理由: {reasoning}")

        lines.append("=== 参考案例结束 ===")
        return "\n".join(lines)

    def format_cases_as_examples(self, cases: List[Dict[str, Any]], include_reward: bool = True) -> str:
        """通用格式化"""
        if not cases:
            return ""

        lines = ["=== 历史案例 ==="]
        for i, case in enumerate(cases, 1):
            action = case.get("action", {})
            lines.append(f"案例{i}:")
            lines.append(f"  问题: {action.get('question_text', 'N/A')}")
            lines.append(f"  回答: {action.get('answer_text', 'N/A')}")

            if include_reward:
                reward = case.get("reward", {})
                lines.append(f"  得分: {reward.get('score', 'N/A')}/10")
                lines.append(f"  理由: {reward.get('reasoning', 'N/A')}")

        lines.append("=== 案例结束 ===")
        return "\n".join(lines)
