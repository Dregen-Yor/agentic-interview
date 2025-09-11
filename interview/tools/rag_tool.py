"""
RAG 向量检索工具
提供 @tool rag_search，用于在知识库中基于向量相似度检索相关题目/知识。
"""

import os
from typing import List, Optional

import pymongo
from dotenv import load_dotenv

from langchain.tools import tool

# 加载环境变量
load_dotenv()


def _get_mongo_collections():
    """获取 MongoDB 连接与集合句柄"""
    client = pymongo.MongoClient(os.getenv("MONGODB_URI"))
    db = client[os.getenv("MONGODB_DB")]
    return client, db["problem"]


def _get_embedding(text: str) -> Optional[List[float]]:
    """
    复用项目中的 embedding 生成逻辑。
    注意：依赖 `init.get_embedding`，保持向量维度与索引一致。
    """
    try:
        from init import get_embedding  # 延迟导入以避免循环依赖
        return get_embedding(text)
    except Exception as e:
        print(f"Embedding 生成失败: {e}")
        return None


@tool
def rag_search(query: str) -> str:
    """
    使用向量搜索在知识库中查找与查询相关的信息。
    知识库中包含编程问题、概念和最佳实践。
    当你需要回答技术问题、评估候选人的技术知识或提供编程示例时，请使用此工具。
    """
    print(f"--- TOOL CALLED: rag_search with query='{query}' ---")

    query_embedding = _get_embedding(query)
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


