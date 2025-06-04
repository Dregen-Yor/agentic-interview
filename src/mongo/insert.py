# ingest_mongodb.py
import os, textwrap, json, pathlib
from dotenv import load_dotenv; load_dotenv()

from pymongo import MongoClient
from openai import OpenAI
from tqdm import tqdm
import httpx
import asyncio

client = MongoClient(os.environ["MONGODB_URI"])
col = client[os.environ["MONGODB_DB"]][os.environ["MONGODB_COL"]]
oa = OpenAI()

def chunk(text: str, max_tokens=400):
    """最简单的按句粗切分"""
    for para in textwrap.wrap(text, width=max_tokens*4):
        yield para.strip()

def embed(texts: str):
    async def get_embedding(prompt: str):
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://localhost:11434/api/embeddings",
                json={
                    "model": "Q78KG/gte-Qwen2-7B-instruct:latest",
                    "prompt": prompt
                }
            )
            resp.raise_for_status()
            return resp.json()["embedding"]

    emb = asyncio.run(get_embedding(texts))
    return emb

def ingest_file(path: pathlib.Path):
    txt = path.read_text(encoding="utf-8")
    chunks = list(chunk(txt))
    vectors = embed(chunks)
    docs = [
        {"doc_id": path.name, "text": t, "embedding": v}
        for t, v in zip(chunks, vectors)
    ]
    col.insert_many(docs)

if __name__ == "__main__":
    col.drop()                # demo：重新导入干净数据
    for p in pathlib.Path("data").glob("*.txt"):
        ingest_file(p)
    # 手动或在 Atlas UI 中创建 embedding 字段的 $vectorSearch 索引
    print("Done.")
