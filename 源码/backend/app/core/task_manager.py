from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from app.core.rate_limiter import RateLimiter, RateLimiterConfig
from app.pipeline.engine import ConsistencyPipelineEngine
from app.pipeline.progress import ProgressWriter
from app.pipeline.state import PipelineState

logger = logging.getLogger(__name__)


class TaskManager:
    """In-process background task manager for consistency evaluation runs."""

    def __init__(self, task_repo: Any, file_repo: Any) -> None:
        self.task_repo = task_repo
        self.file_repo = file_repo
        self.rate_limiter = RateLimiter(RateLimiterConfig(), task_repo)
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._background_tasks: set[asyncio.Task] = set()

    @property
    def active_count(self) -> int:
        return len(self._running_tasks)

    async def start_pipeline(self, state: PipelineState) -> None:
        task_id = state.request.task_id
        task = asyncio.create_task(self._run_pipeline(state))
        self._running_tasks[task_id] = task
        self._background_tasks.add(task)
        task.add_done_callback(lambda finished: self._cleanup_task(task_id, finished))

    async def cancel_task(self, task_id: str, user_scope: str) -> bool:
        task = self._running_tasks.get(task_id)
        if task is None:
            return False
        task.cancel()
        self.task_repo.update(
            task_id,
            user_scope,
            {"status": "cancelled", "error_message": "任务已取消"},
        )
        return True

    async def shutdown(self) -> None:
        for task in list(self._running_tasks.values()):
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._running_tasks.clear()
        self._background_tasks.clear()

    def _cleanup_task(self, task_id: str, task: asyncio.Task) -> None:
        self._running_tasks.pop(task_id, None)
        self._background_tasks.discard(task)

    async def _run_pipeline(self, state: PipelineState) -> None:
        task_id = state.request.task_id
        user_scope = state.request.user_scope
        worker_id = f"async:{os.getpid()}"
        logger.info("[task_id=%s][user=%s] 一致性评估任务开始 worker=%s", task_id, user_scope, worker_id)
        progress = ProgressWriter(self.task_repo, task_id, user_scope)
        try:
            engine = ConsistencyPipelineEngine(self.file_repo, progress)
            await asyncio.to_thread(engine.run, state)
            logger.info("[task_id=%s][user=%s] 一致性评估任务完成", task_id, user_scope)
        except asyncio.CancelledError:
            logger.info("[task_id=%s][user=%s] 一致性评估任务被取消", task_id, user_scope)
            self.task_repo.update(
                task_id,
                user_scope,
                {"status": "cancelled", "error_message": "任务已取消"},
            )
        except Exception as exc:
            logger.exception("[task_id=%s][user=%s] 一致性评估任务失败", task_id, user_scope)
            progress.fail_current(str(exc))
        finally:
            await self.rate_limiter.release(user_scope)
