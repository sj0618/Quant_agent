from __future__ import annotations

import pytest

from ai_graph.data_sources.db import available_indicator_metrics
from ai_graph.llm.base import LLMJsonRequest
from ai_graph.nodes.strategy_research import research_strategy_execution_spec
from ai_graph.research_contract import RuleDraftSigner, build_rule_draft
from ai_graph.strategy_parser import StrategyParseError, parse_natural_language_strategy


class _StructuredClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.requests: list[LLMJsonRequest] = []

    def generate_json(self, request: LLMJsonRequest) -> dict:
        self.requests.append(request)
        return self.payload


def _payload(**overrides: object) -> dict:
    payload = {
        "market": "KRX",
        "timeframe": "daily",
        "entry_conditions": [
            {"metric": "rsi", "comparator": "lte", "value": 30, "lookback": 14, "role": "entry"}
        ],
        "exit_conditions": [
            {"metric": "sma_20", "comparator": "gte", "value": 100, "lookback": 20, "role": "exit"}
        ],
        "unsupported_conditions": [],
        "clarification_required": False,
        "explanation": "지표와 진입·종료 조건을 구조화했습니다.",
    }
    return {**payload, **overrides}


def test_live_json_selects_only_server_metrics_and_records_unsupported_conditions() -> None:
    client = _StructuredClient(
        _payload(
            entry_conditions=[
                {"metric": "rsi", "comparator": "lte", "value": 30, "lookback": 14, "role": "entry"},
                {"metric": "secret_indicator", "comparator": "gte", "value": 1, "lookback": 5, "role": "entry"},
            ]
        )
    )

    result = parse_natural_language_strategy(
        "과매도에서 진입하고 평균선에서 종료",
        available_metrics=["rsi", "sma20"],
        llm_client=client,
        use_llm=True,
    )

    assert [item.metric for item in result.entry_conditions] == ["rsi"]
    assert result.exit_conditions[0].metric == "sma20"
    assert result.clarification_required is True
    assert result.unsupported_conditions[0].condition.startswith("secret_indicator")
    assert client.requests[0].response_schema is not None
    assert "natural_language" in client.requests[0].user_prompt


def test_live_parser_keeps_an_unambiguous_korean_rsi_pair_out_of_the_provider() -> None:
    """A provider outage must not turn a complete RSI rule into a 409 admission."""

    client = _StructuredClient(_payload())

    result = parse_natural_language_strategy(
        "RSI가 30 이하이고 RSI가 70 이상인 일반 조건식을 검토해 주세요.",
        available_metrics=["rsi", "sma20"],
        llm_client=client,
        use_llm=True,
    )

    assert [(item.metric, item.comparator, item.value) for item in result.entry_conditions] == [
        ("rsi", "lte", 30.0)
    ]
    assert [(item.metric, item.comparator, item.value) for item in result.exit_conditions] == [
        ("rsi", "gte", 70.0)
    ]
    assert result.clarification_required is False
    assert client.requests == []


def test_non_live_parser_carries_rsi_across_a_natural_korean_exit_clause() -> None:
    """Beginners should not need to repeat "RSI" before the exit threshold."""

    result = parse_natural_language_strategy(
        "KRX 일봉에서 RSI가 30 이하일 때 진입하고 70 이상일 때 청산하는 전략을 최근 1년 구간으로 백테스트해줘.",
        available_metrics=["rsi", "sma20"],
        use_llm=False,
    )

    assert [(item.metric, item.comparator, item.value) for item in result.entry_conditions] == [
        ("rsi", "lte", 30.0)
    ]
    assert [(item.metric, item.comparator, item.value) for item in result.exit_conditions] == [
        ("rsi", "gte", 70.0)
    ]
    assert result.clarification_required is False


def test_live_parser_keeps_a_natural_korean_rsi_exit_pair_out_of_the_provider() -> None:
    """The normal beginner wording must not add an avoidable AOAI dependency."""

    client = _StructuredClient(_payload())
    result = parse_natural_language_strategy(
        "KRX 일봉에서 RSI가 30 이하일 때 진입하고 70 이상일 때 청산하는 전략을 최근 1년 구간으로 백테스트해줘.",
        available_metrics=["rsi", "sma20"],
        llm_client=client,
        use_llm=True,
    )

    assert [(item.metric, item.comparator, item.value) for item in result.entry_conditions] == [
        ("rsi", "lte", 30.0)
    ]
    assert [(item.metric, item.comparator, item.value) for item in result.exit_conditions] == [
        ("rsi", "gte", 70.0)
    ]
    assert result.clarification_required is False
    assert client.requests == []


def test_live_json_schema_errors_never_become_a_parseable_rule() -> None:
    client = _StructuredClient({**_payload(), "unexpected": True})

    with pytest.raises(StrategyParseError):
        parse_natural_language_strategy(
            "조건",
            available_metrics=["rsi", "sma20"],
            llm_client=client,
            use_llm=True,
        )


def test_invalid_live_output_does_not_issue_an_execution_token() -> None:
    client = _StructuredClient({**_payload(), "entry_conditions": [_payload()["entry_conditions"][0]] * 4})

    draft = build_rule_draft(
        query="조건",
        user_id="user-1",
        signer=RuleDraftSigner("secret"),
        available_metrics=["rsi", "sma20"],
        llm_client=client,
        use_llm=True,
    )

    assert draft.is_executable is False
    assert draft.parse_token is None
    assert draft.strategy_execution_spec is None


def test_non_live_fallback_supports_non_rsi_metrics() -> None:
    result = parse_natural_language_strategy(
        "SMA 20이 100 이상에서 진입하고 MACD가 0 이하에서 종료",
        available_metrics=["sma20", "macd"],
        use_llm=False,
    )

    assert [item.metric for item in result.entry_conditions] == ["sma20"]
    assert [item.metric for item in result.exit_conditions] == ["macd"]


class _CatalogConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[object]]] = []

    def execute(self, query: str, params: list[object]):
        self.calls.append((query, params))
        return self

    def fetchall(self) -> list[dict[str, str]]:
        table = self.calls[-1][0]
        if "ta_momentum" in table:
            return [{"key": "RSI_14"}]
        if "ta_trend" in table:
            return [{"key": "SMA_20"}]
        if "ta_volume" in table:
            return [{"key": "OBV"}]
        return []

    def fetchone(self) -> dict[str, bool]:
        return {"present": False}


def test_indicator_catalog_reads_bounded_postgres_windows() -> None:
    connection = _CatalogConnection()

    metrics = available_indicator_metrics(connection)

    assert {
        "rsi",
        "sma20",
        "obv",
        "volume_ratio_20",
        "relative_strength_20d",
        "relative_strength_60d",
    }.issubset(metrics)
    assert len(connection.calls) == 5
    assert all(
        "time >= %s::date AND time <= %s::date" in query
        for query, _ in connection.calls[:4]
    )


def test_relative_strength_research_is_admitted_from_server_ohlcv_capability() -> None:
    """Derived market-relative returns must reach the AOAI research vocabulary.

    They are calculated from real price paths and the same-date universe at runtime,
    not stored as a precomputed indicator JSONB key.
    """

    response = {
        "resolution_summary": "1개월과 3개월 시장 대비 상대강도가 양수인 주도주를 검증합니다.",
        "sources": [
            {
                "source_id": "source-1",
                "title": "Relative strength definition",
                "url": "https://example.com/relative-strength",
                "claim": "상대강도는 같은 기간 시장 대비 초과수익률입니다.",
            }
        ],
        "candidates": [
            {
                "candidate_id": "research-relative-strength-leader",
                "title": "1개월·3개월 상대강도 주도주",
                "hypothesis": "두 기간의 시장 대비 수익률이 양수인 종목은 추세 지속 후보가 될 수 있습니다.",
                "counter_hypothesis": "강한 상대강도는 추세 반전 직전의 과열일 수 있습니다.",
                "entry_conditions": [
                    {"left": "relative_strength_20d", "operator": "gt", "right": 0},
                    {"left": "relative_strength_60d", "operator": "gt", "right": 0},
                ],
                "exit_conditions": [
                    {"left": "relative_strength_20d", "operator": "lte", "right": 0},
                ],
                "required_metrics": ["relative_strength_20d", "relative_strength_60d"],
                "assumptions": ["KRX 일봉과 같은 날짜의 전체 가격 유니버스를 사용합니다."],
                "source_ids": ["source-1"],
            }
        ],
    }
    metrics = available_indicator_metrics(_CatalogConnection())

    spec = research_strategy_execution_spec(
        query="시장지수보다 최근 1개월·3개월 상대강도가 모두 높은 섹터 주도주를 찾아줘.",
        available_metrics=metrics,
        llm_client=_StructuredClient(response),
    )

    assert spec.candidates[0].required_metrics == [
        "relative_strength_20d",
        "relative_strength_60d",
    ]
