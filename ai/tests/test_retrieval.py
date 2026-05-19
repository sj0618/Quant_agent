from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_graph.retrieval.search import RetrievalDocument, load_markdown_corpus, search_retrieval_corpus


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
