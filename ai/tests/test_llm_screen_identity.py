from __future__ import annotations

from typing import Any

import pytest

from ai_graph.data_sources import llm_screen
from ai_graph.data_sources.llm_screen import enrich_with_symbol_master


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class SymbolMasterConnection:
    def execute(self, query: str, params: object) -> FakeResult:
        assert "FROM core.symbol_master" in query
        assert params == [["025980"]]
        return FakeResult([
            {
                "symbol": "025980",
                "name": "아난티",
                "market": "KOSDAQ",
                "market_segment": "KOSDAQ",
                "sector": "호텔·레저",
            }
        ])


def test_symbol_master_name_overrides_an_llm_row_that_repeats_the_ticker_as_name() -> None:
    enriched = enrich_with_symbol_master(SymbolMasterConnection(), [{
        "ticker": " 25980 ",
        "name": "025980",
        "market": "",
        "sector": None,
    }])

    assert enriched == [{
        "ticker": "025980",
        "name": "아난티",
        "market": "KOSDAQ",
        "sector": "호텔·레저",
    }]


def test_llm_screen_does_not_execute_a_partial_rule_when_data_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NoExecuteConnection:
        def execute(self, *_args: object, **_kwargs: object) -> None:
            pytest.fail("a partial-rule SQL query must not execute")

    monkeypatch.setattr(llm_screen, "build_schema_context", lambda _conn: "schema")
    monkeypatch.setattr(llm_screen, "fetch_known_tickers", lambda _conn: {"005930"})
    monkeypatch.setattr(
        "ai_graph.llm.role_calls.research_screening_terms", lambda *, query: {"metrics": []}
    )
    monkeypatch.setattr(
        "ai_graph.llm.role_calls.generate_screening_sql",
        lambda **_kwargs: {
            "reasoning": "공매도 잔고 데이터가 없습니다.",
            "sql": "",
            "metrics": [],
            "entry_conditions": [],
            "exit_conditions": [],
            "unmet_requirements": ["공매도 잔고"],
        },
    )

    result = llm_screen.screen_with_llm(
        NoExecuteConnection(), "공매도 잔고가 줄어드는 종목을 백테스트해줘"
    )

    assert result is not None
    assert result["exact_rule_blocked"] is True
    assert result["unmet_requirements"] == ["공매도 잔고"]
    assert result["attempts"][0]["outcome"] == "blocked: required data unavailable for exact rule"
