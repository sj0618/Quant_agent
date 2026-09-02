"""An entry-only request must not be refused: the researcher is told to default the exit."""

from ai_graph.nodes import strategy_research


def _prompt_text() -> str:
    request = strategy_research._request(  # noqa: SLF001 - prompt contract test
        query="반도체 섹터에서 RSI 30 이하 종목 매수",
        allowed_metrics=("rsi", "close", "sma20"),
        allowed_sectors=("반도체",),
    )
    return request.system_prompt + "\n" + request.user_prompt


def test_prompt_defaults_a_missing_exit_to_a_twenty_session_hold() -> None:
    text = _prompt_text()
    assert "no exit rule at all" in text
    assert "set ``holding_days`` to 20" in text
    assert "never a reason to return no candidate" in text
    assert "20거래일 보유 후 청산으로 가정" in text
