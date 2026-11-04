from __future__ import annotations

import logging
import time
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from app.repositories.mongo_manager import MongoDBManager
from app.repositories.schemas import TaskHistoryRecord

logger = logging.getLogger(__name__)

TIME_FIELDS = ("created_at", "last_updated_at", "completed_at")
BEIJING_TZ = timezone(timedelta(hours=8))


def _now_beijing_iso() -> str:
    return datetime.now(BEIJING_TZ).isoformat(timespec="milliseconds")


def _coerce_to_utc_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.isdigit():
            return datetime.fromtimestamp(int(normalized), tz=timezone.utc)
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    raise TypeError(f"Unsupported datetime value type: {type(value).__name__}")


def _to_iso_beijing(value: Any) -> Optional[str]:
    dt = _coerce_to_utc_datetime(value)
    if dt is None:
        return None
    return dt.astimezone(BEIJING_TZ).isoformat(timespec="milliseconds")


def _normalize_time_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(data)
    for field in TIME_FIELDS:
        if field in normalized:
            normalized[field] = _to_iso_beijing(normalized[field])
    return normalized


class MongoTaskHistoryRepository:

    def __deepcopy__(self, memo):
        return self

    def __copy__(self):
        return self

    def __init__(self, mongo_manager: MongoDBManager):
        from app.core.config import TASK_COLLECTION
        self.mongo_manager = mongo_manager
        self.collection = mongo_manager.db[TASK_COLLECTION]
        logger.info(f"[MongoTaskHistoryRepository] 初始化完成: collection={TASK_COLLECTION}")

    def create(self, record: TaskHistoryRecord) -> None:
        doc = _normalize_time_fields(record.to_dict(include_steps=True))
        doc["_id"] = record.task_id
        doc.pop("task_id", None)
        try:
            self.collection.insert_one(doc)
        except DuplicateKeyError:
            raise ValueError(f"任务ID已存在: {record.task_id}")

    def update(self, task_id: str, user_scope: str, updates: Dict[str, Any]) -> bool:
        updates = _normalize_time_fields(updates)
        updates["last_updated_at"] = _now_beijing_iso()
        result = self.collection.update_one(
            {"_id": task_id, "user_scope": user_scope},
            {"$set": updates},
        )
        return result.modified_count > 0

    def get(self, task_id: str, user_scope: str, include_steps: bool = False) -> Optional[TaskHistoryRecord]:
        projection = {"steps_data": 0} if not include_steps else None
        doc = self.collection.find_one(
            {"_id": task_id, "user_scope": user_scope},
            projection=projection,
        )
        return self._doc_to_record(doc) if doc else None

    def list(
        self,
        user_scope: str,
        status: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Tuple[List[TaskHistoryRecord], int]:
        filter_dict: Dict[str, Any] = {"user_scope": user_scope}
        if status and status != "all":
            filter_dict["status"] = status
        if search:
            filter_dict["$or"] = [
                {"topic": {"$regex": search, "$options": "i"}},
                {"research_type": {"$regex": search, "$options": "i"}},
            ]

        total = self.collection.count_documents(filter_dict)
        sort_direction = DESCENDING if sort_order.lower() == "desc" else ASCENDING
        offset = (page - 1) * page_size
        cursor = self.collection.find(
            filter_dict,
            projection={"steps_data": 0},
        ).sort(sort_by, sort_direction).skip(offset).limit(page_size)

        records = [self._doc_to_record(doc) for doc in cursor]
        return records, total

    def delete(self, task_id: str, user_scope: str) -> bool:
        result = self.collection.delete_one({"_id": task_id, "user_scope": user_scope})
        return result.deleted_count > 0

    def get_by_run_id(self, run_id: str) -> Optional[TaskHistoryRecord]:
        doc = self.collection.find_one({"_id": run_id})
        return self._doc_to_record(doc) if doc else None

    def update_by_task_id(self, task_id: str, updates: Dict[str, Any]) -> bool:
        updates = _normalize_time_fields(updates)
        updates["last_updated_at"] = _now_beijing_iso()
        result = self.collection.update_one({"_id": task_id}, {"$set": updates})
        return result.modified_count > 0

    def find_stale_tasks(self, timeout_hours: int = 6) -> List[TaskHistoryRecord]:
        cutoff = int(time.time()) - timeout_hours * 3600
        cutoff_iso = _to_iso_beijing(datetime.fromtimestamp(cutoff, tz=timezone.utc))
        cursor = self.collection.find(
            {"status": "running", "last_updated_at": {"$lt": cutoff_iso}},
            projection={"steps_data": 0},
        )
        return [self._doc_to_record(doc) for doc in cursor]

    def mark_stale_tasks_failed(self, timeout_hours: int = 6) -> int:
        cutoff_ts = int(time.time()) - timeout_hours * 3600
        cutoff_iso = _to_iso_beijing(datetime.fromtimestamp(cutoff_ts, tz=timezone.utc))
        now_iso = _now_beijing_iso()
        error_msg = f"任务超时（超过{timeout_hours}小时未完成），已自动标记为失败"

        stale = list(self.collection.find(
            {"status": "running", "last_updated_at": {"$lt": cutoff_iso}},
            projection={"_id": 1, "current_step": 1, "steps_data": 1},
        ))
        if not stale:
            return 0

        updated = 0
        for task_doc in stale:
            tid = task_doc["_id"]
            current_step = task_doc.get("current_step", 0)
            steps_data = task_doc.get("steps_data", [])
            if not isinstance(steps_data, list):
                steps_data = []
            step_idx = current_step - 1
            if step_idx >= 0:
                while len(steps_data) <= step_idx:
                    steps_data.append(None)
                if steps_data[step_idx] is None:
                    steps_data[step_idx] = {"step_no": current_step, "status": "failed", "error": error_msg, "failed_at": now_iso}
                elif isinstance(steps_data[step_idx], dict):
                    steps_data[step_idx]["status"] = "failed"
                    steps_data[step_idx]["error"] = error_msg
                    steps_data[step_idx]["failed_at"] = now_iso

            result = self.collection.update_one(
                {"_id": tid},
                {"$set": {"status": "failed", "error_message": error_msg, "completed_at": now_iso, "last_updated_at": now_iso, "steps_data": steps_data}},
            )
            if result.modified_count > 0:
                updated += 1
        return updated

    def count_running_tasks_by_user(self) -> Dict[str, int]:
        pipeline = [
            {"$match": {"status": {"$in": ["running", "requires_action"]}}},
            {"$group": {"_id": "$user_scope", "count": {"$sum": 1}}},
        ]
        return {doc["_id"]: doc["count"] for doc in self.collection.aggregate(pipeline)}

    def count_running_tasks_global(self) -> int:
        return self.collection.count_documents({"status": {"$in": ["running", "requires_action"]}})

    def _doc_to_record(self, doc: Dict[str, Any]) -> TaskHistoryRecord:
        doc = dict(doc)
        doc["task_id"] = doc.pop("_id")
        if "steps_data" in doc and doc["steps_data"] is None:
            doc["steps_data"] = None
        for field in TIME_FIELDS:
            if field in doc:
                doc[field] = _to_iso_beijing(doc[field])
        allowed = {item.name for item in fields(TaskHistoryRecord)}
        return TaskHistoryRecord(**{key: value for key, value in doc.items() if key in allowed})
