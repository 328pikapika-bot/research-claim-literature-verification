"""
一致性评估智能体 统一配置模块

所有环境变量读取集中在此模块。
加载优先级：.env 文件 -> 系统环境变量（后者覆盖前者）。

变量层级：
  平台级（无前缀）：所有智能体复用
  智能体级（CONSISTENCY_EVALUATION_ 前缀）：仅本智能体使用
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


# ==================== 日志初始化 ====================

def setup_logging() -> None:
    """配置标准日志系统，在 main.py 启动时调用一次。"""
    log_dir = Path(os.getenv("LOG_DIR", "./data/logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    if root.handlers:
        return

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = logging.FileHandler(log_dir / "app.log", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    error_handler = logging.FileHandler(log_dir / "error.log", encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(fmt)
    root.addHandler(error_handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


# 北京时区常量
BEIJING_TZ = timezone(timedelta(hours=8))


# ==================== 平台级运行时配置 ====================

BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "17608"))
LOG_DIR: str = os.getenv("LOG_DIR", "./data/logs")
UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./data/uploads")
FEEDBACK_UPLOAD_DIR: str = os.getenv("FEEDBACK_UPLOAD_DIR", "./data/feedback_uploads")
FEEDBACK_FALLBACK_DIR: str = os.getenv("FEEDBACK_FALLBACK_DIR", "./data/feedback")
FEEDBACK_RATE_LIMIT_PER_MINUTE: int = int(os.getenv("FEEDBACK_RATE_LIMIT_PER_MINUTE", "5"))
SENSITIVE_TEXT_API_URL: str = os.getenv("SENSITIVE_TEXT_API_URL", "").strip()
SENSITIVE_TEXT_API_TIMEOUT: int = int(os.getenv("SENSITIVE_TEXT_API_TIMEOUT", "15"))


def _normalize_url_path(path: str) -> str:
    normalized = (path or "/").strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if not normalized.endswith("/"):
        normalized = f"{normalized}/"
    return normalized


FRONTEND_BASE_PATH: str = _normalize_url_path(
    os.getenv("FRONTEND_BASE_PATH", "/ai/agent/claim_consistency/")
)

# CORS
ALLOWED_ORIGINS: str = os.getenv(
    "ALLOWED_ORIGINS",
    "https://www.nstl.gov.cn,http://127.0.0.1:18094,http://localhost:18094,https://www.nstl.gov.cn:18094",
)


def get_allowed_origins() -> list[str]:
    return [o.strip() for o in ALLOWED_ORIGINS.split(",") if o.strip()]


# ==================== 智能体级 LLM 配置 ====================

DEEPSEEK_API_KEY: str = os.getenv("CONSISTENCY_EVALUATION_DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = os.getenv(
    "CONSISTENCY_EVALUATION_DEEPSEEK_BASE_URL",
    "https://api.deepseek.com",
).rstrip("/")
DEEPSEEK_MODEL: str = os.getenv(
    "CONSISTENCY_EVALUATION_DEEPSEEK_MODEL", "deepseek-v4-flash"
)
DEEPSEEK_TIMEOUT: str = os.getenv("CONSISTENCY_EVALUATION_DEEPSEEK_TIMEOUT", "90")

MODEL_API_KEY: str = os.getenv(
    "CONSISTENCY_EVALUATION_MODEL_API_KEY",
    DEEPSEEK_API_KEY,
)
MODEL_BASE_URL: str = os.getenv(
    "CONSISTENCY_EVALUATION_MODEL_BASE_URL",
    DEEPSEEK_BASE_URL,
).rstrip("/")
MODEL_NAME: str = os.getenv(
    "CONSISTENCY_EVALUATION_MODEL_NAME",
    os.getenv("CONSISTENCY_EVALUATION_QWEN_MODEL", "qwen3.6-35b-a3b"),
)
MODEL_TIMEOUT: int = int(os.getenv("CONSISTENCY_EVALUATION_MODEL_TIMEOUT", DEEPSEEK_TIMEOUT))


# ==================== 用户隔离配置 ====================

ALLOW_DEFAULT_USER_SCOPE: bool = (
    os.getenv("ALLOW_DEFAULT_USER_SCOPE", "false").strip().lower() == "true"
)

_BLOCKED_SCOPES: set[str] = {"default", "unknown", "mock_user_id", ""}
_DEGRADED_SCOPE_PREFIXES: tuple[str, ...] = ("nstl_user_", "test_")


def is_valid_user_scope(scope: str | None) -> bool:
    """检查 user_scope 是否有效。

    正式 NSTL 登录链路只允许真实用户标识。
    ALLOW_DEFAULT_USER_SCOPE 仅兼容历史本地调试，但不会放行明显占位或 mock 值。
    """
    if not scope or not scope.strip():
        return False
    normalized = scope.strip().lower()
    if ALLOW_DEFAULT_USER_SCOPE:
        return True
    if normalized.startswith(_DEGRADED_SCOPE_PREFIXES):
        return True
    if normalized in _BLOCKED_SCOPES:
        return False
    if (
        normalized.startswith("mock_")
        or normalized.startswith("fake_")
        or normalized.startswith("local_")
    ):
        return False
    return True


# ==================== Mock 登录配置 ====================

MOCK_AUTH_ENABLED: bool = (
    os.getenv("CONSISTENCY_EVALUATION_MOCK_AUTH_ENABLED", "false").strip().lower() == "true"
)

_MOCK_USERS_RAW: str = os.getenv(
    "CONSISTENCY_EVALUATION_MOCK_USERS",
    "admin01:admin123,admin02:admin456",
)


def _parse_mock_users(raw: str) -> dict[str, dict[str, str]]:
    users: dict[str, dict[str, str]] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if ":" not in pair:
            continue
        username, password = pair.split(":", 1)
        users[username.strip()] = {
            "password": password.strip(),
            "user_id": f"mock_{username.strip()}",
            "username": username.strip(),
        }
    return users


MOCK_USERS: dict[str, dict[str, str]] = _parse_mock_users(_MOCK_USERS_RAW)


# ---- MongoDB ----
MONGO_HOST: str = os.getenv("MONGO_HOST", "127.0.0.1")
MONGO_PORT: int = int(os.getenv("MONGO_PORT", "27017"))
MONGO_DATABASE: str = os.getenv("MONGO_DATABASE", "ai_agent")
MONGO_USERNAME: str = os.getenv("MONGO_USERNAME", "")
MONGO_PASSWORD: str = os.getenv("MONGO_PASSWORD", "")
MONGO_AUTH_SOURCE: str = os.getenv("MONGO_AUTH_SOURCE", "admin")
MONGO_INSTANCE_ID: str = os.getenv("MONGO_INSTANCE_ID", "test_local")

# ---- MongoDB 集合 ----
TASK_COLLECTION: str = os.getenv(
    "CONSISTENCY_EVALUATION_TASK_COLLECTION", "consistency_evaluation_tasks"
)
EVENT_COLLECTION: str = os.getenv(
    "CONSISTENCY_EVALUATION_EVENT_COLLECTION", "consistency_evaluation_task_events"
)
FILE_COLLECTION: str = os.getenv(
    "CONSISTENCY_EVALUATION_FILE_COLLECTION", "consistency_evaluation_files"
)
HISTORY_COLLECTION: str = os.getenv(
    "CONSISTENCY_EVALUATION_HISTORY_COLLECTION", "consistency_evaluation_history"
)
FEEDBACK_COLLECTION: str = os.getenv(
    "CONSISTENCY_EVALUATION_FEEDBACK_COLLECTION", "consistency_evaluation_feedback"
)

# ---- NSTL 文献检索 ----
LITERATURE_SEARCH_API_URL: str = os.getenv("LITERATURE_SEARCH_API_URL", "")
LITERATURE_SEARCH_TIMEOUT: int = int(os.getenv("LITERATURE_SEARCH_TIMEOUT", "600"))


# ---- 一致性评估链路默认项 ----
CONSISTENCY_EVALUATION_MAX_UPLOAD_FILE_COUNT: int = int(
    os.getenv("CONSISTENCY_EVALUATION_MAX_UPLOAD_FILE_COUNT", "10")
)
CONSISTENCY_EVALUATION_MAX_UPLOAD_FILE_BYTES: int = int(
    os.getenv("CONSISTENCY_EVALUATION_MAX_UPLOAD_FILE_BYTES", str(50 * 1024 * 1024))
)
CONSISTENCY_EVALUATION_MAX_PARSED_FILE_CONTENT_CHARS: int = int(
    os.getenv("CONSISTENCY_EVALUATION_MAX_PARSED_FILE_CONTENT_CHARS", "300000")
)
CONSISTENCY_EVALUATION_MAX_CLAIMS: int = int(
    os.getenv("CONSISTENCY_EVALUATION_MAX_CLAIMS", "12")
)
CONSISTENCY_EVALUATION_RETRIEVAL_TOP_K_PER_CLAIM: int = int(
    os.getenv("CONSISTENCY_EVALUATION_RETRIEVAL_TOP_K_PER_CLAIM", "20")
)
CONSISTENCY_EVALUATION_RETRIEVAL_MAX_REFERENCES_TOTAL: int = int(
    os.getenv("CONSISTENCY_EVALUATION_RETRIEVAL_MAX_REFERENCES_TOTAL", "20")
)
CONSISTENCY_EVALUATION_RETRIEVAL_MAX_CONCURRENCY: int = int(
    os.getenv("CONSISTENCY_EVALUATION_RETRIEVAL_MAX_CONCURRENCY", "3")
)
