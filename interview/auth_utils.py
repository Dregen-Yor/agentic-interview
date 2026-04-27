"""
JWT 认证工具（统一入口）

- generate_token(user_id, name): 生成签发 JWT
- decode_token(token): 解码并校验 JWT
- extract_token_from_request(request): 从 Authorization header 中提取 token
- jwt_required(view_func): Django 视图装饰器，校验失败返回 401，成功后将 payload 注入 request.jwt_payload
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable, Dict, Optional

import jwt
from django.conf import settings
from django.http import JsonResponse

logger = logging.getLogger("interview.auth")

JWT_ALGORITHM = "HS256"
DEFAULT_EXPIRATION_HOURS = 1


def generate_token(user_id: Any, name: str, hours: int = DEFAULT_EXPIRATION_HOURS) -> str:
    payload = {
        "user_id": str(user_id),
        "name": name,
        "exp": datetime.now(timezone.utc) + timedelta(hours=hours),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM])


def extract_token_from_request(request) -> Optional[str]:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or not parts[1].strip():
        return None
    return parts[1].strip()


def jwt_required(view_func: Callable):
    """统一的 JWT 校验装饰器，校验通过后将 payload 注入 request.jwt_payload"""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        token = extract_token_from_request(request)
        if not token:
            return JsonResponse(
                {"error": "Authorization header missing or invalid"}, status=401
            )
        try:
            payload = decode_token(token)
        except jwt.ExpiredSignatureError:
            return JsonResponse({"error": "Token has expired"}, status=401)
        except jwt.InvalidTokenError:
            return JsonResponse({"error": "Invalid token"}, status=401)
        except Exception:
            logger.exception("JWT 校验出现未知错误")
            return JsonResponse({"error": "Token verification failed"}, status=401)

        request.jwt_payload = payload
        return view_func(request, *args, **kwargs)

    return wrapper
