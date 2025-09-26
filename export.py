#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
面试结果数据导出脚本

此脚本连接MongoDB数据库，从results集合中导出所有面试结果数据，
保存为JSON格式并压缩成ZIP文件。
"""

import os
import json
import zipfile
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

def main():
    """主函数：导出MongoDB中的result数据并压缩"""
    # 加载环境变量
    load_dotenv()

    # 获取MongoDB连接配置
    mongo_uri = os.getenv('MONGODB_URI')
    database_name = os.getenv('MONGODB_DB')

    if not mongo_uri or not database_name:
        print("错误：未找到MongoDB连接配置。请检查环境变量 MONGO_URI 和 MONGO_DATABASE_NAME。")
        return

    try:
        # 连接MongoDB
        print("正在连接MongoDB...")
        client = MongoClient(mongo_uri)
        db = client[database_name]

        # 检查连接
        client.admin.command('ping')
        print("MongoDB连接成功！")

        # 获取results集合
        results_collection = db['result']

        # 查询所有result文档
        print("正在查询所有面试结果数据...")
        results = list(results_collection.find({}))

        if not results:
            print("警告：未找到任何面试结果数据。")
            return

        print(f"找到 {len(results)} 条面试结果记录。")

        # 生成导出文件名（包含时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_folder = f"interview_results_{timestamp}"
        zip_filename = f"interview_results_{timestamp}.zip"

        # 创建导出文件夹
        print(f"正在创建导出文件夹 {export_folder}...")
        os.makedirs(export_folder, exist_ok=True)

        # 为每个记录创建单独的JSON文件
        print("正在保存每个记录到单独的JSON文件...")
        saved_files = []

        for i, result in enumerate(results, 1):
            # 获取候选人姓名和session_id用于文件名
            candidate_name = result.get('candidate_name', 'unknown')
            session_id = result.get('session_id', f'record_{i}')

            # 清理文件名，移除特殊字符
            safe_name = "".join(c for c in candidate_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_session = "".join(c for c in session_id if c.isalnum() or c in ('-', '_')).rstrip()

            # 生成文件名
            filename = f"{safe_name}_{safe_session}.json"
            filepath = os.path.join(export_folder, filename)

            # 保存单个记录
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)

            saved_files.append(filename)
            print(f"已保存: {filename}")

        # 创建元数据文件
        metadata = {
            "export_timestamp": timestamp,
            "total_records": len(results),
            "database": database_name,
            "collection": "results",
            "exported_at": datetime.now().isoformat(),
            "files": saved_files,
            "file_format": "individual_json_files"
        }

        metadata_filepath = os.path.join(export_folder, "metadata.json")
        with open(metadata_filepath, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        # 压缩整个文件夹到ZIP
        print(f"正在压缩文件夹到 {zip_filename}...")
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(export_folder):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, os.path.dirname(export_folder))
                    zipf.write(file_path, arcname)

        # 删除临时文件夹
        import shutil
        shutil.rmtree(export_folder)

        print("导出完成！")
        print(f"ZIP文件位置：{os.path.abspath(zip_filename)}")
        print(f"导出记录数量：{len(results)}")

    except Exception as e:
        print(f"导出过程中发生错误：{str(e)}")
        return

    finally:
        # 关闭MongoDB连接
        if 'client' in locals():
            client.close()
            print("MongoDB连接已关闭。")

if __name__ == "__main__":
    main()
