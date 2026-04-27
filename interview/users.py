"""
用户与简历相关的 HTTP 视图。

改造要点：
- 共享 MongoClient 连接池（interview.tools.db.get_mongo_db），避免每次请求新建/关闭连接。
- 统一通过 interview.auth_utils 处理 JWT 生成、解码与权限校验，移除散落各处的重复代码。
- 视图函数通过 @jwt_required 装饰器获得已校验的 request.jwt_payload。
"""
from __future__ import annotations

import json
import logging

import pymongo
from bson.objectid import ObjectId
from django.contrib.auth.hashers import check_password, make_password
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from interview.auth_utils import generate_token, jwt_required
from interview.tools.db import get_mongo_db

logger = logging.getLogger("interview.users")


@csrf_exempt
def new_user(request):
    """创建新用户，密码使用 Django 的 hashing 算法存储。"""
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method is allowed"}, status=405)

    try:
        data = json.loads(request.body)
        name = data.get("name")
        password = data.get("password")

        if not all([name, password]):
            return JsonResponse({"error": "Name and password are required"}, status=400)

        db = get_mongo_db()
        users_collection = db["users"]

        if users_collection.find_one({"name": name}):
            return JsonResponse({"error": "User with this name already exists"}, status=409)

        user_id = users_collection.insert_one({
            "name": name,
            "password": make_password(password),
        }).inserted_id

        db["resumes"].insert_one({"_id": user_id, "content": {}})

        return JsonResponse(
            {"message": "User created successfully", "user_id": str(user_id)},
            status=201,
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON in request body"}, status=400)
    except Exception:
        logger.exception("new_user 出错")
        return JsonResponse({"error": "An unexpected error occurred"}, status=500)


@csrf_exempt
def check_user(request):
    """校验用户名/密码，成功后返回 JWT。"""
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method is allowed"}, status=405)

    try:
        data = json.loads(request.body)
        name = data.get("name")
        password = data.get("password")

        if not name or not password:
            return JsonResponse({"error": "Name and password are required"}, status=400)

        db = get_mongo_db()
        user = db["users"].find_one({"name": name})

        if user and check_password(password, user["password"]):
            token = generate_token(user["_id"], user["name"])
            return JsonResponse({"message": "Login successful", "token": token})

        return JsonResponse({"error": "Invalid credentials"}, status=401)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON in request body"}, status=400)
    except Exception:
        logger.exception("check_user 出错")
        return JsonResponse({"error": "An unexpected error occurred"}, status=500)


@csrf_exempt
@jwt_required
def verify_token(request):
    """验证 JWT 是否有效（解码逻辑统一交给 jwt_required 装饰器）。"""
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method is allowed"}, status=405)

    payload = request.jwt_payload
    return JsonResponse(
        {"message": "Token is valid", "user_id": payload["user_id"]},
        status=200,
    )


@csrf_exempt
@jwt_required
def get_user_resume(request):
    """获取当前用户的简历。"""
    if request.method != "GET":
        return JsonResponse({"error": "Only GET method is allowed"}, status=405)

    try:
        user_id = ObjectId(request.jwt_payload["user_id"])
        resume = get_mongo_db()["resumes"].find_one({"_id": user_id})
        if not resume:
            return JsonResponse({"error": "Resume not found"}, status=404)
        return JsonResponse({"resume": resume.get("content", {})}, status=200)

    except Exception:
        logger.exception("get_user_resume 出错")
        return JsonResponse({"error": "An unexpected error occurred"}, status=500)


@csrf_exempt
@jwt_required
def update_user_resume(request):
    """更新当前用户的简历。"""
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method is allowed"}, status=405)

    try:
        user_id = ObjectId(request.jwt_payload["user_id"])
        request_data = json.loads(request.body)
        new_content = request_data.get("content")

        if new_content is None:
            return JsonResponse({"error": 'Missing "content" in request body'}, status=400)

        result = get_mongo_db()["resumes"].update_one(
            {"_id": user_id},
            {"$set": {"content": new_content}},
        )
        if result.matched_count == 0:
            return JsonResponse({"error": "Resume not found for the user"}, status=404)

        return JsonResponse({"message": "Resume updated successfully"}, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON in request body"}, status=400)
    except Exception:
        logger.exception("update_user_resume 出错")
        return JsonResponse({"error": "An unexpected error occurred"}, status=500)


@csrf_exempt
@jwt_required
def get_interview_result(request):
    """获取当前用户最近一次的面试结果。"""
    if request.method != "GET":
        return JsonResponse({"error": "Only GET method is allowed"}, status=405)

    try:
        username = request.jwt_payload["name"]
        result_collection = get_mongo_db()["result"]

        latest_result = result_collection.find_one(
            {"$or": [{"candidate_name": username}, {"name": username}]},
            sort=[("timestamp", pymongo.DESCENDING)],
        )

        if not latest_result:
            return JsonResponse({"error": "Interview result not found for the user"}, status=404)

        latest_result["_id"] = str(latest_result["_id"])
        timestamp = latest_result.get("timestamp")
        if timestamp is not None and hasattr(timestamp, "isoformat"):
            latest_result["timestamp"] = timestamp.isoformat()

        return JsonResponse(latest_result, status=200)

    except Exception:
        logger.exception("get_interview_result 出错")
        return JsonResponse({"error": "An unexpected error occurred"}, status=500)
