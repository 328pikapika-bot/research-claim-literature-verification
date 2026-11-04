from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.repositories.mongo_manager import MongoDBManager
from app.core.config import HISTORY_COLLECTION

logger = logging.getLogger(__name__)


class MongoHistoryRepository:

    def __deepcopy__(self, memo):
        return self

    def __copy__(self):
        return self

    def __init__(self, mongo_manager: MongoDBManager):
        self.mongo_manager = mongo_manager
        self.collection = mongo_manager.db[HISTORY_COLLECTION]
        logger.info(f"[MongoHistoryRepository] 初始化完成: collection={HISTORY_COLLECTION}")

    def append(
        self,
        thread_id: str,
        run_id: str,
        event_type: str,
        payload: Dict[str, Any],
        user_scope: str = "default",
    ) -> str:
        doc = {
            "thread_id": thread_id,
            "run_id": run_id,
            "user_scope": user_scope,
            "event_type": event_type,
            "payload": payload,
            "ts": datetime.now(timezone.utc),
        }
        result = self.collection.insert_one(doc)
        return str(result.inserted_id)

    def get_events(
        self,
        thread_id: str,
        run_id: Optional[str] = None,
        after_sequence: int = 0,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        filter_dict: Dict[str, Any] = {"thread_id": thread_id}
        if run_id:
            filter_dict["run_id"] = run_id

        cursor = (
            self.collection.find(filter_dict)
            .sort("ts", 1)
            .skip(after_sequence)
            .limit(limit)
        )
        events = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            events.append(doc)
        return events

    def delete_thread_events(self, thread_id: str) -> int:
        result = self.collection.delete_many({"thread_id": thread_id})
        return result.deleted_count
