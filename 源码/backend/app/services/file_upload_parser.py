from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from app.core.config import (
    CONSISTENCY_EVALUATION_MAX_PARSED_FILE_CONTENT_CHARS,
    SENSITIVE_TEXT_API_TIMEOUT,
    SENSITIVE_TEXT_API_URL,
)
from app.pipeline.utils import clean_text

logger = logging.getLogger(__name__)


class UploadFileParseError(ValueError):
    def __init__(self, message: str, *, code: str = "file_parse_failed") -> None:
        super().__init__(message)
        self.code = code


class SensitiveContentError(ValueError):
    def __init__(self, message: str = "敏感词命中，文件包含不适合上传的内容，请修改后重新上传。") -> None:
        super().__init__(message)
        self.code = "sensitive_content_detected"


@dataclass(frozen=True)
class ParsedUploadContent:
    content: str
    original_content_size: int
    truncated: bool = False


def parse_uploaded_file_content(content: bytes, file_type: str, filename: str) -> ParsedUploadContent:
    normalized_type = _normalize_type(file_type)
    if normalized_type == "pdf":
        text = _parse_pdf_content(content, filename)
    elif normalized_type in {"txt", "md"}:
        text = _decode_text_content(content)
    else:
        raise UploadFileParseError("格式不支持，仅支持 PDF、TXT、Markdown 文件。", code="unsupported_file_type")

    text = clean_text(text)
    if not text:
        if normalized_type == "pdf":
            raise UploadFileParseError(
                "扫描件无文本，未提取到可用文字。请先进行 OCR 识别后再上传。",
                code="pdf_no_extractable_text",
            )
        raise UploadFileParseError("文件内容为空，无法参与一致性评估。", code="empty_file_content")

    original_size = len(text)
    truncated = False
    if len(text) > CONSISTENCY_EVALUATION_MAX_PARSED_FILE_CONTENT_CHARS:
        text = text[:CONSISTENCY_EVALUATION_MAX_PARSED_FILE_CONTENT_CHARS]
        truncated = True
    return ParsedUploadContent(content=text, original_content_size=original_size, truncated=truncated)


def check_sensitive_content(text: str, filename: str) -> None:
    if not SENSITIVE_TEXT_API_URL:
        return
    payload = {"contents": [{"id": filename or "uploaded-file", "text": text}]}
    try:
        response = requests.post(
            SENSITIVE_TEXT_API_URL,
            json=payload,
            timeout=SENSITIVE_TEXT_API_TIMEOUT,
            proxies={"http": None, "https": None},
        )
        response.raise_for_status()
        result = response.json()
    except Exception as exc:
        logger.warning("文件安全校验服务不可用 filename=%s error=%s", filename, exc, exc_info=True)
        raise UploadFileParseError(
            "安全校验服务不可用，请稍后重试。",
            code="sensitive_service_unavailable",
        ) from exc

    if _has_sensitive_hit(result):
        logger.info("上传文件命中敏感词 filename=%s", filename)
        raise SensitiveContentError()


def _parse_pdf_content(content: bytes, filename: str) -> str:
    try:
        import fitz  # type: ignore
    except Exception as exc:
        logger.warning("PyMuPDF 未安装，无法解析 PDF: %s", exc)
        raise UploadFileParseError(
            "PDF 解析服务不可用，请稍后重试。",
            code="pdf_parser_unavailable",
        ) from exc

    try:
        with fitz.open(stream=content, filetype="pdf") as doc:
            if doc.needs_pass:
                raise UploadFileParseError(
                    "PDF 加密，暂时无法解析。请去除密码后重新上传。",
                    code="pdf_encrypted",
                )
            return "\n\n".join(page.get_text("text") for page in doc)
    except UploadFileParseError:
        raise
    except Exception as exc:
        logger.warning("PDF 文件无法解析 filename=%s error=%s", filename, exc, exc_info=True)
        raise UploadFileParseError(
            "PDF 损坏或无法解析，请确认文件没有损坏、未加密后重新上传。",
            code="pdf_parse_failed",
        ) from exc


def _decode_text_content(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _normalize_type(file_type: str) -> str:
    normalized = Path(f"x.{file_type}").suffix.lower().lstrip(".")
    if normalized == "markdown":
        return "md"
    return normalized


def _has_sensitive_hit(result: Any) -> bool:
    if isinstance(result, dict):
        if result.get("hasSensitive") is True or result.get("has_sensitive") is True:
            return True
        hits = result.get("sensitiveHits") or result.get("sensitive_hits") or result.get("hits")
        if isinstance(hits, list) and hits:
            return True
        data = result.get("data")
        if data is not result and _has_sensitive_hit(data):
            return True
        contents = result.get("contents")
        if isinstance(contents, list) and any(_has_sensitive_hit(item) for item in contents):
            return True
    if isinstance(result, list):
        return any(_has_sensitive_hit(item) for item in result)
    return False
