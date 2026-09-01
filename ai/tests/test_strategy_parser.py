from __future__ import annotations

import pytest

from ai_graph.data_sources.db import available_indicator_metrics
from ai_graph.llm.base import LLMJsonRequest
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

    assert {"rsi", "sma20", "obv", "volume_ratio_20"}.issubset(metrics)
    assert len(connection.calls) == 5
    assert all(
        "time >= %s::date AND time <= %s::date" in query
        for query, _ in connection.calls[:4]
    )
