from app.pipeline.progress import ProgressWriter


class FakeTaskRepository:
    def __init__(self):
        self.updates = []

    def update(self, task_id, user_scope, updates):
        self.updates.append((task_id, user_scope, updates))
        return True


def test_progress_payload_does_not_emit_stage_rules():
    repo = FakeTaskRepository()
    progress = ProgressWriter(repo, "task-1", "user-1")

    assert all("stage_rules" not in step.get("payload", {}) for step in progress.steps_data)

    progress.complete("preprocess", "done", {"input_summary_text": "已读取 1 份输入材料。"})
    preprocess = progress.steps_data[0]
    assert preprocess["payload"]["input_summary_text"] == "已读取 1 份输入材料。"
    assert "stage_rules" not in preprocess["payload"]
