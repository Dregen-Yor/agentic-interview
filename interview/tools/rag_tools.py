"""
RAG 向量检索与数据库工具
整合了RAG检索、简历管理、面试结果存储、记忆管理等所有检索相关功能
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

import pymongo
from bson import json_util, ObjectId
import json
from dotenv import load_dotenv
from openai import OpenAI

from langchain.tools import tool

# 加载环境变量
load_dotenv()

# 初始化logger
logger = logging.getLogger("interview.tools.rag")


# ==================== 私有辅助函数 ====================

def _get_mongo_client():
    """获取 MongoDB 客户端"""
    return pymongo.MongoClient(os.getenv("MONGODB_URI"))


def _get_mongo_collections():
    """获取 MongoDB 连接与集合句柄"""
    client = _get_mongo_client()
    db = client[os.getenv("MONGODB_DB")]
    return client, db["problem"]


def _get_embedding_from_init(text: str) -> Optional[List[float]]:
    """使用 init.py 中的 get_embedding 函数"""
    try:
        from init import get_embedding
        return get_embedding(text)
    except Exception as e:
        logger.error(f"Embedding 生成失败: {e}")
        return None


# ==================== RAG 搜索工具 ====================

@tool
def rag_search(query: str) -> str:
    """
    使用向量搜索在知识库中查找与查询相关的信息。
    知识库中包含编程问题、概念和最佳实践。
    当你需要回答技术问题、评估候选人的技术知识或提供编程示例时，请使用此工具。
    """
    logger.debug(f"--- TOOL CALLED: rag_search with query={query} ---")

    query_embedding = _get_embedding_from_init(query)
    if not query_embedding:
        return "抱歉，无法为您的查询生成向量，无法进行搜索。"

    pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index",
                "path": "content_vector",
                "queryVector": query_embedding,
                "numCandidates": 100,
                "limit": 3,
            }
        },
        {
            "$project": {
                "_id": 0,
                "content": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]

    client = None
    try:
        client, problem_collection = _get_mongo_collections()
        results = list(problem_collection.aggregate(pipeline))
        if not results:
            return "在知识库中没有找到相关信息。"

        formatted_results = "从知识库中找到以下相关信息：\n\n"
        for i, doc in enumerate(results):
            formatted_results += f"--- 相关文档 {i+1} (相似度: {doc['score']:.4f}) ---\n"
            formatted_results += doc.get("content", "没有内容。") + "\n\n"

        return formatted_results.strip()

    except Exception as e:
        return f"执行 RAG 搜索时出错: {e}"
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


# ==================== RetrievalSystem 类 ====================

class RetrievalSystem:
    """检索系统，负责从知识库和数据库获取信息"""

    def __init__(self):
        # Initialize logger
        self.logger = logging.getLogger("interview.tools.rag.RetrievalSystem")

        # MongoDB 设置
        self.client = _get_mongo_client()
        self.db = self.client[os.getenv("MONGODB_DB")]
        self.resumes_collection = self.db["resumes"]
        self.users_collection = self.db["users"]
        self.result_collection = self.db["result"]
        self.problem_collection = self.db["problem"]
        self.memory_collection = self.db["interview_memories"]
        self.conversation_memory_collection = self.db["conversation_memories"]

        # 初始化OpenAI客户端 (用于阿里云embedding)
        self.embedding_client = OpenAI(
            api_key=os.getenv("ALIYUN_API_KEY"),
            base_url=os.getenv("ALIYUN_BASE_URL")
        )

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """生成文本向量 - 使用OpenAI SDK调用阿里云"""
        try:
            # 使用OpenAI SDK的embeddings.create方法
            completion = self.embedding_client.embeddings.create(
                model="text-embedding-v4",
                input=text,
                dimensions=1024,  # 指定向量维度
                encoding_format="float"
            )
            # 从响应中提取embedding向量
            if completion.data and len(completion.data) > 0:
                return completion.data[0].embedding
            return None
        except Exception as e:
            self.logger.error(f"Error generating embedding with OpenAI SDK: {e}")
            return None

    def get_resume_by_name(self, name: str) -> Dict[str, Any]:
        """根据姓名获取简历信息"""
        try:
            user = self.users_collection.find_one({"name": name})
            if user and "_id" in user:
                resume_id = str(user["_id"])
                resume = self.resumes_collection.find_one({"_id": ObjectId(resume_id)})
                if resume:
                    return json.loads(json_util.dumps(resume))
                else:
                    return {"error": f"找不到姓名为'{name}'的简历。"}
            return {"error": f"找不到姓名为'{name}'的用户。"}
        except Exception as e:
            self.logger.error(f"Error retrieving resume for {name}: {e}")
            return {"error": f"检索简历时发生错误: {str(e)}"}

    def rag_search(self, query: str, limit: int = 3) -> str:
        """使用外部工具 rag_search 执行RAG检索（保留兼容接口）"""
        try:
            # 直接调用模块级的 rag_search 工具
            return rag_search.invoke({"query": query}) if hasattr(rag_search, "invoke") else rag_search(query)
        except Exception as e:
            self.logger.warning(f"调用 rag_search 工具失败，fallback 到空结果: {e}")
            return "在知识库中没有找到相关信息。"

    def get_interview_questions_from_kb(self, position: str, skills: List[str], difficulty: str = "medium") -> List[str]:
        """从知识库获取相关面试题目"""
        # 构建查询字符串
        skills_str = ", ".join(skills) if skills else ""
        query = f"{position} {skills_str} {difficulty} 面试题目"

        # 使用RAG搜索获取相关内容
        rag_results = self.rag_search(query, limit=5)

        # 简单解析返回的内容，提取题目
        # 这里可以根据知识库的具体格式进行调整
        questions = []
        if "没有找到相关信息" not in rag_results:
            # 尝试从结果中提取题目
            lines = rag_results.split('\n')
            for line in lines:
                line = line.strip()
                if line and ('?' in line or '?' in line) and len(line) > 10:
                    questions.append(line)

        return questions[:min(len(questions), 5)]  # 返回最多5个题目

    def save_interview_result(self, candidate_name: str, result_data: Dict[str, Any]) -> bool:
        """保存面试结果到数据库（统一格式）"""
        try:
            # 统一的面试记录格式
            interview_record = {
                # 基本信息
                "candidate_name": candidate_name,
                "session_id": result_data.get("session_id", ""),
                "timestamp": result_data.get("timestamp"),

                # 面试结果（兼容旧字段）
                "name": candidate_name,  # 保持旧字段兼容性
                "result": self._format_decision(result_data.get("final_decision", "conditional")),
                "comment": result_data.get("summary", ""),
                "final_decision": result_data.get("final_decision", "conditional"),
                "final_grade": result_data.get("final_grade", "C"),
                "overall_score": result_data.get("overall_score", 0),

                # 详细数据
                "detailed_scores": result_data.get("scores", []),
                "average_score": result_data.get("average_score", 0),
                "total_questions": result_data.get("total_questions", 0),
                "questions_count": result_data.get("total_questions", 0),  # 保持兼容性
                "qa_history": result_data.get("qa_history", []),
                "detailed_summary": result_data.get("detailed_summary", {}),

                # 安全相关
                "security_alerts": result_data.get("security_alerts", []),
                "security_summary": result_data.get("security_summary", {}),

                # 元数据
                "session_duration": result_data.get("session_duration", 0),
                "termination_reason": result_data.get("termination_reason", "normal_completion"),
                "saved_at": result_data.get("timestamp"),
                "processed_by": "MultiAgentCoordinator"
            }

            result = self.result_collection.insert_one(interview_record)
            self.logger.info(f"面试结果已保存，ID: {result.inserted_id}")
            return True

        except Exception as e:
            self.logger.error(f"保存面试结果时发生错误: {e}")
            return False

    def _format_decision(self, decision: str) -> str:
        """格式化决策结果为中文（兼容旧系统）"""
        decision_mapping = {
            "accept": "通过",
            "reject": "不通过",
            "conditional": "待定"
        }
        return decision_mapping.get(decision, "待定")

    def get_candidate_history(self, candidate_name: str) -> List[Dict[str, Any]]:
        """获取候选人的历史面试记录"""
        try:
            results = list(self.result_collection.find({"name": candidate_name}))
            return json.loads(json_util.dumps(results))
        except Exception as e:
            self.logger.error(f"获取候选人历史记录时发生错误: {e}")
            return []

    def save_memory(self, memory_data: Dict[str, Any]) -> bool:
        """保存面试记忆到数据库"""
        try:
            # 为记忆数据添加元信息
            memory_record = {
                "session_id": memory_data["session_id"],
                "candidate_name": memory_data["memory_data"]["candidate_name"],
                "memory_data": memory_data["memory_data"],
                "saved_at": memory_data["saved_at"],
                "version": "1.0",
                "metadata": {
                    "total_questions": len(memory_data["memory_data"]["qa_history"]),
                    "average_score": memory_data["memory_data"]["average_score"],
                    "has_context": bool(memory_data["memory_data"]["context_memory"])
                }
            }

            # 使用upsert，如果session_id已存在则更新，否则插入
            result = self.memory_collection.replace_one(
                {"session_id": memory_data["session_id"]},
                memory_record,
                upsert=True
            )

            success = result.acknowledged
            if success:
                self.logger.info(f"面试记忆已保存: {memory_data['session_id']}")
            return success

        except Exception as e:
            self.logger.error(f"保存面试记忆时发生错误: {e}")
            return False

    def load_memory(self, session_id: str) -> Optional[Dict[str, Any]]:
        """从数据库加载面试记忆"""
        try:
            memory_record = self.memory_collection.find_one({"session_id": session_id})
            if memory_record:
                # 移除MongoDB特定的字段
                memory_record.pop("_id", None)
                return json.loads(json_util.dumps(memory_record))
            return None
        except Exception as e:
            self.logger.error(f"加载面试记忆时发生错误: {e}")
            return None

    def get_candidate_memories(self, candidate_name: str) -> List[Dict[str, Any]]:
        """获取候选人的所有记忆记录"""
        try:
            results = list(self.memory_collection.find({"candidate_name": candidate_name}))
            # 移除MongoDB特定的_id字段并序列化
            for result in results:
                result.pop("_id", None)
            return json.loads(json_util.dumps(results))
        except Exception as e:
            self.logger.error(f"获取候选人记忆记录时发生错误: {e}")
            return []

    def delete_memory(self, session_id: str) -> bool:
        """删除指定的记忆记录"""
        try:
            result = self.memory_collection.delete_one({"session_id": session_id})
            success = result.deleted_count > 0
            if success:
                self.logger.info(f"记忆记录已删除: {session_id}")
            return success
        except Exception as e:
            self.logger.error(f"删除记忆记录时发生错误: {e}")
            return False

    def cleanup_old_memories(self, days_old: int = 30) -> int:
        """清理指定天数之前的记忆记录"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_old)

            result = self.memory_collection.delete_many({
                "saved_at": {"$lt": cutoff_date.isoformat()}
            })

            deleted_count = result.deleted_count
            self.logger.info(f"已清理 {deleted_count} 条过期记忆记录")
            return deleted_count
        except Exception as e:
            self.logger.error(f"清理过期记忆记录时发生错误: {e}")
            return 0

    # ==================== conversation_memories 集合操作 ====================

    def save_turn_document(self, turn_doc: Dict[str, Any]) -> bool:
        """插入一条 turn 文档到 conversation_memories"""
        try:
            result = self.conversation_memory_collection.insert_one(turn_doc)
            self.logger.debug(f"Turn 文档已保存: session={turn_doc.get('session_id')}, turn={turn_doc.get('turn_index')}")
            return result.acknowledged
        except Exception as e:
            self.logger.error(f"保存 turn 文档失败: {e}")
            return False

    def save_session_meta(self, meta_doc: Dict[str, Any]) -> bool:
        """Upsert session_meta 文档到 conversation_memories"""
        try:
            result = self.conversation_memory_collection.replace_one(
                {"session_id": meta_doc["session_id"], "doc_type": "session_meta"},
                meta_doc,
                upsert=True
            )
            self.logger.debug(f"Session meta 已保存: {meta_doc.get('session_id')}")
            return result.acknowledged
        except Exception as e:
            self.logger.error(f"保存 session meta 失败: {e}")
            return False

    def update_session_meta(self, session_id: str, update_ops: Dict[str, Any]) -> bool:
        """使用 $set/$inc/$push 增量更新 session_meta"""
        try:
            result = self.conversation_memory_collection.update_one(
                {"session_id": session_id, "doc_type": "session_meta"},
                update_ops
            )
            return result.acknowledged
        except Exception as e:
            self.logger.error(f"更新 session meta 失败: {e}")
            return False

    def find_session_meta(self, session_id: str) -> Optional[Dict[str, Any]]:
        """查询 session_meta 文档"""
        try:
            doc = self.conversation_memory_collection.find_one(
                {"session_id": session_id, "doc_type": "session_meta"}
            )
            if doc:
                doc.pop("_id", None)
            return doc
        except Exception as e:
            self.logger.error(f"查询 session meta 失败: {e}")
            return None

    def find_turns_by_session(self, session_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """按 turn_index 升序查询某会话的 turn 文档"""
        try:
            cursor = self.conversation_memory_collection.find(
                {"session_id": session_id, "doc_type": "turn"}
            ).sort("turn_index", pymongo.ASCENDING)

            if limit is not None:
                cursor = cursor.limit(limit)

            results = []
            for doc in cursor:
                doc.pop("_id", None)
                results.append(doc)
            return results
        except Exception as e:
            self.logger.error(f"查询 turn 文档失败: {e}")
            return []

    def vector_search_memories(
        self,
        query_embedding: List[float],
        num_candidates: int = 50,
        limit: int = 10,
        pre_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """使用 $vectorSearch 管道在 conversation_memories 中进行向量检索"""
        try:
            vector_search_stage = {
                "$vectorSearch": {
                    "index": "memory_vector_index",
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": num_candidates,
                    "limit": limit,
                }
            }

            if pre_filter:
                vector_search_stage["$vectorSearch"]["filter"] = pre_filter

            pipeline = [
                vector_search_stage,
                {
                    "$project": {
                        "_id": 0,
                        "session_id": 1,
                        "turn_index": 1,
                        "candidate_name": 1,
                        "state": 1,
                        "action": 1,
                        "reward": 1,
                        "importance": 1,
                        "combined_text": 1,
                        "timestamp": 1,
                        "similarity_score": {"$meta": "vectorSearchScore"},
                    }
                },
            ]

            results = list(self.conversation_memory_collection.aggregate(pipeline))
            return results
        except Exception as e:
            self.logger.error(f"向量检索 memories 失败: {e}")
            return []

    def delete_conversation_memories(self, session_id: str) -> int:
        """删除某会话的全部文档（turn + session_meta）"""
        try:
            result = self.conversation_memory_collection.delete_many({"session_id": session_id})
            deleted = result.deleted_count
            self.logger.info(f"已删除会话 {session_id} 的 {deleted} 条文档")
            return deleted
        except Exception as e:
            self.logger.error(f"删除会话文档失败: {e}")
            return 0

    def ensure_memory_indexes(self) -> None:
        """创建 conversation_memories 的常规索引（幂等操作）"""
        try:
            coll = self.conversation_memory_collection

            # 会话内查询索引
            coll.create_index(
                [("session_id", pymongo.ASCENDING), ("doc_type", pymongo.ASCENDING), ("turn_index", pymongo.ASCENDING)],
                name="idx_session_doc_turn"
            )

            # 跨会话检索索引
            coll.create_index(
                [("candidate_name", pymongo.ASCENDING), ("doc_type", pymongo.ASCENDING), ("importance", pymongo.DESCENDING)],
                name="idx_candidate_doc_importance"
            )

            # 清理过期数据索引
            coll.create_index(
                [("doc_type", pymongo.ASCENDING), ("status", pymongo.ASCENDING), ("created_at", pymongo.ASCENDING)],
                name="idx_doc_status_created"
            )

            self.logger.info("conversation_memories 常规索引创建完成")
        except Exception as e:
            self.logger.error(f"创建常规索引失败: {e}")

    def close_connection(self):
        """关闭数据库连接"""
        if self.client:
            self.client.close()
