from __future__ import annotations

import logging
import re
from typing import Any

from app.core.config import CONSISTENCY_EVALUATION_MAX_CLAIMS
from app.pipeline.model_gateway import ModelGateway
from app.pipeline.progress import ProgressWriter
from app.pipeline.state import PipelineState
from app.pipeline.utils import (
    clean_text,
    clip_text,
    normalize_probability,
    normalize_str_list,
    safe_int,
    safe_preview,
    split_keywords,
)
from app.pipeline.workflow_config import build_model_recovery_chain

logger = logging.getLogger(__name__)

ASSERTION_CUES = (
    "表明",
    "显示",
    "证明",
    "证实",
    "发现",
    "指出",
    "认为",
    "提示",
    "导致",
    "影响",
    "提高",
    "降低",
    "相关",
    "显著",
    "优于",
    "is associated",
    "increases",
    "decreases",
    "improves",
    "reduces",
    "suggests",
    "shows",
    "demonstrates",
)


def run_claim_extract(
    state: PipelineState,
    model_gateway: ModelGateway | None = None,
    progress: ProgressWriter | None = None,
) -> PipelineState:
    gateway = model_gateway or ModelGateway()
    payload = {
        "clean_input": state.clean_input,
        "input_digest": state.input_digest,
        "chunk_digest": state.chunk_digest,
        "max_claims": CONSISTENCY_EVALUATION_MAX_CLAIMS,
    }
    claims = _extract_with_model(payload, gateway, progress)
    if claims:
        state.claims = claims[:CONSISTENCY_EVALUATION_MAX_CLAIMS]
        state.query_plans = [claim["query_plan"] for claim in state.claims]
        state.set_stage_result(
            "claim_extract",
            {
                "claims_preview": state.claims[:6],
                "query_plans": state.query_plans[:6],
                "quality_flags": _build_quality_flags(state.claims),
            },
        )
        return state

    state.add_degradation("claim_extract", "模型未配置或主张提取失败", "已启用规则主张提取兜底")
    claims = _extract_with_rules(state.clean_input)
    if not claims:
        raise ValueError("未能从输入中提取可评估主张")
    state.claims = claims[:CONSISTENCY_EVALUATION_MAX_CLAIMS]
    state.query_plans = [claim["query_plan"] for claim in state.claims]
    state.set_stage_result(
        "claim_extract",
        {
            "claims_preview": state.claims[:6],
            "query_plans": state.query_plans[:6],
            "quality_flags": _build_quality_flags(state.claims),
        },
    )
    return state


def _extract_with_model(
    payload: dict[str, Any],
    gateway: ModelGateway,
    progress: ProgressWriter | None,
) -> list[dict[str, Any]]:
    if not gateway.configured:
        return []

    attempts = build_model_recovery_chain("claim_extract", payload)
    call_model = lambda: gateway.chat_json_with_recovery(
        attempts,
        retries=1,
        on_attempt=lambda index, _: progress.heartbeat(
            "claim_extract",
            summary=f"正在执行主张提取，第 {index} 次模型尝试",
            payload_patch={
                "progress_message": "正在调用模型识别可核验主张并生成检索计划",
                "eta_hint": "通常 30-90 秒；文本较长时会更久",
                "sub_steps": [
                    {"name": "模型识别可核验主张", "status": "running"},
                    {"name": "生成检索计划", "status": "pending"},
                    {"name": "规则校验与修复", "status": "pending"},
                ],
            },
        )
        if progress
        else None,
    )
    if progress:
        result = progress.run_with_periodic_heartbeat(
            "claim_extract",
            call_model,
            summary="正在提取可核验主张并生成检索计划",
            eta_hint="通常 30-90 秒；文本较长时会更久",
            payload_factory=lambda elapsed: {
                "sub_steps": [
                    {"name": f"模型识别可核验主张（已等待 {elapsed} 秒）", "status": "running"},
                    {"name": "生成检索计划", "status": "pending"},
                    {"name": "规则校验与修复", "status": "pending"},
                ],
            },
        )
    else:
        result = call_model()
    if not isinstance(result, dict):
        return []
    raw_claims = result.get("claims")
    if not isinstance(raw_claims, list):
        return []
    normalized = _normalize_claims(raw_claims, payload.get("clean_input") or "")
    return _merge_and_trim_claims(normalized)


def _normalize_claims(raw_claims: list[dict[str, Any]], full_text: str) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for index, item in enumerate(raw_claims, start=1):
        if not isinstance(item, dict):
            continue
        text_value = clip_text(item.get("text"), 500)
        if len(text_value) < 6:
            continue
        keywords = normalize_str_list(item.get("keywords"), limit=8) or split_keywords(text_value)
        source_excerpt = clip_text(item.get("source_excerpt") or safe_preview(text_value, 180), 220)
        conditions = clip_text(item.get("conditions_or_scope"), 180)
        numeric_targets = normalize_str_list(item.get("numeric_targets"), limit=6)
        query_plan = _normalize_query_plan(item.get("query_plan"), text_value, keywords)
        claims.append(
            {
                "claim_id": clean_text(item.get("claim_id")) or f"claim_{index}",
                "text": text_value,
                "assertion_type": clean_text(item.get("assertion_type")) or _guess_assertion_type(text_value),
                "keywords": keywords,
                "conditions_or_scope": conditions,
                "numeric_targets": numeric_targets,
                "confidence": normalize_probability(item.get("confidence"), 0.72),
                "source_excerpt": source_excerpt,
                "priority": max(1, min(5, safe_int(item.get("priority"), 3))),
                "query_plan": query_plan,
                "extraction_method": "model",
            }
        )
    if not claims and full_text:
        return _extract_with_rules(full_text)
    return claims


def _normalize_query_plan(raw_plan: Any, claim_text: str, keywords: list[str]) -> dict[str, Any]:
    raw_plan = raw_plan if isinstance(raw_plan, dict) else {}
    must_terms = normalize_str_list(raw_plan.get("must_terms"), limit=6) or keywords[:4]
    optional_terms = normalize_str_list(raw_plan.get("optional_terms"), limit=6)
    exclusion_terms = normalize_str_list(raw_plan.get("exclusion_terms"), limit=4)
    filters = raw_plan.get("filters") if isinstance(raw_plan.get("filters"), dict) else {}
    return {
        "query_text": clip_text(raw_plan.get("query_text") or claim_text, 280),
        "must_terms": must_terms,
        "optional_terms": optional_terms,
        "exclusion_terms": exclusion_terms,
        "filters": {
            "year_range": filters.get("year_range"),
            "language": filters.get("language"),
            "subject_area": clean_text(filters.get("subject_area")),
        },
        "reason": clip_text(raw_plan.get("reason") or "围绕主张核心实体和条件约束构造检索式", 160),
    }


def _merge_and_trim_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for claim in sorted(claims, key=lambda item: (item.get("priority", 3), -len(item.get("text", "")))):
        key = re.sub(r"\s+", "", claim.get("text", "").lower())
        if not key or key in seen:
            continue
        seen.add(key)
        claim["claim_id"] = f"claim_{len(merged) + 1}"
        merged.append(claim)
        if len(merged) >= CONSISTENCY_EVALUATION_MAX_CLAIMS:
            break
    return merged


def _extract_with_rules(text: str) -> list[dict[str, Any]]:
    sentences = [
        clean_text(item)
        for item in re.split(r"(?<=[。！？!?；;])|\n+", text)
        if clean_text(item)
    ]
    candidates: list[str] = []
    for sentence in sentences:
        if len(sentence) < 8:
            continue
        if len(sentence) > 280:
            parts = [clean_text(p) for p in re.split(r"[。；;]", sentence) if clean_text(p)]
        else:
            parts = [sentence]
        for part in parts:
            lower = part.lower()
            if any(cue in lower for cue in ASSERTION_CUES) or len(split_keywords(part, 5)) >= 3:
                candidates.append(part)
    if not candidates and text:
        candidates = [safe_preview(text, 240)]

    claims: list[dict[str, Any]] = []
    for index, item in enumerate(candidates[:CONSISTENCY_EVALUATION_MAX_CLAIMS], start=1):
        keywords = split_keywords(item)
        claims.append(
            {
                "claim_id": f"claim_{index}",
                "text": item,
                "assertion_type": _guess_assertion_type(item),
                "keywords": keywords,
                "conditions_or_scope": "",
                "numeric_targets": re.findall(r"\d+(?:\.\d+)?%?", item)[:4],
                "confidence": 0.55,
                "source_excerpt": safe_preview(item, 160),
                "priority": 3,
                "query_plan": _normalize_query_plan({}, item, keywords),
                "extraction_method": "rule",
            }
        )
    return claims


def _guess_assertion_type(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ("提高", "降低", "改善", "increases", "reduces", "improves")):
        return "效果/影响"
    if any(word in lower for word in ("相关", "关联", "associated", "correlated")):
        return "相关性"
    if any(word in lower for word in ("导致", "原因", "机制", "cause", "mechanism")):
        return "因果/机制"
    return "事实/结论"


def _build_quality_flags(claims: list[dict[str, Any]]) -> list[str]:
    flags: list[str] = []
    if len(claims) >= CONSISTENCY_EVALUATION_MAX_CLAIMS:
        flags.append("主张数量已达到上限，已执行裁剪")
    low_confidence = sum(1 for claim in claims if claim.get("confidence", 0) < 0.55)
    if low_confidence:
        flags.append(f"{low_confidence} 条主张置信度偏低，建议重点复核")
    missing_conditions = sum(1 for claim in claims if not claim.get("conditions_or_scope"))
    if missing_conditions:
        flags.append(f"{missing_conditions} 条主张缺少明确适用条件，检索时将以核心实体为主")
    return flags
