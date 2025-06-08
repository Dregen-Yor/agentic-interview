import json
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import requests
from tqdm import tqdm

load_dotenv()

# MongoDB connection settings
MONGO_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("MONGODB_DB")
COLLECTION_NAME = "problem"

# Path to the data file
DATA_FILE_PATH = "data/data.jsonl"

# Embedding model settings
EMBEDDING_MODEL = "Q78KG/gte-Qwen2-7B-instruct:latest"
EMBEDDING_API_URL = "http://localhost:11434/api/embeddings"
VECTOR_DIMENSION = 3584


def get_embedding(text):
    """
    Generates an embedding for the given text using a local model API.
    """
    try:
        payload = {"model": EMBEDDING_MODEL, "prompt": text}
        response = requests.post(EMBEDDING_API_URL, json=payload)
        response.raise_for_status()
        return response.json().get("embedding")
    except requests.exceptions.RequestException as e:
        print(f"Skipping line due to embedding generation error: {e}")
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
