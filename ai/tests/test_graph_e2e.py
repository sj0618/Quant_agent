import json
from uuid import UUID

import pytest

from ai_graph.audit import RecordingAuditSink
from ai_graph.audit_postgres import _create_test_audit_sink
from ai_graph.graph import (
    DEBUG_STORE,
    NODE_SEQUENCE,
    ambiguity_classifier_node,
    classify_query,
    run_analysis,
)
from ai_graph.jobs import InMemoryAnalysisJobStore
from ai_graph.schemas import AmbiguityCode, EnvelopeStatus


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
    assert set(internal.model_dump()) == {
        "trace_id",
        "node_outputs",
        "llm_prompts",
        "validation",
        "backtest_artifacts",
        "risk_events",
    }


def test_ready_analysis_connects_trace_nodes_model_calls_and_full_prompts() -> None:
    sink = RecordingAuditSink()

    envelope = run_analysis(
        "RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 팔고 싶어",
        trace_id="trace-logging-ready",
        audit_sink=_create_test_audit_sink(sink),
    )

    assert envelope.status == "ready"
    assert len(sink.sessions) == 1
    session = sink.sessions[0]
    assert [record.agent_name for record in session.agent_executions] == [
        "Supervisor",
        "Ambiguity Classifier",
        "Data",
        "Research",
        "BacktestCode",
        "Backtest",
        "Signal",
        "Risk Manager",
        "Report",
        "Envelope",
    ]
    assert {record.status for record in session.agent_executions} == {"succeeded"}
    assert len(session.model_calls) == len(session.prompt_logs)
    assert "strategy_conditions" in {record.task_type for record in session.model_calls}
    assert {record.trace_id for record in session.model_calls} == {
        session.correlation.db_trace_id
    }
    assert all(record.execution_id is not None for record in session.model_calls)
    assert {record.call_id for record in session.model_calls} == {
        record.call_id for record in session.prompt_logs
    }
    assert all(record.system_prompt for record in session.prompt_logs)
    assert all(record.user_prompt for record in session.prompt_logs)
    assert all(record.assistant_response is not None for record in session.prompt_logs)
    assert all(
        json.dumps(record.variables_jsonb, ensure_ascii=False, allow_nan=False)
        for record in session.prompt_logs
    )


def test_out_of_scope_route_logs_only_nodes_that_really_execute() -> None:
    sink = RecordingAuditSink()

    envelope = run_analysis(
        "옵션 양매도 전략 만들어줘",
        trace_id="trace-logging-rejected",
        audit_sink=_create_test_audit_sink(sink),
    )

    assert envelope.status == "rejected"
    assert [record.agent_name for record in sink.sessions[0].agent_executions] == [
        "Supervisor",
        "Ambiguity Classifier",
        "Data",
        "Envelope",
    ]
    assert sink.sessions[0].model_calls == ()


def test_underspecified_request_is_answered_instead_of_questioned() -> None:
    """The user asked for a strategy because they did not want to write one.

    "저평가주 사줘" names no market, rule, period or risk level, and used to come back
    as a question about all four - the user doing the work twice. Asserted on the
    interpreter rather than end to end so the expectation is about what it decided,
    not about what the backtest happened to return.
    """

    state = ambiguity_classifier_node({"user_query": "저평가주 사줘", "trace_id": "trace-c1"})

    assert state["status"] == EnvelopeStatus.READY.value
    assert state["ambiguity"]["needs_clarification_after_source_check"] is False
    assert state["ambiguity"]["clarification_blocker_type"] is None


@pytest.mark.parametrize(
    "query",
    [
        "돈 버는 전략 만들어서 검증해줘",
        "네가 알아서 설정해",
        "화학 관련주 사줘",
        "좋은 종목 알아서 골라줘",
        "배당주 찾아줘",
        "성장주 찾아줘",
        # Two goals that pull against each other are a trade-off to make, not a
        # contradiction to hand back.
        "변동성 낮은 종목으로 단기 급등 잡아줘",
    ],
)
def test_no_phrasing_of_a_krx_stock_request_stops_the_run(query: str) -> None:
    assert classify_query(query) == AmbiguityCode.READY


def test_dividend_candidate_selection_does_not_loop_back_to_clarification() -> None:
    first = run_analysis(
        "배당수익률이 4% 이상이고 최근 5년 배당 삭감이 없으며 부채비율이 낮은 배당주를 찾아줘.",
        trace_id="trace-dividend-c1",
    )
    assert first.status == "ready"
    assert first.strategy_spec is not None
    assert first.strategy_spec.strategy_id == "dividend_defensive_a"

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


def test_pullback_rsi40_volume_prompt_generates_nonzero_backtest() -> None:
    envelope = run_analysis(
        "200일선 위 상승추세를 유지하면서 RSI(14)가 40 이하로 눌리고 거래량이 20일 평균 이상인 종목을 찾아줘.",
        trace_id="trace-pullback-rsi40-volume",
    )

    assert envelope.status == "ready"
    assert envelope.strategy_spec is not None
    assert envelope.strategy_spec.strategy_id == "pullback_rsi_volume_a"
    assert [
        (condition.left, condition.operator, condition.right)
        for condition in envelope.strategy_spec.entry_conditions
    ] == [
        ("close_above_sma_200", "eq", 1),
        ("rsi", "lte", 40),
        ("volume_ratio_20", "gte", 1.0),
    ]
    assert envelope.user_payload.performance is not None
    # The point of this test is that the strategy the user asked for is the strategy
    # that gets backtested. It previously asserted a non-zero return, which was only
    # satisfiable because a generic template replaced the rule asserted just above.
    assert envelope.rule_provenance is not None
    assert envelope.rule_provenance.substituted is False
    assert envelope.rule_provenance.evaluated_rule == "user_conditions"


def test_option_short_straddle_is_rejected() -> None:
    envelope = run_analysis("옵션 양매도 전략 만들어줘", trace_id="trace-c5")

    assert envelope.status == "rejected"
    assert envelope.retryable is False


def test_conflicting_goals_are_traded_off_rather_than_handed_back() -> None:
    """Low volatility and a short-term surge pull against each other; that is a
    trade-off the interpreter resolves, not a contradiction the user has to settle."""

    state = ambiguity_classifier_node(
        {"user_query": "변동성 낮은 종목으로 단기 급등 잡아줘", "trace_id": "trace-c4"}
    )

    assert state["status"] == EnvelopeStatus.READY.value
    assert state["ambiguity"]["clarification_blocker_type"] is None


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


def test_run_analysis_records_audit_events_when_sink_provided() -> None:
    sink = RecordingAuditSink()

    envelope = run_analysis(
        "RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 팔고 싶어",
        trace_id="trace-audit-ready",
        audit_sink=_create_test_audit_sink(sink),
    )

    assert envelope.status == "ready"
    assert len(sink.sessions) == 1
    session = sink.sessions[0]
    assert isinstance(session.correlation.db_trace_id, UUID)
    assert session.correlation.db_trace_id.version == 4
    assert session.correlation.trace_id == envelope.trace_id
    assert session.correlation.debug_ref is None
    assert session.correlation.entrypoint == "graph.run_analysis"
    assert session.correlation.feature == "analysis"
    assert [event.kind for event in session.buffered_events] == ["step", "step", "finalization"]
    assert [event.step for event in session.buffered_events if event.kind == "step"] == [
        "analysis_started",
        "analysis_completed",
    ]
    assert session.buffered_events[-1].status == "completed"
    assert "internal_payload" not in envelope.model_dump()


def test_run_analysis_records_error_audit_events_when_validation_fails() -> None:
    sink = RecordingAuditSink()

    with pytest.raises(ValueError, match="user_query must not be empty"):
        run_analysis("   ", audit_sink=_create_test_audit_sink(sink))

    assert len(sink.sessions) == 1
    session = sink.sessions[0]
    assert isinstance(session.correlation.db_trace_id, UUID)
    assert session.correlation.trace_id is None
    assert session.correlation.debug_ref is None
    assert [event.kind for event in session.buffered_events] == ["error", "finalization"]
    error_event = session.buffered_events[0]
    assert error_event.error_type == "ValueError"
    assert "user_query" not in error_event.message
    assert session.buffered_events[-1].status == "failed"


def test_work_agent_failure_stops_downstream_and_keeps_one_correlated_error(monkeypatch) -> None:
    sink = RecordingAuditSink()

    class RejectMarkerError(RuntimeError):
        def __setattr__(self, name, value):
            if name.startswith("_quantagent"):
                raise AttributeError("custom marker rejected")
            super().__setattr__(name, value)

    def fail_backtest(state):
        raise RejectMarkerError("private backtest failure")

    monkeypatch.setattr("ai_graph.graph.backtest_node", fail_backtest)

    with pytest.raises(RejectMarkerError, match="private backtest failure"):
        run_analysis(
            "RSI가 30 이하로 떨어진 종목을 사고 70 이상이면 팔아줘",
            trace_id="trace-work-agent-failure",
            audit_sink=_create_test_audit_sink(sink),
        )

    session = sink.sessions[0]
    assert [record.agent_name for record in session.agent_executions] == [
        "Supervisor",
        "Ambiguity Classifier",
        "Data",
        "Research",
        "BacktestCode",
        "Backtest",
    ]
    failed_execution = session.agent_executions[-1]
    assert failed_execution.status == "failed"
    errors = [event for event in session.buffered_events if event.kind == "error"]
    assert len(errors) == 1
    assert errors[0].step == "Backtest"
    assert errors[0].execution_id == failed_execution.execution_id
    assert session.buffered_events[-1].kind == "finalization"
    assert session.buffered_events[-1].status == "failed"


def test_analysis_job_polling_contract_runs_sync() -> None:
    store = InMemoryAnalysisJobStore()
    job = store.create("RSI가 30 이하인 KOSPI200")
    assert [stage.status for stage in job.stages][0] == "queued"

    completed = store.run_sync(job.job_id, lambda query, trace_id: run_analysis(query, trace_id))

    assert completed.result is not None
    assert {stage.status for stage in completed.stages} == {"succeeded"}
