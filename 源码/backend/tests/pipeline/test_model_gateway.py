from app.pipeline.model_gateway import ModelGateway
from app.pipeline.utils import parse_json_loose


def test_model_gateway_recovery_uses_next_attempt_after_failure(monkeypatch):
    gateway = ModelGateway(api_key="k", base_url="https://example.com", model="m", timeout=1)
    calls = {"count": 0}

    def fake_request_json(system, prompt, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TimeoutError("timeout")
        return {"ok": True, "model": kwargs.get("model")}

    monkeypatch.setattr(gateway, "_request_json", fake_request_json)
    result = gateway.chat_json_with_recovery(
        [
            {"label": "a", "system_prompt": "s", "user_prompt": "u", "model": "m1", "api_key": "k", "base_url": "https://x", "timeout": 1},
            {"label": "b", "system_prompt": "s", "user_prompt": "u", "model": "m2", "api_key": "k", "base_url": "https://x", "timeout": 1},
        ],
        retries=0,
    )
    assert result == {"ok": True, "model": "m2"}


def test_parse_json_loose_reads_markdown_wrapped_json():
    assert parse_json_loose('```json\n{"ok": true}\n```') == {"ok": True}


def test_parse_json_loose_selects_json_from_explanatory_text():
    assert parse_json_loose('说明文字\n{"claims": [{"id": "c1"}]}\n结束') == {
        "claims": [{"id": "c1"}]
    }


def test_parse_json_loose_can_repair_simple_truncated_object():
    assert parse_json_loose('{"claims": [{"id": "c1"}]') == {"claims": [{"id": "c1"}]}
