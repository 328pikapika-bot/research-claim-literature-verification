from app.pipeline.stages.output import _build_stable_references, _calculate_overall_score, _sanitize_evidence
from app.pipeline.state import PipelineInput, PipelineState


def test_output_score_respects_abstract_ceiling():
    claims = [
        {"status": "已被证实", "evidence_level": "abstract"},
        {"status": "已被证实", "evidence_level": "abstract"},
    ]
    score = _calculate_overall_score(claims, [])
    assert score == 70


def test_sanitize_evidence_remaps_and_escapes():
    evidence = [
        {
            "evidence_id": "ev1",
            "reference_id": "tmp_1",
            "relation": "support",
            "title": "<b>Paper</b>",
            "year": 2024,
            "snippet": "<script>alert(1)</script>",
            "score": 1,
            "evidence_strength": "strong",
            "evidence_level": "fulltext",
            "why_relevant": "<i>x</i>",
        }
    ]
    sanitized = _sanitize_evidence(evidence, {"tmp_1": "R1"})
    assert sanitized[0]["reference_id"] == "R1"
    assert "&lt;script&gt;" in sanitized[0]["snippet"]


def test_build_stable_references_caps_to_twenty():
    state = PipelineState(
        request=PipelineInput(task_id="task-1", thread_id="thread-1", user_scope="user-1")
    )
    state.retrieval_results = {
        "claim_1": [
            {
                "reference_id": f"tmp_{index}",
                "paper_id": f"paper_{index}",
                "title": f"Paper {index}",
                "authors": [],
                "year": 2024,
            }
            for index in range(25)
        ]
    }

    references, remap = _build_stable_references(state)
    assert len(references) == 20
    assert remap["tmp_0"] == "R1"
    assert "tmp_24" not in remap
