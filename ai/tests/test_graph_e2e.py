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
    assert envelope.retryable is True


def test_pullback_term_unknown_returns_clarification_with_retrieval_cards() -> None:
    envelope = run_analysis("눌림목 전략으로 해줘", trace_id="trace-c2")

    assert envelope.status == "need_clarification"
    assert envelope.user_payload.candidate_cards[1].strategy_id == "pullback_trend"


def test_option_short_straddle_is_rejected() -> None:
    envelope = run_analysis("옵션 양매도 전략 만들어줘", trace_id="trace-c5")

    assert envelope.status == "rejected"
    assert envelope.retryable is False


def test_conflicting_low_volatility_short_surge_requires_clarification() -> None:
    envelope = run_analysis("변동성 낮은 종목으로 단기 급등 잡아줘", trace_id="trace-c4")

    assert envelope.status == "need_clarification"
    assert "충돌" in envelope.user_payload.message


def test_analysis_job_polling_contract_runs_sync() -> None:
    store = InMemoryAnalysisJobStore()
    job = store.create("RSI가 30 이하인 KOSPI200")
    assert [stage.status for stage in job.stages][0] == "queued"

    completed = store.run_sync(job.job_id, lambda query, trace_id: run_analysis(query, trace_id))

    assert completed.result is not None
    assert {stage.status for stage in completed.stages} == {"succeeded"}
