from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional

import requests

from app.core.config import MODEL_API_KEY, MODEL_BASE_URL, MODEL_NAME, MODEL_TIMEOUT
from app.pipeline.utils import parse_json_loose

logger = logging.getLogger(__name__)


class ModelGateway:
    """Small OpenAI-compatible gateway with one retry and rule fallback support."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else MODEL_API_KEY
        self.base_url = (base_url if base_url is not None else MODEL_BASE_URL).rstrip("/")
        self.model = model or MODEL_NAME
        self.timeout = int(timeout or MODEL_TIMEOUT or 90)

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def chat_json(self, system: str, prompt: str) -> Optional[Any]:
        if not self.configured:
            return None
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return self._request_json(system, prompt)
            except Exception as exc:
                last_error = exc
                logger.warning("模型调用失败 attempt=%s error=%s", attempt + 1, exc)
                if attempt == 0:
                    time.sleep(0.8)
        if last_error:
            logger.error("模型调用重试后仍失败: %s", last_error, exc_info=True)
        return None

    def chat_json_with_recovery(
        self,
        attempts: list[dict[str, Any]],
        *,
        retries: int = 1,
        on_attempt: Any | None = None,
    ) -> Optional[Any]:
        last_error: Exception | None = None
        for attempt_index, attempt in enumerate(attempts, start=1):
            model = str(attempt.get("model") or self.model or "").strip()
            api_key = str(attempt.get("api_key") or self.api_key or "").strip()
            base_url = str(attempt.get("base_url") or self.base_url or "").strip().rstrip("/")
            timeout = int(attempt.get("timeout") or self.timeout)
            if not (model and api_key and base_url):
                logger.warning("模型恢复链跳过未配置尝试: %s", attempt.get("label") or attempt_index)
                continue
            if callable(on_attempt):
                try:
                    on_attempt(attempt_index, attempt)
                except Exception:
                    logger.warning("模型恢复链回调执行失败", exc_info=True)
            for retry_index in range(retries + 1):
                try:
                    return self._request_json(
                        attempt.get("system_prompt") or "",
                        attempt.get("user_prompt") or "",
                        model=model,
                        api_key=api_key,
                        base_url=base_url,
                        timeout=timeout,
                    )
                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "模型恢复链失败 step=%s retry=%s error=%s",
                        attempt.get("label") or attempt_index,
                        retry_index + 1,
                        exc,
                    )
                    if retry_index < retries:
                        time.sleep(0.8)
        if last_error:
            logger.error("模型恢复链全部失败: %s", last_error, exc_info=True)
        return None

    def _request_json(
        self,
        system: str,
        prompt: str,
        *,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
    ) -> Any:
        url = f"{(base_url or self.base_url).rstrip('/')}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key or self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model or self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout or self.timeout,
            proxies={"http": None, "https": None},
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return self._parse_json_content(content)

    @staticmethod
    def _parse_json_content(content: str) -> Any:
        text = str(content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text, flags=re.I).strip()
            text = re.sub(r"```$", "", text).strip()
        return parse_json_loose(text)
