from __future__ import annotations

from typing import Any

import ai_graph.graph as graph
from ai_graph.graph import strategy_candidate_cards
from ai_graph.llm import role_calls


class _CapturingClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.request = None

    def generate_json(self, request):  # type: ignore[no-untyped-def]
        self.request = request
        return self.response


def _evidence(publisher: str, published_at: str = "2026-09-03T00:00:00+00:00") -> dict[str, str]:
    return {
        "publisher": publisher,
        "title": f"{publisher} 반도체 산업 보고서",
        "url": f"https://research.example/{publisher}",
        "published_at": published_at,
        "analyst": "홍길동",
        "claim": "재고 정상화와 주문 회복이 동시 진행된다는 분석입니다.",
        "source_kind": "original_analyst_report",
    }


def _candidate(*, metric_ids: list[str] | None = None, evidence: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "strategy_id": "semiconductor_inventory_cycle",
        "title": "반도체 재고 정상화 가설",
        "summary": "재고 정상화가 가격 모멘텀으로 전이되는지를 검증합니다.",
        "key_conditions": ["상대강도", "거래량 확인"],
        "reason": "서로 다른 두 애널리스트 리포트가 같은 공급망 회복 메커니즘을 지적했습니다.",
        "sector": "반도체",
        "mechanism": "inventory normalization",
        "metric_ids": metric_ids or ["relative_strength_20d", "volume_ratio_20"],
        "backtest_query": "KRX 반도체 유니버스에서 relative_strength_20d와 volume_ratio_20을 사용해 20거래일 보유 전략을 백테스트한다.",
        "counter_hypothesis": "수요 회복이 이미 가격에 반영됐을 수 있습니다.",
        "failure_regime": "메모리 가격이 재차 하락하는 국면",
        "evidence": evidence or [_evidence("증권사A"), _evidence("증권사B")],
        "price_target_only": False,
        "consensus_only": False,
    }


def _install_live_client(monkeypatch, payload: dict[str, Any]) -> _CapturingClient:
    client = _CapturingClient(payload)
    monkeypatch.setattr(role_calls, "is_live_llm_provider", lambda: True)
    monkeypatch.setattr(role_calls, "create_llm_client", lambda *, role: client)
    return client


def test_analyst_candidate_research_requests_web_evidence_and_scores_cards(monkeypatch) -> None:
    client = _install_live_client(monkeypatch, {"cards": [_candidate()]})

    cards = role_calls.generate_analyst_strategy_candidates(
        query="최근 반도체 동향으로 백테스트 후보를 찾아줘",
        research_as_of="2026-09-05T00:00:00+00:00",
        allowed_metrics=["relative_strength_20d", "volume_ratio_20"],
    )

    assert client.request is not None
    assert client.request.enable_web_search is True
    assert client.request.require_web_search is True
    assert client.request.web_search_context_size == "high"
    assert client.request.prompt_template_name == "analyst_candidate_research"
    assert client.request.prompt_version == "v1"
    assert "two independent analyst publishers" in client.request.system_prompt
    assert len(cards) == 1
    assert cards[0].backtest_query is not None
    assert cards[0].confidence == 1.0
    assert cards[0].confidence_breakdown is not None
    assert cards[0].confidence_breakdown.score == 100
    assert len(cards[0].research_sources) == 2


def test_analyst_candidate_research_rejects_unsupported_metric_and_stale_source(monkeypatch) -> None:
    stale = [_evidence("증권사A", "2026-07-01T00:00:00+00:00"), _evidence("증권사B")]
    _install_live_client(
        monkeypatch,
        {"cards": [_candidate(metric_ids=["imaginary_metric"]), _candidate(evidence=stale)]},
    )

    cards = role_calls.generate_analyst_strategy_candidates(
        query="후보",
        research_as_of="2026-09-05T00:00:00+00:00",
        allowed_metrics=["relative_strength_20d", "volume_ratio_20"],
    )

    assert cards == []


def test_candidate_card_wrapper_never_restores_static_fallback() -> None:
    assert strategy_candidate_cards() == []
    assert strategy_candidate_cards("RSI 평균회귀") == []
    assert not hasattr(graph, "_static_strategy_candidate_cards")
