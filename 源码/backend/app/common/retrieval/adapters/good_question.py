"""好问题智能体检索适配器。

公共检索客户端只返回 StandardPaper；本适配器负责把它映射成好问题
智能体前端和后续分析使用的 EvidenceItem。
"""

from __future__ import annotations

from app.agents.good_question.schemas import EvidenceItem, EvidenceNeed
from app.common.retrieval.schemas import SearchRequest, StandardPaper


class GoodQuestionSearchAdapter:
    """好问题智能体与公共检索客户端之间的转换层。"""

    source_agent = "good_question"

    def to_search_request(
        self,
        *,
        evidence_need: EvidenceNeed,
        topic: str,
        user_scope: str | None,
        standardized_question: str,
        request_id: str | None = None,
    ) -> SearchRequest:
        """将标准化问题对应的 EvidenceNeed 转成公共 SearchRequest。"""
        year_range = self._year_range(evidence_need)
        return SearchRequest(
            query=evidence_need.query,
            paper_num=evidence_need.top_k,
            year_range=year_range,
            languages=evidence_need.languages or ["zh", "en"],
            rerank=True,
            user_scope=user_scope,
            request_id=request_id,
            source_agent=self.source_agent,
            context={
                "topic": topic,
                "standardized_question": standardized_question,
                "evidence_purpose": evidence_need.purpose,
                "evidence_need_id": evidence_need.evidence_need_id,
            },
        )

    def to_evidence_items(
        self,
        *,
        papers: list[StandardPaper],
        evidence_need: EvidenceNeed,
        evidence_group_id: str = "standard",
    ) -> list[EvidenceItem]:
        """将 StandardPaper 列表映射为 EvidenceItem 列表。"""
        items: list[EvidenceItem] = []
        for paper_index, paper in enumerate(papers, start=1):
            nstl_detail_url = (
                f"https://www.nstl.gov.cn/paper_detail.html?id={paper.paper_id}"
                if paper.paper_id
                else ""
            )
            item = EvidenceItem(
                evidence_id=f"evi_{evidence_group_id}_{paper_index}",
                evidence_need_id=evidence_need.evidence_need_id,
                source_type=f"nstl_{paper.source}",
                title=paper.title,
                authors=paper.authors,
                year=self._normalize_year(paper.year),
                venue=paper.venue,
                doi=paper.doi,
                url=paper.url,
                nstl_url=nstl_detail_url,
                language=paper.language or "zh",
                abstract=paper.abstract,
                score=round(paper.final_score, 4),
                retrieval_query=evidence_need.query,
                support_summary=paper.abstract[:200] if paper.abstract else "",
            )
            items.append(item)
        return items

    def _year_range(self, evidence_need: EvidenceNeed) -> tuple[int, int] | None:
        if len(evidence_need.year_range) >= 2:
            return (evidence_need.year_range[0], evidence_need.year_range[1])
        return None

    def _normalize_year(self, value: int) -> int:
        try:
            year = int(value)
        except (TypeError, ValueError):
            year = 2026
        return max(1900, min(year, 2100))
