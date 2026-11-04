from __future__ import annotations

from typing import Any

from app.pipeline.model_gateway import ModelGateway
from app.pipeline.progress import ProgressWriter
from app.pipeline.stages.claim_extract import run_claim_extract
from app.pipeline.stages.judgment import run_judgment
from app.pipeline.stages.output import run_output
from app.pipeline.stages.preprocess import run_preprocess
from app.pipeline.stages.retrieval import run_retrieval
from app.pipeline.state import PipelineState


class ConsistencyPipelineEngine:
    def __init__(self, file_repo: Any, progress: ProgressWriter) -> None:
        self.file_repo = file_repo
        self.progress = progress
        self.model_gateway = ModelGateway()

    def run(self, state: PipelineState) -> PipelineState:
        previous_degradation_count = 0

        self.progress.start("preprocess", "正在整理用户输入、解析文件和约束条件")
        state = run_preprocess(state, self.file_repo, self.progress)
        self.progress.complete(
            "preprocess",
            f"已整理 {len(state.input_documents)} 份输入文档，共 {state.input_digest.get('total_chars', 0)} 字符",
            {
                "input_digest": state.input_digest,
                "input_summary_text": state.stage_results.get("preprocess", {}).get("input_summary_text", ""),
                "clean_input": state.clean_input[:1200],
                "chunk_digest": state.chunk_digest,
            },
            self._new_degradations(state, previous_degradation_count),
        )
        previous_degradation_count = len(state.degradations)

        self.progress.start("claim_extract", "正在提取主张并生成检索计划")
        state = run_claim_extract(state, self.model_gateway, self.progress)
        self.progress.complete(
            "claim_extract",
            f"提取 {len(state.claims)} 条待评估主张并生成检索计划",
            {
                "claims_preview": state.claims[:6],
                "query_plans": state.query_plans[:6],
                "quality_flags": state.stage_results.get("claim_extract", {}).get("quality_flags", []),
                "progress_message": "已完成主张提取、检索计划生成和规则校验",
                "completed_claims": len(state.claims),
                "total_claims": len(state.claims),
                "sub_steps": [
                    {"name": "模型整批提取主张", "status": "completed"},
                    {"name": "检索计划生成", "status": "completed"},
                    {"name": "规则校验与修复", "status": "completed"},
                ],
            },
            self._new_degradations(state, previous_degradation_count),
        )
        previous_degradation_count = len(state.degradations)

        self.progress.start("retrieval", "正在调用 NSTL/NSTR 检索并组织证据")
        state = run_retrieval(state, self.model_gateway, self.progress)
        retrieved = sum(len(items) for items in state.retrieval_results.values())
        self.progress.complete(
            "retrieval",
            f"完成 {len(state.claims)} 条主张检索，获得 {retrieved} 条真实文献候选并组织证据",
            {
                "search_traces": state.retrieval_detail.get("search_traces", []),
                "literature_preview": state.stage_results.get("retrieval", {}).get("literature_preview", []),
                "evidence_pack_preview": state.stage_results.get("retrieval", {}).get("evidence_pack_preview", []),
                "retrieval_risks": state.stage_results.get("retrieval", {}).get("retrieval_risks", []),
                "retrieved_count": retrieved,
                "max_references_total": state.retrieval_detail.get("max_references_total"),
                "progress_message": f"已保留 {retrieved} 篇来源文献并完成证据组织",
                "completed_claims": len(state.claims),
                "total_claims": len(state.claims),
                "sub_steps": [
                    {"name": "构造公共 SearchRequest", "status": "completed"},
                    {"name": "统一检索网关调用", "status": "completed"},
                    {"name": "模型组织证据包", "status": "completed"},
                    {"name": "真文献校验与去重", "status": "completed"},
                ],
            },
            self._new_degradations(state, previous_degradation_count),
        )
        previous_degradation_count = len(state.degradations)

        self.progress.start("judgment", "正在执行逐主张一致性判定")
        state = run_judgment(state, self.model_gateway, self.progress)
        self.progress.complete(
            "judgment",
            f"完成 {len(state.judgments)} 条主张的一致性判定",
            {
                "judgment_preview": state.judgments[:6],
                "status_distribution": state.stage_results.get("judgment", {}).get("status_distribution", {}),
                "review_flags": state.stage_results.get("judgment", {}).get("review_flags", []),
                "progress_message": "已完成逐主张一致性判定和结论校验",
                "completed_claims": len(state.judgments),
                "total_claims": len(state.claims),
                "sub_steps": [
                    {"name": "逐主张精评", "status": "completed"},
                    {"name": "强结论下调校验", "status": "completed"},
                    {"name": "可直接改写建议生成", "status": "completed"},
                ],
            },
            self._new_degradations(state, previous_degradation_count),
        )
        previous_degradation_count = len(state.degradations)

        self.progress.start("output", "正在生成引用、结论和最终评估包")
        state = run_output(state, self.model_gateway, self.progress)
        self.progress.complete(
            "output",
            "已生成最终一致性评估结果与 Markdown 报告",
            {
                "citation_map": state.final_result.get("citation_map", {}),
                "overall_conclusion": state.final_result.get("overall_conclusion", ""),
                "package_preview": state.stage_results.get("output", {}).get("package_preview", {}),
                "summary": state.final_result.get("summary", {}),
                "progress_message": "已完成引用编号、最终评估包和报告组装",
                "sub_steps": [
                    {"name": "稳定引用编号", "status": "completed"},
                    {"name": "评估包生成", "status": "completed"},
                    {"name": "HTML 实体转义", "status": "completed"},
                    {"name": "最终报告组装", "status": "completed"},
                ],
            },
            self._new_degradations(state, previous_degradation_count),
        )

        self.progress.complete_task(state.final_result, state.input_digest)
        return state

    @staticmethod
    def _new_degradations(state: PipelineState, previous_count: int) -> list[dict[str, Any]]:
        return state.degradations[previous_count:]
