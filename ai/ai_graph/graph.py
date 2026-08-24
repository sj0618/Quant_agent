from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping, Sequence
from contextvars import ContextVar
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
from typing import Any, Literal
from uuid import UUID

from pydantic import ValidationError

from ai_graph.audit import (
    AuditSession,
    AuditSink,
    NoOpAuditSink,
    bind_audit_context,
    create_audit_correlation,
    report_audit_failure,
)
from ai_graph.audit_postgres import is_authorized_audit_session, resolve_audit_sink
from ai_graph.data_sources import (
    PipelineDataUnavailableError,
    load_pipeline_data_from_env,
    screening_data_families,
)
from ai_graph.data_sources.sectors import extract_sector_from_query, get_known_sectors
from ai_graph.envelope import InMemoryDebugStore, build_envelope
from ai_graph.freshness import (
    build_freshness_evidence,
    freshness_status_from_metadata,
    withhold_recommendations_without_l4_evidence,
)
from ai_graph.llm.role_calls import (
    StrategyConditionsPayload,
    generate_strategy_conditions,
    resolve_strategy_intent,
)
from ai_graph.memory import AnalysisMemory
from ai_graph.nodes.backtest import (
    BENCHMARK_LABEL,
    BENCHMARK_METHOD,
    BENCHMARK_WARNING,
    MAX_OBJECTIVE_DRAWDOWN,
    METRIC_ROUND_DIGITS,
    MIN_OBJECTIVE_SHARPE,
    MIN_OBJECTIVE_TRADES,
    _annualized_return,
    _benchmark_objective_reasons,
    _calmar_ratio,
    _equal_weight_benchmark_curve,
    _is_numeric_metric,
    _price_rows,
    _profit_factor,
    _public_engine_summary,
    _summary_float_default,
    backtest_node,
)
from ai_graph.nodes.backtest_code import backtest_code_node
from ai_graph.nodes.report import report_node
from ai_graph.nodes.risk_manager import risk_manager_node
from ai_graph.nodes.signal import signal_node
from ai_graph.preflight import classify_research_request
from ai_graph.progress import (
    raise_if_cancelled,
    raise_if_past_deadline,
    report_activity,
    report_node_stage,
)
from ai_graph.quant_explanations import metric_explanation
from ai_graph.quant_strategy import (
    classify_strategy_request,
    infer_automatic_strategy_preferences,
    robust_strategy_source_refs,
    rsi_trade_rules,
)
from ai_graph.research_eligibility import PerformanceAvailable, PerformanceUnavailable
from ai_graph.schemas import (
    AmbiguityCode,
    APIEnvelope,
    BacktestBenchmark,
    BacktestEquityPoint,
    BacktestMetrics,
    BacktestPerformance,
    BacktestReliability,
    CandidateBacktestResult,
    ClarificationOption,
    Condition,
    DataRequirement,
    EnvelopeStatus,
    EvidenceRef,
    InternalPayload,
    PublicMetricDetail,
    RecommendationGate,
    ScreeningMatch,
    SemanticSlots,
    SourceUsage,
    StrategyCandidateCard,
    StrategySpec,
    TickerAction,
    UserPayload,
)
from ai_graph.source_manifest import (
    build_pipeline_extract_snapshot,
    is_release_profile,
    validate_release_metadata,
)
from ai_graph.state import QuantAgentState

_logger = logging.getLogger(__name__)

DEBUG_STORE = InMemoryDebugStore()
NODE_SEQUENCE = (
    "Supervisor",
    "Ambiguity Classifier",
    "Data",
    "Research",
    "BacktestCode",
    "Backtest",
    "Signal",
    "Risk Manager",
    "Report",
)
_NODE_ERROR_RECORDED: ContextVar[bool] = ContextVar("node_error_recorded", default=False)
_PUBLIC_METRIC_UNAVAILABLE_REASON = "metric unavailable in this analysis window"
_BENCHMARK_UNAVAILABLE_REASON = (
    "benchmark curve requires at least one non-empty trading date and valid closes"
)

_METRIC_DETAIL_KEYS = (
    "total_return",
    "cagr",
    "annualized_volatility",
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "calmar_ratio",
    "win_rate",
    "profit_factor",
    "benchmark_return",
    "excess_return",
    "in_sample_sharpe",
    "out_sample_sharpe",
    "degradation",
)
_RELIABILITY_WARN_UNTIL_DAYS = 30
_RELIABILITY_SUFFICIENT_DAYS = 90
_RELIABILITY_MIN_TICKERS = 2
_UNAVAILABLE_METRIC_REASON = "benchmark cannot be calculated from current data"


class FallbackGraph:
    def __init__(self, audit_session: AuditSession | None = None) -> None:
        self.audit_session = audit_session

    def invoke(self, state: QuantAgentState) -> QuantAgentState:
        current = self._invoke("Supervisor", supervisor_node, state)
        current.update(self._invoke("Ambiguity Classifier", ambiguity_classifier_node, current))
        if _route_after_ambiguity(current) == "final":
            current.update(self._invoke("Envelope", envelope_node, current))
            return current
        current.update(self._invoke("Data", data_node, current))
        if current["status"] == EnvelopeStatus.READY.value:
            current.update(self._invoke("Research", research_node, current))
            current.update(self._invoke("BacktestCode", backtest_code_node, current))
            current.update(self._invoke("Backtest", backtest_node, current))
            current.update(self._invoke("Signal", signal_node, current))
            current.update(self._invoke("Risk Manager", risk_manager_node, current))
            current.update(self._invoke("Report", report_node, current))
        current.update(self._invoke("Envelope", envelope_node, current))
        return current

    def _invoke(
        self,
        name: str,
        node: Callable[[QuantAgentState], QuantAgentState | dict[str, Any]],
        state: QuantAgentState,
    ) -> QuantAgentState | dict[str, Any]:
        return instrument_node(self.audit_session, name, node)(state)


def build_graph(audit_session: AuditSession | None = None) -> Any:
    try:
        from langgraph.graph import END, START, StateGraph
    except ModuleNotFoundError:
        return FallbackGraph(audit_session)

    graph = StateGraph(QuantAgentState)
    graph.add_node("Supervisor", instrument_node(audit_session, "Supervisor", supervisor_node))
    graph.add_node(
        "Ambiguity Classifier",
        instrument_node(audit_session, "Ambiguity Classifier", ambiguity_classifier_node),
    )
    graph.add_node("Data", instrument_node(audit_session, "Data", data_node))
    graph.add_node("Research", instrument_node(audit_session, "Research", research_node))
    graph.add_node(
        "BacktestCode", instrument_node(audit_session, "BacktestCode", backtest_code_node)
    )
    graph.add_node("Backtest", instrument_node(audit_session, "Backtest", backtest_node))
    graph.add_node("Signal", instrument_node(audit_session, "Signal", signal_node))
    graph.add_node(
        "Risk Manager", instrument_node(audit_session, "Risk Manager", risk_manager_node)
    )
    graph.add_node("Report", instrument_node(audit_session, "Report", report_node))
    graph.add_node("Envelope", instrument_node(audit_session, "Envelope", envelope_node))
    graph.add_edge(START, "Supervisor")
    graph.add_edge("Supervisor", "Ambiguity Classifier")
    graph.add_conditional_edges(
        "Ambiguity Classifier",
        _route_after_ambiguity,
        {"data": "Data", "final": "Envelope"},
    )
    graph.add_conditional_edges(
        "Data",
        _route_after_data,
        {"ready": "Research", "final": "Envelope"},
    )
    graph.add_edge("Research", "BacktestCode")
    graph.add_edge("BacktestCode", "Backtest")
    graph.add_edge("Backtest", "Signal")
    graph.add_edge("Signal", "Risk Manager")
    graph.add_edge("Risk Manager", "Report")
    graph.add_edge("Report", "Envelope")
    graph.add_edge("Envelope", END)
    return graph.compile()


def run_analysis(
    user_query: str,
    trace_id: str | None = None,
    *,
    audit_sink: AuditSink | None = None,
    audit_session: AuditSession | None = None,
    audit_entrypoint: str = "graph.run_analysis",
    audit_feature: str = "analysis",
    strategy_id: str | None = None,
    client_request_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> APIEnvelope:
    query = _normalize_user_query(user_query)
    resolved_trace_id = trace_id or (_trace_id(query) if query else None)
    scope_decision = classify_research_request(query)
    if not scope_decision.allowed:
        # This guard intentionally precedes audit-session construction and graph setup.
        # A refused personalized request must not persist a job/audit record, consume a
        # provider slot, or invoke a data source merely because another entrypoint
        # bypassed the HTTP preflight adapter.
        return _scope_refusal_envelope(query, resolved_trace_id or _trace_id(query))
    if audit_session is not None and not is_authorized_audit_session(audit_session):
        report_audit_failure("unapproved_audit_session")
        audit_session = None
        audit_sink = NoOpAuditSink()
    session = audit_session or _open_audit_session(
        audit_sink,
        trace_id=resolved_trace_id,
        debug_ref=None,
        entrypoint=audit_entrypoint,
        feature=audit_feature,
        strategy_id=strategy_id,
        client_request_id=client_request_id,
        user_id=user_id,
        session_id=session_id,
    )
    if not query:
        _record_error(
            session,
            "analysis_input_validation",
            error_type="ValueError",
            message="ValueError raised during analysis input validation",
        )
        _record_finalization(
            session, "failed", message="analysis execution failed before graph invocation"
        )
        raise ValueError("user_query must not be empty")
    _record_step(session, "analysis_started", message="analysis execution started")
    node_error_token = _NODE_ERROR_RECORDED.set(False)
    try:
        state = build_graph(audit_session=session).invoke(
            {"user_query": query, "trace_id": resolved_trace_id or ""}
        )
        envelope = APIEnvelope.model_validate(state["envelope"])
    except Exception as exc:
        if not _NODE_ERROR_RECORDED.get():
            _record_error(
                session,
                "analysis_execution",
                error_type=type(exc).__name__,
                message=f"{type(exc).__name__} raised during analysis execution",
            )
        _record_finalization(session, "failed", message="analysis execution failed")
        raise
    finally:
        _NODE_ERROR_RECORDED.reset(node_error_token)
    status_label = envelope.status.value
    _record_step(session, "analysis_completed", message=f"analysis returned status={status_label}")
    _record_finalization(
        session,
        _finalization_status_for_envelope(envelope),
        message=f"analysis completed with status={status_label}",
        metadata_jsonb={"debug_ref": envelope.debug_ref, "public_trace_id": envelope.trace_id},
    )
    return envelope


def _scope_refusal_envelope(query: str, trace_id: str) -> APIEnvelope:
    decision = classify_research_request(query)
    if decision.allowed:
        raise ValueError("scope refusal envelope requires a refused request")
    headline = (
        "현재 지원 범위 밖의 요청입니다."
        if decision.kind == "unsupported_scope"
        else "개인화된 투자 요청은 분석하지 않습니다."
    )
    return APIEnvelope(
        status=EnvelopeStatus.REJECTED,
        trace_id=trace_id,
        user_payload=UserPayload(
            headline=headline,
            message=decision.public_message,
            next_actions=[decision.public_guidance],
        ),
        strategy_spec=None,
        debug_ref=f"scope-refusal:{_trace_id(query)}",
        retryable=False,
    )


def instrument_node(
    session: AuditSession | None,
    name: str,
    node: Callable[[QuantAgentState], QuantAgentState | dict[str, Any]],
) -> Callable[[QuantAgentState], QuantAgentState | dict[str, Any]]:
    def wrapped(state: QuantAgentState) -> QuantAgentState | dict[str, Any]:
        # Node boundaries are the checkpoints: a cancelled run, or one that has spent
        # its whole time budget, stops here rather than paying for the remaining nodes.
        raise_if_cancelled()
        raise_if_past_deadline()
        # Announce the stage before the node runs so a polling client sees the work
        # it is actually waiting on, not the stage it already finished.
        report_node_stage(name)
        if session is None:
            return node(state)

        execution_id = _start_agent_execution(session, name, state)
        started = perf_counter()
        try:
            with bind_audit_context(session, execution_id):
                result = node(state)
        except Exception as exc:
            latency_ms = (perf_counter() - started) * 1_000
            _finish_agent_execution(
                session,
                execution_id,
                status="failed",
                output_jsonb={},
                error_message=f"{type(exc).__name__} raised during {name}",
                latency_ms=latency_ms,
            )
            _record_error(
                session,
                name,
                error_type=type(exc).__name__,
                message=f"{type(exc).__name__} raised during graph node execution",
                execution_id=execution_id,
            )
            _NODE_ERROR_RECORDED.set(True)
            raise
        _finish_agent_execution(
            session,
            execution_id,
            status="succeeded",
            output_jsonb=_safe_state_metadata(result),
            latency_ms=(perf_counter() - started) * 1_000,
        )
        return result

    return wrapped


def _start_agent_execution(
    session: AuditSession,
    name: str,
    state: Mapping[str, Any],
) -> UUID | None:
    try:
        return session.start_agent_execution(
            name,
            step_name=name,
            input_jsonb=_safe_state_metadata(state),
        )
    except Exception:
        report_audit_failure("start_agent_execution")
        return None


def _finish_agent_execution(
    session: AuditSession,
    execution_id: UUID | None,
    *,
    status: str,
    output_jsonb: Mapping[str, Any],
    error_message: str | None = None,
    latency_ms: float,
) -> None:
    if execution_id is None:
        return
    try:
        session.finish_agent_execution(
            execution_id,
            status=status,
            output_jsonb=output_jsonb,
            error_message=error_message,
            latency_ms=latency_ms,
        )
    except Exception:
        report_audit_failure("finish_agent_execution")


def _safe_state_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {"keys": sorted(str(key) for key in value)}
    for key in ("route", "status", "trace_id"):
        candidate = value.get(key)
        if isinstance(candidate, (str, int, float, bool)):
            metadata[key] = str(candidate)[:128]
    return metadata


# The interpreting stage covers Supervisor -> Ambiguity -> Data and can run for minutes,
# but only the screening pipeline inside Data reported anything. Everything before it sat
# behind a single "전략 해석 중" label with an empty activity log, which reads as a hang.
def supervisor_node(state: QuantAgentState) -> QuantAgentState:
    prepared = _prepare_supervisor_state(
        str(state.get("user_query", "")),
        trace_id=state.get("trace_id") or None,
    )
    report_activity(
        "step", label="요청 접수", detail=_activity_query_preview(prepared["user_query"])
    )
    return {**state, **prepared}


_ACTIVITY_QUERY_PREVIEW_LIMIT = 120


def _activity_query_preview(query: str) -> str:
    text = str(query).strip()
    if len(text) <= _ACTIVITY_QUERY_PREVIEW_LIMIT:
        return text
    return f"{text[:_ACTIVITY_QUERY_PREVIEW_LIMIT]}…"


def _prepare_supervisor_state(user_query: str, *, trace_id: str | None) -> QuantAgentState:
    query = _normalize_user_query(user_query)
    if not query:
        raise ValueError("user_query must not be empty")
    resolved_trace_id = trace_id or _trace_id(query)
    return {
        "user_query": query,
        "trace_id": resolved_trace_id,
        "debug_ref": f"debug:{resolved_trace_id}",
        "route": "strategy_parse",
        "internal_payload": InternalPayload(trace_id=resolved_trace_id).model_dump(),
    }


def _normalize_user_query(user_query: str) -> str:
    return " ".join(str(user_query).split())


def _open_audit_session(
    audit_sink: AuditSink | None,
    *,
    trace_id: str | None,
    debug_ref: str | None,
    entrypoint: str,
    feature: str,
    strategy_id: str | None = None,
    client_request_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> AuditSession:
    correlation = create_audit_correlation(
        trace_id=trace_id,
        debug_ref=debug_ref,
        entrypoint=entrypoint,
        feature=feature,
        strategy_id=strategy_id,
        client_request_id=client_request_id,
        user_id=user_id,
        session_id=session_id,
    )
    sink = resolve_audit_sink(audit_sink)
    try:
        return sink.open_session(correlation)
    except Exception:
        report_audit_failure("open_session")
        return NoOpAuditSink().open_session(correlation)


def _record_step(session: AuditSession, step: str, *, message: str | None = None) -> None:
    try:
        session.record_step(step, message=message)
    except Exception:
        report_audit_failure("record_step")


def _record_error(
    session: AuditSession,
    step: str,
    *,
    error_type: str,
    message: str,
    execution_id: UUID | None = None,
) -> None:
    try:
        session.record_error(
            step,
            error_type=error_type,
            message=message,
            execution_id=execution_id,
        )
    except Exception:
        report_audit_failure("record_error")


def _record_finalization(
    session: AuditSession,
    status: str,
    *,
    message: str | None = None,
    metadata_jsonb: Mapping[str, Any] | None = None,
) -> None:
    try:
        session.record_finalization(status, message=message, metadata_jsonb=metadata_jsonb)
    except Exception:
        report_audit_failure("record_finalization")


def _finalization_status_for_envelope(envelope: APIEnvelope) -> str:
    return "failed" if envelope.status == EnvelopeStatus.FAILED else "completed"


def ambiguity_classifier_node(state: QuantAgentState) -> dict[str, Any]:
    """Resolve what to run, rather than judge whether the input was good enough.

    An underspecified request used to end the analysis in a question: "저평가주 사줘"
    or "네가 알아서 설정해" was pattern-matched as missing a market/rule/risk level and
    came back asking for one. That reads as a refusal, and the user asked for the
    strategy precisely because they did not want to specify it. So the vagueness is
    resolved once, here, by a model that can web-search current market conditions and
    commit to concrete numbers - every later stage reads `resolved_query` and never
    sees that the request started out vague. What still stops a run: a message that is
    not asking for a strategy at all, and an asset class the warehouse cannot price.
    """

    query = state["user_query"]
    if _is_small_talk(query):
        return _ambiguity_state(AmbiguityCode.NO_STRATEGY_INTENT, query, intent=None)
    report_activity("step", label="요청 해석", detail="입력을 실행 가능한 전략으로 구체화하는 중")
    intent = resolve_strategy_intent(query=query, capabilities=data_source_inventory())
    if intent is None:
        # Mock mode and provider failures: no model to decide with, so fall back to the
        # judgments that do not need one - small talk, and asset class.
        return _ambiguity_state(classify_query(query), query, intent=None)
    if intent["scope"] == "not_a_request":
        return _ambiguity_state(AmbiguityCode.NO_STRATEGY_INTENT, query, intent=intent)
    if intent["scope"] == "unsupported":
        return _ambiguity_state(AmbiguityCode.INFEASIBLE, query, intent=intent)
    return _ambiguity_state(AmbiguityCode.READY, query, intent=intent)


def _ambiguity_state(
    category: AmbiguityCode,
    query: str,
    *,
    intent: Mapping[str, Any] | None,
) -> dict[str, Any]:
    status = _status_for_category(category)
    clarification = build_clarification_prompt(category, query)
    assumptions = [str(item) for item in (intent or {}).get("assumptions", []) if str(item).strip()]
    reason = str((intent or {}).get("scope_reason") or "").strip() or _ambiguity_reason(category)
    ambiguity = {
        "category": category.value,
        "ambiguity_category": category.value,
        "safety_priority": category == AmbiguityCode.INFEASIBLE,
        "reason": reason if category != AmbiguityCode.READY else _ambiguity_reason(category),
        "ambiguity_reasons": _ambiguity_reasons(category, query),
        "ambiguity_dimensions": _ambiguity_dimensions(category, query),
        "source_resolvable": category
        in {AmbiguityCode.INPUT_AMBIGUOUS, AmbiguityCode.TERM_UNKNOWN},
        "needs_clarification_after_source_check": category
        not in {
            AmbiguityCode.READY,
            AmbiguityCode.NO_STRATEGY_INTENT,
        },
        "clarification_blocker_type": _clarification_blocker_type(category),
        "clarification_question": clarification["question"],
        "question_reason": clarification["question_reason"],
        "options": [option.model_dump() for option in clarification["options"]],
        "recommended_option": clarification["recommended"],
        "recommendation_confidence": clarification["confidence"],
        "recommendation_confidence_reason": clarification["confidence_reason"],
        "interpretation": str((intent or {}).get("interpretation") or ""),
        "assumptions": assumptions,
        "citations": list((intent or {}).get("citations") or []),
    }
    output: dict[str, Any] = {"ambiguity": ambiguity, "status": status.value}
    if intent is not None:
        output["intent"] = dict(intent)
    if category == AmbiguityCode.READY and intent is not None:
        output["resolved_query"] = str(intent["resolved_query"])

    if category == AmbiguityCode.READY:
        detail = str((intent or {}).get("interpretation") or "").strip()
        if assumptions:
            detail = f"{detail} / 정한 조건: {' '.join(assumptions[:2])}".strip(" /")
        report_activity(
            "step",
            label="요청 해석 완료",
            detail=(detail or "입력한 조건 그대로 진행합니다.")[:200],
        )
    else:
        report_activity("step", label="요청 해석 완료", detail=f"진행할 수 없는 요청: {reason}")
    return output


def _rule_provenance(state: Mapping[str, Any]) -> dict[str, Any] | None:
    """What the backtest reported about the rule it traded, if it ran at all."""

    backtest = state.get("backtest")
    if not isinstance(backtest, Mapping) or not backtest:
        return None
    from ai_graph.nodes.backtest import rule_provenance

    spec = state.get("strategy_spec") or {}
    return rule_provenance(
        backtest,
        spec.get("entry_conditions"),
        selection_mode=spec.get("selection_mode"),
    )


def _strategy_query(state: Mapping[str, Any]) -> str:
    """The strategy every stage after the interpreter works on.

    Falls back to the raw input only when nothing resolved it, so a stage never has to
    know whether the user spelled the strategy out or the interpreter did.
    """

    return str(state.get("resolved_query") or state.get("user_query") or "")


def data_node(state: QuantAgentState) -> dict[str, Any]:
    query = _strategy_query(state)
    semantic_slots = parse_semantic_slots(query, trace_id=state["trace_id"])
    data_requirements = plan_data_requirements(semantic_slots, query=query)
    if not data_requirements:
        # An empty plan means we could not name a single thing to read, so there is
        # nothing to screen on and nothing a later stage could honestly verify. It used
        # to be reported as "0종" and then ignored - the run continued into a full
        # backtest whose data no stage had claimed to need. Stop here with a reason
        # instead.
        return {
            "semantic_slots": semantic_slots.model_dump(),
            "data_requirements": [],
            "status": EnvelopeStatus.NEED_CLARIFICATION.value,
            "ambiguity": _no_data_plan_ambiguity(query),
        }
    report_activity(
        "step",
        label="필요 데이터 정리",
        detail=f"조회할 데이터 항목 {len(data_requirements)}종을 확정했습니다.",
    )
    pipeline_data = load_pipeline_data_from_env(query, state["trace_id"])
    if is_release_profile():
        raw_required_tickers = pipeline_data.metadata.get("tickers", ())
        required_tickers = (
            raw_required_tickers
            if isinstance(raw_required_tickers, Sequence) and not isinstance(raw_required_tickers, str)
            else ()
        )
        manifest_errors = validate_release_metadata(
            pipeline_data.metadata,
            extract_snapshot=build_pipeline_extract_snapshot(
                price_rows=pipeline_data.price_rows,
                screening_candidates=pipeline_data.screening_candidates,
                l4_evidence=pipeline_data.l4_evidence,
                macro_snapshot=pipeline_data.macro_snapshot,
                data_availability=pipeline_data.data_availability,
                required_tickers=required_tickers,
            ),
        )
        if manifest_errors:
            raise PipelineDataUnavailableError(
                "release_source_manifest_invalid",
                "release source manifest is invalid: " + "; ".join(manifest_errors),
            )
    source_usage = build_source_usage(
        query,
        data_requirements,
        trace_id=state["trace_id"],
        pipeline_metadata=pipeline_data.metadata,
    )
    evidence_refs = build_evidence_refs(source_usage, trace_id=state["trace_id"])
    cards = strategy_candidate_cards(
        query,
        screening_candidates=pipeline_data.screening_candidates,
        sector=semantic_slots.sector,
    )
    freshness_evidence = withhold_recommendations_without_l4_evidence(
        build_freshness_evidence(pipeline_data.metadata),
        l4_evidence=pipeline_data.l4_evidence,
    )
    output: dict[str, Any] = {
        "semantic_slots": semantic_slots.model_dump(),
        "data_requirements": [requirement.model_dump() for requirement in data_requirements],
        "source_usage": [usage.model_dump() for usage in source_usage],
        "evidence_refs": [evidence.model_dump() for evidence in evidence_refs],
        "freshness_status": _aggregate_freshness_status(source_usage),
        "freshness_evidence": freshness_evidence.model_dump(),
        "proxy_disclosure": _proxy_disclosure(data_requirements),
        "data": {
            "candidate_cards": [card.model_dump() for card in cards],
            "pipeline_data_source": pipeline_data.metadata,
            "screening_candidates": pipeline_data.screening_candidates,
            "data_availability": pipeline_data.data_availability,
            "data_source_inventory": data_source_inventory(),
        },
    }
    if pipeline_data.price_rows:
        output["price_rows"] = pipeline_data.price_rows
    if pipeline_data.metadata.get("source") == "postgres" or pipeline_data.l4_evidence:
        output["l4_evidence"] = pipeline_data.l4_evidence
    if pipeline_data.macro_snapshot:
        output["macro_snapshot"] = pipeline_data.macro_snapshot
    if pipeline_data.official_benchmark is not None:
        output["official_benchmark"] = pipeline_data.official_benchmark

    # Stop rather than screen on whatever data happens to exist. Conditions we cannot
    # evaluate used to fall through to a price-only profile, so a flow or short-interest
    # strategy came back with a full report built from unrelated names - a result that
    # reads as verified but never tested what the user asked for.
    unsupported = pipeline_data.data_availability.get("unsupported_capabilities") or []
    if unsupported:
        output["status"] = EnvelopeStatus.NEED_CLARIFICATION.value
        output["ambiguity"] = _unverifiable_ambiguity(unsupported)
    return output


def _no_data_plan_ambiguity(query: str) -> dict[str, Any]:
    reason = "요청에서 조회할 데이터 항목을 하나도 확정하지 못했습니다."
    return {
        "category": AmbiguityCode.INPUT_AMBIGUOUS.value,
        "ambiguity_category": AmbiguityCode.INPUT_AMBIGUOUS.value,
        "safety_priority": False,
        "reason": reason,
        "ambiguity_reasons": [reason],
        "ambiguity_dimensions": ["data_availability"],
        "source_resolvable": False,
        "needs_clarification_after_source_check": True,
        "clarification_blocker_type": "missing_data_source",
        "clarification_question": (
            "어떤 지표로 종목을 고를지 알 수 없어 조회할 데이터를 정하지 못했습니다. "
            "기준으로 삼을 지표를 하나만 정해 주시겠어요?"
        ),
        "question_reason": "조회할 데이터가 없으면 어떤 조건도 검증할 수 없습니다.",
        "options": [
            {
                "label": "가격/기술적 지표 기준으로 검증",
                "reason": "이동평균·RSI·거래량 같은 가격 지표는 지금 바로 검증할 수 있습니다.",
            },
            {
                "label": "재무 지표 기준으로 검증",
                "reason": "PER·ROE·부채비율 같은 재무 조건으로 종목을 고를 수 있습니다.",
            },
        ],
        "recommended_option": 0,
        "recommendation_confidence": 0.6,
        "recommendation_confidence_reason": "가격/기술적 지표는 적재 상태가 가장 안정적입니다.",
    }


def _unverifiable_ambiguity(unsupported: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    labels = [str(item.get("label")) for item in unsupported]
    reasons = [f"{item.get('label')}: {item.get('reason')}" for item in unsupported]
    joined = ", ".join(labels)
    return {
        "category": AmbiguityCode.INPUT_AMBIGUOUS.value,
        "ambiguity_category": AmbiguityCode.INPUT_AMBIGUOUS.value,
        "safety_priority": False,
        "reason": f"현재 데이터로 검증할 수 없는 조건이 있습니다: {joined}",
        "ambiguity_reasons": reasons,
        "ambiguity_dimensions": ["data_availability"],
        "source_resolvable": False,
        "needs_clarification_after_source_check": True,
        "clarification_blocker_type": "missing_data_source",
        "clarification_question": (
            f"{joined} 조건은 현재 적재된 데이터로 검증할 수 없습니다. 해당 조건을 빼고 검증할까요?"
        ),
        "question_reason": "검증 불가한 조건을 가격 지표로 대체하면 확인되지 않은 결과가 사실처럼 보입니다.",
        # ClarificationOption takes label and reason only, and forbids extras - the
        # envelope validates these, so an option shaped any other way turns an honest
        # refusal into a failed analysis.
        "options": [
            {
                "label": f"{joined} 조건을 빼고 나머지만 검증",
                "reason": "검증 가능한 조건만으로 다시 요청하면 결과의 신뢰도를 유지할 수 있습니다.",
            },
            {
                "label": "데이터가 연결될 때까지 보류",
                "reason": "해당 데이터 소스가 적재되면 원래 조건 그대로 검증할 수 있습니다.",
            },
        ],
        # An index into options, not a label - UserPayload.recommended is int|None.
        "recommended_option": 0,
        "recommendation_confidence": 0.7,
        "recommendation_confidence_reason": "검증 가능한 조건만 남기면 결과의 신뢰도를 유지할 수 있습니다.",
    }


def research_node(state: QuantAgentState) -> dict[str, Any]:
    """Turn the query into a StrategySpec.

    There is no debate and no separate review here any more. The screening stage already
    researches the strategy's terminology and reasons its conditions into SQL, judging
    its own work when a query returns nothing and rewriting it; a second panel arguing
    over the same specification produced commentary, not changes - its verdict was
    appended to `assumptions` while the conditions that got backtested stayed identical.
    """

    strategy_a = build_strategy_spec(
        _strategy_query(state),
        variant="A",
        semantic_slots=state.get("semantic_slots"),
        original_query=state.get("user_query"),
    )

    # If the screen already expressed the rule as structured conditions, adopt them as
    # the spec's entry/exit conditions. That makes the screen and the spec one
    # definition instead of two independently-derived ones - the drift this whole change
    # is about. The spec's other fields (indicators, risk) stay as built.
    screening = state.get("data", {}).get("pipeline_data_source", {}) or {}
    relaxation = screening.get("screening_relaxation") or {}
    screen_entry = relaxation.get("entry_conditions") or []
    screen_exit = relaxation.get("exit_conditions") or []
    if screen_entry and strategy_a.selection_mode != "automatic":
        try:
            strategy_a = strategy_a.model_copy(
                update={
                    "entry_conditions": [Condition.model_validate(c) for c in screen_entry],
                    "exit_conditions": [Condition.model_validate(c) for c in screen_exit],
                    "assumptions": [
                        *strategy_a.assumptions,
                        "entry/exit 조건을 스크리닝 SQL과 동일한 구조 정의로 통일함",
                    ],
                }
            )
        except ValidationError:
            _logger.warning("screening conditions failed spec validation; keeping built spec")

    return {
        "original_strategy_spec": strategy_a.model_dump(),
        "strategy_spec": strategy_a.model_dump(),
    }


def envelope_node(state: QuantAgentState) -> dict[str, Any]:
    status = EnvelopeStatus(state["status"])
    report = state.get("report")
    cards = [
        StrategyCandidateCard.model_validate(card)
        for card in state.get("data", {}).get("candidate_cards", [])
    ]
    if status == EnvelopeStatus.READY:
        performance = project_public_performance(
            state.get("backtest"),
            price_rows=state.get("price_rows"),
            pipeline_data_source=state.get("data", {}).get("pipeline_data_source"),
        )
        gate = _recommendation_gate(state, performance=performance)
        validated = gate is None or gate.validated
        payload = {
            "headline": (
                "전략 분석이 완료되었습니다."
                if validated
                else "전략이 백테스트 검증을 통과하지 못했습니다."
            ),
            "message": _ready_message(state, validated=validated),
            "next_actions": [
                "web_projection 확인",
                "email_projection 예약",
                "실거래 전 데이터 어댑터 연결",
                *_availability_next_actions(state.get("data", {}).get("data_availability", {})),
                *_freshness_next_actions(state.get("freshness_evidence")),
            ],
            "candidate_cards": cards,
            "report": report,
            "performance": performance,
            "recommendation_gate": gate,
            "ticker_actions": _ticker_actions(
                state,
                cards,
                performance=performance,
                recommendation_gate=gate,
            ),
        }
    elif state["ambiguity"]["category"] == AmbiguityCode.NO_STRATEGY_INTENT.value:
        clarification = _clarification_from_ambiguity(state["ambiguity"])
        payload = {
            "headline": "전략 입력을 기다리고 있습니다.",
            "message": state["ambiguity"]["reason"],
            "next_actions": ["예: RSI가 30 이하일 때 매수하고 70 이상일 때 매도"],
            "candidate_cards": [],
            **clarification,
        }
    elif status == EnvelopeStatus.REJECTED:
        clarification = _clarification_from_ambiguity(state["ambiguity"])
        payload = {
            "headline": "MVP 범위 밖 전략입니다.",
            "message": state["ambiguity"]["reason"],
            "next_actions": ["KRX 현물 주식 전략으로 다시 입력"],
            "candidate_cards": cards,
            **clarification,
        }
    else:
        clarification = _clarification_from_ambiguity(state["ambiguity"])
        payload = {
            "headline": "추가 확인이 필요합니다.",
            "message": state["ambiguity"]["reason"],
            "next_actions": ["후보 카드 중 하나 선택", "시장/기간/조건 보강"],
            "candidate_cards": cards,
            **clarification,
        }
    internal = build_internal_payload(state)
    DEBUG_STORE.put(state["debug_ref"], internal)
    envelope = build_envelope(
        status=status,
        trace_id=state["trace_id"],
        debug_ref=state["debug_ref"],
        user_payload=payload,
        strategy_spec=state.get("strategy_spec"),
        retryable=status in {EnvelopeStatus.NEED_CLARIFICATION, EnvelopeStatus.FAILED},
        semantic_slots=state.get("semantic_slots"),
        data_requirements=state.get("data_requirements"),
        source_usage=state.get("source_usage"),
        freshness_status=state.get("freshness_status"),
        freshness_evidence=state.get("freshness_evidence"),
        proxy_disclosure=state.get("proxy_disclosure"),
        failure_cause=state.get("failure_cause"),
        evidence_refs=state.get("evidence_refs"),
        rule_provenance=_rule_provenance(state),
    )
    _record_analysis_memory(state, status)
    return {"envelope": envelope.model_dump()}


def _ready_message(state: QuantAgentState, *, validated: bool) -> str:
    """What ran, plus what the interpreter decided in the user's place.

    The choices it made are disclosed on the result rather than asked about up front -
    the user sees the strategy they got and exactly which parts of it they did not
    specify, instead of being stopped at a form.
    """

    freshness = state.get("freshness_evidence") or {}
    if isinstance(freshness, Mapping) and freshness.get("no_recommendation"):
        base = "freshness 한계로 추천을 생성하지 않았습니다. 아래 결과는 검토용입니다."
    else:
        base = (
            "StrategySpec, 후보 코드 백테스트, 신호, 리스크, 리포트를 생성했습니다."
            if validated
            else "백테스트 목표 기준에 못 미쳐 아래 종목은 추천이 아닌 참고용입니다."
        )
    sections = [base, *_universe_split_disclosure(state)]
    ambiguity = state.get("ambiguity") or {}
    assumptions = [
        str(item).strip() for item in ambiguity.get("assumptions", []) if str(item).strip()
    ]
    if assumptions:
        listed = "\n".join(f"- {item}" for item in assumptions[:5])
        sections.append(f"지정하지 않으신 부분은 이렇게 정해서 진행했습니다:\n{listed}")
    return "\n\n".join(sections)


def _universe_split_disclosure(state: QuantAgentState) -> list[str]:
    """Explain any point-in-time universe split between testing and screening."""

    pipeline = state.get("data", {}).get("pipeline_data_source") or {}
    descriptor = pipeline.get("backtest_universe") if isinstance(pipeline, Mapping) else None
    if not isinstance(descriptor, Mapping):
        return []
    lines = [
        (
            "백테스트는 과거 시점(PIT) 기준 유니버스로 규칙 자체를 검증하고, "
            "아래 종목은 같은 규칙을 오늘 데이터에 적용한 결과입니다. "
            "두 목록이 서로 다른 것은 정상입니다."
        )
    ]
    excluded = descriptor.get("excluded_screening_candidate_count")
    if isinstance(excluded, int) and not isinstance(excluded, bool) and excluded > 0:
        lines.append(
            f"오늘 스크리닝 후보 중 {excluded}종목은 백테스트 구간의 과거 시점 유니버스에 없어 "
            "백테스트 거래 대상에서 제외됐습니다."
        )
    return lines


def _record_analysis_memory(state: QuantAgentState, status: EnvelopeStatus) -> None:
    """Note how this run turned out, for the next analysis of the same strategy."""

    memory = AnalysisMemory.from_env()
    if not memory.enabled:
        return
    strategy = state.get("strategy_spec") or {}
    strategy_id = str(strategy.get("strategy_id") or "")
    if not strategy_id:
        return

    data = state.get("data") or {}
    pipeline = data.get("pipeline_data_source") or {}
    relaxation = pipeline.get("screening_relaxation") or {}
    availability = data.get("data_availability") or {}
    performance = (
        project_public_performance(
            state.get("backtest"),
            price_rows=state.get("price_rows"),
            pipeline_data_source=state.get("data", {}).get("pipeline_data_source"),
        )
        or {}
    )
    payload = performance.performance if isinstance(performance, PerformanceAvailable) else None
    metrics = payload.get("metrics") if isinstance(payload, Mapping) else None

    try:
        memory.record(
            strategy_id,
            query=str(state.get("user_query") or ""),
            outcome=status.value,
            candidate_count=len(data.get("screening_candidates") or []),
            metrics=metrics or {},
            relaxation_rounds=int(relaxation.get("relaxation_rounds") or 0),
            unmet_requirements=[
                str(item.get("label"))
                for item in availability.get("unsupported_capabilities") or []
            ],
            note=(state.get("strategy_revision") or {}).get("rationale"),
        )
    except Exception:
        # Memory is an optimisation; never let it take down a completed analysis.
        _logger.warning("could not record analysis memory", exc_info=True)


def classify_query(query: str) -> AmbiguityCode:
    """The fallback used only when no model is available to interpret the request.

    It deliberately answers two questions and not the others: is this small talk, and
    is this an asset class the warehouse can price. Everything it used to decide by
    keyword - whether a term was "known", whether enough conditions were named,
    whether two goals conflicted - is a judgment call that belongs to
    resolve_strategy_intent, which can search and then commit. Matching phrases here
    only ever produced questions for inputs a person would have had no trouble acting
    on.
    """

    if _is_small_talk(query):
        return AmbiguityCode.NO_STRATEGY_INTENT
    return AmbiguityCode.INFEASIBLE if _is_unsupported_asset_class(query) else AmbiguityCode.READY


def _is_unsupported_asset_class(query: str) -> bool:
    lowered = query.lower()
    return any(
        term in lowered for term in ("옵션", "양매도", "선물", "crypto", "가상화폐", "비트코인")
    )


# Greetings, thanks and idle questions - a backtest is not an answer to any of them.
_SMALL_TALK_TERMS = (
    "안녕",
    "ㅎㅇ",
    "하이",
    "반가",
    "고마",
    "감사",
    "ㄳ",
    "수고",
    "잘 지내",
    "날씨",
    "몇 시",
    "누구야",
    "누구세요",
    "뭐 해",
    "뭐해",
    "심심",
)
# Anything the warehouse can act on. Present only to keep the check above from firing
# on a real request that happens to be polite.
_MARKET_TERMS = (
    "주",
    "종목",
    "매수",
    "매도",
    "전략",
    "투자",
    "수익",
    "차트",
    "코스피",
    "코스닥",
    "백테스트",
    "포트폴리오",
    "배당",
    "실적",
    "지수",
    "stock",
    "buy",
    "sell",
    "strategy",
)
_SMALL_TALK_LENGTH_LIMIT = 20


def _is_small_talk(query: str) -> bool:
    """Whether this message is not asking for a strategy at all.

    Deliberately shaped as positive evidence of chit-chat rather than as an allowlist
    of strategy words. An allowlist decides by what it fails to recognise, so
    "화학 관련주 사줘" - a perfectly clear request naming no listed keyword - came back
    as a greeting. Every uncertain input must fall through to the analysis; the cost of
    running one is a wasted job, the cost of refusing one is the user's answer.

    Only consulted for the obvious cases, and before the model is called so a greeting
    does not pay for a web search. Live runs let resolve_strategy_intent decide.
    """

    normalized = " ".join(query.split()).lower()
    if not normalized or len(normalized) > _SMALL_TALK_LENGTH_LIMIT:
        return False
    if any(term in normalized for term in _MARKET_TERMS):
        return False
    return any(term in normalized for term in _SMALL_TALK_TERMS)


def parse_semantic_slots(query: str, *, trace_id: str) -> SemanticSlots:
    lowered = query.lower()
    indicator: list[str] = []
    threshold: list[str] = []
    lookback: list[str] = []
    horizon: list[str] = []
    price_basis: list[str] = []
    event: list[str] = []
    action: list[str] = []
    missing_slots: list[str] = []
    contradictions: list[str] = []

    if "rsi" in lowered or "과매도" in query:
        indicator.append("rsi")
    if "볼린저" in query or "bollinger" in lowered:
        indicator.append("bollinger")
    if any(term in query for term in ("거래량", "거래대금")):
        indicator.append("volume")
    if any(term in query for term in ("20일선", "20일 이동평균")):
        indicator.append("sma_20")
    if "200일" in query:
        indicator.append("sma_200")
    if any(term in query for term in ("per", "PER", "저PER")):
        indicator.append("per")
    if "roe" in lowered or "ROE" in query:
        indicator.append("roe")

    if "rsi" in lowered and any(value in query for value in ("30", "70")):
        rsi_rules = rsi_trade_rules(query)
        operator = {"lt": "<", "lte": "<=", "gt": ">", "gte": ">="}[
            rsi_rules.entry_operator
        ]
        threshold.append(f"rsi {operator} {int(rsi_rules.entry_threshold)}")
    if "40" in query and "rsi" in lowered:
        threshold.append("rsi <= 40")
    if "150" in query and "거래량" in query:
        threshold.append("volume_ratio_20 >= 1.5")
    if "100" in query and "부채" in query:
        threshold.append("debt_ratio <= 100")

    if "14" in query and "rsi" in lowered:
        lookback.append("14d")
    if "20일" in query:
        lookback.append("20 trading days")
    if "52주" in query:
        lookback.append("52w")
    if "최근" in query:
        horizon.append("recent")
    if "3개월" in query:
        horizon.append("3m")
    if "5거래일" in query:
        horizon.append("5 trading days")

    if any(term in query for term in ("종가", "close", "재진입", "반등", "돌파")):
        price_basis.append("close")
    if "하단" in query and ("재진입" in query or "반등" in query) and "bollinger" in indicator:
        event.append("lower_band_reentry")
        action.extend(["find_candidates", "reentry", "cross_above"])
        if "close" not in price_basis:
            price_basis.append("close")
    elif any(term in query for term in ("신고가", "돌파")):
        event.append("new_52w_high" if "52주" in query else "upper_band_breakout")
        action.extend(["find_candidates", "breakout"])
    elif "반등" in query:
        event.append("rebound")
        action.extend(["find_candidates", "rebound"])
    else:
        action.append("find_candidates")

    sector = extract_sector_from_query(query, get_known_sectors())
    if not indicator:
        missing_slots.append("indicator")
    if "bollinger" in indicator and "lower_band_reentry" in event and "close" not in price_basis:
        missing_slots.append("price_basis")
    if _has_conflicting_targets(query):
        contradictions.append("low_volatility_vs_short_term_surge")

    confidence = 0.9 if indicator and not contradictions else 0.62 if indicator else 0.45
    parse_status = (
        "ready"
        if confidence >= 0.65 and not contradictions and not missing_slots
        else "needs_clarification"
    )
    return SemanticSlots(
        indicator=_unique(indicator),
        threshold=_unique(threshold),
        lookback=_unique(lookback),
        horizon=_unique(horizon),
        price_basis=_unique(price_basis),
        event=_unique(event),
        action=_unique(action),
        sector=sector,
        slot_evidence_refs=[f"semantic:{trace_id}:deterministic"],
        missing_slots=missing_slots,
        contradictions=contradictions,
        confidence=confidence,
        parse_status=parse_status,
    )


def plan_data_requirements(
    semantic_slots: SemanticSlots, *, query: str | None = None
) -> list[DataRequirement]:
    """What this run will read, as the loader will actually read it.

    The families used to be inferred purely from `semantic_slots`, whose indicator list
    comes from a fixed Korean keyword table (rsi/볼린저/거래량/20일선/200일/per/roe). A
    strategy phrased outside that table - "반도체 섹터 주도주 중 상대강도 강한 종목" - set
    no indicator, so the plan came out empty and the run reported "조회할 데이터 항목
    0종" while the loader went on to screen the whole universe on price/TA and backtest
    233 names. The plan was describing a different run than the one that executed.

    So the families are taken from the screening profile the loader will use, and the
    slots only add what the profile cannot know about. `query` is optional so callers
    that only have slots still work; passing it is what makes the count honest.
    """

    requirements: list[DataRequirement] = []
    indicators = set(semantic_slots.indicator)
    events = set(semantic_slots.event)
    families = set(screening_data_families(query)) if query is not None else set()
    if (
        "ohlcv_ta" in families
        or indicators & {"rsi", "bollinger", "volume", "sma_20", "sma_200"}
        or events & {"lower_band_reentry", "new_52w_high", "upper_band_breakout"}
    ):
        requirements.append(
            DataRequirement(
                family="ohlcv_ta",
                availability="available",
                owner="ai_graph",
                preferred_source="internal_db",
                fallback_sources=["krx"],
                freshness_requirement="same_trading_day",
                source_confidence_floor=0.85,
                evidence_ref="data-plan:ohlcv_ta",
            )
        )
    if (
        "fundamentals" in families
        or indicators & {"per", "roe"}
        or any(slot in semantic_slots.threshold for slot in ("debt_ratio <= 100",))
    ):
        requirements.append(
            DataRequirement(
                family="fundamentals",
                availability="outside_owner",
                owner="product_data_gap",
                preferred_source="dart",
                fallback_sources=["aoai_web_search"],
                freshness_requirement="report_period",
                source_confidence_floor=0.75,
                proxy_allowed=True,
                evidence_ref="data-plan:fundamentals",
            )
        )
    if events & {"disclosure", "earnings_surprise"}:
        requirements.append(
            DataRequirement(
                family="disclosure",
                availability="partial",
                owner="data_source_config",
                preferred_source="dart",
                fallback_sources=["aoai_web_search"],
                freshness_requirement="latest_filing",
                source_confidence_floor=0.8,
                evidence_ref="data-plan:disclosure",
            )
        )
    return requirements


def build_source_usage(
    query: str,
    requirements: list[DataRequirement],
    *,
    trace_id: str,
    pipeline_metadata: Mapping[str, Any],
) -> list[SourceUsage]:
    now = datetime.now(UTC)
    usage: list[SourceUsage] = []
    for requirement in requirements:
        uses_postgres = (
            pipeline_metadata.get("source") == "postgres"
            and requirement.preferred_source == "internal_db"
        )
        source_ref = pipeline_metadata.get("price_source") if uses_postgres else None
        usage.append(
            SourceUsage(
                source_type="internal_db" if uses_postgres else "none",
                query=f"{requirement.family}: {query}",
                retrieved_at=now,
                source_refs=[str(source_ref)] if source_ref else [],
                freshness_status=(
                    freshness_status_from_metadata(pipeline_metadata)
                    if uses_postgres
                    else "unknown"
                ),
                confidence=requirement.source_confidence_floor if uses_postgres else 0.0,
                fallback_used=pipeline_metadata.get("source") == "fixture",
                evidence_refs=[f"source:{trace_id}:{requirement.family}"],
            )
        )
    return usage


def build_evidence_refs(source_usage: list[SourceUsage], *, trace_id: str) -> list[EvidenceRef]:
    return [
        EvidenceRef(
            ref_id=usage.evidence_refs[0] if usage.evidence_refs else f"source:{trace_id}:{index}",
            source_type=usage.source_type,
            stage="data_retrieval",
            retrieved_at=usage.retrieved_at,
            sanitized_summary=f"{usage.source_type} source used for {usage.query.split(':', 1)[0]}",
            confidence=usage.confidence,
        )
        for index, usage in enumerate(source_usage)
    ]


def data_source_inventory() -> list[dict[str, Any]]:
    return [
        {
            "source_type": "internal_db",
            "families": ["ohlcv_ta", "analyst_evidence"],
            "live_required": False,
        },
        {"source_type": "krx", "families": ["ohlcv_ta"], "live_required": False},
        {
            "source_type": "dart",
            "families": ["disclosure", "event", "fundamentals"],
            "live_required": False,
        },
        {
            "source_type": "aoai_web_search",
            "families": ["event", "macro_fx_rates_commodities", "consensus_guidance"],
            "live_required": False,
        },
        {
            "source_type": "analyst_evidence",
            "families": ["analyst_evidence", "consensus_guidance"],
            "live_required": False,
        },
    ]


def _aggregate_freshness_status(source_usage: list[SourceUsage]) -> str:
    statuses = {usage.freshness_status for usage in source_usage}
    if "stale" in statuses:
        return "stale"
    if "unknown" in statuses:
        return "unknown"
    return "fresh" if statuses else "unknown"


def _proxy_disclosure(requirements: list[DataRequirement]) -> dict[str, str] | None:
    proxied = [requirement for requirement in requirements if requirement.proxy_used]
    if not proxied:
        return None
    return {
        requirement.family: requirement.proxy_disclosure.get("reason", "proxy used")
        if requirement.proxy_disclosure
        else "proxy used"
        for requirement in proxied
    }


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def strategy_candidate_cards(
    query: str,
    *,
    screening_candidates: list[dict[str, Any]] | None = None,
    sector: str | None = None,
) -> list[StrategyCandidateCard]:
    cards = _static_strategy_candidate_cards(query)
    if screening_candidates:
        cards = _attach_screening_matches(cards, screening_candidates, sector=sector)
    return cards


def _attach_screening_matches(
    cards: list[StrategyCandidateCard],
    screening_candidates: list[dict[str, Any]],
    *,
    sector: str | None,
) -> list[StrategyCandidateCard]:
    if not cards:
        return cards
    filtered = [
        c for c in screening_candidates if not sector or c.get("sector") == sector
    ] or screening_candidates
    matches = [
        ScreeningMatch(
            ticker=c["ticker"],
            name=c["name"],
            market=c["market"],
            sector=c.get("sector"),
            as_of_date=c["as_of_date"],
            close=c.get("close"),
            matched_rules=c.get("matched_rules", []),
        )
        for c in filtered
    ]
    primary = cards[0].model_copy(
        update={
            "sector": sector,
            "matches": matches,
            "title": f"{cards[0].title} · {sector}" if sector else cards[0].title,
        }
    )
    return [primary, *cards[1:]]


def _static_strategy_candidate_cards(query: str) -> list[StrategyCandidateCard]:
    lowered = query.lower()
    if any(term in query for term in ("EPS", "컨센서스", "어닝", "가이던스", "실적 발표")):
        return [
            StrategyCandidateCard(
                strategy_id="earnings_momentum",
                title="실적 모멘텀",
                summary="컨센서스 상향·어닝 서프라이즈 조건을 기술적 신고가/상대강도 proxy로 검증합니다.",
                key_conditions=["EPS 상향", "20일 신고가", "상대강도", "거래량"],
                confidence=0.7,
                reason="실적 데이터가 부족한 구간도 가격 신고가와 거래량으로 모멘텀 검증이 가능합니다.",
            ),
            StrategyCandidateCard(
                strategy_id="breakout_volume_momentum",
                title="거래량 돌파 모멘텀",
                summary="신고가 또는 박스권 상단 돌파와 20일 평균 대비 거래량 증가를 결합합니다.",
                key_conditions=["신고가", "거래량", "20일선", "상대강도"],
                confidence=0.67,
                reason="실적 모멘텀의 시장 반응을 OHLCV로 대체 검증합니다.",
            ),
            StrategyCandidateCard(
                strategy_id="relative_strength_leader",
                title="상대강도 주도주",
                summary="시장보다 강한 1개월·3개월 수익률을 우선합니다.",
                key_conditions=["1개월 RS", "3개월 RS", "50일선"],
                confidence=0.63,
                reason="컨센서스 확인 전에도 주가 반응이 강한 후보를 좁힙니다.",
            ),
        ]
    if any(term in query for term in ("기관", "외국인", "공매도", "숏커버링", "갭", "수급")):
        return [
            StrategyCandidateCard(
                strategy_id="flow_accumulation",
                title="수급 모멘텀",
                summary="기관·외국인 순매수 또는 수급 이벤트를 거래량·양봉·20일선 proxy로 검증합니다.",
                key_conditions=["순매수", "거래량", "양봉", "20일선"],
                confidence=0.66,
                reason="수급 원천 데이터가 없으면 가격·거래량 반응으로 1차 후보를 만듭니다.",
            ),
            StrategyCandidateCard(
                strategy_id="short_covering_proxy",
                title="숏커버링 proxy",
                summary="공매도 잔고 조건은 거래량 증가와 양봉 돌파로 대체 검증합니다.",
                key_conditions=["공매도", "거래량 증가", "양봉 돌파"],
                confidence=0.6,
                reason="공매도 데이터 연결 전에도 커버링성 가격 반응을 볼 수 있습니다.",
            ),
            StrategyCandidateCard(
                strategy_id="breakout_volume_momentum",
                title="거래량 돌파 모멘텀",
                summary="수급이 가격 돌파로 이어졌는지 확인합니다.",
                key_conditions=["신고가", "거래량", "상대강도"],
                confidence=0.58,
                reason="수급 이벤트의 후행 확인 조건입니다.",
            ),
        ]
    if any(term in query for term in ("볼린저", "밴드", "변동성")):
        return [
            StrategyCandidateCard(
                strategy_id="bollinger_squeeze_breakout",
                title="볼린저 스퀴즈 돌파",
                summary="밴드 폭 축소 후 상단 돌파, 또는 하단 이탈 후 재진입을 봅니다.",
                key_conditions=["밴드폭 축소", "상단 돌파", "재진입", "저변동성"],
                confidence=0.76,
                reason="입력의 변동성 축소/밴드 조건과 직접 매칭됩니다.",
            ),
            StrategyCandidateCard(
                strategy_id="rsi_rebound",
                title="RSI 과매도 반등",
                summary="하단 이탈 뒤 반등 여부를 RSI 회복으로 보조 확인합니다.",
                key_conditions=["RSI <= 30", "RSI 회복", "거래량"],
                confidence=0.68,
                reason="밴드 재진입과 같은 평균회귀 후보입니다.",
            ),
            StrategyCandidateCard(
                strategy_id="breakout_volume_momentum",
                title="거래량 돌파 모멘텀",
                summary="스퀴즈 이후 상단 돌파를 거래량으로 확인합니다.",
                key_conditions=["상단 돌파", "거래량", "20일선"],
                confidence=0.64,
                reason="스퀴즈 돌파의 확인 후보입니다.",
            ),
        ]
    if "배당" in query or any(term in query for term in ("리츠", "유틸리티", "금리")):
        return [
            StrategyCandidateCard(
                strategy_id="dividend_defensive",
                title="배당 방어주",
                summary="배당수익률·재무 안정성과 200일선 회복 여부를 함께 봅니다.",
                key_conditions=["배당수익률", "부채비율", "배당 삭감 없음", "200일선"],
                confidence=0.72,
                reason="입력의 배당/인컴 성격과 가장 직접적으로 연결됩니다.",
            ),
            StrategyCandidateCard(
                strategy_id="low_vol_defensive",
                title="저변동 배당 방어주",
                summary="저변동성·배당·상대강도를 결합해 방어주 후보를 좁힙니다.",
                key_conditions=["저변동성", "배당", "상대강도", "20일선"],
                confidence=0.68,
                reason="방어주 문맥이면 변동성 필터를 함께 적용합니다.",
            ),
            StrategyCandidateCard(
                strategy_id="rate_sensitive_income",
                title="금리 민감 인컴주",
                summary="리츠·유틸리티·배당주의 금리 하락기 강세를 기술 신호로 확인합니다.",
                key_conditions=["금리", "인컴", "50일선", "상대강도"],
                confidence=0.62,
                reason="금리 하락기 문맥의 대체 후보입니다.",
            ),
        ]
    if any(term in query for term in ("성장주", "성장률", "영업이익률", "퀄리티", "매출")):
        return [
            StrategyCandidateCard(
                strategy_id="quality_growth",
                title="퀄리티 성장주",
                summary="수익성·ROE·매출 성장률 조건을 50일선 추세 proxy로 검증합니다.",
                key_conditions=["ROE", "영업이익률", "매출 성장률", "50일선"],
                confidence=0.7,
                reason="성장성과 수익성 조건을 모두 포함합니다.",
            ),
            StrategyCandidateCard(
                strategy_id="reasonable_growth",
                title="합리적 성장주",
                summary="ROE·매출 성장률·PER 업종 비교를 결합한 GARP 후보입니다.",
                key_conditions=["ROE", "매출 성장률", "PER 업종 이하", "50일선"],
                confidence=0.68,
                reason="성장성과 밸류에이션을 동시에 요구할 때 적합합니다.",
            ),
            StrategyCandidateCard(
                strategy_id="growth_momentum",
                title="성장 모멘텀",
                summary="성장률 상위 후보 중 50일선 위 추세가 살아 있는 종목을 봅니다.",
                key_conditions=["성장률", "업종 상위", "50일선", "상대강도"],
                confidence=0.64,
                reason="성장 조건의 시장 반응을 가격 추세로 확인합니다.",
            ),
        ]
    if any(
        term in lowered or term in query
        for term in ("per", "pbr", "roe", "저평가", "가치", "부채", "순현금", "배당", "fcf")
    ):
        return [
            StrategyCandidateCard(
                strategy_id="value_quality",
                title="저평가 퀄리티",
                summary="PER/PBR/ROE 같은 재무 조건을 먼저 두고, 기술적 상대강도로 최종 확인합니다.",
                key_conditions=["PER/PBR", "ROE", "부채비율", "상대강도"],
                confidence=0.72,
                reason="재무 데이터가 없는 구간은 L1 정의와 기술적 proxy로 query smooth가 필요합니다.",
            ),
            StrategyCandidateCard(
                strategy_id="dividend_defensive",
                title="배당 방어주",
                summary="배당수익률·재무 안정성을 우선하고 200일선 회복 여부로 진입 타이밍을 봅니다.",
                key_conditions=["배당수익률", "부채비율", "200일선", "저변동성"],
                confidence=0.66,
                reason="배당/부채 조건은 공개 재무 데이터 연결 전까지 별도 확인이 필요합니다.",
            ),
            StrategyCandidateCard(
                strategy_id="reasonable_growth",
                title="합리적 성장주",
                summary="ROE·매출 성장률·PER 업종 비교를 결합한 GARP 후보입니다.",
                key_conditions=["ROE", "매출 성장률", "PER 업종 이하", "50일선"],
                confidence=0.64,
                reason="성장성과 밸류에이션을 함께 요구하는 입력에 가장 가까운 후보입니다.",
            ),
        ]
    if any(
        term in query
        for term in ("신고가", "거래량", "모멘텀", "돌파", "상대강도", "주도주", "숏커버링", "갭")
    ):
        return [
            StrategyCandidateCard(
                strategy_id="breakout_volume_momentum",
                title="거래량 돌파 모멘텀",
                summary="신고가 또는 박스권 상단 돌파와 20일 평균 대비 거래량 증가를 결합합니다.",
                key_conditions=["신고가", "거래량 150%", "20일선 위", "상대강도"],
                confidence=0.82,
                reason="OHLCV와 TA 지표로 가장 즉시 검증 가능한 모멘텀 유형입니다.",
            ),
            StrategyCandidateCard(
                strategy_id="relative_strength_leader",
                title="상대강도 주도주",
                summary="1개월·3개월 수익률이 시장보다 강한 종목을 추세 후보로 봅니다.",
                key_conditions=["1개월 RS", "3개월 RS", "50일선", "거래대금"],
                confidence=0.77,
                reason="섹터/시장 대비 강도 조건을 기술 지표로 매핑할 수 있습니다.",
            ),
            StrategyCandidateCard(
                strategy_id="short_covering_proxy",
                title="숏커버링 proxy",
                summary="공매도 잔고 데이터가 없으면 거래량 증가와 양봉 돌파를 proxy로 사용합니다.",
                key_conditions=["거래량 증가", "양봉 돌파", "신고가 근처", "변동성 확대"],
                confidence=0.58,
                reason="공매도 잔고는 C5가 아니라 데이터 보강 전 proxy 후보로 처리합니다.",
            ),
        ]
    if any(term in query for term in ("눌림목", "200일", "20일선", "20일 이동평균", "120일")):
        return [
            StrategyCandidateCard(
                strategy_id="pullback_trend",
                title="상승추세 눌림목",
                summary="200일선 위 상승추세에서 20일선까지 조정받은 뒤 재상승하는 후보입니다.",
                key_conditions=["200일선 위", "20일선 조정", "재돌파", "손절선"],
                confidence=0.82,
                reason="L1 눌림목 정의와 이동평균 기반 L2 조건이 직접 매칭됩니다.",
            ),
            StrategyCandidateCard(
                strategy_id="rsi_rebound",
                title="RSI 과매도 반등",
                summary="RSI(14)가 30 이하로 내려간 뒤 30을 회복하는 단기 반등 후보입니다.",
                key_conditions=["RSI <= 30", "RSI 30 상향", "거래량 확인"],
                confidence=0.78,
                reason="눌림목 뒤 반등 확인을 보조하는 기술 후보입니다.",
            ),
            StrategyCandidateCard(
                strategy_id="bollinger_squeeze_breakout",
                title="볼린저 스퀴즈 돌파",
                summary="밴드 폭 축소 후 상단 돌파, 또는 하단 이탈 후 밴드 재진입을 봅니다.",
                key_conditions=["밴드폭 축소", "상단 돌파", "재진입", "저변동성"],
                confidence=0.72,
                reason="조정 뒤 변동성 회복을 확인하는 대체 후보입니다.",
            ),
        ]
    if (
        any(
            term in query
            for term in ("눌림목", "200일", "20일선", "120일", "볼린저", "변동성", "반등")
        )
        or "rsi" in lowered
    ):
        return [
            StrategyCandidateCard(
                strategy_id="rsi_rebound",
                title="RSI 과매도 반등",
                summary="RSI(14)가 30 이하로 내려간 뒤 30을 회복하는 단기 반등 후보입니다.",
                key_conditions=["RSI <= 30", "RSI 30 상향", "거래량 확인"],
                confidence=0.86,
                reason="현재 백테스트 엔진이 가장 안정적으로 검증하는 기술 반등 유형입니다.",
            ),
            StrategyCandidateCard(
                strategy_id="pullback_trend",
                title="상승추세 눌림목",
                summary="200일선 위 상승추세에서 20일선까지 조정받은 뒤 재상승하는 후보입니다.",
                key_conditions=["200일선 위", "20일선 조정", "재돌파", "손절선"],
                confidence=0.78,
                reason="L1 눌림목 정의와 이동평균 기반 L2 조건이 매칭됩니다.",
            ),
            StrategyCandidateCard(
                strategy_id="bollinger_squeeze_breakout",
                title="볼린저 스퀴즈 돌파",
                summary="밴드 폭 축소 후 상단 돌파, 또는 하단 이탈 후 밴드 재진입을 봅니다.",
                key_conditions=["밴드폭 축소", "상단 돌파", "재진입", "저변동성"],
                confidence=0.74,
                reason="변동성 축소와 돌파 조건을 명확히 분리할 수 있습니다.",
            ),
        ]
    return [
        StrategyCandidateCard(
            strategy_id="rsi_mean_reversion",
            title="RSI 평균회귀",
            summary="RSI 30 이하 매수, 70 이상 청산.",
            key_conditions=["RSI <= 30", "RSI >= 70"],
            confidence=0.86,
            reason="과매도/과매수 기준이 명확한 기본 후보입니다.",
        ),
        StrategyCandidateCard(
            strategy_id="pullback_trend",
            title="눌림목 추세 추종",
            summary="상승 추세 내 단기 조정 후 재진입.",
            key_conditions=["추세 필터", "조정 폭", "재상승 확인"],
            confidence=0.74,
            reason="모호한 추세 추종 입력을 이동평균 조건으로 구체화합니다.",
        ),
        StrategyCandidateCard(
            strategy_id="value_quality",
            title="저평가 퀄리티",
            summary="밸류에이션과 수익성 조건을 함께 확인.",
            key_conditions=["PER/PBR", "ROE", "거래대금"],
            confidence=0.68,
            reason="재무 조건이 포함된 입력에 대한 query smooth 후보입니다.",
        ),
    ]


def build_clarification_prompt(category: AmbiguityCode, query: str) -> dict[str, Any]:
    """Three things still stop a run: a message that is not asking for a strategy at
    all, an unsupported asset class, and a condition the warehouse cannot evaluate.
    Everything else the interpreter decides itself, so there is no longer a prompt for
    a vague sentence or an unfamiliar term."""

    if category == AmbiguityCode.NO_STRATEGY_INTENT:
        return {
            "question": "어떤 투자 전략이나 매매 조건을 분석할까요?",
            "question_reason": "전략 요청이 아닌 대화로 보여 분석을 시작하지 않았습니다.",
            "options": [],
            "recommended": None,
            "confidence": 1.0,
            "confidence_reason": "전략을 요청한 것이 확실할 때만 분석 파이프라인을 시작합니다.",
        }
    if category == AmbiguityCode.INFEASIBLE:
        options = [
            ClarificationOption(
                label="KRX 현물로 대체", reason="현재 실행 가능한 데이터/백테스트 범위입니다."
            ),
            ClarificationOption(
                label="기술 신호만 분석", reason="파생상품 노출 대신 현물 proxy 신호를 확인합니다."
            ),
            ClarificationOption(
                label="지원 범위 확인", reason="지원하지 않는 자산군을 명확히 분리합니다."
            ),
        ]
        return _clarification(
            question="KRX 현물 주식 전략으로 바꿔서 볼까요?",
            question_reason="옵션·선물·가상자산은 현재 데이터 인프라 범위 밖입니다.",
            options=options,
            recommended=0,
            confidence=0.9,
            confidence_reason="현재 API/백테스트는 KRX 현물 주식 중심으로 검증됩니다.",
        )
    cards = strategy_candidate_cards(query)
    options = [
        ClarificationOption(
            label=card.title,
            reason=card.reason or card.summary,
        )
        for card in cards[:3]
    ]
    return _clarification(
        question="먼저 어떤 후보 전략으로 구체화할까요?",
        question_reason="입력 조건 일부가 재무·컨센서스·공시 데이터에 걸쳐 있어 실행 가능한 후보로 나눕니다.",
        options=options,
        recommended=0,
        confidence=0.7,
        confidence_reason="첫 후보가 입력의 핵심 조건과 현재 검증 가능한 데이터 범위의 교집합이 가장 큽니다.",
    )


def _clarification(
    *,
    question: str,
    question_reason: str,
    options: list[ClarificationOption],
    recommended: int,
    confidence: float,
    confidence_reason: str,
) -> dict[str, Any]:
    return {
        "question": question,
        "question_reason": question_reason,
        "options": options[:3],
        "recommended": recommended,
        "confidence": confidence,
        "confidence_reason": confidence_reason,
    }


def _clarification_from_ambiguity(ambiguity: dict[str, Any]) -> dict[str, Any]:
    return {
        "question": ambiguity.get("clarification_question"),
        "options": [
            ClarificationOption.model_validate(option) for option in ambiguity.get("options", [])
        ],
        "recommended": ambiguity.get("recommended_option"),
    }


def _ambiguity_dimensions(category: AmbiguityCode, query: str) -> list[str]:
    if category == AmbiguityCode.READY:
        return []
    if category == AmbiguityCode.NO_STRATEGY_INTENT:
        return ["intent_missing"]
    if category == AmbiguityCode.INPUT_AMBIGUOUS:
        # The only route left to this category is a condition the warehouse cannot
        # evaluate (data_node's _unverifiable_ambiguity), never a vague sentence.
        return ["data_missing"]
    if category == AmbiguityCode.TERM_UNKNOWN:
        return ["intent_ambiguous", "source_resolvable"]
    if category == AmbiguityCode.CONFLICTING:
        return ["intent_ambiguous", "source_conflict"]
    return ["unsupported_source"]


def _clarification_blocker_type(category: AmbiguityCode) -> str | None:
    if category == AmbiguityCode.READY:
        return None
    if category == AmbiguityCode.NO_STRATEGY_INTENT:
        return "intent_missing"
    if category == AmbiguityCode.INPUT_AMBIGUOUS:
        return "data_missing"
    if category == AmbiguityCode.TERM_UNKNOWN:
        return "intent_ambiguous"
    if category == AmbiguityCode.CONFLICTING:
        return "source_conflict"
    return "unsupported_source"


def _has_conflicting_targets(query: str) -> bool:
    return any(term in query for term in ("변동성 낮", "저변동성")) and "급등" in query


def _is_pullback_rsi_volume_query(query: str) -> bool:
    lowered = query.lower()
    has_trend_filter = "200일" in query or "sma200" in lowered or "sma_200" in lowered
    has_rsi_pullback = "rsi" in lowered and ("40" in query or "눌" in query)
    has_volume_filter = "거래량" in query or "volume" in lowered
    return has_trend_filter and has_rsi_pullback and has_volume_filter


def _ambiguity_reasons(category: AmbiguityCode, query: str) -> list[str]:
    if category == AmbiguityCode.READY:
        return ["L1/L2 또는 기술 지표 조건으로 해석 가능한 KRX 현물 전략입니다."]
    if category == AmbiguityCode.NO_STRATEGY_INTENT:
        return ["전략 관련 표현이 없어 분석 파이프라인을 시작하지 않습니다."]
    if category == AmbiguityCode.INPUT_AMBIGUOUS:
        return ["요청한 조건 중 현재 적재된 데이터로 검증할 수 없는 항목이 있습니다."]
    return [f"{query[:40]} 입력은 현재 KRX 현물 데이터 범위를 벗어난 자산군을 포함합니다."]


def build_strategy_spec(
    query: str,
    *,
    variant: str,
    semantic_slots: Mapping[str, Any] | None = None,
    original_query: str | None = None,
) -> StrategySpec:
    # The interpreter may turn "알아서 좋은 거" into a concrete RSI sentence.  That
    # resolution is useful for data lookup but it must not erase the user's original
    # lack of a rule; otherwise an arbitrary interpreter default becomes user intent.
    preference_query = original_query or query
    selection_mode = classify_strategy_request(preference_query)
    automatic_preferences = (
        infer_automatic_strategy_preferences(preference_query)
        if selection_mode == "automatic"
        else None
    )
    profile = _strategy_profile(
        query,
        semantic_slots=semantic_slots,
        selection_mode=selection_mode,
    )
    slots = semantic_slots or {}
    sector = slots.get("sector")
    fallback_conditions = StrategyConditionsPayload(
        entry_conditions=profile["entry_conditions"],
        exit_conditions=profile["exit_conditions"],
        indicators=profile["indicators"],
        confidence=float(profile["confidence"]),
    )
    # Automatic mode is a deterministic, cited strategy.  Letting the language model
    # rewrite its conditions would make the displayed rationale differ from the rule
    # actually backtested.  Concrete user rules continue through the normal parser.
    conditions = (
        fallback_conditions
        if selection_mode == "automatic"
        else generate_strategy_conditions(
            query=query,
            semantic_slots=dict(slots),
            fallback=fallback_conditions,
        )
    )
    risk_constraints: dict[str, float | int | str | bool] = {
        "max_position_pct": 0.1,
        "stop_loss_pct": 0.08,
    }
    customization_assumptions: list[str] = []
    strategy_name = str(profile["name"])
    if automatic_preferences is not None:
        medium_momentum_weight = {
            "short": 0.70,
            "medium": 0.60,
            "long": 0.40,
        }[automatic_preferences.horizon]
        risk_constraints = {
            "max_position_pct": round(1.0 / automatic_preferences.max_positions, 6),
            "stop_loss_pct": automatic_preferences.stop_loss_pct,
            "take_profit_pct": 10.0,
            "trailing_stop_pct": automatic_preferences.trailing_stop_pct,
            "rebalance_interval_days": automatic_preferences.rebalance_interval_days,
            "medium_momentum_weight": medium_momentum_weight,
            "strategy_style": automatic_preferences.risk_style,
            "investment_horizon": automatic_preferences.horizon,
            "benchmark_objective": "fixed_universe_excess_return",
            "benchmark_evaluation_period_days": 126,
            # The generic automatic StrategySpec intentionally has broad indicators.
            # Preserve the normalized request so the pre-registered catalog can tell
            # "low volatility" from "breakout" without inspecting any return data.
            "catalog_query": preference_query,
        }
        style_label = {
            "aggressive": "공격형",
            "balanced": "균형형",
            "defensive": "방어형",
        }[automatic_preferences.risk_style]
        horizon_label = {
            "short": "단기",
            "medium": "중기",
            "long": "장기",
        }[automatic_preferences.horizon]
        strategy_name = f"{style_label}·{horizon_label} {strategy_name}"
        customization_assumptions = [
            f"사용자 입력을 {style_label}·{horizon_label} 성향으로 해석",
            (
                f"최대 {automatic_preferences.max_positions}종목, "
                f"{automatic_preferences.rebalance_interval_days}거래일 교체, "
                f"손절 {automatic_preferences.stop_loss_pct:.0%}, "
                f"고점 추적손절 {automatic_preferences.trailing_stop_pct:.0%}"
            ),
            "63거래일 고정 구간 중 벤치마크 패배 구간이 50% 이상이면 검증 실패",
        ]
    return StrategySpec(
        strategy_id=f"{profile['strategy_id']}_{variant.lower()}",
        name=strategy_name,
        market="KRX",
        sector=sector,
        timeframe="daily",
        entry_conditions=conditions.entry_conditions,
        exit_conditions=conditions.exit_conditions,
        indicators=conditions.indicators or profile["indicators"],
        risk_constraints=risk_constraints,
        assumptions=[
            f"sector filter: {sector}" if sector else "all matching listed common stocks",
            "daily adjusted close data",
            *customization_assumptions,
            *profile["assumptions"],
        ],
        source_refs=list(profile.get("source_refs", [])),
        selection_mode=selection_mode,
        confidence=float(conditions.confidence),
    )


def _strategy_profile(
    query: str,
    *,
    semantic_slots: Mapping[str, Any] | None = None,
    selection_mode: str | None = None,
) -> dict[str, Any]:
    profile = _strategy_profile_base(
        query,
        semantic_slots=semantic_slots,
        selection_mode=selection_mode,
    )
    sector = semantic_slots.get("sector") if semantic_slots else None
    if sector:
        profile = {
            **profile,
            "name": f"{profile['name']} ({sector})",
            "assumptions": [*profile["assumptions"], f"{sector} 섹터로 후보를 한정합니다."],
        }
    return profile


def _strategy_profile_base(
    query: str,
    *,
    semantic_slots: Mapping[str, Any] | None = None,
    selection_mode: str | None = None,
) -> dict[str, Any]:
    lowered = query.lower()
    slot_indicator = set(semantic_slots.get("indicator", [])) if semantic_slots else set()
    slot_event = set(semantic_slots.get("event", [])) if semantic_slots else set()
    rsi_rules = rsi_trade_rules(query)
    rsi_operator_symbols = {"lt": "<", "lte": "<=", "gt": ">", "gte": ">="}
    rsi_is_overbought = rsi_rules.entry_side == "overbought"
    rsi_entry_description = (
        f"RSI {rsi_operator_symbols[rsi_rules.entry_operator]} {int(rsi_rules.entry_threshold)}"
    )
    if not rsi_is_overbought and rsi_rules.entry_operator == "lte":
        rsi_entry_description += " 또는 30 상향 회복"
    rsi_exit_description = (
        f"RSI {rsi_operator_symbols[rsi_rules.exit_operator]} {int(rsi_rules.exit_threshold)}"
    )
    if (selection_mode or classify_strategy_request(query)) == "automatic":
        return {
            "strategy_id": "automatic_performance_momentum",
            "name": "벤치마크 초과수익 맞춤 모멘텀 전략군",
            "entry_conditions": [
                Condition(
                    left="past_only_signal",
                    operator="eq",
                    right=1,
                    description="미래 데이터를 쓰지 않은 모멘텀·추세 신호가 매수 상태",
                ),
                Condition(
                    left="trend_confirmation",
                    operator="eq",
                    right=1,
                    description="후보 전략의 중기 또는 장기 상승 추세 확인",
                ),
                Condition(
                    left="risk_filter",
                    operator="eq",
                    right=1,
                    description="변동성·손실 제한 조건 통과",
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="selected_profile_exit",
                    operator="eq",
                    right=1,
                    description="선택된 전략의 추세 훼손 또는 손실 제한 규칙",
                )
            ],
            "indicators": [
                "cross_sectional_rank",
                "momentum_12_1",
                "medium_momentum_126d",
                "SMA200",
                "realized_volatility_21d",
                "rebalance_21d",
                "crash_risk_guard",
                "benchmark_period_gate",
            ],
            "assumptions": [
                "사용자 위험성향과 투자기간에 맞는 독립 모멘텀 전략 3개를 백테스트 전에 생성",
                "앞 70% 구간만 후보 선택에 사용하고 마지막 30%는 별도 검증",
                "63거래일 고정 구간 중 벤치마크에 진 구간이 50% 이상이면 패배",
                "지표는 평가 시점까지 알려진 조정 종가만 사용",
                "45% 같은 조기 고정 익절로 큰 승자를 자르지 않고 상대 순위와 장기 추세가 유지되면 보유",
                "보유 종목 수·교체 주기·손실 제한은 사용자 입력에서 수익률을 보기 전에 결정",
                "후보 수와 기본 파라미터를 백테스트 전에 고정해 과최적화 탐색을 제한",
                "과거 연구와 백테스트는 미래 수익을 보장하지 않음",
            ],
            "source_refs": robust_strategy_source_refs(),
            "confidence": 0.84,
        }
    if _is_pullback_rsi_volume_query(query):
        return {
            "strategy_id": "pullback_rsi_volume",
            "name": "RSI40 거래량 눌림목",
            "entry_conditions": [
                Condition(
                    left="close_above_sma_200",
                    operator="eq",
                    right=1,
                    description="주가가 200일선 위",
                ),
                Condition(left="rsi", operator="lte", right=40, description="RSI(14) <= 40 눌림"),
                Condition(
                    left="volume_ratio_20",
                    operator="gte",
                    right=1.0,
                    description="거래량이 20일 평균 이상",
                ),
            ],
            "exit_conditions": [
                Condition(left="rsi", operator="gte", right=60, description="RSI >= 60 회복"),
                Condition(
                    left="close_below_sma_200", operator="eq", right=1, description="200일선 이탈"
                ),
            ],
            "indicators": ["SMA200", "RSI", "volume_ratio_20"],
            "assumptions": [
                "200일선 위는 상승추세 필터로 해석",
                "RSI 40 이하는 과매도보다 완만한 눌림목 조건으로 해석",
                "거래량 20일 평균 이상은 volume_ratio_20 >= 1.0으로 해석",
            ],
            "confidence": 0.82,
        }
    if "dividend_defensive" in lowered or "배당 방어주" in query:
        return {
            "strategy_id": "dividend_defensive",
            "name": "배당 방어주",
            "entry_conditions": [
                Condition(
                    left="dividend_yield",
                    operator="gte",
                    right=0.04,
                    description="배당수익률 4% 이상",
                ),
                Condition(
                    left="debt_ratio", operator="lte", right=100, description="부채비율 100% 이하"
                ),
                Condition(
                    left="dividend_cut_5y",
                    operator="eq",
                    right=0,
                    description="최근 5년 배당 삭감 없음",
                ),
                Condition(
                    left="close_above_sma_200",
                    operator="eq",
                    right=1,
                    description="200일선 위 기술 확인",
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="close_below_sma_200", operator="eq", right=1, description="200일선 이탈"
                )
            ],
            "indicators": ["dividend_yield", "debt_ratio", "dividend_cut_5y", "SMA200"],
            "assumptions": [
                "배당수익률과 부채비율은 L1/L2에서 재무 안정성 필터로 해석",
                "배당 삭감 이력 데이터가 없으면 후보 확정 후 기술 proxy 백테스트로 검증",
            ],
            "confidence": 0.73,
        }
    if "value_quality" in lowered or "저평가 퀄리티" in query:
        return {
            "strategy_id": "value_quality",
            "name": "저평가 퀄리티",
            "entry_conditions": [
                Condition(
                    left="per_percentile",
                    operator="lte",
                    right=0.4,
                    description="PER 업종/시장 하위권",
                ),
                Condition(left="roe", operator="gte", right=0.15, description="ROE 15% 이상"),
                Condition(
                    left="debt_ratio", operator="lte", right=100, description="부채비율 100% 이하"
                ),
                Condition(
                    left="relative_strength_20d",
                    operator="gte",
                    right=0,
                    description="20일 상대강도 양호",
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="relative_strength_20d",
                    operator="lt",
                    right=0,
                    description="단기 상대강도 약화",
                )
            ],
            "indicators": ["PER", "ROE", "debt_ratio", "relative_strength_20d"],
            "assumptions": ["재무 조건은 후보 필터, OHLCV 기반 상대강도는 검증 proxy로 사용"],
            "confidence": 0.75,
        }
    if "reasonable_growth" in lowered or "합리적 성장주" in query:
        return {
            "strategy_id": "reasonable_growth",
            "name": "합리적 성장주",
            "entry_conditions": [
                Condition(left="roe", operator="gte", right=0.15, description="ROE 15% 이상"),
                Condition(
                    left="sales_growth",
                    operator="gte",
                    right=0.1,
                    description="매출 성장률 10% 이상",
                ),
                Condition(
                    left="per_vs_industry",
                    operator="lte",
                    right=1,
                    description="PER 업종 평균 이하",
                ),
                Condition(
                    left="close_above_sma_50", operator="eq", right=1, description="50일선 위"
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="close_below_sma_50", operator="eq", right=1, description="50일선 이탈"
                )
            ],
            "indicators": ["ROE", "sales_growth", "PER", "SMA50"],
            "assumptions": ["성장성과 밸류에이션을 결합한 GARP 후보로 확정"],
            "confidence": 0.72,
        }
    if any(term in query for term in ("순현금", "자사주", "PBR 1배")):
        return {
            "strategy_id": "asset_value_catalyst",
            "name": "자산가치 촉매",
            "entry_conditions": [
                Condition(left="pbr", operator="lte", right=1, description="PBR 1배 이하"),
                Condition(left="net_cash", operator="gte", right=1, description="순현금 보유"),
                Condition(
                    left="buyback_notice", operator="eq", right=1, description="자사주 매입 공시"
                ),
                Condition(
                    left="close_above_sma_20",
                    operator="eq",
                    right=1,
                    description="20일선 위 기술 확인",
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="close_below_sma_20", operator="eq", right=1, description="20일선 이탈"
                )
            ],
            "indicators": ["PBR", "net_cash", "buyback_notice", "SMA20"],
            "assumptions": [
                "공시/재무 조건은 후보 필터, OHLCV 기반 추세 회복은 백테스트 proxy로 사용"
            ],
            "confidence": 0.69,
        }
    if any(
        term in lowered or term in query for term in ("저per", "per", "pbr", "저평가", "가치주")
    ):
        return {
            "strategy_id": "value_quality",
            "name": "저평가 퀄리티",
            "entry_conditions": [
                Condition(
                    left="per_percentile",
                    operator="lte",
                    right=0.4,
                    description="PER 업종/시장 하위권",
                ),
                Condition(left="roe", operator="gte", right=0.15, description="ROE 15% 이상"),
                Condition(
                    left="debt_ratio", operator="lte", right=100, description="부채비율 100% 이하"
                ),
                Condition(
                    left="relative_strength_20d",
                    operator="gte",
                    right=0,
                    description="20일 상대강도 양호",
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="relative_strength_20d",
                    operator="lt",
                    right=0,
                    description="단기 상대강도 약화",
                )
            ],
            "indicators": ["PER", "ROE", "debt_ratio", "relative_strength_20d"],
            "assumptions": ["재무 조건은 후보 필터, OHLCV 기반 상대강도는 검증 proxy로 사용"],
            "confidence": 0.75,
        }
    if any(term in query for term in ("저변동성", "방어주")) and "배당" in query:
        return {
            "strategy_id": "low_vol_defensive",
            "name": "저변동 배당 방어주",
            "entry_conditions": [
                Condition(
                    left="realized_volatility_20d",
                    operator="lte",
                    right=0.25,
                    description="20일 변동성 낮음",
                ),
                Condition(
                    left="relative_strength_20d",
                    operator="gte",
                    right=0,
                    description="20일 시장 대비 우위",
                ),
                Condition(
                    left="dividend_yield", operator="gte", right=0.04, description="배당수익률 양호"
                ),
                Condition(
                    left="close_above_sma_20", operator="eq", right=1, description="20일선 위"
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="relative_strength_20d",
                    operator="lt",
                    right=0,
                    description="상대강도 약화",
                )
            ],
            "indicators": [
                "realized_volatility_20d",
                "relative_strength_20d",
                "dividend_yield",
                "SMA20",
            ],
            "assumptions": ["방어주 성격은 저변동성과 배당 조건, 진입 타이밍은 OHLCV proxy로 검증"],
            "confidence": 0.7,
        }
    if any(term in query for term in ("금리", "리츠", "유틸리티")):
        return {
            "strategy_id": "rate_sensitive_income",
            "name": "금리 민감 인컴주",
            "entry_conditions": [
                Condition(
                    left="rate_down_proxy",
                    operator="eq",
                    right=1,
                    description="금리 하락기 강세 업종 후보",
                ),
                Condition(
                    left="dividend_yield",
                    operator="gte",
                    right=0.04,
                    description="배당 또는 인컴 성격",
                ),
                Condition(
                    left="close_above_sma_50",
                    operator="eq",
                    right=1,
                    description="50일선 위 기술 상승",
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="close_below_sma_50", operator="eq", right=1, description="50일선 이탈"
                )
            ],
            "indicators": ["rate_down_proxy", "dividend_yield", "SMA50"],
            "assumptions": ["금리 민감도와 업종 분류는 후보 필터, 현재 검증은 추세 proxy로 수행"],
            "confidence": 0.66,
        }
    if "배당" in query:
        return {
            "strategy_id": "dividend_defensive",
            "name": "배당 방어주",
            "entry_conditions": [
                Condition(
                    left="dividend_yield",
                    operator="gte",
                    right=0.04,
                    description="배당수익률 4% 이상",
                ),
                Condition(
                    left="debt_ratio", operator="lte", right=100, description="부채비율 100% 이하"
                ),
                Condition(
                    left="dividend_cut_5y",
                    operator="eq",
                    right=0,
                    description="최근 5년 배당 삭감 없음",
                ),
                Condition(
                    left="close_above_sma_200",
                    operator="eq",
                    right=1,
                    description="200일선 위 기술 확인",
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="close_below_sma_200", operator="eq", right=1, description="200일선 이탈"
                )
            ],
            "indicators": ["dividend_yield", "debt_ratio", "dividend_cut_5y", "SMA200"],
            "assumptions": [
                "배당수익률과 부채비율은 L1/L2에서 재무 안정성 필터로 해석",
                "배당 삭감 이력 데이터가 없으면 후보 확정 후 기술 proxy 백테스트로 검증",
            ],
            "confidence": 0.73,
        }
    if any(term in query for term in ("원달러", "환율", "수출주")):
        return {
            "strategy_id": "fx_exporter_revision",
            "name": "환율 수혜 이익상향",
            "entry_conditions": [
                Condition(
                    left="fx_benefit_proxy",
                    operator="eq",
                    right=1,
                    description="환율 상승 수혜 업종 후보",
                ),
                Condition(
                    left="earnings_revision_3m",
                    operator="gte",
                    right=0,
                    description="이익 전망 상향",
                ),
                Condition(
                    left="relative_strength_20d",
                    operator="gte",
                    right=0,
                    description="20일 상대강도 양호",
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="relative_strength_20d",
                    operator="lt",
                    right=0,
                    description="상대강도 약화",
                )
            ],
            "indicators": ["fx_benefit_proxy", "earnings_revision_3m", "relative_strength_20d"],
            "assumptions": [
                "환율 수혜와 이익 전망은 후보 필터, OHLCV 상대강도는 검증 proxy로 사용"
            ],
            "confidence": 0.65,
        }
    if any(term in query for term in ("원자재", "마진 개선", "화학", "운송", "소비재")):
        return {
            "strategy_id": "margin_improvement",
            "name": "원가하락 마진 개선",
            "entry_conditions": [
                Condition(
                    left="input_cost_tailwind_proxy",
                    operator="eq",
                    right=1,
                    description="원자재 가격 하락 수혜 후보",
                ),
                Condition(
                    left="operating_margin_improving",
                    operator="eq",
                    right=1,
                    description="영업이익률 개선",
                ),
                Condition(
                    left="close_above_sma_50", operator="eq", right=1, description="50일선 위"
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="close_below_sma_50", operator="eq", right=1, description="50일선 이탈"
                )
            ],
            "indicators": ["input_cost_tailwind_proxy", "operating_margin", "SMA50"],
            "assumptions": ["원자재/업종 민감도는 후보 필터, 기술 추세는 검증 proxy로 사용"],
            "confidence": 0.64,
        }
    if any(term in query for term in ("매출총이익률", "재고자산", "재고")):
        return {
            "strategy_id": "margin_inventory_quality",
            "name": "마진·재고 퀄리티",
            "entry_conditions": [
                Condition(
                    left="gross_margin_streak",
                    operator="gte",
                    right=3,
                    description="매출총이익률 3개 분기 개선",
                ),
                Condition(
                    left="inventory_growth_vs_sales",
                    operator="lte",
                    right=1,
                    description="재고 증가율이 매출 증가율 이하",
                ),
                Condition(
                    left="close_above_sma_50", operator="eq", right=1, description="50일선 위"
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="close_below_sma_50", operator="eq", right=1, description="50일선 이탈"
                )
            ],
            "indicators": ["gross_margin", "inventory_growth", "sales_growth", "SMA50"],
            "assumptions": ["분기 재무 품질 조건은 후보 필터, 가격 추세로 타이밍을 검증"],
            "confidence": 0.68,
        }
    if any(term in lowered or term in query for term in ("fcf", "현금흐름", "현금흐름이 안정")):
        return {
            "strategy_id": "fcf_recovery",
            "name": "FCF 회복주",
            "entry_conditions": [
                Condition(
                    left="fcf_yield", operator="gte", right=0.05, description="FCF 수익률 양호"
                ),
                Condition(
                    left="cashflow_stability", operator="eq", right=1, description="현금흐름 안정"
                ),
                Condition(
                    left="close_above_sma_200",
                    operator="eq",
                    right=1,
                    description="200일선 위 회복",
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="close_below_sma_200", operator="eq", right=1, description="200일선 재이탈"
                )
            ],
            "indicators": ["FCF_yield", "cashflow_stability", "SMA200"],
            "assumptions": ["현금흐름 조건은 후보 필터, 200일선 회복은 기술 proxy로 검증"],
            "confidence": 0.69,
        }
    if "4분기" in query or ("영업이익" in query and "60일 고점" in query):
        return {
            "strategy_id": "operating_profit_pullback",
            "name": "이익성장 조정주",
            "entry_conditions": [
                Condition(
                    left="operating_profit_growth_streak",
                    operator="gte",
                    right=4,
                    description="4분기 연속 영업이익 증가",
                ),
                Condition(
                    left="drawdown_60d",
                    operator="lte",
                    right=-0.1,
                    description="60일 고점 대비 10% 이상 조정",
                ),
                Condition(
                    left="relative_strength_60d",
                    operator="gte",
                    right=0,
                    description="중기 상대강도 유지",
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="relative_strength_60d",
                    operator="lt",
                    right=0,
                    description="중기 상대강도 훼손",
                )
            ],
            "indicators": ["operating_profit_growth", "drawdown_60d", "relative_strength_60d"],
            "assumptions": ["분기 이익 조건은 후보 필터, 조정 폭과 상대강도는 OHLCV proxy로 검증"],
            "confidence": 0.68,
        }
    if any(term in query for term in ("어닝", "가이던스", "EPS", "컨센서스", "실적 발표")):
        if any(term in query for term in ("60거래일", "20% 이상 하락", "과매도 우량주")):
            return {
                "strategy_id": "oversold_quality",
                "name": "과매도 우량주",
                "entry_conditions": [
                    Condition(
                        left="drawdown_60d",
                        operator="lte",
                        right=-0.2,
                        description="60일 고점 대비 20% 이상 하락",
                    ),
                    Condition(
                        left="earnings_revision_3m",
                        operator="gte",
                        right=0,
                        description="실적 컨센서스 유지",
                    ),
                    Condition(left="rsi", operator="lte", right=35, description="과매도권"),
                ],
                "exit_conditions": [
                    Condition(left="rsi", operator="gte", right=60, description="반등 과열 전 청산")
                ],
                "indicators": ["drawdown_60d", "earnings_revision_3m", "RSI"],
                "assumptions": ["컨센서스 유지 조건은 후보 필터, 낙폭과 RSI는 OHLCV proxy로 검증"],
                "confidence": 0.69,
            }
        if "어닝" in query or "가이던스" in query or "실적 발표" in query:
            strategy_id = "earnings_surprise_guidance"
            name = "어닝 서프라이즈 가이던스"
        else:
            strategy_id = "earnings_momentum"
            name = "실적 모멘텀"
        return {
            "strategy_id": strategy_id,
            "name": name,
            "entry_conditions": [
                Condition(
                    left="earnings_revision_3m",
                    operator="gte",
                    right=0,
                    description="최근 3개월 이익 전망 상향",
                ),
                Condition(
                    left="breakout_high",
                    operator="eq",
                    right=1,
                    description="20일 신고가 또는 상단 돌파",
                ),
                Condition(
                    left="relative_strength_20d",
                    operator="gte",
                    right=0,
                    description="20일 상대강도 양호",
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="relative_strength_20d",
                    operator="lt",
                    right=0,
                    description="상대강도 약화",
                )
            ],
            "indicators": ["earnings_revision_3m", "rolling_high", "relative_strength_20d"],
            "assumptions": [
                "실적/가이던스 조건은 후보 필터, 신고가와 상대강도는 검증 proxy로 사용"
            ],
            "confidence": 0.72,
        }
    if any(term in query for term in ("기관", "외국인")):
        return {
            "strategy_id": "flow_accumulation",
            "name": "기관·외국인 수급 모멘텀",
            "entry_conditions": [
                Condition(
                    left="net_buy_streak_5d",
                    operator="gte",
                    right=5,
                    description="기관·외국인 5거래일 순매수",
                ),
                Condition(
                    left="close_above_sma_20", operator="eq", right=1, description="주가 20일선 위"
                ),
                Condition(
                    left="volume_ratio_20", operator="gte", right=1, description="거래량 확인"
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="close_below_sma_20", operator="eq", right=1, description="20일선 이탈"
                )
            ],
            "indicators": ["net_buy_streak_5d", "SMA20", "volume_ratio_20"],
            "assumptions": ["수급 데이터가 없으면 거래량과 20일선 proxy로 검증"],
            "confidence": 0.66,
        }
    if "공매도" in query or "숏커버링" in query:
        return {
            "strategy_id": "short_covering_proxy",
            "name": "숏커버링 proxy",
            "entry_conditions": [
                Condition(
                    left="short_balance_high",
                    operator="eq",
                    right=1,
                    description="공매도 잔고 높은 후보",
                ),
                Condition(
                    left="volume_ratio_20", operator="gte", right=1.5, description="거래량 증가"
                ),
                Condition(left="bullish_breakout", operator="eq", right=1, description="양봉 돌파"),
            ],
            "exit_conditions": [
                Condition(
                    left="close_below_sma_20", operator="eq", right=1, description="20일선 이탈"
                )
            ],
            "indicators": ["short_balance", "volume_ratio_20", "bullish_breakout"],
            "assumptions": ["공매도 잔고는 후보 필터, 거래량·양봉 돌파는 백테스트 proxy로 사용"],
            "confidence": 0.62,
        }
    if "갭" in query or "수급" in query:
        return {
            "strategy_id": "gap_hold_momentum",
            "name": "갭 유지 수급 모멘텀",
            "entry_conditions": [
                Condition(left="gap_up", operator="eq", right=1, description="최근 갭 상승"),
                Condition(
                    left="gap_unfilled", operator="eq", right=1, description="갭 미충족 횡보"
                ),
                Condition(
                    left="relative_strength_20d",
                    operator="gte",
                    right=0,
                    description="20일 상대강도 양호",
                ),
            ],
            "exit_conditions": [
                Condition(left="gap_filled", operator="eq", right=1, description="갭 메움")
            ],
            "indicators": ["gap_up", "gap_unfilled", "relative_strength_20d"],
            "assumptions": ["갭 유지 여부는 OHLCV 패턴으로 검증"],
            "confidence": 0.67,
        }
    if (
        "bollinger" in slot_indicator
        or "lower_band_reentry" in slot_event
        or "볼린저" in query
        or "변동성" in query
    ):
        lower_reentry = "lower_band_reentry" in slot_event or any(
            term in query for term in ("하단", "재진입", "반등")
        )
        return {
            "strategy_id": "bollinger_lower_reentry"
            if lower_reentry
            else "bollinger_squeeze_breakout",
            "name": "볼린저 하단 재진입" if lower_reentry else "볼린저 스퀴즈 돌파",
            "entry_conditions": [
                Condition(
                    left="close_below_lower_band_recent",
                    operator="eq",
                    right=1,
                    description="최근 종가가 볼린저 하단 밴드 아래를 확인",
                ),
                Condition(
                    left="close_cross_above_lower_band",
                    operator="eq",
                    right=1,
                    description="종가가 하단 밴드 위로 재진입",
                ),
            ]
            if lower_reentry
            else [
                Condition(
                    left="bb_width_percentile",
                    operator="lte",
                    right=0.25,
                    description="밴드 폭 축소",
                ),
                Condition(
                    left="bollinger_breakout",
                    operator="eq",
                    right=1,
                    description="상단 돌파 또는 밴드 재진입",
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="close_below_middle_band",
                    operator="eq",
                    right=1,
                    description="중심선 이탈",
                )
            ],
            "indicators": ["Bollinger Bands", "close"],
            "assumptions": [
                "볼린저 하단 재진입은 RSI 반등과 별도 의미로 보존",
                "판정 기준은 종가 기준으로 고정",
            ]
            if lower_reentry
            else ["상단 돌파와 하단 재진입은 입력 문맥에 따라 L2에서 분기"],
            "confidence": 0.8 if lower_reentry else 0.74,
        }
    if "200일" in query and "rsi" in lowered:
        return {
            "strategy_id": "trend_rsi_volume_pullback",
            "name": "추세 내 RSI 눌림목",
            "entry_conditions": [
                Condition(
                    left="close_above_sma_200",
                    operator="eq",
                    right=1,
                    description="200일선 위 상승추세",
                ),
                Condition(left="rsi", operator="lte", right=40, description="RSI 40 이하 눌림"),
                Condition(
                    left="volume_ratio_20",
                    operator="gte",
                    right=1,
                    description="거래량 20일 평균 이상",
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="close_below_sma_20", operator="eq", right=1, description="20일선 이탈"
                )
            ],
            "indicators": ["SMA200", "RSI", "volume_ratio_20"],
            "assumptions": ["장기 추세는 200일선, 단기 눌림은 RSI와 거래량으로 검증"],
            "confidence": 0.76,
        }
    if "1개월" in query and "6개월" in query:
        return {
            "strategy_id": "midterm_pullback",
            "name": "중기 상승추세 눌림목",
            "entry_conditions": [
                Condition(
                    left="relative_strength_20d",
                    operator="lt",
                    right=0,
                    description="최근 1개월 시장 대비 약세",
                ),
                Condition(
                    left="relative_strength_120d",
                    operator="gte",
                    right=0,
                    description="6개월 시장 대비 강세",
                ),
                Condition(
                    left="close_above_sma_200", operator="eq", right=1, description="장기 추세 유지"
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="relative_strength_120d",
                    operator="lt",
                    right=0,
                    description="중기 상대강도 훼손",
                )
            ],
            "indicators": ["relative_strength_20d", "relative_strength_120d", "SMA200"],
            "assumptions": ["중기 추세와 단기 조정의 조합을 OHLCV proxy로 검증"],
            "confidence": 0.72,
        }
    if "120일" in query and "20일선" in query:
        return {
            "strategy_id": "breakout_pullback",
            "name": "신고가 돌파 후 되돌림",
            "entry_conditions": [
                Condition(
                    left="breakout_high",
                    operator="eq",
                    right=1,
                    description="120일 신고가 돌파 이력",
                ),
                Condition(
                    left="pullback_to_sma_20",
                    operator="eq",
                    right=1,
                    description="20일선까지 되돌림",
                ),
                Condition(
                    left="relative_strength_60d",
                    operator="gte",
                    right=0,
                    description="중기 상대강도 유지",
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="close_below_sma_20", operator="eq", right=1, description="20일선 이탈"
                )
            ],
            "indicators": ["rolling_high", "SMA20", "relative_strength_60d"],
            "assumptions": ["신고가 이후 눌림목을 추세 지속 proxy로 검증"],
            "confidence": 0.74,
        }
    if "돌파 대기" in query or "횡보" in query:
        return {
            "strategy_id": "breakout_setup",
            "name": "돌파 대기",
            "entry_conditions": [
                Condition(
                    left="near_recent_high", operator="eq", right=1, description="최근 신고가 근처"
                ),
                Condition(
                    left="volume_dry_up", operator="eq", right=1, description="거래량 감소 횡보"
                ),
                Condition(
                    left="turnover_sufficient", operator="eq", right=1, description="거래대금 충분"
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="close_below_sma_20", operator="eq", right=1, description="20일선 이탈"
                )
            ],
            "indicators": ["near_recent_high", "volume_dry_up", "turnover"],
            "assumptions": ["거래대금과 횡보 압축은 OHLCV proxy로 검증"],
            "confidence": 0.68,
        }
    if any(
        term in query for term in ("영업이익률", "영업이익", "매출 성장률", "퀄리티 성장", "성장주")
    ):
        if "ROE 15%" in query or "합리적 성장주" in query or "PER" in query:
            return {
                "strategy_id": "reasonable_growth",
                "name": "합리적 성장주",
                "entry_conditions": [
                    Condition(left="roe", operator="gte", right=0.15, description="ROE 15% 이상"),
                    Condition(
                        left="sales_growth",
                        operator="gte",
                        right=0.1,
                        description="매출 성장률 10% 이상",
                    ),
                    Condition(
                        left="per_vs_industry",
                        operator="lte",
                        right=1,
                        description="PER 업종 평균 이하",
                    ),
                    Condition(
                        left="close_above_sma_50", operator="eq", right=1, description="50일선 위"
                    ),
                ],
                "exit_conditions": [
                    Condition(
                        left="close_below_sma_50", operator="eq", right=1, description="50일선 이탈"
                    )
                ],
                "indicators": ["ROE", "sales_growth", "PER", "SMA50"],
                "assumptions": ["성장성과 밸류에이션을 결합한 GARP 후보로 확정"],
                "confidence": 0.72,
            }
        strategy_id = (
            "quality_growth" if "ROE" in query or "업종 평균" in query else "growth_momentum"
        )
        return {
            "strategy_id": strategy_id,
            "name": "퀄리티 성장주" if strategy_id == "quality_growth" else "성장 모멘텀",
            "entry_conditions": [
                Condition(
                    left="sales_growth",
                    operator="gte",
                    right=0.2 if "20%" in query else 0.1,
                    description="매출 성장률 양호",
                ),
                Condition(
                    left="operating_margin_improving",
                    operator="eq",
                    right=1,
                    description="영업이익률 개선",
                ),
                Condition(
                    left="debt_ratio", operator="lte", right=100, description="부채비율 100% 이하"
                ),
                Condition(
                    left="close_above_sma_50", operator="eq", right=1, description="50일선 위"
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="close_below_sma_50", operator="eq", right=1, description="50일선 이탈"
                )
            ],
            "indicators": ["sales_growth", "operating_margin", "debt_ratio", "SMA50"],
            "assumptions": ["성장·수익성 조건은 후보 필터, 추세는 OHLCV proxy로 검증"],
            "confidence": 0.7,
        }
    if "rsi" in lowered or "rsi" in slot_indicator or "과매도" in query or "반등" in query:
        return {
            "strategy_id": "rsi_rebound",
            "name": "RSI 과매수 모멘텀" if rsi_is_overbought else "RSI 과매도 반등",
            "entry_conditions": [
                Condition(
                    left="rsi",
                    operator=rsi_rules.entry_operator,
                    right=rsi_rules.entry_threshold,
                    description=rsi_entry_description,
                )
            ],
            "exit_conditions": [
                Condition(
                    left="rsi",
                    operator=rsi_rules.exit_operator,
                    right=rsi_rules.exit_threshold,
                    description=rsi_exit_description,
                )
            ],
            "indicators": ["RSI"],
            "assumptions": [
                "RSI 70 이상 매수·30 미만 매도 조건을 그대로 적용"
                if rsi_is_overbought
                else "RSI 30 회복 조건은 L2에서 과매도 반등 proxy로 해석"
            ],
            "confidence": 0.84,
        }
    if any(term in query for term in ("52주", "120일", "신고가", "거래량", "돌파", "갭")):
        return {
            "strategy_id": "breakout_volume_momentum",
            "name": "거래량 돌파 모멘텀",
            "entry_conditions": [
                Condition(
                    left="breakout_high",
                    operator="eq",
                    right=1,
                    description="신고가 또는 상단 돌파",
                ),
                Condition(
                    left="volume_ratio_20",
                    operator="gte",
                    right=1.5,
                    description="20일 평균 대비 거래량 150% 이상",
                ),
                Condition(
                    left="close_above_sma_20",
                    operator="eq",
                    right=1,
                    description="종가가 20일선 위",
                ),
                Condition(
                    left="relative_strength_20d",
                    operator="gte",
                    right=0,
                    description="20일 상대강도 양호",
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="close_below_sma_20", operator="eq", right=1, description="20일선 이탈"
                )
            ],
            "indicators": ["rolling_high", "volume_ratio_20", "SMA20", "relative_strength_20d"],
            "assumptions": ["신고가 기간은 입력의 52주/120일/20일 표현에 맞춰 L2에서 선택"],
            "confidence": 0.8,
        }
    if any(term in query for term in ("눌림목", "200일", "20일선", "20일 이동평균")):
        return {
            "strategy_id": "pullback_trend",
            "name": "상승추세 눌림목",
            "entry_conditions": [
                Condition(
                    left="close_above_sma_200",
                    operator="eq",
                    right=1,
                    description="주가가 200일선 위",
                ),
                Condition(
                    left="pullback_to_sma_20",
                    operator="eq",
                    right=1,
                    description="20일선 근처 조정",
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="close_below_sma_20", operator="eq", right=1, description="20일선 이탈"
                )
            ],
            "indicators": ["SMA20", "SMA200"],
            "assumptions": ["눌림목은 L1 정의에 따라 장기 상승추세 안의 단기 조정으로 해석"],
            "confidence": 0.78,
        }
    if "볼린저" in query or "변동성" in query:
        return {
            "strategy_id": "bollinger_squeeze_breakout",
            "name": "볼린저 스퀴즈 돌파",
            "entry_conditions": [
                Condition(
                    left="bb_width_percentile",
                    operator="lte",
                    right=0.25,
                    description="밴드 폭 축소",
                ),
                Condition(
                    left="bollinger_breakout",
                    operator="eq",
                    right=1,
                    description="상단 돌파 또는 밴드 재진입",
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="close_below_middle_band",
                    operator="eq",
                    right=1,
                    description="중심선 이탈",
                )
            ],
            "indicators": ["Bollinger Bands", "realized_volatility"],
            "assumptions": ["상단 돌파와 하단 재진입은 입력 문맥에 따라 L2에서 분기"],
            "confidence": 0.74,
        }
    if any(term in query for term in ("상대강도", "주도주", "시장보다", "섹터")):
        return {
            "strategy_id": "relative_strength_leader",
            "name": "상대강도 주도주",
            "entry_conditions": [
                Condition(
                    left="relative_strength_20d",
                    operator="gte",
                    right=0,
                    description="20일 시장 대비 초과수익",
                ),
                Condition(
                    left="relative_strength_60d",
                    operator="gte",
                    right=0,
                    description="60일 시장 대비 초과수익",
                ),
            ],
            "exit_conditions": [
                Condition(
                    left="relative_strength_20d",
                    operator="lt",
                    right=0,
                    description="단기 상대강도 약화",
                )
            ],
            "indicators": ["relative_strength_20d", "relative_strength_60d"],
            "assumptions": ["시장 대표 수익률을 비교 기준으로 해석"],
            "confidence": 0.76,
        }
    return {
        "strategy_id": "rsi_rebound",
        "name": "RSI 과매수 모멘텀" if rsi_is_overbought else "RSI 과매도 반등",
        "entry_conditions": [
            Condition(
                left="rsi",
                operator=rsi_rules.entry_operator,
                right=rsi_rules.entry_threshold,
                description=rsi_entry_description,
            )
        ],
        "exit_conditions": [
            Condition(
                left="rsi",
                operator=rsi_rules.exit_operator,
                right=rsi_rules.exit_threshold,
                description=rsi_exit_description,
            )
        ],
        "indicators": ["RSI"],
        "assumptions": [
            "RSI 70 이상 매수·30 미만 매도 조건을 그대로 적용"
            if rsi_is_overbought
            else "명확한 기술 조건이 없으면 RSI 평균회귀 후보를 기본 제안"
        ],
        "confidence": 0.68,
    }


def build_internal_payload(state: QuantAgentState) -> InternalPayload:
    node_outputs = {
        key: state[key]
        for key in (
            "ambiguity",
            "semantic_slots",
            "data_requirements",
            "source_usage",
            "failure_cause",
            "evidence_refs",
            "data",
            "strategy_spec",
            "original_strategy_spec",
            "research_review",
            "backtest_code",
            "backtest",
            "signal",
            "investment_signal",
            "risk",
            "report_debate",
            "report",
        )
        if key in state
    }
    validation = {
        "node_sequence": list(NODE_SEQUENCE),
        "schema_validation": "pydantic",
        "langgraph_optional": True,
        "pipeline_data_source": state.get("data", {}).get("pipeline_data_source", {}),
        "data_availability": state.get("data", {}).get("data_availability", {}),
        "semantic_parse_status": state.get("semantic_slots", {}).get("parse_status"),
        "data_requirement_count": len(state.get("data_requirements", [])),
        "source_usage_count": len(state.get("source_usage", [])),
    }
    return InternalPayload(
        trace_id=state["trace_id"],
        node_outputs=node_outputs,
        llm_prompts=["research.md", "signal.md", "backtest_code.md", "report.md"],
        validation=validation,
        backtest_artifacts=state.get("backtest", {}),
        risk_events=state.get("risk", {}).get("adjustments", []),
    )


def build_public_backtest_performance(  # noqa: F811
    backtest: Mapping[str, Any] | None,
) -> BacktestPerformance | None:
    if not backtest:
        return None

    result = CandidateBacktestResult.model_validate(backtest)
    if result.selected_candidate.metrics is None:
        return None
    return BacktestPerformance(
        selected_candidate_id=result.selected_candidate.candidate_id,
        metrics=result.selected_candidate.metrics,
        equity_curve=result.equity_curve,
        # Public jobs are polled and persisted as JSON. Keep that durable document small;
        # detailed QuantStats arrays stay in the internal/debug backtest artifacts.
        engine_summary=_public_engine_summary(result.engine_summary),
    )


def _ticker_actions(
    state: QuantAgentState,
    cards: list[StrategyCandidateCard],
    *,
    performance: PerformanceAvailable | PerformanceUnavailable | None = None,
    recommendation_gate: RecommendationGate | None = None,
) -> list[TickerAction]:
    """Per-stock BUY/SELL/HOLD, plus WATCH for screened names the rule is not acting on.

    The backtest reports only the names it acts on, because "no signal, no position" is
    not a recommendation it can make about a stock it never looked at. The screen, on the
    other hand, hands the user a specific list and that list needs a verdict for every
    row - otherwise a name silently disappearing reads as "sell". So screened names with
    no action from the backtest come back as WATCH, explicitly.  The explanation is
    constrained to facts recorded by the run; this formatter never re-evaluates entry
    conditions for a ticker the backtest did not price.
    """

    freshness = state.get("freshness_evidence") or {}
    if isinstance(freshness, Mapping) and freshness.get("no_recommendation"):
        return []
    if isinstance(performance, PerformanceUnavailable):
        return []
    if recommendation_gate is not None and recommendation_gate.unmet_data_requirements:
        return []

    backtest = state.get("backtest") or {}
    actions = [
        TickerAction.model_validate(item) for item in backtest.get("ticker_actions") or []
    ]
    decided = {action.ticker for action in actions}
    as_of = actions[0].as_of_date if actions else None
    traded = _traded_universe(backtest)
    slots_full_reason = _slots_full_reason(backtest)
    for card in cards:
        for match in card.matches:
            if match.ticker in decided:
                continue
            decided.add(match.ticker)
            actions.append(
                TickerAction(
                    ticker=match.ticker,
                    name=match.name or match.ticker,
                    action="WATCH",
                    reason=_watch_reason(
                        match.ticker, traded=traded, slots_full_reason=slots_full_reason
                    ),
                    as_of_date=as_of or match.as_of_date,
                    close=match.close,
                )
            )
    order = {"SELL": 0, "BUY": 1, "HOLD": 2, "WATCH": 3}
    return sorted(actions, key=lambda a: (order[a.action], a.ticker))


_WATCH_OUTSIDE_UNIVERSE = (
    "백테스트가 거래한 과거 시점(PIT) 유니버스에 없는 종목이라 백테스트가 판정한 적이 "
    "없습니다. 오늘 스크리닝 조건에는 부합합니다."
)
_WATCH_NO_INSTRUCTION = "백테스트 마지막 거래일에 이 종목에 대한 신규 진입·청산 지시가 없었습니다."


def _watch_reason(
    ticker: str, *, traded: set[str] | None, slots_full_reason: str | None
) -> str:
    if traded is not None and str(ticker).zfill(6) not in traded:
        return _WATCH_OUTSIDE_UNIVERSE
    if slots_full_reason is not None:
        return slots_full_reason
    return _WATCH_NO_INSTRUCTION


def _traded_universe(backtest: Mapping[str, Any]) -> set[str] | None:
    """The tickers actually priced by the backtest, if the run recorded them."""

    payload = backtest.get("backtest_payload")
    tickers = payload.get("tickers") if isinstance(payload, Mapping) else None
    if not isinstance(tickers, list) or not tickers:
        return None
    return {str(ticker).zfill(6) for ticker in tickers}


def _slots_full_reason(backtest: Mapping[str, Any]) -> str | None:
    """Name a full-position limit only when the engine recorded both inputs."""

    summary = backtest.get("engine_summary")
    if not isinstance(summary, Mapping):
        return None
    held = summary.get("open_position_tickers")
    if not isinstance(held, list):
        return None
    context = summary.get("ai_backtest_context")
    limit = context.get("applied_max_positions") if isinstance(context, Mapping) else None
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        return None
    if len(held) < limit:
        return None
    return (
        f"백테스트 마지막 거래일에 전략 보유 슬롯 {len(held)}/{limit}이 모두 차 있어 "
        "신규 진입이 제한된 상태였습니다."
    )


def _recommendation_gate(state: QuantAgentState) -> RecommendationGate | None:
    """Gate today's picks on the backtest of the strategy that produced them.

    Returns None when there was no backtest to gate against (no picks, or the backtest
    node never ran). Otherwise validated mirrors whether the backtest cleared the
    objective floor, so a strategy that failed history is not dressed up as a buy list.
    """

    if state.get("backtest") is None:
        return None
    validated = bool(state.get("strategy_validated"))
    reason = (
        "백테스트가 목표 기준(샤프·MDD·벤치마크 초과)을 충족했습니다."
        if validated
        else "백테스트가 목표 기준(샤프·MDD·벤치마크 초과)에 미달해 참고용입니다."
    )
    return RecommendationGate(validated=validated, reason=reason)


def _status_for_category(category: AmbiguityCode) -> EnvelopeStatus:
    if category == AmbiguityCode.READY:
        return EnvelopeStatus.READY
    if category == AmbiguityCode.INFEASIBLE:
        return EnvelopeStatus.REJECTED
    return EnvelopeStatus.NEED_CLARIFICATION


def _ambiguity_reason(category: AmbiguityCode) -> str:
    return {
        AmbiguityCode.NO_STRATEGY_INTENT: "안녕하세요! 분석할 투자 전략이나 매매 조건을 말씀해 주세요.",
        AmbiguityCode.READY: "분석 가능한 전략 입력입니다.",
        AmbiguityCode.INPUT_AMBIGUOUS: "요청한 조건 중 현재 데이터로 검증할 수 없는 항목이 있습니다.",
        AmbiguityCode.TERM_UNKNOWN: "용어를 L1/L2 지식베이스와 매칭했지만 확인이 필요합니다.",
        AmbiguityCode.CONFLICTING: "낮은 변동성과 단기 급등 목표가 서로 충돌합니다.",
        AmbiguityCode.INFEASIBLE: "옵션/선물/가상자산은 AI MVP 지원 범위 밖입니다.",
    }[category]


def _availability_next_actions(data_availability: Mapping[str, Any]) -> list[str]:
    if not data_availability:
        return []
    proxy_items = data_availability.get("proxy_used")
    if isinstance(proxy_items, list) and proxy_items:
        return ["재무/공시/뉴스 조건은 proxy 여부 확인"]
    return []


def _freshness_next_actions(evidence: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(evidence, Mapping) or not evidence.get("no_recommendation"):
        return []
    return ["최신 source manifest 확인 후 다시 실행"]


def _route_after_ambiguity(state: QuantAgentState) -> str:
    if state["ambiguity"]["category"] == AmbiguityCode.NO_STRATEGY_INTENT.value:
        return "final"
    return "data"


def _route_after_data(state: QuantAgentState) -> str:
    return "ready" if state["status"] == EnvelopeStatus.READY.value else "final"


def _trace_id(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:16]


def _pipeline_source(
    pipeline_data_source: Mapping[str, Any] | None,
) -> Literal["fixture", "postgres", "unknown"]:
    if not isinstance(pipeline_data_source, Mapping):
        return "unknown"
    source = pipeline_data_source.get("source")
    if source in {"fixture", "postgres"}:
        return source
    return "unknown"


def build_public_backtest_performance(  # noqa: F811
    backtest: Mapping[str, Any] | None,
    *,
    price_rows: Sequence[Mapping[str, Any]] | None = None,
    pipeline_data_source: Mapping[str, Any] | None = None,
) -> BacktestPerformance | None:
    if not backtest:
        return None

    result = CandidateBacktestResult.model_validate(backtest)
    if result.selected_candidate.metrics is None:
        return None

    normalized_rows = _price_rows(price_rows)
    source = _pipeline_source(pipeline_data_source)
    reliability = _build_backtest_reliability(result, normalized_rows, source=source)
    benchmark = _build_public_benchmark(normalized_rows)
    return BacktestPerformance(
        selected_candidate_id=result.selected_candidate.candidate_id,
        metrics=result.selected_candidate.metrics,
        equity_curve=result.equity_curve,
        engine_summary=_public_engine_summary(result.engine_summary),
        reliability=reliability,
        data_quality=_build_data_quality(reliability),
        benchmark=benchmark,
        metric_details=_build_public_metric_details(
            result,
            price_rows=normalized_rows,
            benchmark=benchmark,
        ),
    )


def _minimum_input_gaps(performance: PerformanceUnavailable) -> list[str]:
    """Name the minimum-input rule and what the run actually had, as data not prose."""

    facts = performance.safe_facts
    gaps = [f"performance_unavailable:{performance.reason_code}"]
    for observed_key, required_key in (
        ("trading_days", "minimum_trading_days"),
        ("ticker_count", "minimum_tickers"),
    ):
        observed = facts.get(observed_key)
        required = facts.get(required_key)
        if isinstance(observed, int) and isinstance(required, int) and observed < required:
            gaps.append(f"{observed_key}:{observed} < {required_key}:{required}")
    return gaps


def _insufficient_input_reason(performance: PerformanceUnavailable) -> str:
    if performance.reason_code == "insufficient_reliability":
        return (
            "입력 기간·유니버스가 최소 기준에 미달해 추천을 생성하지 않습니다. "
            f"(거래일 {performance.safe_facts.get('trading_days')}일 / 최소 "
            f"{performance.safe_facts.get('minimum_trading_days')}일, "
            f"종목 {performance.safe_facts.get('ticker_count')}개 / 최소 "
            f"{performance.safe_facts.get('minimum_tickers')}개)"
        )
    return (
        "공개 가능한 백테스트 성과가 없어 추천 규칙 통과 여부를 판단할 수 없습니다. "
        f"({performance.reason_code})"
    )


def _recommendation_gate(
    state: QuantAgentState,
    *,
    performance: PerformanceAvailable | PerformanceUnavailable | None = None,
) -> RecommendationGate | None:
    freshness = state.get("freshness_evidence") or {}
    if isinstance(freshness, Mapping) and freshness.get("no_recommendation"):
        return RecommendationGate(
            validated=False,
            reason=str(
                freshness.get("reason")
                or "freshness 한계를 확인할 수 없어 추천을 생성하지 않습니다."
            ),
        )
    if isinstance(performance, PerformanceUnavailable):
        # The picks are validated by the backtest of the same rule. When that backtest
        # could not be published - the input period or universe fell under the minimum
        # data rule, or its method manifest was incomplete - there is nothing to
        # validate against, and a metric threshold that was computed over too little
        # history must not be reported as if the strategy had passed.
        return RecommendationGate(
            validated=False,
            reason=_insufficient_input_reason(performance),
            verification_complete=False,
            unmet_data_requirements=_minimum_input_gaps(performance),
        )
    backtest_payload = state.get("backtest")
    if backtest_payload is None:
        return None
    try:
        backtest = CandidateBacktestResult.model_validate(backtest_payload)
    except Exception:
        return RecommendationGate(
            validated=False,
            reason="백테스트 결과를 해석할 수 없어 추천 규칙 통과 여부를 판단할 수 없습니다.",
        )

    selected = backtest.selected_candidate
    if selected.metrics is None:
        return RecommendationGate(
            validated=False,
            reason="검증 대상 백테스트 지표가 없어 추천 규칙 통과 여부를 판단할 수 없습니다.",
        )

    reasons = _objective_gate_reasons(
        selected.metrics,
        backtest.engine_summary,
        selection_mode=backtest.strategy_a.selection_mode,
        benchmark_return=backtest.backtest_payload.get("benchmark_return"),
    )
    validated = not reasons
    shortfalls = [item for item in reasons if not _is_data_gap_reason(item)]
    gaps = [
        *_benchmark_input_gaps(backtest),
        *(item for item in reasons if _is_data_gap_reason(item)),
    ]
    return RecommendationGate(
        validated=validated,
        reason=_gate_reason(validated, shortfalls, gaps),
        verification_complete=not gaps,
        unmet_objective_criteria=shortfalls,
        unmet_data_requirements=gaps,
    )


# These messages describe inputs that did not arrive, not an observed metric below its
# threshold. They must remain distinct from a measured strategy shortfall.
_DATA_GAP_REASON_MARKERS = ("is unavailable", "계산할 수 없음", "비교 구간이 없습니다")


def _is_data_gap_reason(reason: str) -> bool:
    return any(marker in reason for marker in _DATA_GAP_REASON_MARKERS)


def _benchmark_input_gaps(backtest: CandidateBacktestResult) -> list[str]:
    if backtest.strategy_a.selection_mode != "automatic":
        return []
    payload = backtest.backtest_payload
    benchmark = payload.get("benchmark") if isinstance(payload, Mapping) else None
    primary = benchmark.get("primary") if isinstance(benchmark, Mapping) else None
    if isinstance(primary, Mapping) and primary.get("available"):
        return []
    detail = ""
    if isinstance(primary, Mapping):
        stated = str(primary.get("unavailable_reason") or "").strip()
        detail = f" ({stated})" if stated else ""
    return [
        (
            "공식 KOSPI/KOSDAQ TR 벤치마크 시계열이 아직 적재되지 않아 "
            f"벤치마크 대비 검증을 완료하지 못했습니다{detail}"
        )
    ]


def _gate_reason(validated: bool, shortfalls: Sequence[str], gaps: Sequence[str]) -> str:
    if validated and not gaps:
        return "objective gate를 모두 통과해 오늘의 추천을 유지합니다."
    if validated:
        return (
            "측정된 objective 지표는 모두 통과했지만, 검증에 필요한 데이터가 없어 "
            "검증을 끝내지 못했습니다: " + "; ".join(gaps)
        )
    if shortfalls and gaps:
        return (
            "objective 조건 미충족: "
            + ", ".join(shortfalls)
            + " / 그리고 아직 검증하지 못한 항목: "
            + "; ".join(gaps)
        )
    if shortfalls:
        return "objective 조건 미충족: " + ", ".join(shortfalls)
    return (
        "성과가 기준에 미달한 것이 아니라, 검증에 필요한 데이터가 아직 없어 "
        "판정을 내리지 못했습니다: " + "; ".join(gaps)
    )


def _objective_gate_reasons(
    metrics: BacktestMetrics,
    engine_summary: Mapping[str, Any],
    *,
    selection_mode: str = "standard",
    benchmark_return: Any | None = None,
) -> list[str]:
    trade_count = _summary_float_default(engine_summary, "effective_trade_count", 0.0)
    reasons: list[str] = []
    if trade_count < MIN_OBJECTIVE_TRADES:
        reasons.append(
            f"거래 횟수 {trade_count:.0f}회로 MIN_OBJECTIVE_TRADES={MIN_OBJECTIVE_TRADES} 조건 미달"
        )
    if metrics.out_sample_sharpe is None:
        reasons.append("워크포워드 외부 샤프비율을 신뢰성 있게 계산할 수 없음")
    elif metrics.out_sample_sharpe < MIN_OBJECTIVE_SHARPE:
        reasons.append(
            f"보유 구간 외부 샤프비율 {metrics.out_sample_sharpe:.4f} < {MIN_OBJECTIVE_SHARPE:.2f}"
        )
    if metrics.max_drawdown < MAX_OBJECTIVE_DRAWDOWN:
        reasons.append(
            f"최대 낙폭 {metrics.max_drawdown:.4f} < {MAX_OBJECTIVE_DRAWDOWN:.2f} (리스크 허용치 미달)"
        )
    if selection_mode == "automatic":
        reasons.extend(_benchmark_objective_reasons(metrics))
    return reasons


def _record_analysis_memory(state: QuantAgentState, status: EnvelopeStatus) -> None:
    """Note how this run turned out, for the next analysis of the same strategy."""

    memory = AnalysisMemory.from_env()
    if not memory.enabled:
        return
    strategy = state.get("strategy_spec") or {}
    strategy_id = str(strategy.get("strategy_id") or "")
    if not strategy_id:
        return

    data = state.get("data") or {}
    pipeline = data.get("pipeline_data_source") or {}
    relaxation = pipeline.get("screening_relaxation") or {}
    availability = data.get("data_availability") or {}
    performance = (
        project_public_performance(
            state.get("backtest"),
            price_rows=state.get("price_rows"),
            pipeline_data_source=state.get("data", {}).get("pipeline_data_source"),
        )
        or {}
    )
    payload = performance.performance if isinstance(performance, PerformanceAvailable) else None
    metrics = payload.get("metrics") if isinstance(payload, Mapping) else None

    try:
        memory.record(
            strategy_id,
            query=str(state.get("user_query") or ""),
            outcome=status.value,
            candidate_count=len(data.get("screening_candidates") or []),
            metrics=metrics or {},
            relaxation_rounds=int(relaxation.get("relaxation_rounds") or 0),
            unmet_requirements=[
                str(item.get("label"))
                for item in availability.get("unsupported_capabilities") or []
            ],
            note=(state.get("strategy_revision") or {}).get("rationale"),
        )
    except Exception:
        # Memory is an optimisation; never let it take down a completed analysis.
        _logger.warning("could not record analysis memory", exc_info=True)


def _build_backtest_reliability(
    result: CandidateBacktestResult,
    price_rows: Sequence[Mapping[str, Any]],
    *,
    source: Literal["fixture", "postgres", "unknown"],
) -> BacktestReliability:
    row_count = len(price_rows)
    dates = sorted({str(row.get("date")) for row in price_rows if row.get("date") is not None})
    trading_days = len(dates)
    ticker_count = len(
        {
            str(row.get("ticker") or "005930").zfill(6)
            for row in price_rows
            if row.get("ticker") is not None
        }
    )
    trade_count = int(_summary_float_default(result.engine_summary, "effective_trade_count", 0.0))
    reasons: list[str] = []
    warnings: list[str] = []

    if row_count == 0:
        reasons.append("가격 행이 없습니다.")
    if trading_days < _RELIABILITY_WARN_UNTIL_DAYS:
        reasons.append("거래일 수가 너무 적어 통계 신뢰도가 낮습니다.")
    elif trading_days < _RELIABILITY_SUFFICIENT_DAYS:
        warnings.append("거래일 수가 90일 미만으로 품질이 제한적입니다.")
    if ticker_count < _RELIABILITY_MIN_TICKERS:
        reasons.append("티커 수가 2개 미만입니다.")
    if source == "fixture" and row_count <= 4 and ticker_count == 1:
        reasons.append("기본 fixture 샘플(4개 행/1종목)에서는 안정적 통계 산출이 제한됩니다.")
    if trade_count < MIN_OBJECTIVE_TRADES:
        warnings.append(
            f"실제 거래 횟수 {trade_count}회로 MIN_OBJECTIVE_TRADES={MIN_OBJECTIVE_TRADES} 미만입니다."
        )

    if reasons:
        status = "insufficient"
    elif warnings:
        status = "limited"
    else:
        status = "sufficient"

    return BacktestReliability(
        source=source,
        status=status,
        row_count=row_count,
        ticker_count=ticker_count,
        trading_days=trading_days,
        history_start=dates[0] if dates else None,
        history_end=dates[-1] if dates else None,
        trade_count=trade_count,
        reasons=reasons,
        warnings=warnings,
    )


def _build_data_quality(reliability: BacktestReliability) -> list[str]:
    quality = [
        f"source:{reliability.source}",
        f"rows:{reliability.row_count}",
        f"tickers:{reliability.ticker_count}",
        f"trading_days:{reliability.trading_days}",
        f"trades:{reliability.trade_count}",
    ]
    if reliability.status == "insufficient":
        quality.append("신뢰도: 불충분")
    elif reliability.status == "limited":
        quality.append("신뢰도: 제한적")
    else:
        quality.append("신뢰도: 충분")
    return quality


def _build_public_benchmark(price_rows: Sequence[Mapping[str, Any]]) -> BacktestBenchmark:
    curve, total_return = _equal_weight_benchmark_curve(price_rows)
    if not curve:
        return BacktestBenchmark(
            label=BENCHMARK_LABEL,
            method=BENCHMARK_METHOD,
            warning=BENCHMARK_WARNING,
            total_return=None,
            cumulative_curve=[],
            is_available=False,
            unavailable_reason=_BENCHMARK_UNAVAILABLE_REASON,
        )
    return BacktestBenchmark(
        label=BENCHMARK_LABEL,
        method=BENCHMARK_METHOD,
        warning=BENCHMARK_WARNING,
        total_return=total_return,
        cumulative_curve=curve,
        is_available=True,
        unavailable_reason=None,
    )


def _build_public_metric_details(
    result: CandidateBacktestResult,
    *,
    price_rows: Sequence[Mapping[str, Any]],
    benchmark: BacktestBenchmark,
) -> list[PublicMetricDetail]:
    metrics = result.selected_candidate.metrics
    if metrics is None:
        return []

    trading_days = len({str(row.get("date")) for row in price_rows if row.get("date") is not None})
    equity_returns = _equity_returns(result.equity_curve)
    benchmark_return = benchmark.total_return if benchmark.is_available else None
    cagr = _annualized_return(metrics.total_return, trading_days=trading_days)
    calmar = _calmar_ratio(cagr, metrics.max_drawdown)

    values: dict[str, float | None] = {
        "total_return": metrics.total_return,
        "cagr": cagr,
        "annualized_volatility": _annualized_volatility(equity_returns),
        "sharpe_ratio": metrics.sharpe_ratio,
        "sortino_ratio": _sortino_ratio(cagr, equity_returns),
        "max_drawdown": metrics.max_drawdown,
        "calmar_ratio": calmar,
        "win_rate": metrics.win_rate,
        "profit_factor": _profit_factor(result.engine_summary),
        "benchmark_return": benchmark_return,
        "excess_return": (
            metrics.total_return - benchmark_return
            if _is_numeric_metric(benchmark_return)
            else None
        ),
        "in_sample_sharpe": metrics.in_sample_sharpe,
        "out_sample_sharpe": metrics.out_sample_sharpe,
        "degradation": metrics.degradation,
    }

    return [_metric_detail(key, values.get(key)) for key in _METRIC_DETAIL_KEYS]


def _metric_detail(key: str, value: float | None) -> PublicMetricDetail:
    explanation = metric_explanation(key)
    is_available = _is_numeric_metric(value)
    return PublicMetricDetail(
        key=key,
        label=explanation["label"],
        value=round(float(value), METRIC_ROUND_DIGITS) if is_available else None,
        unit=explanation["unit"],
        is_available=is_available,
        unavailable_reason=None if is_available else _UNAVAILABLE_METRIC_REASON,
        plain_explanation=explanation["plain_explanation"],
        why_used=explanation["why_used"],
        caution=explanation["caution"],
    )


def _equity_returns(equity_curve: Sequence[BacktestEquityPoint]) -> list[float]:
    if len(equity_curve) < 2:
        return []
    returns: list[float] = []
    for previous, current in zip(equity_curve, equity_curve[1:]):
        previous_value = previous.cumulative_return + 1.0
        current_value = current.cumulative_return + 1.0
        if previous_value == 0.0:
            return []
        returns.append(current_value / previous_value - 1.0)
    return returns


def _annualized_volatility(returns: Sequence[float]) -> float | None:
    if len(returns) < 2:
        return None
    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)
    if variance <= 0.0:
        return 0.0
    return math.sqrt(variance) * math.sqrt(252.0)


def _sortino_ratio(total_return: float, returns: Sequence[float]) -> float | None:
    if len(returns) < 2:
        return None
    downside = [value for value in returns if value < 0.0]
    if not downside:
        return None
    downside_mean = sum(downside) / len(downside)
    downside_variance = sum((value - downside_mean) ** 2 for value in downside) / len(downside)
    if downside_variance <= 0.0:
        return None
    downside_std = math.sqrt(downside_variance) * math.sqrt(252.0)
    if downside_std == 0.0:
        return None
    return total_return / downside_std


# Public performance helpers are sourced from quant_performance for a stable behavior contract.
from ai_graph.quant_performance import (  # noqa: E402, F401, F811
    build_public_backtest_performance,
    project_public_performance,
)
