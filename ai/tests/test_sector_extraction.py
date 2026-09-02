import time

from ai_graph.data_sources.sectors import (
    WICS_SECTOR_FALLBACK,
    clear_sector_cache,
    extract_sector_from_query,
    get_known_sectors,
)


def setup_function() -> None:
    clear_sector_cache()


def test_extract_sector_matches_canonical_label() -> None:
    sector = extract_sector_from_query(
        "반도체 섹터에서 RSI 30 이하로 과매도된 종목 찾아줘", WICS_SECTOR_FALLBACK
    )

    assert sector == "반도체"


def test_extract_sector_resolves_colloquial_alias() -> None:
    assert extract_sector_from_query("바이오 관련주 찾아줘", WICS_SECTOR_FALLBACK) == "건강관리"
    assert extract_sector_from_query("2차전지 종목 찾아줘", WICS_SECTOR_FALLBACK) == "화학"


def test_extract_sector_returns_none_when_no_match() -> None:
    assert extract_sector_from_query("저평가 우량주 찾아줘", WICS_SECTOR_FALLBACK) is None


def test_extract_sector_prefers_longest_alias_match() -> None:
    sector = extract_sector_from_query("IT하드웨어 부품주 찾아줘", WICS_SECTOR_FALLBACK)

    assert sector == "IT하드웨어"


def test_get_known_sectors_falls_back_when_no_dsn(monkeypatch) -> None:
    monkeypatch.delenv("AI_DATABASE_DSN", raising=False)
    monkeypatch.delenv("QUANT_DB_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    sectors = get_known_sectors()

    assert sectors == list(WICS_SECTOR_FALLBACK)


def test_get_known_sectors_uses_injected_connection() -> None:
    class Result:
        def __init__(self, rows: list[dict[str, str]]) -> None:
            self.rows = rows

        def fetchall(self) -> list[dict[str, str]]:
            return self.rows

    class FakeConnection:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def execute(self, query: str) -> Result:
            self.calls.append(query)
            return Result(rows=[{"sector": "반도체"}, {"sector": "화학"}])

    conn = FakeConnection()
    sectors = get_known_sectors(conn=conn)

    assert sectors == ["반도체", "화학"]
    assert len(conn.calls) == 1
    # Read from the WICS membership history, which is also what the PIT backtest
    # universe is restricted with. Offering a sector name from anywhere else would let
    # research seal a sector the universe filter then matches nobody for.
    assert "DISTINCT sector_name" in conn.calls[0]
    assert "FROM feature.wics_symbol_sector_history" in conn.calls[0]
    assert "common_stock_universe_asof" not in conn.calls[0]


def test_get_known_sectors_caches_within_ttl(monkeypatch) -> None:
    class Result:
        def __init__(self, rows: list[dict[str, str]]) -> None:
            self.rows = rows

        def fetchall(self) -> list[dict[str, str]]:
            return self.rows

    class CountingConnection:
        def __init__(self) -> None:
            self.call_count = 0

        def execute(self, query: str) -> Result:
            self.call_count += 1
            return Result(rows=[{"sector": "반도체"}])

    conn = CountingConnection()
    fake_time = {"value": 1000.0}
    monkeypatch.setattr(time, "monotonic", lambda: fake_time["value"])

    first = get_known_sectors(conn=conn)
    second = get_known_sectors(conn=conn)

    assert first == ["반도체"]
    assert second == ["반도체"]
    assert conn.call_count == 1

    fake_time["value"] += 301  # past the default 300s TTL
    third = get_known_sectors(conn=conn)

    assert third == ["반도체"]
    assert conn.call_count == 2
