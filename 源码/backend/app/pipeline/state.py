from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PipelineInput:
    task_id: str
    thread_id: str
    user_scope: str
    user_input: str = ""
    uploaded_files: List[Dict[str, Any]] = field(default_factory=list)
    subject_area: str = ""
    year_range: Optional[List[int]] = None
    language_pref: str = "zh"
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineState:
    request: PipelineInput
    clean_input: str = ""
    input_documents: List[Dict[str, Any]] = field(default_factory=list)
    input_digest: Dict[str, Any] = field(default_factory=dict)
    chunk_digest: List[Dict[str, Any]] = field(default_factory=list)
    claims: List[Dict[str, Any]] = field(default_factory=list)
    query_plans: List[Dict[str, Any]] = field(default_factory=list)
    retrieval_results: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    retrieval_detail: Dict[str, Any] = field(default_factory=dict)
    evidence_by_claim: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    judgments: List[Dict[str, Any]] = field(default_factory=list)
    stage_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    citation_map: Dict[str, str] = field(default_factory=dict)
    overall_score: Optional[int] = None
    final_result: Dict[str, Any] = field(default_factory=dict)
    degradations: List[Dict[str, Any]] = field(default_factory=list)

    def add_degradation(self, stage: str, reason: str, detail: str = "") -> None:
        self.degradations.append({"stage": stage, "reason": reason, "detail": detail})

    def set_stage_result(self, stage: str, payload: Dict[str, Any]) -> None:
        self.stage_results[stage] = payload

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
