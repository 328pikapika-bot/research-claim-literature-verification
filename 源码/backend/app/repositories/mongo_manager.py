from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from pymongo import ASCENDING, MongoClient
from pymongo.errors import ConnectionFailure

from app.core.config import (
    MONGO_HOST, MONGO_PORT, MONGO_DATABASE,
    MONGO_USERNAME, MONGO_PASSWORD, MONGO_AUTH_SOURCE,
    TASK_COLLECTION, FILE_COLLECTION, HISTORY_COLLECTION,
)

logger = logging.getLogger(__name__)


class MongoDBConnectionError(Exception):
    pass


class MongoDBManager:

    def __deepcopy__(self, memo):
        return self

    def __copy__(self):
        return self

    def __init__(self):
        self.client: Optional[MongoClient] = None
        self.db: Optional[Any] = None
        self.read_executor = ThreadPoolExecutor(
            max_workers=int(os.getenv("MONGO_READ_POOL_SIZE", "8")),
            thread_name_prefix="mongo-read",
        )
        self.write_executor = ThreadPoolExecutor(
            max_workers=int(os.getenv("MONGO_WRITE_POOL_SIZE", "8")),
            thread_name_prefix="mongo-write",
        )
        self._connect()
        self._create_indexes()
        logger.info(
            f"[MongoDBManager] 初始化完成: host={MONGO_HOST}, db={MONGO_DATABASE}"
        )

    def shutdown_executors(self) -> None:
        self.read_executor.shutdown(wait=True)
        self.write_executor.shutdown(wait=True)

    def _build_uri(self) -> str:
        if MONGO_USERNAME and MONGO_PASSWORD:
            return (
                f"mongodb://{MONGO_USERNAME}:{MONGO_PASSWORD}"
                f"@{MONGO_HOST}:{MONGO_PORT}/{MONGO_DATABASE}"
                f"?authSource={MONGO_AUTH_SOURCE}"
            )
        return f"mongodb://{MONGO_HOST}:{MONGO_PORT}/{MONGO_DATABASE}"

    def _connect(self) -> None:
        uri = self._build_uri()
        try:
            self.client = MongoClient(
                uri,
                connectTimeoutMS=5000,
                serverSelectionTimeoutMS=5000,
                maxPoolSize=100,
                minPoolSize=10,
            )
            self.client.admin.command("ping")
            self.db = self.client[MONGO_DATABASE]
            logger.info(f"[MongoDBManager] 连接成功: {MONGO_HOST}:{MONGO_PORT}")
        except Exception as e:
            logger.warning(f"[MongoDBManager] 连接失败（服务将以降级模式运行）: {e}")
            self.client = None
            self.db = None

    def _create_indexes(self) -> None:
        if self.db is None:
            return

        try:
            existing = {idx["name"] for idx in self.db[TASK_COLLECTION].list_indexes()}
            indexes = [
                ("idx_user_scope_created", [("user_scope", ASCENDING), ("created_at", ASCENDING)]),
                ("idx_status_created", [("status", ASCENDING), ("created_at", ASCENDING)]),
                ("idx_thread_id", [("thread_id", ASCENDING)]),
                ("idx_created_at", [("created_at", ASCENDING)]),
                ("idx_user_status", [("user_scope", ASCENDING), ("status", ASCENDING)]),
            ]
            for name, keys in indexes:
                if name not in existing:
                    self.db[TASK_COLLECTION].create_index(keys, name=name)
                    logger.info(f"[MongoDBManager] 创建索引: {TASK_COLLECTION}.{name}")

            file_existing = {idx["name"] for idx in self.db[FILE_COLLECTION].list_indexes()}
            if "idx_user_scope_created" not in file_existing:
                self.db[FILE_COLLECTION].create_index(
                    [("user_scope", ASCENDING), ("created_at", ASCENDING)],
                    name="idx_user_scope_created",
                )

            hist_existing = {idx["name"] for idx in self.db[HISTORY_COLLECTION].list_indexes()}
            for name, keys in [
                ("idx_thread_run_ts", [("thread_id", ASCENDING), ("run_id", ASCENDING), ("ts", ASCENDING)]),
                ("idx_thread_ts", [("thread_id", ASCENDING), ("ts", ASCENDING)]),
            ]:
                if name not in hist_existing:
                    self.db[HISTORY_COLLECTION].create_index(keys, name=name)
        except Exception as e:
            logger.warning(f"[MongoDBManager] 创建索引失败: {e}")

    def test_connection(self) -> bool:
        if self.client is None:
            return False
        try:
            self.client.admin.command("ping")
            return True
        except Exception:
            return False

    def close(self) -> None:
        if self.client:
            self.client.close()
            logger.info("[MongoDBManager] 连接已关闭")

    @property
    def is_connected(self) -> bool:
        return self.client is not None and self.db is not None


_mongo_manager: Optional[MongoDBManager] = None


def get_mongo_manager() -> MongoDBManager:
    global _mongo_manager
    if _mongo_manager is None:
        _mongo_manager = MongoDBManager()
    return _mongo_manager
