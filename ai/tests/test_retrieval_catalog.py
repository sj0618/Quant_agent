from ai_graph.retrieval.catalog import validate_catalog
from ai_graph.retrieval.search import search_retrieval_corpus


def test_retrieval_catalog_has_l1_l2_mvp_coverage() -> None:
    result = validate_catalog()

    assert result.ok, result.errors
    assert result.l1_count >= 50
    assert result.l2_count >= 150


def test_retrieval_catalog_smoke_finds_breakout_and_rsi_entries() -> None:
    breakout = search_retrieval_corpus("52주 신고가 거래량 150% 돌파", top_k=5)
    rsi = search_retrieval_corpus("RSI 30 상향 돌파 과매도 반등", top_k=5)

    assert any("breakout" in hit.snippet.lower() or "신고가" in hit.snippet for hit in breakout.hits)
    assert any("rsi" in hit.snippet.lower() for hit in rsi.hits)
