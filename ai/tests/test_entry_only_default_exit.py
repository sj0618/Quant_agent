"""An entry-only request must be researched, not refused or given a hidden default."""

from ai_graph.nodes import strategy_research


def _prompt_text() -> str:
    request = strategy_research._request(
        query="반도체 섹터에서 RSI 30 이하 종목 매수",
        allowed_metrics=("rsi", "close", "sma20"),
        allowed_sectors=("반도체",),
    )
    return request.system_prompt + "\n" + request.user_prompt


def test_prompt_researches_a_missing_exit_before_sealing_a_hold() -> None:
    text = _prompt_text()
    assert "no exit rule at all" in text
    assert "pre-backtest research" in text
    assert "choose a concrete holding period" in text
    assert "never a reason" in text
    assert "return no candidate" in text
    assert "``ai_assumptions``" in text
    assert "20거래일 보유 후 청산으로 가정" not in text
