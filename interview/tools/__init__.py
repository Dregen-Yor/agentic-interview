"""interview.tools — 数据访问与外部工具集"""

from .db import close_mongo_client, get_mongo_client, get_mongo_db

__all__ = [
    "close_mongo_client",
    "get_mongo_client",
    "get_mongo_db",
]
