from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

BEIJING_TZ = timezone(timedelta(hours=8))


def now_beijing_iso() -> str:
    return datetime.now(BEIJING_TZ).isoformat(timespec="milliseconds")


def clean_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\u200b", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def escape_text(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def safe_preview(value: Any, limit: int = 180) -> str:
    text = clean_text(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def split_keywords(text: str, max_keywords: int = 8) -> list[str]:
    raw = re.findall(r"[\u4e00-\u9fa5]{2,}|[A-Za-z][A-Za-z0-9\-]{2,}", text)
    stop_words = {
        "研究",
        "结果",
        "显示",
        "发现",
        "表明",
        "认为",
        "using",
        "with",
        "from",
        "this",
        "that",
        "study",
        "results",
    }
    seen: set[str] = set()
    keywords: list[str] = []
    for item in raw:
        key = item.lower()
        if key in stop_words or key in seen:
            continue
        seen.add(key)
        keywords.append(item)
        if len(keywords) >= max_keywords:
            break
    return keywords


def ensure_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def normalize_probability(value: Any, default: float = 0.5) -> float:
    try:
        numeric = float(value)
    except Exception:
        return default
    if numeric < 0:
        return 0.0
    if numeric > 1:
        if numeric <= 100:
            return round(numeric / 100, 4)
        return 1.0
    return round(numeric, 4)


def clip_text(value: Any, limit: int) -> str:
    text = clean_text(value)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def normalize_str_list(value: Any, *, limit: int | None = None) -> list[str]:
    items = []
    for item in ensure_list(value):
        text = clean_text(item)
        if not text:
            continue
        items.append(text)
        if limit and len(items) >= limit:
            break
    return items


def deep_escape(value: Any) -> Any:
    if isinstance(value, dict):
        return {escape_text(key): deep_escape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [deep_escape(item) for item in value]
    if isinstance(value, str):
        return escape_text(value)
    return value


def parse_json_loose(content: str) -> Any:
    text = str(content or "").strip()
    if not text:
        raise ValueError("empty json content")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.I).strip()
        text = re.sub(r"```$", "", text).strip()
    initial_error: Exception | None = None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        initial_error = exc

    candidates = _extract_json_candidates(text)
    last_error: Exception | None = initial_error
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            repaired = _repair_truncated_json(candidate)
            if repaired != candidate:
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError as repair_exc:
                    last_error = repair_exc
    if last_error:
        raise last_error
    raise ValueError("no json object found")


def _extract_json_candidates(text: str) -> list[str]:
    decoder = json.JSONDecoder()
    candidates: list[tuple[int, str]] = []
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            _, end = decoder.raw_decode(text[index:])
            candidate = text[index : index + end].strip()
            if candidate:
                candidates.append((len(candidate), candidate))
        except json.JSONDecodeError:
            balanced = _balanced_json_slice(text[index:])
            if balanced:
                candidates.append((len(balanced), balanced))
    candidates.sort(key=lambda item: item[0], reverse=True)
    seen: set[str] = set()
    result: list[str] = []
    for _, candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
    return result


def _balanced_json_slice(text: str) -> str:
    stack: list[str] = []
    in_string = False
    escape = False
    pairs = {"{": "}", "[": "]"}
    for index, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in pairs:
            stack.append(pairs[char])
        elif stack and char == stack[-1]:
            stack.pop()
            if not stack:
                return text[: index + 1]
    return text if stack else ""


def _repair_truncated_json(candidate: str) -> str:
    text = candidate.strip()
    stack: list[str] = []
    in_string = False
    escape = False
    pairs = {"{": "}", "[": "]"}
    for char in text:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in pairs:
            stack.append(pairs[char])
        elif stack and char == stack[-1]:
            stack.pop()
    if in_string:
        text += '"'
    while stack:
        text += stack.pop()
    return text
