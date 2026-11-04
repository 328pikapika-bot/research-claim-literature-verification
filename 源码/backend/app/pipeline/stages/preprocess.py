from __future__ import annotations

import logging
from typing import Any

from app.core.config import CONSISTENCY_EVALUATION_MAX_PARSED_FILE_CONTENT_CHARS
from app.pipeline.progress import ProgressWriter
from app.pipeline.state import PipelineState
from app.pipeline.utils import clean_text, safe_preview

logger = logging.getLogger(__name__)


def _file_id(ref: dict[str, Any]) -> str:
    return str(ref.get("file_id") or ref.get("fileId") or ref.get("id") or "").strip()


def run_preprocess(
    state: PipelineState,
    file_repo: Any,
    progress: ProgressWriter | None = None,
) -> PipelineState:
    request = state.request
    documents: list[dict[str, Any]] = []

    user_text = clean_text(request.user_input)
    if user_text:
        documents.append(
            {
                "document_id": "user_input",
                "name": "用户输入",
                "type": "text",
                "source": "user_input",
                "content": user_text,
                "content_size": len(user_text),
                "truncated": False,
            }
        )

    resolved_file_ids: list[str] = []
    missing_files: list[str] = []
    truncated_files = 0
    for ref in request.uploaded_files:
        fid = _file_id(ref)
        if not fid:
            continue
        try:
            record = file_repo.get(fid, request.user_scope, include_content=True)
        except Exception as exc:
            logger.warning("读取解析文件失败 file_id=%s: %s", fid, exc)
            state.add_degradation("preprocess", "读取解析文件失败", f"{fid}: {exc}")
            missing_files.append(fid)
            continue
        if not record:
            missing_files.append(fid)
            state.add_degradation("preprocess", "解析文件不存在", fid)
            continue
        content = clean_text(record.content)
        original_size = len(content)
        truncated = bool(record.truncated)
        if len(content) > CONSISTENCY_EVALUATION_MAX_PARSED_FILE_CONTENT_CHARS:
            content = content[:CONSISTENCY_EVALUATION_MAX_PARSED_FILE_CONTENT_CHARS]
            truncated = True
        if truncated:
            truncated_files += 1
        resolved_file_ids.append(fid)
        documents.append(
            {
                "document_id": fid,
                "file_id": fid,
                "name": record.name,
                "type": record.type,
                "source": record.source or "client_parser",
                "content": content,
                "content_size": len(content),
                "original_content_size": record.original_content_size or original_size,
                "content_hash": record.content_hash,
                "truncated": truncated,
            }
        )
        if progress:
            progress.heartbeat(
                "preprocess",
                summary=f"已整理 {len(documents)} 份输入文档",
                payload_patch={"resolved_file_count": len(resolved_file_ids)},
            )

    if resolved_file_ids:
        try:
            file_repo.touch_used(resolved_file_ids, request.user_scope)
        except Exception as exc:
            logger.warning("更新解析文件使用时间失败: %s", exc)

    total_chars = sum(len(item.get("content", "")) for item in documents)
    if total_chars <= 0:
        raise ValueError("输入文本和上传文件解析内容均为空，无法启动一致性评估")

    clean_input = "\n\n".join(item.get("content", "") for item in documents if item.get("content"))
    state.clean_input = clean_input
    state.input_documents = documents
    state.chunk_digest = [
        {
            "document_id": item.get("document_id"),
            "name": item.get("name"),
            "chars": len(item.get("content", "")),
            "truncated": bool(item.get("truncated")),
            "preview": safe_preview(item.get("content"), 180),
        }
        for item in documents[:12]
    ]
    state.input_digest = {
        "document_count": len(documents),
        "input_text_chars": len(user_text),
        "total_chars": total_chars,
        "uploaded_file_count": len(request.uploaded_files),
        "resolved_file_count": len(resolved_file_ids),
        "missing_file_ids": missing_files,
        "truncated_file_count": truncated_files,
        "subject_area": request.subject_area,
        "year_range": request.year_range,
        "language_pref": request.language_pref,
        "file_missing": bool(missing_files),
        "has_truncation": truncated_files > 0,
        "previews": [
            {
                "document_id": item.get("document_id"),
                "name": item.get("name"),
                "preview": safe_preview(item.get("content"), 120),
            }
            for item in documents[:5]
        ],
    }
    input_summary_text = _build_input_summary_text(state.input_digest)
    state.input_digest["summary_text"] = input_summary_text
    state.set_stage_result(
        "preprocess",
        {
            "clean_input": clean_input[:4000],
            "chunk_digest": state.chunk_digest,
            "input_digest": state.input_digest,
            "input_summary_text": input_summary_text,
        },
    )
    return state


def _build_input_summary_text(input_digest: dict[str, Any]) -> str:
    document_count = int(input_digest.get("document_count") or 0)
    total_chars = int(input_digest.get("total_chars") or 0)
    uploaded_count = int(input_digest.get("uploaded_file_count") or 0)
    resolved_count = int(input_digest.get("resolved_file_count") or 0)
    missing_count = len(input_digest.get("missing_file_ids") or [])
    truncated_count = int(input_digest.get("truncated_file_count") or 0)

    parts = [
        f"已读取 {document_count} 份输入材料，共 {total_chars:,} 字符",
    ]
    if uploaded_count:
        file_text = f"上传文件 {uploaded_count} 份，成功解析 {resolved_count} 份"
        if missing_count:
            file_text += f"，{missing_count} 份未找到或解析失败"
        if truncated_count:
            file_text += f"，{truncated_count} 份因长度较长已截断"
        parts.append(file_text)

    constraints: list[str] = []
    if input_digest.get("subject_area"):
        constraints.append(f"学科方向：{input_digest['subject_area']}")
    year_range = input_digest.get("year_range")
    if isinstance(year_range, list) and len(year_range) >= 2:
        constraints.append(f"年份范围：{year_range[0]}-{year_range[1]}")
    if input_digest.get("language_pref"):
        constraints.append(f"语言偏好：{input_digest['language_pref']}")
    if constraints:
        parts.append("；".join(constraints))
    return "；".join(parts) + "。"
