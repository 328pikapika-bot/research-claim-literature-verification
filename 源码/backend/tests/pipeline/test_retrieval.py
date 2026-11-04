from app.pipeline.stages.retrieval import (
    _build_evidence_pack_preview,
    _build_literature_preview,
    _limit_references_by_claim,
    _normalize_evidence_pack,
    _validate_real_references,
)


def test_validate_real_references_filters_missing_title_and_duplicates():
    items = [
        {"reference_id": "a", "title": "Paper 1", "paper_id": "p1", "year": 2023},
        {"reference_id": "b", "title": "", "paper_id": "p2", "year": 2023},
        {"reference_id": "c", "title": "Paper 1", "paper_id": "p1", "year": 2023},
    ]
    validated = _validate_real_references(items)
    assert len(validated) == 1
    assert validated[0]["reference_id"] == "a"


def test_normalize_evidence_pack_drops_unknown_reference_ids():
    claim = {"claim_id": "claim_1"}
    references = [{"reference_id": "tmp_claim_1_1", "title": "Paper A", "year": 2023, "abstract": "supportive abstract"}]
    raw_pack = [
        {"reference_id": "tmp_claim_1_1", "relation": "support", "evidence_level": "abstract", "evidence_strength": "moderate", "snippet": "A", "why_relevant": "B"},
        {"reference_id": "fake", "relation": "support", "evidence_level": "abstract", "evidence_strength": "moderate", "snippet": "X", "why_relevant": "Y"},
    ]
    normalized = _normalize_evidence_pack(claim, references, raw_pack)
    assert len(normalized) == 1
    assert normalized[0]["reference_id"] == "tmp_claim_1_1"


def test_limit_references_by_claim_caps_total_and_keeps_claim_coverage():
    claims = [{"claim_id": "claim_1", "text": "A"}, {"claim_id": "claim_2", "text": "B"}]
    results = {
        "claim_1": [_paper("c1", index, 100 - index) for index in range(15)],
        "claim_2": [_paper("c2", index, 80 - index) for index in range(15)],
    }

    limited = _limit_references_by_claim(results, claims, 20)
    assert sum(len(items) for items in limited.values()) == 20
    assert limited["claim_1"]
    assert limited["claim_2"]

    preview = _build_literature_preview(limited, claims)
    assert len(preview) == 20
    assert preview[0]["claim_label"] == "主张一"


def test_evidence_pack_preview_uses_human_claim_label():
    claims = [{"claim_id": "claim_1", "text": "A improves B"}]
    preview = _build_evidence_pack_preview(
        {
            "claim_1": [
                {"relation": "support", "evidence_level": "abstract"},
                {"relation": "conflict", "evidence_level": "title"},
            ]
        },
        claims,
    )

    assert preview[0]["claim_label"] == "主张一"
    assert preview[0]["summary_text"].startswith("主张一：已整理 2 条证据线索")


def _paper(prefix: str, index: int, score: float) -> dict:
    return {
        "reference_id": f"tmp_{prefix}_{index}",
        "paper_id": f"{prefix}_{index}",
        "title": f"Paper {prefix}-{index}",
        "year": 2024,
        "final_score": score,
        "abstract": "abstract",
    }
