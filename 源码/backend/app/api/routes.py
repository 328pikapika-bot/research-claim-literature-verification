"""
API routes for claim consistency evaluation MVP.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import (
    CONSISTENCY_EVALUATION_MAX_UPLOAD_FILE_BYTES,
    CONSISTENCY_EVALUATION_MAX_PARSED_FILE_CONTENT_CHARS,
    CONSISTENCY_EVALUATION_MAX_UPLOAD_FILE_COUNT,
    FEEDBACK_RATE_LIMIT_PER_MINUTE,
    FEEDBACK_UPLOAD_DIR,
    is_valid_user_scope,
)
from app.core.task_manager import TaskManager
from app.pipeline.progress import STAGE_DEFINITIONS
from app.pipeline.state import PipelineInput, PipelineState
from app.pipeline.utils import clean_text, now_beijing_iso
from app.repositories.feedback_repository import FeedbackStorageError
from app.repositories.file_repository import content_hash
from app.repositories.schemas import ParsedFileRecord, TaskHistoryRecord
from app.services.file_upload_parser import (
    SensitiveContentError,
    UploadFileParseError,
    check_sensitive_content,
    parse_uploaded_file_content,
)

logger = logging.getLogger(__name__)

router = APIRouter()
_feedback_rate_lock = asyncio.Lock()
_feedback_rate_window: dict[str, list[float]] = {}
ALLOWED_PARSED_FILE_TYPES = {"pdf", "txt", "md"}


def _get_mongo_manager():
    from app.repositories.mongo_manager import get_mongo_manager

    return get_mongo_manager()


def _get_task_repo():
    from app.repositories.task_repository import MongoTaskHistoryRepository

    return MongoTaskHistoryRepository(_get_mongo_manager())


def _get_file_repo():
    from app.repositories.file_repository import MongoParsedFileRepository

    return MongoParsedFileRepository(_get_mongo_manager())


def _get_history_repo():
    from app.repositories.history_repository import MongoHistoryRepository

    return MongoHistoryRepository(_get_mongo_manager())


def _get_feedback_repo():
    from app.repositories.feedback_repository import FeedbackRepository

    return FeedbackRepository(_get_mongo_manager())


def _get_task_manager(request: Request) -> TaskManager:
    manager = getattr(request.app.state, "task_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Task manager unavailable")
    return manager


def _resolve_user_scope(request: Request) -> str:
    header_user = request.headers.get("X-User-Scope", "").strip()
    if header_user:
        return header_user
    query_user = request.query_params.get("user_scope", "").strip()
    if query_user:
        return query_user
    return ""


def _check_user_scope(user_scope: str) -> None:
    if not is_valid_user_scope(user_scope):
        raise HTTPException(status_code=401, detail="请先登录 NSTL 账号")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _is_image_upload(file: UploadFile) -> bool:
    return bool(file.content_type and file.content_type.startswith("image/"))


def _safe_upload_filename(name: str) -> str:
    stem = Path(name or "feedback-image").stem[:80] or "feedback-image"
    suffix = Path(name or "").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        suffix = ".png"
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._") or "feedback-image"
    return f"{uuid.uuid4().hex}_{safe_stem}{suffix}"


async def _save_feedback_file(file: UploadFile, feedback_id: str) -> dict[str, Any]:
    if not _is_image_upload(file):
        raise HTTPException(status_code=422, detail="仅支持上传图片文件")

    content = await file.read()
    max_file_size = 5 * 1024 * 1024
    if len(content) > max_file_size:
        raise HTTPException(status_code=422, detail="单个图片不能超过 5MB")

    feedback_dir = Path(FEEDBACK_UPLOAD_DIR) / feedback_id
    feedback_dir.mkdir(parents=True, exist_ok=True)
    stored_name = _safe_upload_filename(file.filename or "")
    target = feedback_dir / stored_name
    await asyncio.to_thread(target.write_bytes, content)

    return {
        "original_name": file.filename or "",
        "stored_name": stored_name,
        "content_type": file.content_type or "",
        "size": len(content),
        "path": str(target),
    }


async def _check_feedback_rate_limit(user_scope: str) -> None:
    now = datetime.now(timezone.utc).timestamp()
    window_start = now - 60
    async with _feedback_rate_lock:
        recent = [ts for ts in _feedback_rate_window.get(user_scope, []) if ts >= window_start]
        if len(recent) >= FEEDBACK_RATE_LIMIT_PER_MINUTE:
            _feedback_rate_window[user_scope] = recent
            raise HTTPException(status_code=429, detail="反馈提交过于频繁，请稍后再试")
        recent.append(now)
        _feedback_rate_window[user_scope] = recent


def _extract_user_input(body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    user_text = ""
    structured: dict[str, Any] = {}
    for item in body.get("input", []):
        for content in item.get("content", []):
            content_type = content.get("type")
            if content_type == "input_text":
                text_value = clean_text(content.get("text"))
                if text_value:
                    user_text = text_value
            elif content_type == "input_json" and isinstance(content.get("json"), dict):
                structured = content["json"]
    return user_text, structured


def _normalize_year_range(value: Any) -> list[int]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            start, end = sorted((int(value[0]), int(value[1])))
            return [start, end]
        except Exception:
            return []
    return []


def _normalize_uploaded_files(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    refs: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        file_id = str(item.get("file_id") or item.get("fileId") or "").strip()
        if not file_id:
            continue
        refs.append(
            {
                "file_id": file_id,
                "name": str(item.get("name") or "").strip(),
                "type": str(item.get("type") or "").strip().lower(),
                "size": int(item.get("size") or 0),
                "parsed_at": str(item.get("parsed_at") or item.get("parsedAt") or ""),
                "url": str(item.get("url") or ""),
            }
        )
    return refs


def _validate_parsed_file_payload(raw_file: dict[str, Any], user_scope: str, index: int) -> ParsedFileRecord:
    from app.repositories.file_repository import content_hash

    file_id = str(raw_file.get("file_id") or raw_file.get("fileId") or "").strip()
    if not file_id:
        raise HTTPException(status_code=422, detail=f"第 {index} 个文件缺少 fileId")

    name = str(raw_file.get("name") or "").strip() or file_id
    file_type = str(raw_file.get("type") or "").strip().lower().lstrip(".")
    if file_type == "markdown":
        file_type = "md"
    if file_type not in ALLOWED_PARSED_FILE_TYPES:
        raise HTTPException(status_code=422, detail=f"第 {index} 个文件类型不支持: {file_type}")

    content = clean_text(raw_file.get("content"))
    if not content:
        raise HTTPException(status_code=422, detail=f"第 {index} 个文件解析文本为空")

    original_content_size = len(content)
    truncated = False
    if len(content) > CONSISTENCY_EVALUATION_MAX_PARSED_FILE_CONTENT_CHARS:
        content = content[:CONSISTENCY_EVALUATION_MAX_PARSED_FILE_CONTENT_CHARS]
        truncated = True
    now = now_beijing_iso()
    return ParsedFileRecord(
        file_id=file_id,
        user_scope=user_scope,
        name=name,
        type=file_type,
        size=int(raw_file.get("size") or 0),
        parsed_at=str(raw_file.get("parsed_at") or raw_file.get("parsedAt") or now),
        content=content,
        url=str(raw_file.get("url") or f"/v1/parsed-files/{file_id}"),
        content_size=len(content),
        original_content_size=original_content_size,
        content_hash=content_hash(content),
        source=str(raw_file.get("source") or "client_parser"),
        truncated=truncated,
        created_at=now,
        updated_at=now,
        last_used_at=None,
    )


def _parsed_file_response(record: ParsedFileRecord, include_content: bool = False) -> dict[str, Any]:
    data = record.to_dict(include_content=include_content)
    return {
        "file_id": data["file_id"],
        "fileId": data["file_id"],
        "user_scope": data["user_scope"],
        "name": data["name"],
        "type": data["type"],
        "size": data["size"],
        "parsed_at": data["parsed_at"],
        "parsedAt": data["parsed_at"],
        "url": data.get("url"),
        "content": data.get("content") if include_content else None,
        "content_size": data.get("content_size", 0),
        "original_content_size": data.get("original_content_size", 0),
        "content_hash": data.get("content_hash", ""),
        "source": data.get("source", ""),
        "truncated": data.get("truncated", False),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "last_used_at": data.get("last_used_at"),
    }


def _create_initial_steps_data() -> list[dict[str, Any]]:
    return [
        {
            "step_no": index,
            "step_key": key,
            "title": title,
            "status": "pending",
            "summary": "",
            "sub_steps": [],
            "degradations": [],
        }
        for index, (key, title) in enumerate(STAGE_DEFINITIONS, start=1)
    ]


@router.get("/system/health")
async def health_check():
    mongo_ok = False
    try:
        mongo_ok = _get_mongo_manager().test_connection()
    except Exception:
        pass
    return {
        "status": "ok",
        "service": "claim-consistency-agent",
        "mongodb": "connected" if mongo_ok else "disconnected",
    }


@router.post("/api/service/nstl/web/user-feedback/submit")
@router.post("/v1/user-feedback/submit")
async def submit_user_feedback(
    request: Request,
    systemName: str = Form(default="claim-consistency-agent"),
    content: str = Form(default=""),
    contact: str = Form(default=""),
    pageUrl: str = Form(default=""),
    files: list[UploadFile] = File(default_factory=list),
):
    user_scope = _resolve_user_scope(request)
    _check_user_scope(user_scope)
    await _check_feedback_rate_limit(user_scope)

    description = content.strip()
    if not description:
        raise HTTPException(status_code=422, detail="请填写问题描述或建议")
    if len(description) > 300:
        raise HTTPException(status_code=422, detail="问题描述不能超过 300 字")
    contact_text = contact.strip()
    if contact_text and not re.match(r"^1\d{10}$|^[^\s@]+@[^\s@]+\.[^\s@]+$", contact_text):
        raise HTTPException(status_code=422, detail="请输入正确的手机号或邮箱")
    if len(files) > 10:
        raise HTTPException(status_code=422, detail="最多上传 10 张图片")

    feedback_id = f"fb_{uuid.uuid4().hex[:12]}"
    attachments = [await _save_feedback_file(file, feedback_id) for file in files]
    now = _now_utc_iso()
    record = {
        "feedback_id": feedback_id,
        "system_name": systemName.strip() or "claim-consistency-agent",
        "content": description,
        "contact": contact_text,
        "page_url": pageUrl.strip(),
        "user_scope": user_scope,
        "client_host": request.client.host if request.client else "",
        "user_agent": request.headers.get("user-agent", ""),
        "attachments": attachments,
        "status": "submitted",
        "created_at": now,
        "updated_at": now,
    }

    repo = _get_feedback_repo()
    try:
        await repo.create(record)
    except FeedbackStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"code": 200, "message": "提交成功", "data": {"feedback_id": feedback_id}}


@router.post("/v1/parsed-files/batch")
async def save_parsed_files_batch(request: Request):
    user_scope = _resolve_user_scope(request)
    _check_user_scope(user_scope)
    body = await request.json()
    raw_files = body.get("files")
    if not isinstance(raw_files, list):
        raise HTTPException(status_code=422, detail="files 必须为数组")
    if len(raw_files) > CONSISTENCY_EVALUATION_MAX_UPLOAD_FILE_COUNT:
        raise HTTPException(
            status_code=422,
            detail=f"单次最多保存 {CONSISTENCY_EVALUATION_MAX_UPLOAD_FILE_COUNT} 个文件",
        )
    records = [
        _validate_parsed_file_payload(raw_file, user_scope, index)
        for index, raw_file in enumerate(raw_files, start=1)
    ]
    file_repo = _get_file_repo()
    saved_count, errors, data = file_repo.batch_create(records)
    return {
        "success": not errors,
        "saved": saved_count,
        "total": len(records),
        "data": data,
        "errors": errors,
    }


@router.post("/v1/parsed-files")
async def save_parsed_file(request: Request):
    user_scope = _resolve_user_scope(request)
    _check_user_scope(user_scope)
    body = await request.json()
    raw_file = body.get("file") if isinstance(body.get("file"), dict) else body
    record = _validate_parsed_file_payload(raw_file, user_scope, 1)
    file_repo = _get_file_repo()
    saved_count, errors, data = file_repo.batch_create([record])
    return {
        "success": not errors,
        "saved": saved_count,
        "total": 1,
        "data": _parsed_file_response(record),
        "errors": errors,
    }


@router.get("/v1/parsed-files")
async def list_parsed_files(
    request: Request,
    include_content: bool = Query(default=False),
):
    user_scope = _resolve_user_scope(request)
    _check_user_scope(user_scope)
    file_repo = _get_file_repo()
    files = file_repo.list(user_scope, include_content=include_content)
    return {
        "success": True,
        "total": len(files),
        "data": [_parsed_file_response(record, include_content=include_content) for record in files],
    }


@router.get("/v1/parsed-files/{file_id}")
async def get_parsed_file(
    file_id: str,
    request: Request,
    include_content: bool = Query(default=True),
):
    user_scope = _resolve_user_scope(request)
    _check_user_scope(user_scope)
    file_repo = _get_file_repo()
    record = file_repo.get(file_id, user_scope, include_content=include_content)
    if not record:
        raise HTTPException(status_code=404, detail="解析文件不存在")
    return {"success": True, "data": _parsed_file_response(record, include_content=include_content)}


@router.delete("/v1/parsed-files/{file_id}")
async def delete_parsed_file(file_id: str, request: Request):
    user_scope = _resolve_user_scope(request)
    _check_user_scope(user_scope)
    file_repo = _get_file_repo()
    deleted = file_repo.delete(file_id, user_scope)
    if not deleted:
        raise HTTPException(status_code=404, detail="解析文件不存在")
    return {"success": True, "deleted_count": 1, "file_id": file_id}


@router.delete("/v1/parsed-files")
async def clear_parsed_files(request: Request):
    user_scope = _resolve_user_scope(request)
    _check_user_scope(user_scope)
    file_repo = _get_file_repo()
    deleted_count = file_repo.clear(user_scope)
    return {"success": True, "deleted_count": deleted_count}


@router.post("/v1/threads/{thread_id}/runs")
async def create_or_resume_run(thread_id: str, request: Request):
    user_scope = _resolve_user_scope(request)
    _check_user_scope(user_scope)
    task_manager = _get_task_manager(request)
    body = await request.json()

    if "resume" in body:
        run_id = str(body.get("resume", {}).get("run_id") or "").strip()
        if not run_id:
            raise HTTPException(status_code=422, detail="resume.run_id 不能为空")
        task = _get_task_repo().get(run_id, user_scope, include_steps=True)
        if not task:
            raise HTTPException(status_code=404, detail="Run not found")
        return {
            "id": run_id,
            "thread_id": thread_id,
            "status": task.status,
            "created_at": task.created_at,
        }

    allowed, msg = await task_manager.rate_limiter.check_and_acquire(user_scope)
    if not allowed:
        raise HTTPException(status_code=429, detail=msg)

    user_text, structured = _extract_user_input(body)
    uploaded_files = _normalize_uploaded_files(structured.get("uploaded_files"))
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    created_at = now_beijing_iso()
    research_type = str(structured.get("research_type") or "综合评估").strip() or "综合评估"
    record = TaskHistoryRecord(
        task_id=run_id,
        thread_id=thread_id,
        user_scope=user_scope,
        topic=user_text[:200],
        research_type=research_type,
        status="queued",
        created_at=created_at,
        last_updated_at=created_at,
        current_step=0,
        steps_data=_create_initial_steps_data(),
        input_digest={
            "subject_area": structured.get("subject_area", ""),
            "year_range": _normalize_year_range(structured.get("year_range")),
            "language_pref": structured.get("language_pref", "zh"),
            "uploaded_file_count": len(uploaded_files),
        },
    )

    task_repo = _get_task_repo()
    history_repo = _get_history_repo()
    try:
        task_repo.create(record)
        history_repo.append(
            thread_id,
            run_id,
            "run.created",
            {"run_id": run_id, "status": "queued", "topic": record.topic},
            user_scope,
        )
    except Exception as exc:
        await task_manager.rate_limiter.release(user_scope)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    pipeline_input = PipelineInput(
        task_id=run_id,
        thread_id=thread_id,
        user_scope=user_scope,
        user_input=user_text,
        uploaded_files=uploaded_files,
        subject_area=str(structured.get("subject_area") or "").strip(),
        year_range=_normalize_year_range(structured.get("year_range")),
        language_pref=str(structured.get("language_pref") or "zh").strip() or "zh",
        raw_payload=body,
    )
    await task_manager.start_pipeline(PipelineState(request=pipeline_input))
    return {
        "id": run_id,
        "thread_id": thread_id,
        "status": "queued",
        "created_at": created_at,
    }


@router.get("/v1/threads/{thread_id}/runs/{run_id}")
async def get_run(thread_id: str, run_id: str, request: Request):
    user_scope = _resolve_user_scope(request)
    _check_user_scope(user_scope)
    task_repo = _get_task_repo()
    task = task_repo.get(run_id, user_scope, include_steps=True)
    if not task:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "id": task.task_id,
        "thread_id": task.thread_id,
        "status": task.status,
        "created_at": task.created_at,
        "completed_at": task.completed_at,
        "current_step": task.current_step,
        "steps_data": task.steps_data,
        "error_message": task.error_message,
        "final_result": task.final_result,
    }


@router.post("/v1/threads/{thread_id}/runs/{run_id}/cancel")
async def cancel_run(thread_id: str, run_id: str, request: Request):
    user_scope = _resolve_user_scope(request)
    _check_user_scope(user_scope)
    task_manager = _get_task_manager(request)
    cancelled = await task_manager.cancel_task(run_id, user_scope)
    await task_manager.rate_limiter.release(user_scope)
    if not cancelled:
        _get_task_repo().update(run_id, user_scope, {"status": "cancelled", "error_message": "任务已取消"})
    return {"status": "cancelled", "run_id": run_id}


@router.get("/v1/tasks")
async def list_tasks(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    user_scope = _resolve_user_scope(request)
    _check_user_scope(user_scope)
    task_repo = _get_task_repo()
    records, total = task_repo.list(
        user_scope=user_scope,
        status=status,
        search=search,
        page=page,
        page_size=page_size,
    )
    tasks = [
        {
            "task_id": record.task_id,
            "thread_id": record.thread_id,
            "topic": record.topic,
            "research_type": record.research_type,
            "status": record.status,
            "created_at": record.created_at,
            "completed_at": record.completed_at,
            "duration_seconds": record.duration_seconds,
            "current_step": record.current_step,
            "input_digest": record.input_digest,
            "error_category": record.error_category,
        }
        for record in records
    ]
    return {
        "success": True,
        "data": tasks,
        "total": total,
        "page": page,
        "page_size": page_size,
        "source": "mongodb",
    }


@router.get("/v1/tasks/{task_id}")
async def get_task(
    task_id: str,
    request: Request,
    include_steps: bool = Query(True),
):
    user_scope = _resolve_user_scope(request)
    _check_user_scope(user_scope)
    task_repo = _get_task_repo()
    task = task_repo.get(task_id, user_scope, include_steps=include_steps)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "data": task.to_dict(include_steps=include_steps), "source": "mongodb"}


@router.get("/v1/tasks/{task_id}/stream")
async def stream_task(
    task_id: str,
    request: Request,
):
    user_scope = _resolve_user_scope(request)
    _check_user_scope(user_scope)
    task_repo = _get_task_repo()
    initial = task_repo.get(task_id, user_scope, include_steps=True)
    if not initial:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator():
        last_snapshot = ""
        while True:
            if await request.is_disconnected():
                break
            task = task_repo.get(task_id, user_scope, include_steps=True)
            if not task:
                yield "event: error\ndata: {\"message\": \"Task not found\"}\n\n"
                break
            payload = {"success": True, "data": task.to_dict(include_steps=True), "source": "mongodb"}
            serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            if serialized != last_snapshot:
                last_snapshot = serialized
                yield f"event: task\ndata: {serialized}\n\n"
            if str(task.status).lower() in {"completed", "failed", "cancelled"}:
                yield "event: done\ndata: {\"done\": true}\n\n"
                break
            await asyncio.sleep(1.0)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/v1/tasks")
async def create_task(request: Request):
    user_scope = _resolve_user_scope(request)
    _check_user_scope(user_scope)
    body = await request.json()
    now = now_beijing_iso()
    record = TaskHistoryRecord(
        task_id=body["task_id"],
        thread_id=body.get("thread_id", ""),
        user_scope=user_scope,
        topic=body.get("topic", ""),
        research_type=body.get("research_type", ""),
        status=body.get("status", "completed"),
        created_at=body.get("created_at", now),
        last_updated_at=now,
        completed_at=body.get("completed_at"),
        duration_seconds=body.get("duration_seconds"),
        current_step=body.get("current_step", 0),
        steps_data=body.get("steps_data"),
        result=body.get("result"),
        final_result=body.get("final_result"),
        input_digest=body.get("input_digest"),
        error_category=body.get("error_category"),
    )
    _get_task_repo().create(record)
    return {"success": True, "task_id": record.task_id}


@router.put("/v1/tasks/{task_id}")
async def update_task(task_id: str, request: Request):
    user_scope = _resolve_user_scope(request)
    _check_user_scope(user_scope)
    body = await request.json()
    updates = dict(body)
    updates.pop("task_id", None)
    ok = _get_task_repo().update(task_id, user_scope, updates)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "task_id": task_id}


@router.delete("/v1/tasks/{task_id}")
async def delete_task(task_id: str, request: Request):
    user_scope = _resolve_user_scope(request)
    _check_user_scope(user_scope)
    deleted = _get_task_repo().delete(task_id, user_scope)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "message": "Task deleted"}


@router.post("/v1/files/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    user_scope = _resolve_user_scope(request)
    _check_user_scope(user_scope)
    content = await file.read()
    if len(content) > CONSISTENCY_EVALUATION_MAX_UPLOAD_FILE_BYTES:
        raise HTTPException(status_code=413, detail="文件过大，单个文件最大支持 50MB。")
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    file_type = "md" if ext == "markdown" else ext
    if file_type not in ALLOWED_PARSED_FILE_TYPES:
        raise HTTPException(status_code=422, detail="格式不支持，仅支持 PDF、TXT、Markdown 文件。")
    try:
        parsed = parse_uploaded_file_content(content, file_type, file.filename or "unknown")
        check_sensitive_content(parsed.content, file.filename or "unknown")
    except SensitiveContentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UploadFileParseError as exc:
        status_code = 503 if exc.code in {"sensitive_service_unavailable", "pdf_parser_unavailable"} else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    file_id = f"file_{uuid.uuid4().hex[:12]}"
    now = now_beijing_iso()
    record = ParsedFileRecord(
        file_id=file_id,
        user_scope=user_scope,
        name=file.filename or "unknown",
        type=file_type,
        size=len(content),
        parsed_at=now,
        content=parsed.content,
        url=f"/v1/parsed-files/{file_id}",
        content_size=len(parsed.content),
        original_content_size=parsed.original_content_size,
        content_hash=content_hash(parsed.content),
        source="server_upload",
        truncated=parsed.truncated,
        created_at=now,
        updated_at=now,
    )
    _get_file_repo().create(record)
    return {
        "id": file_id,
        "fileId": file_id,
        "url": f"/v1/parsed-files/{file_id}",
        "name": file.filename,
        "size": len(content),
        "type": file_type,
        "content_size": len(parsed.content),
        "original_content_size": parsed.original_content_size,
        "truncated": parsed.truncated,
        "parsedAt": now,
    }


@router.get("/system/limits")
async def get_rate_limits(request: Request):
    task_manager = _get_task_manager(request)
    return task_manager.rate_limiter.get_stats()
