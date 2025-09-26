#!/usr/bin/env python3
"""
快速检查导入结果
"""

import pymongo
import os
from dotenv import load_dotenv

load_dotenv()

def main():
    print("快速检查自荐信导入结果...")

    try:
        # 连接数据库
        client = pymongo.MongoClient(os.getenv('MONGODB_URI'))
        db = client[os.getenv('MONGO_DATABASE_NAME', 'interview')]
        print("✅ 数据库连接成功")

        # 基本统计
        users_count = db.users.count_documents({})
        resumes_count = db.resumes.count_documents({})

        print(f"👥 用户总数: {users_count}")
        print(f"📄 简历总数: {resumes_count}")

        # 检查是否有内容
        sample_resume = db.resumes.find_one({'content': {'$exists': True}})
        if sample_resume:
            content_length = len(sample_resume.get('content', {}).get('text', ''))
            print(f"📝 示例简历长度: {content_length} 字符")
            print("✅ 导入成功!")
        else:
            print("❌ 没有找到导入的内容")

        client.close()

    except Exception as e:
        print(f"❌ 错误: {e}")

if __name__ == "__main__":
    main()
