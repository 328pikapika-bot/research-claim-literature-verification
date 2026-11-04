from __future__ import annotations

from typing import Any

from app.pipeline.utils import safe_float, safe_preview


CHINESE_NUMERALS = "零一二三四五六七八九十"


def build_evidence_pack_preview(
    evidence_by_claim: dict[str, list[dict[str, Any]]],
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    claim_lookup = {claim.get("claim_id", ""): (idx, claim) for idx, claim in enumerate(claims, start=1)}
    for claim_id, items in list(evidence_by_claim.items())[:6]:
        index, claim = claim_lookup.get(claim_id, (len(preview) + 1, {}))
        support = sum(1 for item in items if item.get("relation") == "support")
        conflict = sum(1 for item in items if item.get("relation") == "conflict")
        abstract_only = sum(1 for item in items if item.get("evidence_level") == "abstract")
        preview.append(
            {
                "claim_id": claim_id,
                "claim_label": claim_label(index),
                "claim_text": claim.get("text", ""),
                "count": len(items),
                "support": support,
                "conflict": conflict,
                "abstract_only": abstract_only,
                "summary_text": f"{claim_label(index)}：已整理 {len(items)} 条证据线索，其中支持 {support} 条、冲突 {conflict} 条、摘要级 {abstract_only} 条。",
            }
        )
    return preview


def limit_references_by_claim(
    results_by_claim: dict[str, list[dict[str, Any]]],
    claims: list[dict[str, Any]],
    max_total: int,
) -> dict[str, list[dict[str, Any]]]:
    if max_total <= 0:
        return {claim.get("claim_id", ""): [] for claim in claims}

    claim_order = [claim.get("claim_id", "") for claim in claims]
    selected: dict[str, list[dict[str, Any]]] = {claim_id: [] for claim_id in claim_order}
    seen: set[str] = set()

    def take(claim_id: str, item: dict[str, Any]) -> bool:
        if sum(len(values) for values in selected.values()) >= max_total:
            return False
        identity = reference_identity(item)
        if not identity or identity in seen:
            return False
        seen.add(identity)
        selected.setdefault(claim_id, []).append(item)
        return True

    ranked_by_claim = {
        claim_id: sorted(
            list(enumerate(results_by_claim.get(claim_id, []))),
            key=lambda pair: (-reference_score(pair[1]), pair[0]),
        )
        for claim_id in claim_order
    }

    for claim_id in claim_order:
        for _, item in ranked_by_claim.get(claim_id, []):
            if take(claim_id, item):
                break

    pool: list[tuple[int, int, float, str, dict[str, Any]]] = []
    order_lookup = {claim_id: index for index, claim_id in enumerate(claim_order)}
    for claim_id, ranked_items in ranked_by_claim.items():
        for original_index, item in ranked_items:
            pool.append((order_lookup.get(claim_id, 999), original_index, reference_score(item), claim_id, item))
    pool.sort(key=lambda item: (-item[2], item[0], item[1]))

    for _, _, _, claim_id, item in pool:
        if sum(len(values) for values in selected.values()) >= max_total:
            break
        take(claim_id, item)
    return selected


def build_literature_preview(
    results_by_claim: dict[str, list[dict[str, Any]]],
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    seen: set[str] = set()
    for claim_index, claim in enumerate(claims, start=1):
        claim_id = claim.get("claim_id", "")
        for item in results_by_claim.get(claim_id, []):
            identity = reference_identity(item)
            if not identity or identity in seen:
                continue
            seen.add(identity)
            ref_number = len(preview) + 1
            preview.append(
                {
                    "id": item.get("reference_id") or item.get("paper_id") or f"ref_{ref_number}",
                    "reference_id": item.get("reference_id", ""),
                    "paper_id": item.get("paper_id", ""),
                    "refNumber": ref_number,
                    "title": item.get("title", ""),
                    "authors": item.get("authors", []),
                    "year": item.get("year") or "",
                    "venue": item.get("venue", ""),
                    "doi": item.get("doi", ""),
                    "url": item.get("url", ""),
                    "language": item.get("language", ""),
                    "abstract": safe_preview(item.get("abstract"), 600),
                    "source": item.get("source", ""),
                    "sourceTitle": item.get("venue", ""),
                    "claim_label": claim_label(claim_index),
                    "claim_id": claim_id,
                    "final_score": item.get("final_score") or item.get("retrieval_score"),
                }
            )
    return preview


def build_trace_display_text(trace: dict[str, Any], index: int, kept_count: int) -> str:
    label = trace.get("claim_label") or claim_label(index)
    query = safe_preview(trace.get("query") or trace.get("question") or "当前主张关键词", 100)
    returned = int(trace.get("returned_count") or trace.get("total") or 0)
    if not trace.get("success"):
        errors = trace.get("errors") if isinstance(trace.get("errors"), list) else []
        reason = errors[0] if errors else "检索服务未返回可用结果"
        return f"{label}：使用“{query}”检索失败，原因：{reason}。"
    return f"{label}：使用“{query}”检索，返回 {returned} 篇候选文献，保留 {kept_count} 篇真实来源文献。"


def reference_identity(item: dict[str, Any]) -> str:
    return (
        str(item.get("doi") or "").lower().strip()
        or str(item.get("paper_id") or "").lower().strip()
        or f"{str(item.get('title') or '').lower().strip()}::{item.get('year') or ''}"
    )


def reference_score(item: dict[str, Any]) -> float:
    return safe_float(item.get("final_score") or item.get("quality_score") or item.get("retrieval_score"))


def claim_label(index: int) -> str:
    return f"主张{chinese_number(index)}"


def chinese_number(value: int) -> str:
    if value <= 0:
        return str(value)
    if value <= 10:
        return CHINESE_NUMERALS[value]
    if value < 20:
        return f"十{CHINESE_NUMERALS[value - 10]}"
    tens, ones = divmod(value, 10)
    if ones == 0:
        return f"{CHINESE_NUMERALS[tens]}十"
    return f"{CHINESE_NUMERALS[tens]}十{CHINESE_NUMERALS[ones]}"
