from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from app.pipeline.model_gateway import ModelGateway
from app.pipeline.progress import ProgressWriter
from app.pipeline.stages.retrieval_preview import claim_label
from app.pipeline.state import PipelineState
from app.pipeline.utils import clean_text, clip_text, normalize_probability, normalize_str_list
from app.pipeline.workflow_config import VALID_JUDGMENT_STATUSES, build_model_recovery_chain

logger = logging.getLogger(__name__)

VALID_STATUSES = set(VALID_JUDGMENT_STATUSES)


def run_judgment(
    state: PipelineState,
    model_gateway: ModelGateway | None = None,
    progress: ProgressWriter | None = None,
) -> PipelineState:
    gateway = model_gateway or ModelGateway()
    judgments: list[dict[str, Any]] = []
    review_flags: list[str] = []
    for index, claim in enumerate(state.claims, start=1):
        claim_id = claim.get("claim_id", "")
        evidence_pack = state.evidence_by_claim.get(claim_id, [])
        judgment = _judge_claim(claim, evidence_pack, state.retrieval_detail, gateway, progress, index)
        judgement_after_rules, flags = _apply_judgment_guardrails(judgment, evidence_pack, state.degradations)
        judgments.append(judgement_after_rules)
        review_flags.extend(flags)
        if progress:
            label = claim_label(index)
            progress.heartbeat(
                "judgment",
                summary=f"已完成 {index}/{len(state.claims)} 条主张判定",
                payload_patch={
                    "progress_message": f"已完成{label}的一致性判定",
                    "judgment_preview": judgments[-4:],
                    "status_distribution": dict(Counter(item.get("status") for item in judgments)),
                    "review_flags": review_flags[-6:],
                    "completed_claims": index,
                    "total_claims": len(state.claims),
                },
            )

    state.judgments = judgments
    state.set_stage_result(
        "judgment",
        {
            "judgment_preview": judgments[:6],
            "status_distribution": dict(Counter(item.get("status") for item in judgments)),
            "review_flags": review_flags,
        },
    )
    return state


def _judge_claim(
    claim: dict[str, Any],
    evidence_pack: list[dict[str, Any]],
    retrieval_detail: dict[str, Any],
    gateway: ModelGateway,
    progress: ProgressWriter | None,
    index: int,
) -> dict[str, Any]:
    label = claim_label(index)
    if gateway.configured:
        payload = {
            "claim": claim,
            "evidence_pack": evidence_pack,
            "retrieval_detail": retrieval_detail,
        }
        attempts = build_model_recovery_chain("judgment", payload)
        call_model = lambda: gateway.chat_json_with_recovery(
            attempts,
            retries=1,
            on_attempt=lambda attempt_no, _: progress.heartbeat(
                "judgment",
                summary=f"正在判定{label}，第 {attempt_no} 次模型尝试",
                payload_patch={
                    "progress_message": f"正在比对{label}与证据",
                    "completed_claims": max(0, index - 1),
                    "sub_steps": [
                        {"name": f"判定{label}", "status": "running"},
                        {"name": "结论强度校验", "status": "pending"},
                        {"name": "改写建议生成", "status": "pending"},
                    ],
                },
            )
            if progress
            else None,
        )
        if progress:
            result = progress.run_with_periodic_heartbeat(
                "judgment",
                call_model,
                summary=f"正在判定{label}",
                eta_hint="通常每条主张 10-30 秒；证据较多时会更久",
                payload_factory=lambda elapsed: {
                    "completed_claims": max(0, index - 1),
                    "sub_steps": [
                        {"name": f"判定{label}（已等待 {elapsed} 秒）", "status": "running"},
                        {"name": "结论强度校验", "status": "pending"},
                        {"name": "改写建议生成", "status": "pending"},
                    ],
                },
            )
        else:
            result = call_model()
        normalized = _normalize_judgment(claim, evidence_pack, result)
        if normalized:
            return normalized
    return _fallback_judgment(claim, evidence_pack)


def _normalize_judgment(
    claim: dict[str, Any],
    evidence_pack: list[dict[str, Any]],
    raw: Any,
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    status = clean_text(raw.get("status"))
    if status not in VALID_STATUSES:
        status = "缺乏文献支持"
    valid_ids = {item.get("evidence_id") for item in evidence_pack}
    support_ids = [item for item in normalize_str_list(raw.get("support_ids")) if item in valid_ids]
    conflict_ids = [item for item in normalize_str_list(raw.get("conflict_ids")) if item in valid_ids]
    background_ids = [item for item in normalize_str_list(raw.get("background_ids")) if item in valid_ids]
    limitations = normalize_str_list(raw.get("limitations"), limit=6)
    explanation = clip_text(raw.get("explanation") or raw.get("reason"), 360)
    suggestion = clip_text(raw.get("suggestion"), 320)
    if not explanation:
        explanation = _fallback_reason(status, evidence_pack)
    return {
        "claim_id": claim.get("claim_id", ""),
        "claim_text": claim.get("text", ""),
        "status": status,
        "explanation": explanation,
        "reason": explanation,
        "suggestion": suggestion or _fallback_suggestion(claim, status),
        "confidence": normalize_probability(raw.get("confidence"), 0.72),
        "support_ids": support_ids,
        "conflict_ids": conflict_ids,
        "background_ids": background_ids,
        "limitations": limitations,
        "evidence": evidence_pack,
        "method": "model",
        "degraded": False,
    }


def _fallback_judgment(claim: dict[str, Any], evidence_pack: list[dict[str, Any]]) -> dict[str, Any]:
    support_ids = [item.get("evidence_id") for item in evidence_pack if item.get("relation") == "support"]
    conflict_ids = [item.get("evidence_id") for item in evidence_pack if item.get("relation") == "conflict"]
    background_ids = [item.get("evidence_id") for item in evidence_pack if item.get("relation") == "background"]
    status = _fallback_status(evidence_pack)
    explanation = _fallback_reason(status, evidence_pack)
    return {
        "claim_id": claim.get("claim_id", ""),
        "claim_text": claim.get("text", ""),
        "status": status,
        "explanation": explanation,
        "reason": explanation,
        "suggestion": _fallback_suggestion(claim, status),
        "confidence": 0.6 if status != "缺乏文献支持" else 0.45,
        "support_ids": support_ids,
        "conflict_ids": conflict_ids,
        "background_ids": background_ids,
        "limitations": [],
        "evidence": evidence_pack,
        "method": "rule",
        "degraded": True,
    }


def _fallback_status(evidence_pack: list[dict[str, Any]]) -> str:
    support_count = sum(1 for item in evidence_pack if item.get("relation") == "support")
    conflict_count = sum(1 for item in evidence_pack if item.get("relation") == "conflict")
    if support_count == 0 and conflict_count == 0:
        return "缺乏文献支持"
    if support_count > 0 and conflict_count > 0:
        return "存在争议"
    if conflict_count > 0:
        return "与文献冲突"
    if support_count >= 2:
        return "已被证实"
    return "部分被证实"


def _apply_judgment_guardrails(
    judgment: dict[str, Any],
    evidence_pack: list[dict[str, Any]],
    degradations: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    flags: list[str] = []
    support_levels = [item.get("evidence_level") for item in evidence_pack if item.get("relation") == "support"]
    has_conflict = any(item.get("relation") == "conflict" for item in evidence_pack)
    has_real_support = bool(support_levels)
    abstract_only_support = has_real_support and all(level in {"title", "abstract"} for level in support_levels)
    retrieval_degraded = any(item.get("stage") == "retrieval" for item in degradations)

    status = judgment.get("status", "缺乏文献支持")
    if not has_real_support and status in {"已被证实", "部分被证实"}:
        status = "缺乏文献支持"
        flags.append(f"{judgment.get('claim_id')} 缺少有效支持证据，已下调判定")
    elif has_conflict and status == "已被证实":
        status = "存在争议"
        flags.append(f"{judgment.get('claim_id')} 同时存在冲突证据，已下调为存在争议")
    elif abstract_only_support and status == "已被证实":
        status = "部分被证实"
        flags.append(f"{judgment.get('claim_id')} 仅有摘要级支持，已下调为部分被证实")
    elif retrieval_degraded and status == "已被证实":
        status = "部分被证实"
        flags.append(f"{judgment.get('claim_id')} 检索阶段已降级，已避免输出过强结论")

    judgment = dict(judgment)
    judgment["status"] = status
    judgment["reason"] = judgment.get("explanation") or judgment.get("reason") or _fallback_reason(status, evidence_pack)
    judgment["explanation"] = judgment["reason"]
    judgment["degraded"] = judgment.get("degraded", False) or bool(flags)
    return judgment, flags


def _fallback_reason(status: str, evidence_pack: list[dict[str, Any]]) -> str:
    support_count = sum(1 for item in evidence_pack if item.get("relation") == "support")
    conflict_count = sum(1 for item in evidence_pack if item.get("relation") == "conflict")
    background_count = sum(1 for item in evidence_pack if item.get("relation") == "background")
    if status == "缺乏文献支持":
        return "未检索到可直接支持或冲突该主张的真实文献证据。"
    if status == "存在争议":
        return f"当前证据中同时存在 {support_count} 条支持线索和 {conflict_count} 条冲突线索。"
    if status == "与文献冲突":
        return f"当前证据中存在 {conflict_count} 条与主张方向不一致的文献线索。"
    if status == "已被证实":
        return f"当前证据中发现 {support_count} 条支持线索，且未发现明确冲突证据。"
    return f"当前证据中发现 {support_count} 条支持线索，另有 {background_count} 条背景相关文献。"


def _fallback_suggestion(claim: dict[str, Any], status: str) -> str:
    text = clean_text(claim.get("text"))
    if status == "已被证实":
        return f"可保留原表述，但建议补充适用条件或关键证据来源：{text}"
    if status == "部分被证实":
        return f"建议改写为“现有文献在特定条件下支持 {text}，但证据仍不充分”。"
    if status == "存在争议":
        return f"建议改写为“关于 {text}，现有研究结论并不一致，仍需区分条件与样本差异”。"
    if status == "与文献冲突":
        return f"建议改写为“现有文献未支持 {text}，部分研究结果与该表述相反”。"
    return f"建议改写为“目前缺少可直接支持 {text} 的真实文献证据”。"
