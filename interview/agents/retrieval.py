"""
检索系统
提供RAG检索和简历信息获取功能
"""

import os
import pymongo
from typing import List, Dict, Any, Optional
from bson import json_util, ObjectId
import json
from openai import OpenAI


class RetrievalSystem:
    """检索系统，负责从知识库和数据库获取信息"""
    
    def __init__(self):
        # MongoDB 设置
        self.client = pymongo.MongoClient(os.getenv("MONGODB_URI"))
        self.db = self.client[os.getenv("MONGODB_DB")]
        self.resumes_collection = self.db["resumes"]
        self.users_collection = self.db["users"]
        self.result_collection = self.db["result"]
        self.problem_collection = self.db["problem"]
        self.memory_collection = self.db["interview_memories"]

        # 初始化OpenAI客户端（使用DashScope）
        self.embedding_client = OpenAI(
            api_key=os.getenv("ALIYUN_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
    
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """生成文本向量 - 使用OpenAI SDK调用DashScope"""
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
            print(f"Error generating embedding with OpenAI SDK: {e}")
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
            print(f"Error retrieving resume for {name}: {e}")
            return {"error": f"检索简历时发生错误: {str(e)}"}
    
    def rag_search(self, query: str, limit: int = 3) -> str:
        """使用外部工具 rag_search 执行RAG检索（保留兼容接口）"""
        try:
            # 延迟导入工具，避免循环依赖
            from interview.tools.rag_tool import rag_search as tool_rag_search
            return tool_rag_search.invoke({"query": query}) if hasattr(tool_rag_search, "invoke") else tool_rag_search(query)
        except Exception as e:
            print(f"调用 rag_search 工具失败，fallback 到空结果: {e}")
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
                if line and ('？' in line or '?' in line) and len(line) > 10:
                    questions.append(line)
        
        # 如果没有找到足够的题目，提供一些默认题目
        if len(questions) < 3:
            default_questions = [
                f"请介绍一下您在{position}岗位上的工作经验。",
                f"您如何看待{position}这个职位的发展前景？",
                "请描述一次您解决复杂问题的经历。"
            ]
            questions.extend(default_questions)
        
        return questions[:5]  # 返回最多5个题目
    
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
            print(f"面试结果已保存，ID: {result.inserted_id}")
            return True
            
        except Exception as e:
            print(f"保存面试结果时发生错误: {e}")
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
            print(f"获取候选人历史记录时发生错误: {e}")
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
                print(f"面试记忆已保存: {memory_data['session_id']}")
            return success

        except Exception as e:
            print(f"保存面试记忆时发生错误: {e}")
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
            print(f"加载面试记忆时发生错误: {e}")
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
            print(f"获取候选人记忆记录时发生错误: {e}")
            return []

    def delete_memory(self, session_id: str) -> bool:
        """删除指定的记忆记录"""
        try:
            result = self.memory_collection.delete_one({"session_id": session_id})
            success = result.deleted_count > 0
            if success:
                print(f"记忆记录已删除: {session_id}")
            return success
        except Exception as e:
            print(f"删除记忆记录时发生错误: {e}")
            return False

    def cleanup_old_memories(self, days_old: int = 30) -> int:
        """清理指定天数之前的记忆记录"""
        try:
            from datetime import datetime, timedelta
            cutoff_date = datetime.now() - timedelta(days=days_old)

            result = self.memory_collection.delete_many({
                "saved_at": {"$lt": cutoff_date.isoformat()}
            })

            deleted_count = result.deleted_count
            print(f"已清理 {deleted_count} 条过期记忆记录")
            return deleted_count
        except Exception as e:
            print(f"清理过期记忆记录时发生错误: {e}")
            return 0
    
    def close_connection(self):
        """关闭数据库连接"""
        if self.client:
            self.client.close()

