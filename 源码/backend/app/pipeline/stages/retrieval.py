from __future__ import annotations

import logging
from typing import Any

from app.common.retrieval.adapters.claim_consistency import (
    ClaimConsistencySearchAdapter,
    paper_to_literature_item,
)
from app.core.config import (
    CONSISTENCY_EVALUATION_RETRIEVAL_MAX_REFERENCES_TOTAL,
    CONSISTENCY_EVALUATION_RETRIEVAL_MAX_CONCURRENCY,
    CONSISTENCY_EVALUATION_RETRIEVAL_TOP_K_PER_CLAIM,
)
from app.pipeline.model_gateway import ModelGateway
from app.pipeline.progress import ProgressWriter
from app.pipeline.stages.retrieval_preview import (
    build_evidence_pack_preview as _build_evidence_pack_preview,
    build_literature_preview as _build_literature_preview,
    build_trace_display_text as _build_trace_display_text,
    claim_label as _claim_label,
    limit_references_by_claim as _limit_references_by_claim,
)
from app.pipeline.state import PipelineState
from app.pipeline.utils import (
    clean_text,
    clip_text,
    normalize_str_list,
    safe_float,
    safe_preview,
)
from app.pipeline.workflow_config import (
    EVIDENCE_LEVELS,
    EVIDENCE_RELATIONS,
    EVIDENCE_STRENGTH_LEVELS,
    MAX_ABSTRACT_EVIDENCE_ITEMS_PER_CLAIM,
    MAX_EVIDENCE_ITEMS_PER_CLAIM,
    build_model_recovery_chain,
)

logger = logging.getLogger(__name__)


def run_retrieval(
    state: PipelineState,
    model_gateway: ModelGateway | None = None,
    progress: ProgressWriter | None = None,
    adapter: ClaimConsistencySearchAdapter | None = None,
) -> PipelineState:
    gateway = model_gateway or ModelGateway()
    search_adapter = adapter or ClaimConsistencySearchAdapter()
    languages = _language_pref_to_list(state.request.language_pref)

    requests = [
        search_adapter.build_request(
            _claim_with_query_text(claim),
            user_scope=state.request.user_scope,
            year_range=state.request.year_range,
            languages=languages,
            paper_num=CONSISTENCY_EVALUATION_RETRIEVAL_TOP_K_PER_CLAIM,
            task_id=state.request.task_id,
        )
        for claim in state.claims
    ]
    if not requests:
        state.retrieval_detail = {"search_traces": [], "errors": ["无可检索主张"]}
        state.evidence_by_claim = {}
        return state

    if progress:
        progress.heartbeat(
            "retrieval",
            summary=f"正在向 NSTL/NSTR 检索 {len(requests)} 条主张",
            payload_patch={
                "progress_message": "正在连接 NSTL/NSTR 检索服务并批量检索候选文献",
                "eta_hint": "通常 1-3 分钟；主张较多或检索服务繁忙时会更久",
                "completed_claims": 0,
                "total_claims": len(state.claims),
                "sub_steps": [
                    {"name": "构造检索请求", "status": "completed"},
                    {"name": "检索候选文献", "status": "running"},
                    {"name": "组织证据包", "status": "pending"},
                ],
            },
        )

    def search_all() -> list[Any]:
        return search_adapter.search_multi(
            requests,
            max_concurrency=CONSISTENCY_EVALUATION_RETRIEVAL_MAX_CONCURRENCY,
        )

    if progress:
        responses = progress.run_with_periodic_heartbeat(
            "retrieval",
            search_all,
            summary=f"正在检索 {len(requests)} 条主张的候选文献",
            eta_hint="通常 1-3 分钟；检索完成后会立即展示来源文献",
            payload_factory=lambda elapsed: {
                "completed_claims": 0,
                "total_claims": len(state.claims),
                "sub_steps": [
                    {"name": "构造检索请求", "status": "completed"},
                    {"name": f"检索候选文献（已等待 {elapsed} 秒）", "status": "running"},
                    {"name": "组织证据包", "status": "pending"},
                ],
            },
        )
    else:
        responses = search_all()

    raw_results_by_claim: dict[str, list[dict[str, Any]]] = {}
    evidence_by_claim: dict[str, list[dict[str, Any]]] = {}
    traces: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    retrieval_risks: list[str] = []

    for index, (claim, response) in enumerate(zip(state.claims, responses), start=1):
        claim_id = claim.get("claim_id", "")
        claim_label = _claim_label(index)
        trace = dict(response.search_trace or {})
        trace["claim_id"] = claim_id
        trace["claim_label"] = claim_label
        trace["claim_text"] = claim.get("text", "")
        trace["query"] = response.query
        trace["success"] = response.success
        trace["total"] = response.total
        trace["returned_count"] = response.total
        trace["query_plan"] = claim.get("query_plan", {})
        traces.append(trace)
        if not response.success:
            errors.append({"claim_id": claim_id, "claim_label": claim_label, "error": response.error or "检索失败"})
        papers = response.papers if response.success else []
        items = [
            paper_to_literature_item(paper, reference_id=f"tmp_{claim_id}_{paper_index}")
            for paper_index, paper in enumerate(papers, start=1)
        ]
        validated_items = _validate_real_references(items)
        if len(validated_items) < len(items):
            retrieval_risks.append(f"{claim_label} 存在无法验证身份的候选文献，已剔除")
        if not validated_items:
            retrieval_risks.append(f"{claim_label} 未检索到可用真实文献")
        raw_results_by_claim[claim_id] = validated_items

    results_by_claim = _limit_references_by_claim(
        raw_results_by_claim,
        state.claims,
        CONSISTENCY_EVALUATION_RETRIEVAL_MAX_REFERENCES_TOTAL,
    )
    raw_total = sum(len(items) for items in raw_results_by_claim.values())
    kept_total = sum(len(items) for items in results_by_claim.values())
    if raw_total > kept_total:
        retrieval_risks.append(
            f"候选文献较多，已按相关性和主张覆盖保留 {kept_total} 篇来源文献用于展示和后续判定"
        )

    for index, trace in enumerate(traces, start=1):
        claim_id = trace.get("claim_id", "")
        kept_count = len(results_by_claim.get(claim_id, []))
        trace["kept_count"] = kept_count
        trace["display_text"] = _build_trace_display_text(trace, index, kept_count)

    literature_preview = _build_literature_preview(results_by_claim, state.claims)
    retrieval_detail = {
        "search_traces": traces,
        "queries": traces,
        "errors": errors,
        "top_k_per_claim": CONSISTENCY_EVALUATION_RETRIEVAL_TOP_K_PER_CLAIM,
        "max_references_total": CONSISTENCY_EVALUATION_RETRIEVAL_MAX_REFERENCES_TOTAL,
        "max_concurrency": CONSISTENCY_EVALUATION_RETRIEVAL_MAX_CONCURRENCY,
    }
    state.retrieval_detail = retrieval_detail

    if progress:
        progress.heartbeat(
            "retrieval",
            summary=f"检索完成，已保留 {kept_total} 篇来源文献，正在组织证据包",
            payload_patch={
                "progress_message": "检索完成，正在把候选文献整理为逐主张证据包",
                "search_traces": traces,
                "literature_preview": literature_preview,
                "retrieval_risks": retrieval_risks[-5:],
                "retrieved_count": kept_total,
                "completed_claims": 0,
                "total_claims": len(state.claims),
                "sub_steps": [
                    {"name": "构造检索请求", "status": "completed"},
                    {"name": "检索候选文献", "status": "completed"},
                    {"name": "组织证据包", "status": "running"},
                ],
            },
        )

    for index, claim in enumerate(state.claims, start=1):
        claim_id = claim.get("claim_id", "")
        evidence_pack = _organize_evidence_pack(
            claim,
            results_by_claim.get(claim_id, []),
            retrieval_detail,
            gateway,
            progress,
            index,
            len(state.claims),
        )
        evidence_by_claim[claim_id] = evidence_pack
        if progress:
            progress.heartbeat(
                "retrieval",
                summary=f"已完成 {index}/{len(state.claims)} 条主张检索与证据组织",
                payload_patch={
                    "progress_message": f"正在整理证据包，已完成 {index}/{len(state.claims)} 条主张",
                    "search_traces": traces,
                    "literature_preview": literature_preview,
                    "evidence_pack_preview": _build_evidence_pack_preview(evidence_by_claim, state.claims),
                    "retrieval_risks": retrieval_risks[-5:],
                    "completed_claims": index,
                    "total_claims": len(state.claims),
                    "sub_steps": [
                        {"name": "构造检索请求", "status": "completed"},
                        {"name": "检索候选文献", "status": "completed"},
                        {"name": f"组织证据包（{index}/{len(state.claims)}）", "status": "running" if index < len(state.claims) else "completed"},
                    ],
                },
            )

    if errors:
        state.add_degradation("retrieval", "部分或全部统一检索失败", "; ".join(e["error"] for e in errors[:3]))
    if not any(results_by_claim.values()):
        state.add_degradation("retrieval", "未获得真实文献结果", "后续判定将按缺乏文献支持处理")

    state.retrieval_results = results_by_claim
    state.evidence_by_claim = evidence_by_claim
    state.retrieval_detail = retrieval_detail
    state.set_stage_result(
        "retrieval",
        {
            "search_traces": traces,
            "literature_preview": literature_preview,
            "evidence_pack_preview": _build_evidence_pack_preview(evidence_by_claim, state.claims),
            "retrieval_risks": retrieval_risks,
        },
    )
    return state


def _claim_with_query_text(claim: dict[str, Any]) -> dict[str, Any]:
    plan = claim.get("query_plan", {}) if isinstance(claim.get("query_plan"), dict) else {}
    query_text = clean_text(plan.get("query_text")) or clean_text(claim.get("text"))
    keywords = normalize_str_list(plan.get("must_terms"), limit=8) or normalize_str_list(claim.get("keywords"), limit=8)
    patched = dict(claim)
    patched["text"] = query_text
    patched["keywords"] = keywords
    return patched


def _organize_evidence_pack(
    claim: dict[str, Any],
    references: list[dict[str, Any]],
    retrieval_detail: dict[str, Any],
    gateway: ModelGateway,
    progress: ProgressWriter | None,
    index: int,
    total_claims: int,
) -> list[dict[str, Any]]:
    if not references:
        return []
    payload = {
        "claim": claim,
        "retrieval_detail": retrieval_detail,
        "references": [
            {
                "reference_id": item.get("reference_id"),
                "title": item.get("title"),
                "year": item.get("year"),
                "abstract": safe_preview(item.get("abstract"), 900),
                "has_fulltext": bool(item.get("has_fulltext")),
                "final_score": item.get("final_score"),
            }
            for item in references[:12]
        ],
    }
    raw_pack: list[dict[str, Any]] = []
    if gateway.configured:
        attempts = build_model_recovery_chain("retrieval", payload)
        call_model = lambda: gateway.chat_json_with_recovery(
            attempts,
            retries=1,
            on_attempt=lambda attempt_no, _: progress.heartbeat(
                "retrieval",
                summary=f"正在组织{_claim_label(index)}的证据包，第 {attempt_no} 次模型尝试",
                payload_patch={
                    "progress_message": f"正在组织{_claim_label(index)}的证据包",
                    "completed_claims": max(0, index - 1),
                    "total_claims": total_claims,
                },
            )
            if progress
            else None,
        )
        if progress:
            result = progress.run_with_periodic_heartbeat(
                "retrieval",
                call_model,
                summary=f"正在组织{_claim_label(index)}的证据包",
                eta_hint="通常 10-30 秒；模型繁忙时会更久",
                payload_factory=lambda elapsed: {
                    "completed_claims": max(0, index - 1),
                    "total_claims": total_claims,
                    "sub_steps": [
                        {"name": "构造检索请求", "status": "completed"},
                        {"name": "检索候选文献", "status": "completed"},
                        {"name": f"组织{_claim_label(index)}证据包（已等待 {elapsed} 秒）", "status": "running"},
                    ],
                },
            )
        else:
            result = call_model()
        if isinstance(result, dict):
            maybe_pack = result.get("evidence_pack")
            if isinstance(maybe_pack, list):
                raw_pack = maybe_pack
    normalized = _normalize_evidence_pack(claim, references, raw_pack)
    if normalized:
        return normalized
    return _fallback_evidence_pack(claim, references)


def _normalize_evidence_pack(
    claim: dict[str, Any],
    references: list[dict[str, Any]],
    raw_pack: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_reference_id = {str(item.get("reference_id")): item for item in references if item.get("reference_id")}
    evidence: list[dict[str, Any]] = []
    abstract_only_count = 0
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(raw_pack, start=1):
        if not isinstance(item, dict):
            continue
        reference_id = str(item.get("reference_id") or "").strip()
        source_ref = by_reference_id.get(reference_id)
        if not source_ref:
            continue
        relation = clean_text(item.get("relation")).lower()
        if relation not in EVIDENCE_RELATIONS:
            relation = "uncertain"
        evidence_level = clean_text(item.get("evidence_level")).lower()
        if evidence_level not in EVIDENCE_LEVELS:
            evidence_level = "abstract" if source_ref.get("abstract") else "title"
        if evidence_level == "abstract":
            abstract_only_count += 1
            if abstract_only_count > MAX_ABSTRACT_EVIDENCE_ITEMS_PER_CLAIM:
                continue
        evidence_strength = clean_text(item.get("evidence_strength")).lower()
        if evidence_strength not in EVIDENCE_STRENGTH_LEVELS:
            evidence_strength = "moderate" if evidence_level == "fulltext" else "weak"
        dedupe_key = (reference_id, relation)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        evidence.append(
            {
                "evidence_id": f"{claim.get('claim_id', '')}_ev_{len(evidence) + 1}",
                "reference_id": reference_id,
                "relation": relation,
                "evidence_strength": evidence_strength,
                "evidence_level": evidence_level,
                "title": source_ref.get("title", ""),
                "year": source_ref.get("year", 0),
                "snippet": clip_text(item.get("snippet") or source_ref.get("abstract") or source_ref.get("title"), 320),
                "why_relevant": clip_text(item.get("why_relevant"), 220),
                "score": safe_float(source_ref.get("final_score") or source_ref.get("retrieval_score")),
            }
        )
        if len(evidence) >= MAX_EVIDENCE_ITEMS_PER_CLAIM:
            break
    return evidence


def _fallback_evidence_pack(claim: dict[str, Any], references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for index, item in enumerate(references[:MAX_EVIDENCE_ITEMS_PER_CLAIM], start=1):
        relation = "support" if index <= 2 else "background"
        evidence.append(
            {
                "evidence_id": f"{claim.get('claim_id', '')}_ev_{index}",
                "reference_id": item.get("reference_id", ""),
                "relation": relation,
                "evidence_strength": "weak",
                "evidence_level": "fulltext" if item.get("has_fulltext") else ("abstract" if item.get("abstract") else "title"),
                "title": item.get("title", ""),
                "year": item.get("year", 0),
                "snippet": clip_text(item.get("abstract") or item.get("title"), 260),
                "why_relevant": "检索结果与主张关键词高度重合，作为候选证据保留。",
                "score": safe_float(item.get("final_score") or item.get("retrieval_score")),
            }
        )
    return evidence


def _validate_real_references(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for item in items:
        title = clean_text(item.get("title"))
        if not title:
            continue
        identity_key = (
            str(item.get("doi") or "").lower().strip()
            or str(item.get("paper_id") or "").lower().strip()
            or f"{title.lower()}::{item.get('year') or ''}"
        )
        if identity_key in seen_keys:
            continue
        seen_keys.add(identity_key)
        validated.append(item)
    return validated


def _language_pref_to_list(language_pref: str) -> list[str]:
    pref = (language_pref or "").lower()
    if pref in {"zh", "cn", "chinese", "中文"}:
        return ["zh"]
    if pref in {"en", "english", "英文"}:
        return ["en"]
    return ["zh", "en"]
