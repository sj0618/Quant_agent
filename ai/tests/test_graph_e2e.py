from ai_graph.graph import DEBUG_STORE, NODE_SEQUENCE, run_analysis
from ai_graph.jobs import InMemoryAnalysisJobStore


def test_rsi_strategy_runs_ready_e2e_without_external_keys() -> None:
    envelope = run_analysis(
        "RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 팔고 싶어",
        trace_id="trace-rsi",
    )

    assert envelope.status == "ready"
    assert envelope.trace_id == "trace-rsi"
    assert envelope.strategy_spec is not None
    assert envelope.strategy_spec.entry_conditions[0].left == "rsi"
    assert envelope.user_payload.report is not None
    assert envelope.user_payload.report.web_projection
    assert envelope.user_payload.report.email_projection
    dumped = envelope.model_dump()
    assert "internal_payload" not in dumped

    internal = DEBUG_STORE.get(envelope.debug_ref)
    assert internal is not None
    assert internal.validation["node_sequence"] == list(NODE_SEQUENCE)
    assert len(internal.model_dump()) == 7


def test_ambiguous_value_request_returns_cards() -> None:
    envelope = run_analysis("저평가주 사줘", trace_id="trace-c1")

    assert envelope.status == "need_clarification"
    assert len(envelope.user_payload.candidate_cards) == 3
    assert envelope.user_payload.question
    assert len(envelope.user_payload.options) == 3
    assert envelope.user_payload.recommended == 0
    assert envelope.retryable is True


def test_dividend_candidate_selection_does_not_loop_back_to_clarification() -> None:
    first = run_analysis(
        "배당수익률이 4% 이상이고 최근 5년 배당 삭감이 없으며 부채비율이 낮은 배당주를 찾아줘.",
        trace_id="trace-dividend-c1",
    )
    assert first.status == "need_clarification"
    assert any(card.strategy_id == "dividend_defensive" for card in first.user_payload.candidate_cards)

    selected = run_analysis(
        "후보 확정: strategy_id=dividend_defensive; 배당 방어주. 배당수익률·재무 안정성을 우선하고 "
        "200일선 회복 여부로 진입 타이밍을 봅니다. 조건: 배당수익률, 부채비율, 200일선, 저변동성.",
        trace_id="trace-dividend-selected",
    )

    assert selected.status == "ready"
    assert selected.strategy_spec is not None
    assert selected.strategy_spec.strategy_id == "dividend_defensive_a"
    assert selected.user_payload.report is not None
    assert selected.user_payload.performance is not None


def test_pullback_term_uses_l1_l2_definition_without_blocking() -> None:
    envelope = run_analysis("눌림목 전략으로 해줘", trace_id="trace-c2")

    assert envelope.status == "ready"
    assert envelope.user_payload.candidate_cards[0].strategy_id == "pullback_trend"


def test_option_short_straddle_is_rejected() -> None:
    envelope = run_analysis("옵션 양매도 전략 만들어줘", trace_id="trace-c5")

    assert envelope.status == "rejected"
    assert envelope.retryable is False


def test_conflicting_low_volatility_short_surge_requires_clarification() -> None:
    envelope = run_analysis("변동성 낮은 종목으로 단기 급등 잡아줘", trace_id="trace-c4")

    assert envelope.status == "need_clarification"
    assert "충돌" in envelope.user_payload.message
    assert envelope.user_payload.question


def test_supported_prompt_set_avoids_c5_for_krx_stock_screening_language() -> None:
    prompts = [
        "저PER·고ROE·부채비율 100% 이하 조건을 만족하는 가치주 중 최근 20일 수익률이 시장보다 강한 종목을 찾아줘.",
        "최근 52주 신고가를 돌파했고 거래량이 20일 평균 대비 150% 이상 증가한 모멘텀 종목을 찾아줘.",
        "최근 3개월 EPS 컨센서스가 상향 조정되고 주가도 20일 신고가를 돌파한 실적 모멘텀 종목을 찾아줘.",
        "기관과 외국인이 최근 5거래일 연속 순매수했고 주가가 20일선 위에 있는 종목을 찾아줘.",
        "원달러 환율 상승기에 수혜를 받는 수출주 중 최근 이익 전망이 상향된 종목을 찾아줘.",
        "공매도 잔고가 높지만 최근 거래량 증가와 양봉 돌파가 나온 숏커버링 후보 종목을 찾아줘.",
    ]

    for prompt in prompts:
        assert run_analysis(prompt, trace_id=f"trace-{len(prompt)}").status != "rejected"


def test_analysis_job_polling_contract_runs_sync() -> None:
    store = InMemoryAnalysisJobStore()
    job = store.create("RSI가 30 이하인 KOSPI200")
    assert [stage.status for stage in job.stages][0] == "queued"

    completed = store.run_sync(job.job_id, lambda query, trace_id: run_analysis(query, trace_id))

    assert completed.result is not None
    assert {stage.status for stage in completed.stages} == {"succeeded"}
