from __future__ import annotations

import logging
import threading
import time
from copy import deepcopy
from datetime import datetime
from typing import Any, Callable, TypeVar

from app.pipeline.workflow_config import MODEL_HEARTBEAT_INTERVAL_SECONDS, STAGE_DISPLAY_DEFINITIONS
from app.pipeline.utils import now_beijing_iso

logger = logging.getLogger(__name__)


STAGE_DEFINITIONS = [(item["key"], item["title"]) for item in STAGE_DISPLAY_DEFINITIONS]
T = TypeVar("T")


class ProgressWriter:
    def __init__(self, task_repo: Any, task_id: str, user_scope: str) -> None:
        self.task_repo = task_repo
        self.task_id = task_id
        self.user_scope = user_scope
        self.steps_data = [
            {
                "step_no": index,
                "step_key": key,
                "title": title,
                "status": "pending",
                "summary": "",
                "sub_steps": [],
                "degradations": [],
                "payload": {},
            }
            for index, (key, title) in enumerate(STAGE_DEFINITIONS, start=1)
        ]

    def stage_index(self, stage_key: str) -> int:
        for index, (key, _) in enumerate(STAGE_DEFINITIONS, start=1):
            if key == stage_key:
                return index
        return 0

    def start(self, stage_key: str, summary: str = "") -> None:
        idx = self.stage_index(stage_key)
        self._update_step(
            stage_key,
            {
                "status": "running",
                "started_at": now_beijing_iso(),
                "summary": summary,
            },
        )
        self._persist({"status": "running", "current_step": idx, "steps_data": self.steps_data})

    def heartbeat(
        self,
        stage_key: str,
        summary: str | None = None,
        payload_patch: dict[str, Any] | None = None,
    ) -> None:
        idx = self.stage_index(stage_key)
        update: dict[str, Any] = {"status": "running", "heartbeat_at": now_beijing_iso()}
        if summary is not None:
            update["summary"] = summary
        if payload_patch:
            step = self._get_step(stage_key)
            current_payload = deepcopy(step.get("payload") or {})
            current_payload.update(deepcopy(payload_patch))
            update["payload"] = current_payload
            if "sub_steps" in current_payload:
                update["sub_steps"] = current_payload.get("sub_steps", [])
        self._update_step(stage_key, update)
        self._persist({"status": "running", "current_step": idx, "steps_data": self.steps_data})

    def patch_payload(self, stage_key: str, patch: dict[str, Any]) -> None:
        self.heartbeat(stage_key, payload_patch=patch)

    def run_with_periodic_heartbeat(
        self,
        stage_key: str,
        action: Callable[[], T],
        *,
        summary: str,
        eta_hint: str = "",
        payload_factory: Callable[[int], dict[str, Any]] | None = None,
        interval_seconds: float = MODEL_HEARTBEAT_INTERVAL_SECONDS,
    ) -> T:
        """Run a blocking action while keeping the task snapshot fresh for the UI."""

        stop_event = threading.Event()
        started = time.monotonic()

        def emit_heartbeat() -> None:
            elapsed = int(time.monotonic() - started)
            patch: dict[str, Any] = {
                "progress_message": summary,
                "elapsed_seconds": elapsed,
            }
            if eta_hint:
                patch["eta_hint"] = eta_hint
            if payload_factory:
                try:
                    patch.update(payload_factory(elapsed) or {})
                except Exception:
                    logger.warning("阶段心跳 payload 生成失败 stage=%s", stage_key, exc_info=True)
            self.heartbeat(stage_key, summary=summary, payload_patch=patch)

        def worker() -> None:
            while not stop_event.wait(max(1.0, interval_seconds)):
                try:
                    emit_heartbeat()
                except Exception:
                    logger.warning("阶段心跳写入失败 stage=%s", stage_key, exc_info=True)

        thread = threading.Thread(
            target=worker,
            name=f"progress-heartbeat-{stage_key}-{self.task_id}",
            daemon=True,
        )
        thread.start()
        try:
            return action()
        finally:
            stop_event.set()
            thread.join(timeout=1.0)

    def complete(
        self,
        stage_key: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        degradations: list[dict[str, Any]] | None = None,
    ) -> None:
        payload_data = deepcopy(payload) if payload else {}
        update = {
            "status": "completed",
            "completed_at": now_beijing_iso(),
            "summary": summary,
        }
        if payload_data:
            update["payload"] = payload_data
            update["sub_steps"] = payload_data.get("sub_steps", update.get("sub_steps", []))
        if degradations:
            update["degradations"] = degradations
        self._update_step(stage_key, update)
        self._persist({"steps_data": self.steps_data})

    def fail(self, stage_key: str, error: str) -> None:
        idx = self.stage_index(stage_key)
        self._update_step(
            stage_key,
            {
                "status": "failed",
                "failed_at": now_beijing_iso(),
                "error": error,
                "summary": "阶段执行失败",
            },
        )
        self._persist(
            {
                "status": "failed",
                "current_step": idx,
                "steps_data": self.steps_data,
                "error_message": error,
                "error_category": stage_key,
                "completed_at": now_beijing_iso(),
            }
        )

    def fail_current(self, error: str) -> None:
        task = self.task_repo.get(self.task_id, self.user_scope, include_steps=True)
        stage_key = "preprocess"
        if task and task.current_step:
            index = max(0, min(task.current_step - 1, len(STAGE_DEFINITIONS) - 1))
            stage_key = STAGE_DEFINITIONS[index][0]
        self.fail(stage_key, error)

    def complete_task(self, final_result: dict[str, Any], input_digest: dict[str, Any]) -> None:
        task = self.task_repo.get(self.task_id, self.user_scope, include_steps=True)
        created_at = getattr(task, "created_at", None) if task else None
        duration = _duration_seconds(created_at)
        self._persist(
            {
                "status": "completed",
                "current_step": len(STAGE_DEFINITIONS),
                "steps_data": self.steps_data,
                "result": final_result,
                "final_result": final_result,
                "input_digest": input_digest,
                "completed_at": now_beijing_iso(),
                "duration_seconds": duration,
            }
        )

    def _update_step(self, stage_key: str, updates: dict[str, Any]) -> None:
        idx = self.stage_index(stage_key) - 1
        if idx < 0:
            logger.warning("未知阶段: %s", stage_key)
            return
        self.steps_data[idx].update(deepcopy(updates))

    def _get_step(self, stage_key: str) -> dict[str, Any]:
        idx = self.stage_index(stage_key) - 1
        if idx < 0:
            return {}
        return self.steps_data[idx]

    def _persist(self, updates: dict[str, Any]) -> None:
        ok = self.task_repo.update(self.task_id, self.user_scope, updates)
        if not ok:
            logger.warning("任务进度写入未命中 task_id=%s user=%s", self.task_id, self.user_scope)


def _duration_seconds(created_at: Any) -> int | None:
    if not created_at:
        return None
    try:
        if isinstance(created_at, (int, float)):
            return max(0, int(datetime.now().timestamp() - float(created_at)))
        parsed = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return max(0, int((datetime.now(parsed.tzinfo) - parsed).total_seconds()))
    except Exception:
        return None
