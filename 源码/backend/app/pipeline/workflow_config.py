from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from app.core.config import (
    CONSISTENCY_EVALUATION_MAX_CLAIMS,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    DEEPSEEK_TIMEOUT,
    MODEL_API_KEY,
    MODEL_BASE_URL,
    MODEL_NAME,
    MODEL_TIMEOUT,
)


VALID_JUDGMENT_STATUSES = [
    "已被证实",
    "部分被证实",
    "存在争议",
    "缺乏文献支持",
    "与文献冲突",
]

STATUS_SCORE_MAP = {
    "已被证实": 100,
    "部分被证实": 70,
    "存在争议": 40,
    "缺乏文献支持": 20,
    "与文献冲突": 0,
}

EVIDENCE_RELATIONS = {"support", "conflict", "background", "uncertain"}
EVIDENCE_LEVELS = ("title", "abstract", "fulltext")
EVIDENCE_STRENGTH_LEVELS = ("weak", "moderate", "strong")
EVIDENCE_LEVEL_PRIORITY = {"title": 1, "abstract": 2, "fulltext": 3}
ABSTRACT_ONLY_SCORE_CEILING = 70
TITLE_ONLY_SCORE_CEILING = 40
DEGRADED_PACKAGE_SCORE_CEILING = 85
MAX_EVIDENCE_ITEMS_PER_CLAIM = 8
MAX_ABSTRACT_EVIDENCE_ITEMS_PER_CLAIM = 6
MODEL_HEARTBEAT_INTERVAL_SECONDS = 4.0
SSE_POLL_INTERVAL_SECONDS = 1.0


STAGE_DISPLAY_DEFINITIONS = [
    {
        "key": "preprocess",
        "title": "输入预处理",
        "rules": [
            "规则化清洗用户输入与解析后的文件文本，保留缺失、截断与约束信息。",
            "预处理阶段不调用模型，只输出 clean_input、input_documents、input_digest、chunk_digest。",
            "输入为空时立即拦截，不进入后续主张提取与一致性评估。",
        ],
    },
    {
        "key": "claim_extract",
        "title": "文本解析与主张提取",
        "rules": [
            "统一由目标模型整批提取待核验主张并同步生成 query_plans。",
            "规则层只负责坏 JSON 修复、去重、过拆合并、字段补全和数量裁剪。",
            "每条主张必须具备 claim_id、text、assertion_type、keywords、conditions_or_scope、numeric_targets、confidence、source_excerpt、priority、query_plan。",
        ],
    },
    {
        "key": "retrieval",
        "title": "文献检索与证据组织",
        "rules": [
            "真实文献检索只允许走 NSTL/NSTR 服务，模型不得编造或替代检索结果。",
            "检索后由目标模型组织 evidence_pack，规则层负责真文献校验、去重、摘要级上限约束和降级标记。",
            "阶段输出必须包含 search_traces、evidence_pack_preview 和 retrieval_risks。",
        ],
    },
    {
        "key": "judgment",
        "title": "一致性判定",
        "rules": [
            "只允许输出五种判定状态：已被证实、部分被证实、存在争议、缺乏文献支持、与文献冲突。",
            "逐主张精评时只读取 claims、evidence_pack、retrieval_detail，不再回访检索服务。",
            "检索降级、证据缺失或仅摘要级支持时必须自动下调过强结论。",
        ],
    },
    {
        "key": "output",
        "title": "引用标注与最终输出",
        "rules": [
            "最终输出包在不改变阶段四事实判定的前提下生成 overall_conclusion、summary_text、risk_notes、rewrite_overview 和 final_report_markdown。",
            "规则层统一负责稳定引用编号、XSS 转义、引用合法性复核与字段裁剪。",
            "final_result 需要保持 legacy 兼容并额外输出 richer payload。",
        ],
    },
]

STAGE_RULES_MAP = {item["key"]: item["rules"] for item in STAGE_DISPLAY_DEFINITIONS}
STAGE_TITLE_MAP = {item["key"]: item["title"] for item in STAGE_DISPLAY_DEFINITIONS}


def _json_prompt(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


CLAIM_EXTRACT_SYSTEM_PROMPT = (
    "你是科技文献一致性评估系统的主张提取器。"
    "只能输出 JSON，不输出思维链，不编造来源。"
)

RETRIEVAL_EVIDENCE_SYSTEM_PROMPT = (
    "你是科技文献一致性评估系统的证据组织器。"
    "你只能基于给定的真实检索结果生成 JSON，不得创造不存在的文献或 reference_id。"
)

JUDGMENT_SYSTEM_PROMPT = (
    "你是科技文献一致性评估系统的一致性判定器。"
    "你只能基于给定主张和证据输出 JSON，不输出思维链。"
)

OUTPUT_SYSTEM_PROMPT = (
    "你是科技文献一致性评估系统的结果包装器。"
    "你不能改写既有状态或文献身份字段，只能生成总结、风险提示、改写建议与 Markdown 报告。"
)


def build_claim_extract_user_prompt(payload: dict[str, Any], *, compact: bool = False) -> str:
    requirements = [
        "只输出 JSON，顶层结构为 {\"claims\": [...]}。",
        "每条 claim 包含 claim_id、text、assertion_type、keywords、conditions_or_scope、numeric_targets、confidence、source_excerpt、priority、query_plan。",
        "query_plan 包含 query_text、must_terms、optional_terms、exclusion_terms、filters、reason。",
        "reason 必须是给用户看的中文短句，说明为什么这样检索；不要写 claim_1、evidence_id 或内部处理过程。",
        "只提取需要文献核验的科研主张，不输出常识性废话或思维过程。",
    ]
    if compact:
        requirements = requirements[:3]
    return _json_prompt(
        {
            "task": "从输入文本中提取可核验科研主张，并为每条主张生成检索计划。",
            "max_claims": payload.get("max_claims", CONSISTENCY_EVALUATION_MAX_CLAIMS),
            "requirements": requirements,
            "input_digest": payload.get("input_digest", {}),
            "chunk_digest": payload.get("chunk_digest", [])[:8],
            "clean_input": str(payload.get("clean_input") or "")[:16000],
        }
    )


def build_retrieval_evidence_user_prompt(payload: dict[str, Any], *, compact: bool = False) -> str:
    requirements = [
        "只输出 JSON，结构为 {\"claim_id\": \"...\", \"evidence_pack\": [...], \"retrieval_risks\": [...]}。",
        "evidence_pack 中每项包含 evidence_id、reference_id、relation、evidence_strength、evidence_level、snippet、why_relevant。",
        "relation 只允许 support/conflict/background/uncertain。",
        "只能引用提供的 reference_id，不得创造新的文献身份。",
        "snippet 和 why_relevant 必须面向用户、简洁中文表达；解释文字中不要写 claim_1、claim_id 等机器标签。",
    ]
    if compact:
        requirements = requirements[:3]
    return _json_prompt(
        {
            "task": "基于给定真实检索结果，为单条主张组织可追溯的证据包。",
            "requirements": requirements,
            "claim": payload.get("claim", {}),
            "retrieval_detail": payload.get("retrieval_detail", {}),
            "references": payload.get("references", [])[:12],
        }
    )


def build_judgment_user_prompt(payload: dict[str, Any], *, compact: bool = False) -> str:
    requirements = [
        "只输出 JSON，结构为 {\"claim_id\": \"...\", \"status\": \"...\", \"explanation\": \"...\", \"suggestion\": \"...\", \"confidence\": 0-1, \"support_ids\": [], \"conflict_ids\": [], \"background_ids\": [], \"limitations\": []}。",
        "status 只允许五种：已被证实、部分被证实、存在争议、缺乏文献支持、与文献冲突。",
        "suggestion 必须尽量给出可直接替换原句的改写表达。",
        "只能引用给定 evidence_id，不能编造新证据。",
        "explanation、suggestion 和 limitations 必须是用户可读的中文短句，不输出思维链，不使用 claim_1 等机器标签。",
    ]
    if compact:
        requirements = requirements[:3]
    return _json_prompt(
        {
            "task": "根据单条主张的证据包输出一致性判定。",
            "requirements": requirements,
            "allowed_statuses": VALID_JUDGMENT_STATUSES,
            "claim": payload.get("claim", {}),
            "evidence_pack": payload.get("evidence_pack", [])[:12],
            "retrieval_detail": payload.get("retrieval_detail", {}),
        }
    )


def build_output_user_prompt(payload: dict[str, Any], *, compact: bool = False) -> str:
    requirements = [
        "只输出 JSON，结构为 {\"overall_conclusion\": \"...\", \"summary_text\": \"...\", \"risk_notes\": [...], \"rewrite_overview\": [...], \"final_report_markdown\": \"...\"}。",
        "不得改写 claims 的 status、reference_id、evidence_id 和引用事实。",
        "risk_notes 聚焦检索降级、摘要级证据、引用覆盖不足等真实风险。",
        "rewrite_overview 输出可直接替换原句的改写建议，按 claim_id 对齐。",
        "final_report_markdown 使用稳定引用编号 [R1]、[R2] ...。",
    ]
    if compact:
        requirements = requirements[:3]
    return _json_prompt(
        {
            "task": "基于既有主张判定与稳定引用，生成最终评估包。",
            "requirements": requirements,
            "summary": payload.get("summary", {}),
            "claims": payload.get("claims", []),
            "references": payload.get("references", [])[:20],
            "citation_map": payload.get("citation_map", {}),
        }
    )


PromptBuilder = Callable[[dict[str, Any]], str]


@dataclass(frozen=True)
class ModelStageConfig:
    stage_key: str
    system_prompt: str
    prompt_builder: PromptBuilder
    compact_prompt_builder: PromptBuilder
    timeout: int
    retries: int = 1


def _claim_builder(payload: dict[str, Any]) -> str:
    return build_claim_extract_user_prompt(payload, compact=False)


def _claim_compact_builder(payload: dict[str, Any]) -> str:
    return build_claim_extract_user_prompt(payload, compact=True)


def _retrieval_builder(payload: dict[str, Any]) -> str:
    return build_retrieval_evidence_user_prompt(payload, compact=False)


def _retrieval_compact_builder(payload: dict[str, Any]) -> str:
    return build_retrieval_evidence_user_prompt(payload, compact=True)


def _judgment_builder(payload: dict[str, Any]) -> str:
    return build_judgment_user_prompt(payload, compact=False)


def _judgment_compact_builder(payload: dict[str, Any]) -> str:
    return build_judgment_user_prompt(payload, compact=True)


def _output_builder(payload: dict[str, Any]) -> str:
    return build_output_user_prompt(payload, compact=False)


def _output_compact_builder(payload: dict[str, Any]) -> str:
    return build_output_user_prompt(payload, compact=True)


MODEL_STAGE_CONFIGS = {
    "claim_extract": ModelStageConfig(
        stage_key="claim_extract",
        system_prompt=CLAIM_EXTRACT_SYSTEM_PROMPT,
        prompt_builder=_claim_builder,
        compact_prompt_builder=_claim_compact_builder,
        timeout=max(int(MODEL_TIMEOUT or 90), 120),
    ),
    "retrieval": ModelStageConfig(
        stage_key="retrieval",
        system_prompt=RETRIEVAL_EVIDENCE_SYSTEM_PROMPT,
        prompt_builder=_retrieval_builder,
        compact_prompt_builder=_retrieval_compact_builder,
        timeout=max(int(MODEL_TIMEOUT or 90), 150),
    ),
    "judgment": ModelStageConfig(
        stage_key="judgment",
        system_prompt=JUDGMENT_SYSTEM_PROMPT,
        prompt_builder=_judgment_builder,
        compact_prompt_builder=_judgment_compact_builder,
        timeout=max(int(MODEL_TIMEOUT or 90), 120),
    ),
    "output": ModelStageConfig(
        stage_key="output",
        system_prompt=OUTPUT_SYSTEM_PROMPT,
        prompt_builder=_output_builder,
        compact_prompt_builder=_output_compact_builder,
        timeout=max(int(MODEL_TIMEOUT or 90), 150),
    ),
}


def get_model_stage_config(stage_key: str) -> ModelStageConfig:
    if stage_key not in MODEL_STAGE_CONFIGS:
        raise KeyError(f"Unknown model stage: {stage_key}")
    return MODEL_STAGE_CONFIGS[stage_key]


def build_model_recovery_chain(stage_key: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    config = get_model_stage_config(stage_key)
    backup_model = DEEPSEEK_MODEL or MODEL_NAME
    backup_api_key = DEEPSEEK_API_KEY or MODEL_API_KEY
    backup_base_url = (DEEPSEEK_BASE_URL or MODEL_BASE_URL).rstrip("/")
    backup_timeout = max(int(DEEPSEEK_TIMEOUT or MODEL_TIMEOUT or 90), config.timeout)
    return [
        {
            "label": "primary_prompt",
            "system_prompt": config.system_prompt,
            "user_prompt": config.prompt_builder(payload),
            "model": MODEL_NAME,
            "api_key": MODEL_API_KEY,
            "base_url": MODEL_BASE_URL,
            "timeout": config.timeout,
        },
        {
            "label": "compact_prompt",
            "system_prompt": config.system_prompt,
            "user_prompt": config.compact_prompt_builder(payload),
            "model": MODEL_NAME,
            "api_key": MODEL_API_KEY,
            "base_url": MODEL_BASE_URL,
            "timeout": config.timeout,
        },
        {
            "label": "backup_model_compact_prompt",
            "system_prompt": config.system_prompt,
            "user_prompt": config.compact_prompt_builder(payload),
            "model": backup_model,
            "api_key": backup_api_key,
            "base_url": backup_base_url,
            "timeout": backup_timeout,
        },
    ]
