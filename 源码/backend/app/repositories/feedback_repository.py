from __future__ import annotations

import asyncio
import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

from app.core.config import FEEDBACK_COLLECTION, FEEDBACK_FALLBACK_DIR
from app.repositories.mongo_manager import MongoDBManager

logger = logging.getLogger(__name__)


class FeedbackStorageError(RuntimeError):
    """Feedback persistence error."""


class FeedbackRepository:
    """Persist user feedback to MongoDB, with JSONL fallback when Mongo is unavailable."""

    def __init__(self, mongo_manager: MongoDBManager):
        self.mongo_manager = mongo_manager
        self.collection = (
            mongo_manager.db[FEEDBACK_COLLECTION]
            if mongo_manager.db is not None
            else None
        )
        self.fallback_dir = Path(FEEDBACK_FALLBACK_DIR)
        self._fallback_lock = asyncio.Lock()
        if self.collection is not None:
            self._create_indexes()
        logger.info(
            "[FeedbackRepository] initialized collection=%s mongo_connected=%s",
            FEEDBACK_COLLECTION,
            self.collection is not None,
        )

    async def create(self, record: dict[str, Any]) -> str:
        if self.collection is None:
            await self._append_fallback(record)
            return record["feedback_id"]

        doc = deepcopy(record)
        doc["_id"] = doc["feedback_id"]
        try:
            await asyncio.to_thread(self.collection.insert_one, doc)
            return record["feedback_id"]
        except PyMongoError as exc:
            logger.error(
                "保存意见反馈到 MongoDB 失败 feedback_id=%s: %s",
                record.get("feedback_id"),
                exc,
            )
            await self._append_fallback(record)
            return record["feedback_id"]
        except Exception as exc:
            logger.exception(
                "保存意见反馈失败 feedback_id=%s",
                record.get("feedback_id"),
            )
            raise FeedbackStorageError(f"保存意见反馈失败：{exc}") from exc

    def _create_indexes(self) -> None:
        assert self.collection is not None
        try:
            existing = {idx["name"] for idx in self.collection.list_indexes()}
            if "idx_feedback_id" not in existing:
                self.collection.create_index(
                    [("feedback_id", ASCENDING)],
                    name="idx_feedback_id",
                    unique=True,
                )
            if "idx_user_scope_created" not in existing:
                self.collection.create_index(
                    [("user_scope", ASCENDING), ("created_at", DESCENDING)],
                    name="idx_user_scope_created",
                )
            if "idx_system_created" not in existing:
                self.collection.create_index(
                    [("system_name", ASCENDING), ("created_at", DESCENDING)],
                    name="idx_system_created",
                )
        except Exception as exc:
            logger.warning("[FeedbackRepository] 创建索引失败: %s", exc)

    async def _append_fallback(self, record: dict[str, Any]) -> None:
        async with self._fallback_lock:
            self.fallback_dir.mkdir(parents=True, exist_ok=True)
            target = self.fallback_dir / "feedback.jsonl"
            line = json.dumps(deepcopy(record), ensure_ascii=False, default=str)
            await asyncio.to_thread(self._write_line, target, line)

    @staticmethod
    def _write_line(target: Path, line: str) -> None:
        with target.open("a", encoding="utf-8") as fp:
            fp.write(line)
            fp.write("\n")
