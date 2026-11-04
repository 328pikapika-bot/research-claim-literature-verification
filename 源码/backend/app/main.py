"""
一致性评估智能体 FastAPI 后端入口。

启动方式:
    cd backend
    python -m uvicorn app.main:app --host 0.0.0.0 --port 17608 --reload
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import BACKEND_PORT, FRONTEND_BASE_PATH, get_allowed_origins, setup_logging

setup_logging()
logger = logging.getLogger(__name__)


# ============================================================================
# MongoDB 初始化 & 后台任务
# ============================================================================

async def _stale_task_cleanup_loop():
    """每 10 分钟扫描一次，将超过 6 小时未完成的 running 任务标记为 failed。"""
    while True:
        await asyncio.sleep(600)
        try:
            from app.repositories.mongo_manager import get_mongo_manager
            from app.repositories.task_repository import MongoTaskHistoryRepository
            mongo = get_mongo_manager()
            repo = MongoTaskHistoryRepository(mongo)
            marked = repo.mark_stale_tasks_failed(timeout_hours=6)
            if marked > 0:
                logger.info(f"[StaleCleanup] 标记了 {marked} 个超时任务为 failed")
        except Exception as e:
            logger.warning(f"[StaleCleanup] 扫描出错: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化 MongoDB
    try:
        from app.core.task_manager import TaskManager
        from app.repositories.file_repository import MongoParsedFileRepository
        from app.repositories.mongo_manager import get_mongo_manager
        from app.repositories.task_repository import MongoTaskHistoryRepository
        mongo = get_mongo_manager()
        if mongo.test_connection():
            logger.info("[Startup] MongoDB 连接成功")
        else:
            logger.warning("[Startup] MongoDB 连接失败")
        app.state.task_manager = TaskManager(
            MongoTaskHistoryRepository(mongo),
            MongoParsedFileRepository(mongo),
        )
    except Exception as e:
        logger.warning(f"[Startup] MongoDB 初始化失败: {e}")

    # 启动过期任务清理后台任务
    cleanup_task = asyncio.create_task(_stale_task_cleanup_loop())

    yield

    # 关闭时清理
    cleanup_task.cancel()
    task_manager = getattr(app.state, "task_manager", None)
    if task_manager is not None:
        await task_manager.shutdown()
    try:
        from app.repositories.mongo_manager import get_mongo_manager
        mongo = get_mongo_manager()
        mongo.shutdown_executors()
        mongo.close()
        logger.info("[Shutdown] MongoDB 连接已关闭")
    except Exception as exc:
        logger.warning("[Shutdown] MongoDB 连接清理失败: %s", exc, exc_info=True)


app = FastAPI(
    title="一致性评估智能体",
    description="Claim Consistency Agent - 科技文献一致性评估与引文验证系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# 静态文件服务 - 优先 frontend/web/dist，回退 web_demo
_frontend_dist_path = (Path(__file__).resolve().parent.parent.parent / "frontend" / "web" / "dist").resolve()
_web_demo_path = (Path(__file__).resolve().parent.parent.parent / "frontend" / "web_demo").resolve()
_static_frontend_path = _frontend_dist_path if _frontend_dist_path.exists() else _web_demo_path
if _static_frontend_path.exists():
    _frontend_mount_path = FRONTEND_BASE_PATH.rstrip("/")

    @app.get(_frontend_mount_path, include_in_schema=False)
    async def frontend_home_redirect():
        return RedirectResponse(url=FRONTEND_BASE_PATH, status_code=308)

    app.mount(
        _frontend_mount_path,
        StaticFiles(directory=str(_static_frontend_path), html=True),
        name="frontend_prefixed",
    )
    app.mount("/", StaticFiles(directory=str(_static_frontend_path), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=BACKEND_PORT, reload=True)
