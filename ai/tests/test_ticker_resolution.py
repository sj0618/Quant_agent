from ai_graph.data_sources.ticker_resolution import resolve_query_tickers


SYMBOLS = [
    {"symbol": "001680", "name": "대상"},
    {"symbol": "084690", "name": "대상홀딩스"},
    {"symbol": "005930", "name": "삼성전자"},
    {"symbol": "000660", "name": "SK하이닉스"},
]


def test_company_name_resolution_handles_korean_context() -> None:
    cases = {
        "대상": ("001680",),
        "(주)대상": ("001680",),
        "대상홀딩스": ("084690",),
        "삼성전자, SK하이닉스.": ("005930", "000660"),
        "삼성전자와 SK하이닉스": ("005930", "000660"),
        "삼성전자랑 SK하이닉스": ("005930", "000660"),
        "삼성전자이랑 SK하이닉스": ("005930", "000660"),
        "삼성전자를 대상으로 장기 백테스트": ("005930",),
        "삼성전자를 대상과 비교": ("005930", "001680"),
        "코스피에서 (주)대상의 RSI": ("001680",),
        "대상을 대상으로 장기 백테스트": ("001680",),
        "코스피 종목을 대상으로 장기 백테스트": (),
        "코스피 코스닥 보통주 대상 장기 퀀트 전략 백테스트": (),
    }
    for query, expected in cases.items():
        assert resolve_query_tickers(query, SYMBOLS) == expected


def test_explicit_codes_are_ordered_deduplicated_and_digit_bounded() -> None:
    assert resolve_query_tickers(
        "005930, 000660, 삼성전자", SYMBOLS
    ) == ("005930", "000660")
    assert resolve_query_tickers("10059300", SYMBOLS) == ()
    assert resolve_query_tickers("주가 100000원 이상", SYMBOLS) == ()
    assert resolve_query_tickers("거래량 100000주 이상", SYMBOLS) == ()
    assert resolve_query_tickers("005930 주가", SYMBOLS) == ("005930",)
    assert resolve_query_tickers("005930 원익IPS", SYMBOLS) == ("005930",)
    assert resolve_query_tickers("005930 일진전기", SYMBOLS) == ("005930",)
    assert resolve_query_tickers("005930 배당", SYMBOLS) == ("005930",)


if __name__ == "__main__":
    test_company_name_resolution_handles_korean_context()
    test_explicit_codes_are_ordered_deduplicated_and_digit_bounded()
