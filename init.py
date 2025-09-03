import json
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import requests
from tqdm import tqdm
from openai import OpenAI

load_dotenv()

# MongoDB connection settings
MONGO_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("MONGODB_DB")
COLLECTION_NAME = "problem"

# Path to the data file
DATA_FILE_PATH = "data/data.jsonl"

# 初始化OpenAI客户端（使用DashScope）
embedding_client = OpenAI(
    api_key=os.getenv("ALIYUN_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# 向量维度设置
VECTOR_DIMENSION = 1024  # text-embedding-v4的向量维度


def get_embedding(text):
    """
    Generates an embedding for the given text using OpenAI SDK with DashScope.
    """
    try:
        # 使用OpenAI SDK的embeddings.create方法
        completion = embedding_client.embeddings.create(
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
        print(f"Skipping line due to OpenAI SDK embedding generation error: {e}")
        return None


def load_data_to_mongodb():
    """
    Loads data from a JSONL file into a MongoDB collection, generating embeddings,
    starting from a specific ID without clearing the collection.
    """
    client = None
    start_id = "prob_171"
    processing_started = False
    try:
        # Establish a connection to MongoDB
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]

        # We are continuing an existing process, so we do not clear the collection.
        # print(f"Clearing collection '{COLLECTION_NAME}'...")
        # collection.delete_many({})
        # print("Collection cleared.")

        # Count total lines for the progress bar
        total_lines = 0
        with open(DATA_FILE_PATH, 'r', encoding='utf-8') as f:
            total_lines = sum(1 for _ in f)

        # Read the JSONL file and insert data into the collection
        print(f"Continuing to load data from '{DATA_FILE_PATH}' starting at id '{start_id}'...")
        count = 0
        with open(DATA_FILE_PATH, 'r', encoding='utf-8') as f:
            with tqdm(total=total_lines, desc="Processing files") as pbar:
                for line in f:
                    pbar.update(1)
                    try:
                        data = json.loads(line)
                        current_id = data.get("id")

                        if not processing_started and current_id == start_id:
                            processing_started = True

                        if not processing_started:
                            continue  # Skip until we find the start_id

                        # Check if document already exists to avoid duplicates
                        if collection.count_documents({'id': current_id}) > 0:
                            continue

                        content = data.get("content")
                        if content:
                            embedding = get_embedding(content)
                            if embedding:
                                data['content_vector'] = embedding
                                collection.insert_one(data)
                                count += 1
                            else:
                                print(f"Skipping document with id {data.get('id')} due to missing embedding.")
                    except json.JSONDecodeError as e:
                        print(f"Skipping line due to JSON decode error: {e}")

        print(
            f"Successfully loaded {count} new documents into '{COLLECTION_NAME}' collection."
        )

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if client:
            client.close()
            print("MongoDB connection closed after data loading.")


def create_vector_index():
    """
    Creates a vector search index on the 'content_vector' field.
    """
    client = None
    try:
        print("Connecting to MongoDB to create vector index...")
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]

        index_model = {
            "fields": [
                {
                    "type": "vector",
                    "path": "content_vector",
                    "numDimensions": VECTOR_DIMENSION,
                    "similarity": "cosine",
                }
            ]
        }

        print("Creating vector search index on MongoDB Atlas...")
        db.command(
            "createSearchIndex",
            COLLECTION_NAME,
            index={"name": "vector_index", "definition": index_model},
        )
        print("Vector search index creation command issued successfully.")
        print("Note: Index creation is an asynchronous operation and may take a few minutes.")

    except Exception as e:
        print(f"An error occurred during index creation: {e}")
    finally:
        if client:
            client.close()
            print("MongoDB connection closed after index creation.")


if __name__ == "__main__":
    load_data_to_mongodb()
    create_vector_index()
