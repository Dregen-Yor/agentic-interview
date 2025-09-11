#!/usr/bin/env python3
"""
用户创建脚本
用于在命令行下创建新用户账户

使用方法:
    python create_user.py --name "用户名" --password "密码"
    python create_user.py -n "用户名" -p "密码"
    
可选参数:
    --batch-file FILE    从文件批量创建用户
    --dry-run           仅验证不实际创建
    --force             强制覆盖已存在的用户
"""

import os
import sys
import argparse
import json
import pymongo
from pathlib import Path
from dotenv import load_dotenv
from django.contrib.auth.hashers import make_password

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv()

# 配置Django设置
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'interview_backend.settings')
import django
django.setup()

def get_db():
    """Helper function to connect to MongoDB and get the database."""
    try:
        client = pymongo.MongoClient(os.getenv("MONGODB_URI"))
        db = client[os.getenv("MONGODB_DB")]
        return db, client
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        sys.exit(1)

def validate_user_input(name, password):
    """验证用户输入"""
    errors = []
    
    if not name or not name.strip():
        errors.append("用户名不能为空")
    elif len(name.strip()) < 2:
        errors.append("用户名长度不能少于2个字符")
    elif len(name.strip()) > 50:
        errors.append("用户名长度不能超过50个字符")
    
    if not password:
        errors.append("密码不能为空")
    elif len(password) < 6:
        errors.append("密码长度不能少于6个字符")
    elif len(password) > 128:
        errors.append("密码长度不能超过128个字符")
    
    return errors

def user_exists(db, name):
    """检查用户是否已存在"""
    users_collection = db['users']
    return users_collection.find_one({'name': name}) is not None

def create_single_user(name, password, force=False, dry_run=False):
    """创建单个用户"""
    try:
        # 清理输入
        name = name.strip()

        # 验证必填字段
        if not all([name, password]):
            print(f"❌ 用户 '{name}' 创建失败: 用户名和密码都是必需的")
            return False

        # 验证输入
        validation_errors = validate_user_input(name, password)
        if validation_errors:
            print(f"❌ 用户 '{name}' 验证失败:")
            for error in validation_errors:
                print(f"   - {error}")
            return False

        if dry_run:
            print(f"✅ 验证通过 - 用户 '{name}' 可以创建")
            return True

        # Hash the password for security
        hashed_password = make_password(password)

        db, client = get_db()
        users_collection = db['users']

        # Check if user already exists
        if users_collection.find_one({'name': name}):
            if not force:
                client.close()
                print(f"❌ 用户 '{name}' 已存在（使用 --force 强制覆盖）")
                return False
            else:
                print(f"⚠️  将覆盖已存在的用户 '{name}'")

        # 如果使用force，先删除现有用户数据
        if force:
            existing_user = users_collection.find_one({'name': name})
            if existing_user:
                user_id = existing_user['_id']
                users_collection.delete_one({'_id': user_id})
                resumes_collection = db['resumes']
                resumes_collection.delete_one({'_id': user_id})
                print(f"🗑️  已删除原有用户 '{name}' 的数据")

        # 创建新用户
        user_result = users_collection.insert_one({
            'name': name,
            'password': hashed_password,
        })

        user_id = user_result.inserted_id

        # Create an empty resume for the new user
        resumes_collection = db['resumes']
        resumes_collection.insert_one({
            '_id': user_id,
            'content': {}
        })

        client.close()
        print(f"✅ 用户 '{name}' 创建成功 (ID: {user_id})")
        return True

    except Exception as e:
        print(f"❌ 创建用户 '{name}' 时发生错误: {e}")
        return False

def create_users_from_file(file_path, force=False, dry_run=False):
    """从文件批量创建用户"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            users_data = json.load(f)

        if not isinstance(users_data, list):
            print("❌ 文件格式错误：应为用户对象数组")
            return False

        success_count = 0
        total_count = len(users_data)

        print(f"📖 从文件读取到 {total_count} 个用户")

        for i, user_data in enumerate(users_data, 1):
            if not isinstance(user_data, dict):
                print(f"❌ 第 {i} 个用户数据格式错误：应为对象")
                continue

            name = user_data.get('name')
            password = user_data.get('password')

            print(f"\n[{i}/{total_count}] 处理用户: {name}")

            if create_single_user(name, password, force, dry_run):
                success_count += 1

        print(f"\n📊 批量处理完成: {success_count}/{total_count} 个用户处理成功")
        return success_count == total_count

    except FileNotFoundError:
        print(f"❌ 文件不存在: {file_path}")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ JSON文件格式错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 处理文件时发生错误: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="创建用户脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  创建单个用户:
    python create_user.py -n "张三" -p "123456"
    
  批量创建用户:
    python create_user.py --batch-file users.json
    
  仅验证不创建:
    python create_user.py -n "李四" -p "password" --dry-run
    
  强制覆盖已存在用户:
    python create_user.py -n "王五" -p "newpass" --force

批量文件格式示例 (users.json):
[
  {"name": "用户1", "password": "password1"},
  {"name": "用户2", "password": "password2"}
]

当前项目中的示例文件: users.json
        """
    )
    
    # 单个用户创建参数
    parser.add_argument('-n', '--name', help='用户名')
    parser.add_argument('-p', '--password', help='密码')
    
    # 批量创建参数
    parser.add_argument('--batch-file', help='批量创建用户的JSON文件路径')
    
    # 选项参数
    parser.add_argument('--dry-run', action='store_true', 
                       help='仅验证用户数据，不实际创建')
    parser.add_argument('--force', action='store_true', 
                       help='强制覆盖已存在的用户')
    
    args = parser.parse_args()
    
    # 验证参数
    if args.batch_file:
        if args.name or args.password:
            print("❌ 批量模式下不能同时指定单个用户参数")
            sys.exit(1)
    else:
        if not args.name or not args.password:
            print("❌ 请提供用户名和密码，或使用 --batch-file 进行批量创建")
            print("使用 --help 查看详细用法")
            sys.exit(1)
    
    try:
        if args.batch_file:
            # 批量创建模式
            success = create_users_from_file(args.batch_file, args.force, args.dry_run)
        else:
            # 单个用户创建模式
            success = create_single_user(args.name, args.password, args.force, args.dry_run)

        if success:
            action = "验证" if args.dry_run else "创建"
            print(f"\n🎉 用户{action}完成！")
        else:
            print(f"\n💥 用户创建过程中遇到错误")
            sys.exit(1)

    except Exception as e:
        print(f"❌ 脚本执行时发生错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
