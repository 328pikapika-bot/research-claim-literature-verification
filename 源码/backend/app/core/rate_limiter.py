from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("consistency_evaluation.task")


def _get_int_from_env(env_var: str, default: int) -> int:
    value = os.getenv(env_var)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning(f"[RateLimiter] invalid env value: {env_var}={value!r}, fallback={default}")
        return default


@dataclass
class RateLimiterConfig:
    max_tasks_per_user: int = field(
        default_factory=lambda: _get_int_from_env("RATE_LIMIT_MAX_PER_USER", 5)
    )
    max_tasks_global: int = field(
        default_factory=lambda: _get_int_from_env("RATE_LIMIT_MAX_GLOBAL", 16)
    )
    running_states: List[str] = field(default_factory=lambda: ["running", "requires_action"])


class RateLimiter:

    def __init__(self, config: RateLimiterConfig, task_history_repo: Any):
        self.config = config
        self.task_history_repo = task_history_repo
        self._lock = asyncio.Lock()
        self.user_counts: Dict[str, int] = {}
        self.global_count = 0
        self.calibrate()
        logger.info(
            "[RateLimiter] initialized max_per_user=%s max_global=%s",
            config.max_tasks_per_user, config.max_tasks_global,
        )

    async def check_and_acquire(self, user_scope: str) -> Tuple[bool, str]:
        try:
            async with self._lock:
                user_count = self.user_counts.get(user_scope, 0)
                if user_count >= self.config.max_tasks_per_user:
                    return False, "当前在线使用人数过多，请您耐心等待，稍后即可体验系统功能。"
                if self.global_count >= self.config.max_tasks_global:
                    return False, "当前在线使用人数过多，请您耐心等待，稍后即可体验系统功能。"
                self.user_counts[user_scope] = user_count + 1
                self.global_count += 1
                return True, ""
        except Exception as exc:
            logger.warning("[RateLimiter] acquire failed: %s", exc)
            return True, ""

    async def release(self, user_scope: str) -> None:
        try:
            async with self._lock:
                user_count = self.user_counts.get(user_scope, 0)
                if user_count > 1:
                    self.user_counts[user_scope] = user_count - 1
                elif user_count > 0:
                    self.user_counts.pop(user_scope, None)
                if self.global_count > 0:
                    self.global_count -= 1
        except Exception as exc:
            logger.warning("[RateLimiter] release failed: %s", exc)

    def calibrate(self) -> None:
        try:
            user_counts_dict = dict(self.task_history_repo.count_running_tasks_by_user())
            global_total = self.task_history_repo.count_running_tasks_global()
            self.user_counts.clear()
            self.user_counts.update(user_counts_dict)
            self.global_count = global_total
        except Exception as exc:
            logger.warning("[RateLimiter] calibration failed: %s", exc)

    def get_stats(self) -> Dict[str, Any]:
        try:
            return {
                "global_count": self.global_count,
                "user_counts": dict(self.user_counts),
                "config": {
                    "max_tasks_per_user": self.config.max_tasks_per_user,
                    "max_tasks_global": self.config.max_tasks_global,
                },
            }
        except Exception as exc:
            return {"global_count": 0, "user_counts": {}, "config": {}, "error": str(exc)}
