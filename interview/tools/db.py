"""
MongoDB 连接池统一入口

- 模块级单例 MongoClient（pymongo 自带连接池），所有数据访问都应通过此模块拿连接，
  避免每个请求新建/关闭连接造成 fd 耗尽和性能下降。
- 进程退出时由 close_mongo_client() 显式关闭。
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

import pymongo
from pymongo.database import Database

logger = logging.getLogger("interview.tools.db")

_client_lock = threading.Lock()
_client: Optional[pymongo.MongoClient] = None


def _read_uri() -> str:
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("环境变量 MONGODB_URI 未配置")
    return uri


def _read_db_name() -> str:
    name = os.getenv("MONGODB_DB")
    if not name:
        raise RuntimeError("环境变量 MONGODB_DB 未配置")
    return name


def get_mongo_client() -> pymongo.MongoClient:
    """获取共享 MongoClient（线程安全的双检锁懒加载）"""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = pymongo.MongoClient(_read_uri())
                logger.info("MongoClient 已初始化（共享连接池）")
    return _client


def get_mongo_db() -> Database:
    """获取默认数据库句柄"""
    return get_mongo_client()[_read_db_name()]


def close_mongo_client() -> None:
    """关闭共享 MongoClient，一般仅在进程退出时调用"""
    global _client
    if _client is not None:
        with _client_lock:
            if _client is not None:
                try:
                    _client.close()
                finally:
                    _client = None
                    logger.info("MongoClient 已关闭")
