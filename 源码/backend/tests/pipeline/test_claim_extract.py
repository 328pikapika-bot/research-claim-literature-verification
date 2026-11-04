from app.pipeline.stages.claim_extract import _merge_and_trim_claims, _normalize_query_plan


def test_query_plan_fills_defaults():
    plan = _normalize_query_plan({}, "维生素D可降低跌倒风险", ["维生素D", "跌倒"])
    assert plan["query_text"] == "维生素D可降低跌倒风险"
    assert plan["must_terms"][:2] == ["维生素D", "跌倒"]
    assert "reason" in plan


def test_merge_and_trim_claims_dedupes_by_text():
    claims = [
        {"claim_id": "a", "text": "A improves B", "priority": 3},
        {"claim_id": "b", "text": "A improves B", "priority": 1},
        {"claim_id": "c", "text": "C reduces D", "priority": 2},
    ]
    merged = _merge_and_trim_claims(claims)
    assert len(merged) == 2
    assert merged[0]["claim_id"] == "claim_1"
    assert merged[1]["claim_id"] == "claim_2"
