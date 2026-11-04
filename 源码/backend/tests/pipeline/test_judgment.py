from app.pipeline.stages.judgment import _apply_judgment_guardrails


def test_judgment_downgrades_abstract_only_support():
    judgment = {
        "claim_id": "claim_1",
        "status": "已被证实",
        "explanation": "e",
        "reason": "e",
        "degraded": False,
    }
    evidence = [
        {"relation": "support", "evidence_level": "abstract", "evidence_id": "ev1"},
        {"relation": "support", "evidence_level": "abstract", "evidence_id": "ev2"},
    ]
    adjusted, flags = _apply_judgment_guardrails(judgment, evidence, [])
    assert adjusted["status"] == "部分被证实"
    assert flags


def test_judgment_downgrades_without_support():
    judgment = {
        "claim_id": "claim_1",
        "status": "部分被证实",
        "explanation": "e",
        "reason": "e",
        "degraded": False,
    }
    adjusted, flags = _apply_judgment_guardrails(judgment, [], [])
    assert adjusted["status"] == "缺乏文献支持"
    assert flags
