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

# Initialize OpenAI client (using DashScope)
embedding_client = OpenAI(
    api_key=os.getenv("ALIYUN_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# Vector dimension settings
VECTOR_DIMENSION = 1024  # Vector dimension for text-embedding-v4


def get_embedding(text):
    """
    Generates an embedding for the given text using OpenAI SDK with DashScope.
    """
    try:
        # Use OpenAI SDK's embeddings.create method
        completion = embedding_client.embeddings.create(
            model="text-embedding-v4",
            input=text,
            dimensions=1024,  # Specify vector dimension
            encoding_format="float"
        )
        # Extract embedding vector from response
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


def create_memory_vector_index():
    """
    Creates a vector search index on the 'conversation_memories' collection
    for Memento-style case retrieval.
    Also creates regular indexes for common query patterns.
    """
    client = None
    try:
        print("Connecting to MongoDB to create memory vector index...")
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]

        memory_collection_name = "conversation_memories"

        # 1. 创建向量搜索索引 (Atlas Search)
        vector_index_model = {
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": VECTOR_DIMENSION,
                    "similarity": "cosine",
                },
                {
                    "type": "filter",
                    "path": "doc_type",
                },
                {
                    "type": "filter",
                    "path": "session_id",
                },
                {
                    "type": "filter",
                    "path": "candidate_name",
                },
            ]
        }

        print("Creating memory vector search index on MongoDB Atlas...")
        db.command(
            "createSearchIndex",
            memory_collection_name,
            index={"name": "memory_vector_index", "definition": vector_index_model},
        )
        print("Memory vector search index creation command issued successfully.")

        # 2. 创建常规索引（幂等）
        coll = db[memory_collection_name]

        coll.create_index(
            [("session_id", 1), ("doc_type", 1), ("turn_index", 1)],
            name="idx_session_doc_turn"
        )
        coll.create_index(
            [("candidate_name", 1), ("doc_type", 1), ("importance", -1)],
            name="idx_candidate_doc_importance"
        )
        coll.create_index(
            [("doc_type", 1), ("status", 1), ("created_at", 1)],
            name="idx_doc_status_created"
        )
        print("Regular indexes created successfully.")
        print("Note: Vector index creation is asynchronous and may take a few minutes.")

    except Exception as e:
        print(f"An error occurred during memory index creation: {e}")
    finally:
        if client:
            client.close()
            print("MongoDB connection closed after memory index creation.")


if __name__ == "__main__":
    load_data_to_mongodb()
    create_vector_index()
    create_memory_vector_index()
