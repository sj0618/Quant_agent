from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_graph.retrieval.search import (
    RetrievalDocument,
    load_markdown_corpus,
    search_retrieval_corpus,
)


def test_loads_l1_l2_fixture_corpus_without_network():
    corpus = load_markdown_corpus()

    assert {document.level for document in corpus} == {"L1", "L2"}
    assert all(Path(document.path).exists() for document in corpus)


def test_search_returns_ranked_research_and_signal_hits():
    response = search_retrieval_corpus("KRX 삼성전자 RSI 후보 리서치 signal", top_k=2)

    assert response.corpus_size >= 2
    assert len(response.hits) == 2
    assert response.hits[0].score >= response.hits[1].score
    assert {hit.level for hit in response.hits} == {"L1", "L2"}


def test_search_preserves_l1_l2_diversity_when_one_level_dominates_scores():
    documents = [
        RetrievalDocument(
            document_id="l1-high",
            level="L1",
            title="RSI RSI",
            body="RSI RSI RSI RSI",
            path="/tmp/l1-high.md",
        ),
        RetrievalDocument(
            document_id="l1-next",
            level="L1",
            title="RSI",
            body="RSI RSI",
            path="/tmp/l1-next.md",
        ),
        RetrievalDocument(
            document_id="l2-match",
            level="L2",
            title="RSI",
            body="RSI",
            path="/tmp/l2-match.md",
        ),
    ]

    response = search_retrieval_corpus("RSI", documents=documents, top_k=2)

    assert [hit.document_id for hit in response.hits] == ["l1-high", "l2-match"]
    assert {hit.level for hit in response.hits} == {"L1", "L2"}
    assert response.hits[0].score >= response.hits[1].score


def test_strategy_prompt_playbook_covers_value_and_breakout_queries():
    value_response = search_retrieval_corpus("저PER 고ROE 부채비율 100% 가치주", top_k=3)
    breakout_response = search_retrieval_corpus("52주 신고가 거래량 150% 모멘텀", top_k=3)

    assert any(hit.document_id == "l1_screening_strategy_playbook" for hit in value_response.hits)
    assert any(hit.document_id == "l2_screening_indicator_mapping" for hit in breakout_response.hits)


def test_retrieval_document_rejects_extra_fields():
    with pytest.raises(ValidationError):
        RetrievalDocument(
            document_id="doc",
            level="L1",
            title="Title",
            body="Body",
            path="/tmp/doc.md",
            internal_payload={"leak": True},
        )
