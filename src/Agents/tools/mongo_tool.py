import os, typing, asyncio
from dotenv import load_dotenv; load_dotenv()
import httpx

# 新增 MongoDB 相关部分
from pymongo import MongoClient
import json

# 读取环境变量
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB", "agentic_interview")
COLLECTION_NAME = os.getenv("MONGO_COLLECTION", "problems")

# 初始化 MongoDB 客户端
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

def load_problems(file_path: str = "data/problem.jsonl") -> dict:
    """
    将 problem.jsonl 中的题目导入 MongoDB.
    """
    # 清空已有数据
    collection.delete_many({})
    docs = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            docs.append(json.loads(line))
    if docs:
        collection.insert_many(docs)
    return {"inserted_count": len(docs)}

def get_random_problems(count: int) -> list:
    """
    根据难度均匀随机检索 count 道题目.
    """
    difficulties = collection.distinct("difficulty")
    if not difficulties:
        return []
    difficulties = sorted(difficulties)
    n = len(difficulties)
    base = count // n
    remainder = count % n
    results = []
    for i, diff in enumerate(difficulties):
        size = base + (1 if i < remainder else 0)
        if size <= 0:
            continue
        pipeline = [
            {"$match": {"difficulty": diff}},
            {"$sample": {"size": size}}
        ]
        results.extend(list(collection.aggregate(pipeline)))
    return results

# 异步包装，供智能体调用
async def tool_load_problems(*, file_path: str = "data/problem.jsonl") -> dict:
    return load_problems(file_path)

async def tool_get_random_problems(*, count: int) -> dict:
    problems = get_random_problems(count)
    return {"problems": problems}

