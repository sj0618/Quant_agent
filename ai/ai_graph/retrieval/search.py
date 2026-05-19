from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_CORPUS_DIR = Path(__file__).resolve().parent
DOCUMENT_GLOB = "l*.md"
TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣_]+")
MIN_QUERY_TOKEN_LENGTH = 2
SNIPPET_RADIUS = 90

RetrievalLevel = Literal["L1", "L2"]


class RetrievalDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    level: RetrievalLevel
    title: str
    body: str
    path: str

    @field_validator("document_id", "title", "body", "path")
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized


class RetrievalHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    level: RetrievalLevel
    title: str
    score: float = Field(ge=0.0)
    snippet: str
    source_path: str


class RetrievalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    hits: list[RetrievalHit]
    corpus_size: int = Field(ge=0)


@dataclass(frozen=True)
class _ScoredDocument:
    document: RetrievalDocument
    score: float
    snippet: str


def load_markdown_corpus(corpus_dir: Path | None = None) -> list[RetrievalDocument]:
    """Load bundled L1/L2 markdown evidence without network access."""

    root = corpus_dir or DEFAULT_CORPUS_DIR
    documents: list[RetrievalDocument] = []
    for path in sorted(root.glob(DOCUMENT_GLOB)):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        documents.append(_parse_markdown_document(path, text))
    return documents


def search_retrieval_corpus(
    query: str,
    *,
    documents: Iterable[RetrievalDocument] | None = None,
    top_k: int = 5,
) -> RetrievalResponse:
    """Return deterministic local evidence hits for a natural-language strategy query."""

    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be empty")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    corpus = list(documents) if documents is not None else load_markdown_corpus()
    query_tokens = _tokenize(normalized_query)
    scored = [
        scored_document
        for document in corpus
        if (scored_document := _score_document(document, query_tokens)).score > 0
    ]
    scored.sort(
        key=lambda item: (-item.score, item.document.level, item.document.document_id)
    )

    hits = [
        RetrievalHit(
            document_id=item.document.document_id,
            level=item.document.level,
            title=item.document.title,
            score=round(item.score, 4),
            snippet=item.snippet,
            source_path=item.document.path,
        )
        for item in scored[:top_k]
    ]
    return RetrievalResponse(query=normalized_query, hits=hits, corpus_size=len(corpus))


def _parse_markdown_document(path: Path, text: str) -> RetrievalDocument:
    title = _first_heading(text) or path.stem.replace("_", " ").title()
    level = _infer_level(path, title)
    return RetrievalDocument(
        document_id=path.stem,
        level=level,
        title=title,
        body=text.strip(),
        path=str(path),
    )


def _infer_level(path: Path, title: str) -> RetrievalLevel:
    marker = f"{path.stem} {title}".lower()
    if "l2" in marker:
        return "L2"
    return "L1"


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return None


def _score_document(
    document: RetrievalDocument, query_tokens: set[str]
) -> _ScoredDocument:
    haystack = document.body.lower()
    title = document.title.lower()
    score = 0.0
    first_match_index: int | None = None
    for token in query_tokens:
        occurrences = haystack.count(token)
        if occurrences == 0:
            continue
        score += float(occurrences)
        if token in title:
            score += 2.0
        index = haystack.find(token)
        if first_match_index is None or index < first_match_index:
            first_match_index = index

    if first_match_index is None:
        return _ScoredDocument(
            document=document, score=0.0, snippet=document.body[:SNIPPET_RADIUS]
        )
    return _ScoredDocument(
        document=document,
        score=score,
        snippet=_snippet(document.body, first_match_index),
    )


def _tokenize(text: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN_PATTERN.findall(text)
        if len(token.strip()) >= MIN_QUERY_TOKEN_LENGTH
    }


def _snippet(text: str, index: int) -> str:
    start = max(0, index - SNIPPET_RADIUS)
    end = min(len(text), index + SNIPPET_RADIUS)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"
