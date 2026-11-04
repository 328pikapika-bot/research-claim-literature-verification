from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router


@dataclass
class FakeTask:
    task_id: str = "task_1"
    thread_id: str = "thread_1"
    user_scope: str = "nstl_user_demo"
    topic: str = "topic"
    research_type: str = "type"
    status: str = "completed"
    created_at: str = "2026-06-04T00:00:00+08:00"
    last_updated_at: str = "2026-06-04T00:00:01+08:00"
    completed_at: str = "2026-06-04T00:00:02+08:00"
    current_step: int = 5
    steps_data: list | None = None
    final_result: dict | None = None
    result: dict | None = None
    input_digest: dict | None = None
    error_message: str | None = None
    duration_seconds: int | None = None
    error_category: str | None = None

    def to_dict(self, include_steps: bool = True):
        return {
            "task_id": self.task_id,
            "thread_id": self.thread_id,
            "user_scope": self.user_scope,
            "topic": self.topic,
            "research_type": self.research_type,
            "status": self.status,
            "created_at": self.created_at,
            "last_updated_at": self.last_updated_at,
            "completed_at": self.completed_at,
            "current_step": self.current_step,
            "steps_data": self.steps_data if include_steps else None,
            "final_result": self.final_result,
            "result": self.result,
            "input_digest": self.input_digest,
        }


class FakeTaskRepo:
    def get(self, task_id, user_scope, include_steps=False):
        return FakeTask(steps_data=[{"step_key": "output", "status": "completed"}], final_result={"summary": {"overall_score": 88}})


def test_task_stream_emits_snapshot(monkeypatch):
    from app.api import routes

    monkeypatch.setattr(routes, "_get_task_repo", lambda: FakeTaskRepo())
    monkeypatch.setattr(routes, "_check_user_scope", lambda scope: None)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    with client.stream("GET", "/v1/tasks/task_1/stream?user_scope=nstl_user_demo") as response:
        chunks = list(response.iter_text())
    joined = "".join(chunks)
    assert "event: task" in joined
    assert "\"overall_score\": 88" in joined
    assert "event: done" in joined
