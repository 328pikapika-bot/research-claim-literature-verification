from __future__ import annotations

from typing import Any

from app.common.retrieval.client import LiteratureSearchClient
from app.common.retrieval.schemas import SearchRequest, StandardPaper


class ClaimConsistencySearchAdapter:
    """Adapter from claim-consistency business claims to public retrieval requests."""

    def __init__(self, client: LiteratureSearchClient | None = None) -> None:
        self.client = client or LiteratureSearchClient()

    def build_request(
        self,
        claim: dict[str, Any],
        *,
        user_scope: str,
        year_range: list[int] | tuple[int, int] | None,
        languages: list[str],
        paper_num: int,
        task_id: str,
    ) -> SearchRequest:
        keywords = " ".join(str(item) for item in claim.get("keywords", []) if item)
        query = str(claim.get("text") or "").strip()
        if keywords:
            query = f"{query} {keywords}".strip()
        parsed_year_range = None
        if year_range and len(year_range) >= 2:
            start_year, end_year = sorted((int(year_range[0]), int(year_range[1])))
            parsed_year_range = (start_year, end_year)
        return SearchRequest(
            query=query,
            paper_num=paper_num,
            year_range=parsed_year_range,
            languages=languages,
            rerank=True,
            intent_classification=True,
            solr_type=2,
            user_scope=user_scope,
            source_agent="claim_consistency",
            request_id=f"{task_id}:{claim.get('claim_id', '')}",
            context={"claim_id": claim.get("claim_id"), "claim_text": claim.get("text")},
        )

    def search_multi(
        self,
        requests: list[SearchRequest],
        *,
        max_concurrency: int,
    ):
        return self.client.search_multi_sync(requests, max_concurrency=max_concurrency)


def paper_to_literature_item(paper: StandardPaper, reference_id: str) -> dict[str, Any]:
    return {
        "reference_id": reference_id,
        "paper_id": paper.paper_id or reference_id,
        "source": paper.source,
        "title": paper.title,
        "authors": paper.authors,
        "year": paper.year,
        "venue": paper.venue,
        "doi": paper.doi,
        "url": paper.url,
        "language": paper.language,
        "abstract": paper.abstract,
        "keywords": paper.keywords,
        "doc_type": paper.doc_type,
        "index_level": paper.index_level,
        "has_fulltext": paper.has_fulltext,
        "retrieval_query": paper.retrieval_query,
        "retrieval_score": paper.retrieval_score,
        "quality_score": paper.quality_score,
        "final_score": paper.final_score,
        "citation_count": paper.citation_count,
    }
