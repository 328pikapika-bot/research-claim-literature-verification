from __future__ import annotations

import hashlib
import logging
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from pymongo import UpdateOne

from app.core.config import FILE_COLLECTION
from app.repositories.mongo_manager import MongoDBManager
from app.repositories.schemas import ParsedFileRecord

logger = logging.getLogger(__name__)

BEIJING_TZ = timezone(timedelta(hours=8))


def now_beijing_iso() -> str:
    return datetime.now(BEIJING_TZ).isoformat(timespec="milliseconds")


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()


def normalize_file_type(value: Any) -> str:
    file_type = str(value or "").strip().lower().lstrip(".")
    if file_type == "markdown":
        return "md"
    return file_type


class MongoParsedFileRepository:
    def __deepcopy__(self, memo):
        return self

    def __copy__(self):
        return self

    def __init__(self, mongo_manager: MongoDBManager):
        self.mongo_manager = mongo_manager
        self.collection = mongo_manager.db[FILE_COLLECTION]
        logger.info("[MongoParsedFileRepository] 初始化完成: collection=%s", FILE_COLLECTION)

    def create(self, record: ParsedFileRecord) -> ParsedFileRecord:
        saved, errors, _ = self.batch_create([record])
        if errors or saved < 1:
            detail = errors[0].get("error") if errors else "unknown error"
            raise ValueError(f"保存解析文件失败: {detail}")
        return record

    def get(
        self,
        file_id: str,
        user_scope: str,
        include_content: bool = True,
    ) -> Optional[ParsedFileRecord]:
        projection = {"content": 0} if not include_content else None
        doc = self.collection.find_one(
            {"_id": self._doc_id(user_scope, file_id), "user_scope": user_scope},
            projection=projection,
        )
        return self._doc_to_record(doc) if doc else None

    def list(self, user_scope: str, include_content: bool = False) -> List[ParsedFileRecord]:
        projection = {"content": 0} if not include_content else None
        cursor = self.collection.find(
            {"user_scope": user_scope},
            projection=projection,
        ).sort("created_at", -1)
        return [self._doc_to_record(doc) for doc in cursor]

    def delete(self, file_id: str, user_scope: str) -> bool:
        result = self.collection.delete_one(
            {"_id": self._doc_id(user_scope, file_id), "user_scope": user_scope}
        )
        return result.deleted_count > 0

    def clear(self, user_scope: str) -> int:
        result = self.collection.delete_many({"user_scope": user_scope})
        return int(result.deleted_count)

    def batch_create(
        self, records: List[ParsedFileRecord]
    ) -> Tuple[int, List[Dict[str, Any]], List[Dict[str, Any]]]:
        if not records:
            return 0, [], []

        operations = []
        public_records: list[dict[str, Any]] = []
        for record in records:
            normalized = self._normalize_record(record)
            doc = normalized.to_dict(include_content=True)
            doc["_id"] = self._doc_id(normalized.user_scope, normalized.file_id)
            doc.pop("file_id", None)
            operations.append(
                UpdateOne(
                    {"_id": doc["_id"], "user_scope": normalized.user_scope},
                    {
                        "$set": {
                            key: value
                            for key, value in doc.items()
                            if key not in {"_id", "created_at"}
                        },
                        "$setOnInsert": {"created_at": doc.get("created_at") or now_beijing_iso()},
                    },
                    upsert=True,
                )
            )
            public_records.append(normalized.to_dict(include_content=False))

        try:
            self.collection.bulk_write(operations, ordered=False)
            return len(records), [], public_records
        except Exception as exc:
            logger.error("批量保存解析文件失败: %s", exc, exc_info=True)
            return 0, [{"error": str(exc)}], []

    def touch_used(self, file_ids: List[str], user_scope: str) -> None:
        if not file_ids:
            return
        ids = [self._doc_id(user_scope, file_id) for file_id in file_ids if file_id]
        if not ids:
            return
        self.collection.update_many(
            {"_id": {"$in": ids}, "user_scope": user_scope},
            {"$set": {"last_used_at": now_beijing_iso()}},
        )

    def _normalize_record(self, record: ParsedFileRecord) -> ParsedFileRecord:
        data = record.to_dict(include_content=True)
        content = str(data.get("content") or "")
        now = now_beijing_iso()
        data["type"] = normalize_file_type(data.get("type"))
        data["content_size"] = int(data.get("content_size") or len(content))
        data["original_content_size"] = int(
            data.get("original_content_size") or data["content_size"]
        )
        data["content_hash"] = data.get("content_hash") or content_hash(content)
        data["source"] = data.get("source") or "client_parser"
        data["created_at"] = data.get("created_at") or now
        data["updated_at"] = now
        data["last_used_at"] = data.get("last_used_at") or None
        data["truncated"] = bool(data.get("truncated"))
        data["url"] = data.get("url") or f"/v1/parsed-files/{record.file_id}"
        return ParsedFileRecord(**data)

    @staticmethod
    def _doc_id(user_scope: str, file_id: str) -> str:
        return f"{user_scope}:{file_id}"

    def _doc_to_record(self, doc: Dict[str, Any]) -> ParsedFileRecord:
        data = deepcopy(doc)
        stored_id = str(data.pop("_id", ""))
        data["file_id"] = data.get("file_id") or stored_id.split(":", 1)[-1]
        data.setdefault("content", "")
        data.setdefault("content_size", len(data.get("content") or ""))
        data.setdefault("original_content_size", data["content_size"])
        data.setdefault("content_hash", content_hash(data.get("content") or ""))
        data.setdefault("source", "client_parser")
        data.setdefault("truncated", False)
        data.setdefault("created_at", None)
        data.setdefault("updated_at", None)
        data.setdefault("last_used_at", None)
        return ParsedFileRecord(**data)
