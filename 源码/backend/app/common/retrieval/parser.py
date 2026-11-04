"""统一检索网关响应解析。"""

from __future__ import annotations

import logging
from typing import Any

from app.common.retrieval.schemas import StandardPaper

logger = logging.getLogger(__name__)


class SearchResultParser:
    """将检索网关原始响应转换为 StandardPaper。"""

    def parse(self, response_data: dict[str, Any], query: str) -> list[StandardPaper]:
        """解析 NSTL 网关返回的 JSON 数据，单条异常不影响整批结果。"""
        papers: list[StandardPaper] = []
        data_list = response_data.get("data", [])
        if not isinstance(data_list, list):
            logger.warning("NSTL 响应 data 字段不是数组，返回空结果")
            return papers

        for item in data_list:
            if not isinstance(item, dict):
                continue
            try:
                papers.append(self._parse_item(item, query))
            except Exception as exc:
                logger.warning("跳过无法解析的文献记录: %s", exc)
        return papers

    def _parse_item(self, item: dict[str, Any], query: str) -> StandardPaper:
        authors = self._parse_authors(
            item.get("hasAuthor") or item.get("authors") or item.get("author") or []
        )

        keywords = item.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = []

        return StandardPaper(
            paper_id=str(item.get("id", "")),
            source=str(item.get("source", "nstl")),
            title=str(item.get("title", "")),
            authors=authors,
            year=self._safe_int(item.get("year", 0)),
            venue=self._parse_venue(item.get("hasSource", "")),
            doi=str(item.get("doi", "")),
            url=str(item.get("hasFile", "")),
            language=str(item.get("language", "")) or "zh",
            abstract=str(item.get("abstract", "")),
            keywords=[str(keyword) for keyword in keywords],
            doc_type=str(item.get("docType", item.get("doc_type", "JournalPaper"))),
            index_level=str(item.get("indexLevel", item.get("index_level", ""))),
            has_fulltext=bool(item.get("hasFulltext", item.get("has_fulltext", False))),
            retrieval_query=query,
            retrieval_score=self._safe_float(item.get("score", 0.0)),
            rrf_score=self._safe_float(item.get("rrf_score", 0.0)),
            quality_score=self._safe_float(item.get("quality_score", 0.0)),
            final_score=self._safe_float(item.get("final_score", item.get("score", 0.0))),
            rerank_score=(
                self._safe_float(item["rerank_score"])
                if item.get("rerank_score") is not None
                else None
            ),
            citation_count=self._safe_int(item.get("citation_count", 0)),
            references=item.get("references", []) if isinstance(item.get("references"), list) else [],
            raw=item,
        )

    def _parse_authors(self, value: Any) -> list[str]:
        """Normalize NSTL author fields to a list of display names."""
        if value is None:
            return []
        if isinstance(value, str):
            return [
                name.strip()
                for name in value.replace("；", ";").replace("\n", ";").split(";")
                if name.strip()
            ]
        if isinstance(value, dict):
            full_name = value.get("fullName") or value.get("name") or value.get("authorName")
            return [str(full_name).strip()] if full_name and str(full_name).strip() else []
        if isinstance(value, list):
            authors: list[str] = []
            for author in value:
                authors.extend(self._parse_authors(author))
            return authors
        return []

    def _safe_int(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _safe_float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _parse_venue(self, has_source: Any) -> str:
        """解析期刊/来源信息，兼容 dict 和 string 两种格式。

        NSTL 网关返回的 hasSource 通常是期刊名字符串，但部分记录
        会返回完整 dict（含 volume/issue/title 等字段）。
        """
        if isinstance(has_source, str):
            return has_source
        if isinstance(has_source, dict):
            return str(has_source.get("title", "") or "")
        return str(has_source) if has_source else ""
