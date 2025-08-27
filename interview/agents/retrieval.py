"""
检索系统
提供RAG检索和简历信息获取功能
"""

import os
import requests
import pymongo
from typing import List, Dict, Any, Optional
from bson import json_util, ObjectId
import json


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
        
        # Embedding model settings
        self.embedding_api_url = "http://localhost:11434/api/embeddings"
        self.embedding_model = "Q78KG/gte-Qwen2-7B-instruct:latest"
    
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """生成文本向量"""
        try:
            payload = {"model": self.embedding_model, "prompt": text}
            response = requests.post(self.embedding_api_url, json=payload)
            response.raise_for_status()
            return response.json().get("embedding")
        except requests.exceptions.RequestException as e:
            print(f"Error generating embedding: {e}")
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
        """使用向量搜索在知识库中查找相关信息"""
        print(f"--- RAG搜索查询: '{query}' ---")
        
        query_embedding = self.get_embedding(query)
        if not query_embedding:
            return "抱歉，无法为您的查询生成向量，无法进行搜索。"
        
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "vector_index",
                    "path": "content_vector",
                    "queryVector": query_embedding,
                    "numCandidates": 100,
                    "limit": limit,
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
        
        try:
            results = list(self.problem_collection.aggregate(pipeline))
            if not results:
                return "在知识库中没有找到相关信息。"
            
            # Format the results
            formatted_results = "从知识库中找到以下相关信息：\n\n"
            for i, doc in enumerate(results):
                formatted_results += f"--- 相关文档 {i+1} (相似度: {doc['score']:.4f}) ---\n"
                formatted_results += doc.get("content", "没有内容。") + "\n\n"
            
            return formatted_results.strip()
            
        except Exception as e:
            return f"执行 RAG 搜索时出错: {e}"
    
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
        """保存面试结果到数据库"""
        try:
            interview_record = {
                "name": candidate_name,
                "comment": result_data.get("summary", ""),
                "result": "通过" if result_data.get("final_decision", False) else "不通过",
                "detailed_scores": result_data.get("scores", []),
                "average_score": result_data.get("average_score", 0),
                "questions_count": result_data.get("total_questions", 0),
                "timestamp": result_data.get("timestamp"),
                "security_alerts": result_data.get("security_alerts", []),
                "qa_history": result_data.get("qa_history", [])
            }
            
            result = self.result_collection.insert_one(interview_record)
            print(f"面试结果已保存，ID: {result.inserted_id}")
            return True
            
        except Exception as e:
            print(f"保存面试结果时发生错误: {e}")
            return False
    
    def get_candidate_history(self, candidate_name: str) -> List[Dict[str, Any]]:
        """获取候选人的历史面试记录"""
        try:
            results = list(self.result_collection.find({"name": candidate_name}))
            return json.loads(json_util.dumps(results))
        except Exception as e:
            print(f"获取候选人历史记录时发生错误: {e}")
            return []
    
    def close_connection(self):
        """关闭数据库连接"""
        if self.client:
            self.client.close()


class KnowledgeExtractor:
    """知识提取器，用于从简历中提取关键信息"""
    
    @staticmethod
    def extract_skills_from_resume(resume_data: Dict[str, Any]) -> List[str]:
        """从简历中提取技能"""
        skills = []
        
        # 从不同字段提取技能信息
        if "skills" in resume_data:
            skills.extend(resume_data["skills"])
        
        if "技能" in resume_data:
            skills.extend(resume_data["技能"])
        
        # 从经验描述中提取技能（这里可以加入更复杂的NLP处理）
        if "experience" in resume_data:
            for exp in resume_data["experience"]:
                if isinstance(exp, dict) and "description" in exp:
                    # 简单的关键词提取
                    desc = exp["description"].lower()
                    common_skills = ["python", "java", "javascript", "react", "vue", "django", "mysql", "mongodb"]
                    for skill in common_skills:
                        if skill in desc and skill not in skills:
                            skills.append(skill)
        
        return list(set(skills))  # 去重
    
    @staticmethod
    def extract_position_from_resume(resume_data: Dict[str, Any]) -> str:
        """从简历中提取目标职位"""
        # 尝试从多个字段获取职位信息
        position_fields = ["desired_position", "target_position", "职位", "目标职位", "position"]
        
        for field in position_fields:
            if field in resume_data and resume_data[field]:
                return str(resume_data[field])
        
        # 如果没有明确的职位信息，根据技能推断
        skills = KnowledgeExtractor.extract_skills_from_resume(resume_data)
        if any(skill in ["python", "django", "flask"] for skill in skills):
            return "Python开发工程师"
        elif any(skill in ["java", "spring"] for skill in skills):
            return "Java开发工程师"
        elif any(skill in ["javascript", "react", "vue"] for skill in skills):
            return "前端开发工程师"
        
        return "软件工程师"  # 默认职位
    
    @staticmethod
    def extract_experience_level(resume_data: Dict[str, Any]) -> str:
        """从简历中提取经验水平"""
        if "experience" in resume_data:
            exp_count = len(resume_data["experience"])
            if exp_count >= 5:
                return "senior"
            elif exp_count >= 2:
                return "medium"
            else:
                return "junior"
        
        # 从工作年限判断
        if "work_years" in resume_data:
            years = resume_data["work_years"]
            if isinstance(years, (int, float)):
                if years >= 5:
                    return "senior"
                elif years >= 2:
                    return "medium"
                else:
                    return "junior"
        
        return "junior"  # 默认为初级