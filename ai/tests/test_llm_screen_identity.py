from __future__ import annotations

from typing import Any

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
