from __future__ import annotations

from hashlib import sha256
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from ai_graph.retrieval.search import RetrievalHit, search_retrieval_corpus

DEFAULT_TOP_K = 5


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str:
        """Return a deterministic completion for the supplied prompt."""


class MockResearchLLM:
    """Default offline LLM client used by tests and local development."""

    def complete(self, prompt: str) -> str:
        return "mock-research-summary: " + prompt[:120]


class ResearchEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    level: str
    title: str
    snippet: str
    score: float = Field(ge=0.0)
    source_path: str


class ResearchSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    debug_ref: str
    query: str
    summary: str
    evidence: list[ResearchEvidence]
    candidate_tickers: list[str] = Field(default_factory=list)


def build_research_summary(
    query: str,
    *,
    trace_id: str | None = None,
    llm_client: LLMClient | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> ResearchSummary:
    normalized_query = " ".join(query.strip().split())
    if not normalized_query:
        raise ValueError("query must not be empty")

    trace = trace_id or _trace_id(normalized_query)
    retrieval = search_retrieval_corpus(normalized_query, top_k=top_k)
    prompt = _format_prompt(normalized_query, retrieval.hits)
    summary_text = (llm_client or MockResearchLLM()).complete(prompt)
    evidence = [_to_evidence(hit) for hit in retrieval.hits]
    return ResearchSummary(
        trace_id=trace,
        debug_ref=f"research:{trace}",
        query=normalized_query,
        summary=summary_text,
        evidence=evidence,
        candidate_tickers=_candidate_tickers(normalized_query),
    )


def research_node(state: dict[str, Any]) -> dict[str, Any]:
    query = str(state.get("user_query") or state.get("query") or "")
    result = build_research_summary(query, trace_id=state.get("trace_id"))
    return {
        "research": result.model_dump(),
        "trace_id": result.trace_id,
        "debug_ref": result.debug_ref,
    }


def _format_prompt(query: str, hits: list[RetrievalHit]) -> str:
    evidence_lines = [f"- [{hit.level}] {hit.title}: {hit.snippet}" for hit in hits]
    return "\n".join([f"Query: {query}", "Evidence:", *evidence_lines])


def _to_evidence(hit: RetrievalHit) -> ResearchEvidence:
    return ResearchEvidence(
        evidence_id=hit.document_id,
        level=hit.level,
        title=hit.title,
        snippet=hit.snippet,
        score=hit.score,
        source_path=hit.source_path,
    )


def _candidate_tickers(query: str) -> list[str]:
    lowered = query.lower()
    tickers: list[str] = []
    if "삼성" in lowered or "samsung" in lowered:
        tickers.append("005930")
    if "sk" in lowered or "하이닉스" in lowered:
        tickers.append("000660")
    return tickers


def _trace_id(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:16]
