from dotenv import load_dotenv
import os
import pymongo
import json
from tqdm import tqdm

# 加载环境变量
load_dotenv()

# 导入 init.py 中的 get_embedding 函数
from init import get_embedding


def _get_mongo_collections():
    """获取 MongoDB 连接与集合句柄"""
    client = pymongo.MongoClient(os.getenv("MONGODB_URI"))
    db = client[os.getenv("MONGODB_DB")]
    return client, db["problem"]


def update_content_vector():
    """更新 MongoDB 中所有文档的 content_vector 字段"""
    client, collection = None, None
    try:
        client, collection = _get_mongo_collections()

        # 获取所有文档的数量
        total_docs = collection.count_documents({})

        print(f"开始更新 {total_docs} 个文档的 content_vector...")

        # 获取所有文档
        documents = list(collection.find({}))

        updated_count = 0

        with tqdm(total=total_docs, desc="更新向量") as pbar:
            for doc in documents:
                try:
                    # 获取文档内容
                    content = doc.get("content")
                    if content:
                        # 使用 init.py 中的 get_embedding 函数生成新向量
                        new_embedding = get_embedding(content)

                        if new_embedding:
                            # 更新文档的 content_vector 字段
                            collection.update_one(
                                {"_id": doc["_id"]},
                                {"$set": {"content_vector": new_embedding}}
                            )
                            updated_count += 1
                        else:
                            print(f"跳过文档 ID {doc.get('id')}：无法生成向量")
                    else:
                        print(f"跳过文档 ID {doc.get('id')}：缺少 content 字段")

                except Exception as e:
                    print(f"更新文档 ID {doc.get('id')} 时出错：{e}")

                pbar.update(1)

        print(f"成功更新了 {updated_count} 个文档的 content_vector")

    except Exception as e:
        print(f"更新过程中出错：{e}")
    finally:
        if client:
            client.close()
            print("MongoDB 连接已关闭")


def update_specific_document(doc_id):
    """更新指定文档的 content_vector"""
    client, collection = None, None
    try:
        client, collection = _get_mongo_collections()

        # 查找指定文档
        doc = collection.find_one({"id": doc_id})

        if doc:
            content = doc.get("content")
            if content:
                # 生成新向量
                new_embedding = get_embedding(content)

                if new_embedding:
                    # 更新文档
                    collection.update_one(
                        {"id": doc_id},
                        {"$set": {"content_vector": new_embedding}}
                    )
                    print(f"成功更新文档 ID {doc_id} 的 content_vector")
                else:
                    print(f"无法为文档 ID {doc_id} 生成向量")
            else:
                print(f"文档 ID {doc_id} 缺少 content 字段")
        else:
            print(f"未找到文档 ID {doc_id}")

    except Exception as e:
        print(f"更新文档时出错：{e}")
    finally:
        if client:
            client.close()
            print("MongoDB 连接已关闭")


def show_document_structure():
    """显示文档结构示例"""
    client, collection = None, None
    try:
        client, collection = _get_mongo_collections()

        # 获取一个示例文档
        doc = collection.find_one({})

        if doc:
            print("文档结构示例：")
            print(json.dumps({
                "_id": str(doc.get("_id")),
                "id": doc.get("id"),
                "type": doc.get("type"),
                "difficulty": doc.get("difficulty"),
                "title": doc.get("title"),
                "content": doc.get("content")[:100] + "..." if doc.get("content") else None,
                "content_vector_length": len(doc.get("content_vector", []))
            }, indent=2, ensure_ascii=False))
        else:
            print("集合中没有文档")

    except Exception as e:
        print(f"获取文档结构时出错：{e}")
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    # 显示当前文档结构
    show_document_structure()

    # 更新所有文档的向量
    update_content_vector()