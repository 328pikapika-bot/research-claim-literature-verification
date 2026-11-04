from __future__ import annotations

from collections import Counter
from typing import Any

from app.core.config import CONSISTENCY_EVALUATION_RETRIEVAL_MAX_REFERENCES_TOTAL
from app.pipeline.model_gateway import ModelGateway
from app.pipeline.progress import ProgressWriter
from app.pipeline.state import PipelineState
from app.pipeline.utils import clip_text, deep_escape, escape_text, normalize_str_list, safe_preview
from app.pipeline.workflow_config import (
    ABSTRACT_ONLY_SCORE_CEILING,
    DEGRADED_PACKAGE_SCORE_CEILING,
    STATUS_SCORE_MAP,
    TITLE_ONLY_SCORE_CEILING,
    build_model_recovery_chain,
)


def run_output(
    state: PipelineState,
    model_gateway: ModelGateway | None = None,
    progress: ProgressWriter | None = None,
) -> PipelineState:
    gateway = model_gateway or ModelGateway()
    references, remap = _build_stable_references(state)
    state.citation_map = remap
    claims = []
    evidence_by_claim: dict[str, list[dict[str, Any]]] = {}

    for judgment in state.judgments:
        claim_id = judgment.get("claim_id", "")
        evidence = _sanitize_evidence(judgment.get("evidence", []), remap)
        evidence_by_claim[claim_id] = evidence
        claims.append(_build_claim_card(judgment, evidence))

    summary = _build_summary(claims, references, state.degradations)
    state.overall_score = summary.get("overall_score")
    package_payload = {
        "summary": summary,
        "claims": claims,
        "references": references,
        "citation_map": remap,
    }
    package = _build_package_with_model(package_payload, gateway, progress)
    final_report_markdown = _ensure_markdown(package, claims, references, summary)

    final_result = {
        "summary": summary,
        "claims": claims,
        "references": references,
        "evidence_by_claim": evidence_by_claim,
        "retrieval_detail": deep_escape(state.retrieval_detail),
        "input_digest": deep_escape(state.input_digest),
        "query_plans": deep_escape(state.query_plans),
        "stage_results": deep_escape(state.stage_results),
        "overall_conclusion": escape_text(package.get("overall_conclusion", "")),
        "summary_text": escape_text(package.get("summary_text", "")),
        "risk_notes": [escape_text(item) for item in normalize_str_list(package.get("risk_notes"), limit=8)],
        "rewrite_overview": _normalize_rewrite_overview(package.get("rewrite_overview"), claims),
        "overall_score": summary.get("overall_score"),
        "citation_map": remap,
        "final_report_markdown": final_report_markdown,
    }
    state.final_result = final_result
    state.evidence_by_claim = evidence_by_claim
    state.set_stage_result(
        "output",
        {
            "citation_map": remap,
            "overall_conclusion": final_result["overall_conclusion"],
            "package_preview": {
                "overall_score": summary.get("overall_score"),
                "risk_notes": final_result["risk_notes"][:4],
                "rewrite_overview": final_result["rewrite_overview"][:4],
            },
        },
    )
    return state


def _build_claim_card(judgment: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    support_levels = [item.get("evidence_level") for item in evidence if item.get("relation") == "support"]
    strongest_level = _strongest_level(support_levels)
    strongest_strength = _strongest_strength(
        [item.get("evidence_strength") for item in evidence if item.get("relation") == "support"]
    )
    return {
        "claim_id": escape_text(judgment.get("claim_id", "")),
        "text": escape_text(judgment.get("claim_text", "")),
        "status": escape_text(judgment.get("status", "")),
        "explanation": escape_text(judgment.get("explanation", "")),
        "reason": escape_text(judgment.get("reason", "")),
        "suggestion": escape_text(judgment.get("suggestion", "")),
        "confidence": judgment.get("confidence") or 0,
        "evidence": evidence,
        "evidence_strength": escape_text(strongest_strength),
        "evidence_level": escape_text(strongest_level),
        "limitations": [escape_text(item) for item in judgment.get("limitations", [])],
        "method": escape_text(judgment.get("method", "")),
        "degraded": bool(judgment.get("degraded")),
        "support_ids": judgment.get("support_ids", []),
        "conflict_ids": judgment.get("conflict_ids", []),
        "background_ids": judgment.get("background_ids", []),
    }


def _build_summary(
    claims: list[dict[str, Any]],
    references: list[dict[str, Any]],
    degradations: list[dict[str, Any]],
) -> dict[str, Any]:
    counts = Counter(claim.get("status") for claim in claims)
    overall_score = _calculate_overall_score(claims, degradations)
    evidence_coverage = round(
        sum(1 for claim in claims if claim.get("evidence")) / len(claims),
        4,
    ) if claims else 0
    confidence_distribution = {
        "high": sum(1 for claim in claims if float(claim.get("confidence") or 0) >= 0.8),
        "medium": sum(1 for claim in claims if 0.55 <= float(claim.get("confidence") or 0) < 0.8),
        "low": sum(1 for claim in claims if float(claim.get("confidence") or 0) < 0.55),
    }
    degradations_payload = [
        {
            "stage": escape_text(item.get("stage")),
            "reason": escape_text(item.get("reason")),
            "detail": escape_text(item.get("detail")),
        }
        for item in degradations
    ]
    return {
        "claim_count": len(claims),
        "total": len(claims),
        "reference_count": len(references),
        "overall_score": overall_score,
        "status_counts": dict(counts),
        "confirmed": counts.get("已被证实", 0),
        "partial": counts.get("部分被证实", 0),
        "disputed": counts.get("存在争议", 0),
        "lack": counts.get("缺乏文献支持", 0),
        "conflicted": counts.get("与文献冲突", 0),
        "degraded": bool(degradations),
        "degradations": degradations_payload,
        "evidence_coverage": evidence_coverage,
        "confidence_distribution": confidence_distribution,
    }


def _calculate_overall_score(claims: list[dict[str, Any]], degradations: list[dict[str, Any]]) -> int:
    if not claims:
        return 0
    scores = []
    for claim in claims:
        base = STATUS_SCORE_MAP.get(claim.get("status"), 20)
        level = claim.get("evidence_level")
        if level == "abstract":
            base = min(base, ABSTRACT_ONLY_SCORE_CEILING)
        elif level == "title":
            base = min(base, TITLE_ONLY_SCORE_CEILING)
        scores.append(base)
    avg = round(sum(scores) / len(scores))
    if degradations:
        avg = min(avg, DEGRADED_PACKAGE_SCORE_CEILING)
    return max(0, min(100, avg))


def _build_package_with_model(
    payload: dict[str, Any],
    gateway: ModelGateway,
    progress: ProgressWriter | None,
) -> dict[str, Any]:
    default_package = {
        "overall_conclusion": "",
        "summary_text": "",
        "risk_notes": [],
        "rewrite_overview": [],
        "final_report_markdown": "",
    }
    if not gateway.configured:
        return default_package
    attempts = build_model_recovery_chain("output", payload)
    call_model = lambda: gateway.chat_json_with_recovery(
        attempts,
        retries=1,
        on_attempt=lambda index, _: progress.heartbeat(
            "output",
            summary=f"正在生成最终评估包，第 {index} 次模型尝试",
            payload_patch={
                "progress_message": "正在生成综合结论、风险提示和最终报告",
                "eta_hint": "通常 30-90 秒；报告较长时会更久",
                "sub_steps": [
                    {"name": "稳定引用编号", "status": "completed"},
                    {"name": "生成最终评估包", "status": "running"},
                    {"name": "最终报告组装", "status": "pending"},
                ],
            },
        )
        if progress
        else None,
    )
    if progress:
        result = progress.run_with_periodic_heartbeat(
            "output",
            call_model,
            summary="正在生成最终评估包和报告",
            eta_hint="通常 30-90 秒；报告较长时会更久",
            payload_factory=lambda elapsed: {
                "sub_steps": [
                    {"name": "稳定引用编号", "status": "completed"},
                    {"name": f"生成最终评估包（已等待 {elapsed} 秒）", "status": "running"},
                    {"name": "最终报告组装", "status": "pending"},
                ],
            },
        )
    else:
        result = call_model()
    if not isinstance(result, dict):
        return default_package
    return {
        "overall_conclusion": clip_text(result.get("overall_conclusion"), 600),
        "summary_text": clip_text(result.get("summary_text"), 600),
        "risk_notes": normalize_str_list(result.get("risk_notes"), limit=8),
        "rewrite_overview": result.get("rewrite_overview", []),
        "final_report_markdown": str(result.get("final_report_markdown") or ""),
    }


def _normalize_rewrite_overview(raw: Any, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        normalized: list[dict[str, Any]] = []
        for item in raw[:12]:
            if isinstance(item, dict):
                normalized.append(
                    {
                        "claim_id": escape_text(item.get("claim_id", "")),
                        "rewrite": escape_text(item.get("rewrite") or item.get("suggestion") or ""),
                    }
                )
            else:
                normalized.append({"claim_id": "", "rewrite": escape_text(item)})
        return normalized
    suggestions = []
    for claim in claims[:12]:
        if claim.get("suggestion"):
            suggestions.append({"claim_id": claim.get("claim_id"), "rewrite": claim.get("suggestion")})
    return suggestions


def _build_stable_references(state: PipelineState) -> tuple[list[dict[str, Any]], dict[str, str]]:
    by_key: dict[str, dict[str, Any]] = {}
    old_to_new: dict[str, str] = {}
    new_to_number: dict[str, str] = {}
    for items in state.retrieval_results.values():
        for item in items:
            key = (
                str(item.get("doi") or "").lower()
                or str(item.get("paper_id") or "").lower()
                or f"{item.get('title', '')}:{item.get('year', '')}".lower()
            )
            if not key.strip(":"):
                continue
            if key not in by_key:
                if len(by_key) >= CONSISTENCY_EVALUATION_RETRIEVAL_MAX_REFERENCES_TOTAL:
                    continue
                ref_id = f"R{len(by_key) + 1}"
                by_key[key] = {
                    "reference_id": ref_id,
                    "paper_id": escape_text(item.get("paper_id")),
                    "title": escape_text(item.get("title")),
                    "authors": [escape_text(author) for author in item.get("authors", [])],
                    "year": item.get("year") or 0,
                    "venue": escape_text(item.get("venue")),
                    "doi": escape_text(item.get("doi")),
                    "url": escape_text(item.get("url")),
                    "language": escape_text(item.get("language")),
                    "abstract": escape_text(safe_preview(item.get("abstract"), 600)),
                    "source": escape_text(item.get("source")),
                    "citation_count": item.get("citation_count") or 0,
                }
                new_to_number[ref_id] = str(len(by_key))
            old_ref = str(item.get("reference_id") or "")
            if old_ref:
                old_to_new[old_ref] = by_key[key]["reference_id"]
                old_to_new[by_key[key]["reference_id"]] = new_to_number[by_key[key]["reference_id"]]
    return list(by_key.values()), old_to_new


def _sanitize_evidence(evidence: list[dict[str, Any]], remap: dict[str, str]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for item in evidence:
        old_ref = str(item.get("reference_id") or "")
        ref_id = remap.get(old_ref, old_ref)
        if old_ref and not ref_id.startswith("R"):
            continue
        sanitized.append(
            {
                "evidence_id": escape_text(item.get("evidence_id")),
                "reference_id": ref_id if ref_id.startswith("R") else "",
                "relation": escape_text(item.get("relation")),
                "title": escape_text(item.get("title")),
                "year": item.get("year") or 0,
                "snippet": escape_text(item.get("snippet")),
                "score": item.get("score") or 0,
                "evidence_strength": escape_text(item.get("evidence_strength")),
                "evidence_level": escape_text(item.get("evidence_level")),
                "why_relevant": escape_text(item.get("why_relevant")),
            }
        )
    return sanitized


def _ensure_markdown(
    package: dict[str, Any],
    claims: list[dict[str, Any]],
    references: list[dict[str, Any]],
    summary: dict[str, Any],
) -> str:
    report = str(package.get("final_report_markdown") or "").strip()
    if report:
        return report
    lines = ["# 一致性评估报告", ""]
    lines.append(f"- 主张数量：{summary['claim_count']}")
    lines.append(f"- 参考文献数量：{summary['reference_count']}")
    lines.append(f"- 综合评分：{summary['overall_score']}/100")
    lines.append("")
    if package.get("summary_text"):
        lines.append("## 综合结论")
        lines.append(str(package["summary_text"]))
        lines.append("")
    lines.append("## 逐主张结论")
    for claim in claims:
        refs = [evidence["reference_id"] for evidence in claim.get("evidence", []) if evidence.get("reference_id")]
        ref_text = "、".join(f"[{ref}]" for ref in refs[:5]) or "无"
        lines.append("")
        lines.append(f"### {claim['claim_id']}：{claim['status']}")
        lines.append(f"- 主张：{claim['text']}")
        lines.append(f"- 说明：{claim['explanation']}")
        if claim.get("suggestion"):
            lines.append(f"- 改写建议：{claim['suggestion']}")
        lines.append(f"- 引用：{ref_text}")
    if references:
        lines.append("")
        lines.append("## 参考文献")
        for ref in references:
            authors = "、".join(ref.get("authors") or [])
            prefix = f"[{ref['reference_id']}]"
            lines.append(
                f"- {prefix} {authors}. {ref.get('title', '')}. "
                f"{ref.get('venue', '')}, {ref.get('year', '')}."
            )
    return "\n".join(lines).strip()


def _strongest_level(levels: list[str]) -> str:
    ordered = {"title": 1, "abstract": 2, "fulltext": 3}
    best = "title"
    for level in levels:
        if ordered.get(level, 0) > ordered.get(best, 0):
            best = level
    return best


def _strongest_strength(levels: list[str]) -> str:
    ordered = {"weak": 1, "moderate": 2, "strong": 3}
    best = "weak"
    for level in levels:
        if ordered.get(level, 0) > ordered.get(best, 0):
            best = level
    return best
