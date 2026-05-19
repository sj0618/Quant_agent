from __future__ import annotations

from ai_graph.graph import MockLLMClient, build_quantagent_graph, public_response, run_quantagent
from ai_graph.schemas import NodeName, PublicRunPayload, ScenarioCode
from envelope import success_envelope
from jobs import InMemoryJobStore, get_job, submit_job


def test_graph_ready_e2e_public_payload_excludes_internal_payload():
    state = run_quantagent("RSI 낮고 거래량이 증가한 반도체 대형주 전략")

    assert state["trace_id"].startswith("trc_")
    assert state["debug_ref"].startswith("dbg_")
    assert "internal_payload" in state

    payload = public_response(state)
    envelope = success_envelope(
        trace_id=state["trace_id"],
        debug_ref=state["debug_ref"],
        data=payload,
    )
    dumped = envelope.model_dump(mode="json")

    assert dumped["ok"] is True
    assert dumped["trace_id"] == state["trace_id"]
    assert dumped["debug_ref"] == state["debug_ref"]
    assert "internal_payload" not in dumped
    assert "raw_llm" not in str(dumped)
    assert dumped["data"]["scenario"]["scenario"] == ScenarioCode.READY.value
    assert dumped["data"]["workspace"]["signalDecisions"][0]["generatedBy"] == "Signal Judge"


def test_graph_runs_all_nine_nodes_with_fallback_invoke_contract():
    graph = build_quantagent_graph(MockLLMClient())
    state = graph.invoke(
        {
            "user_input": "방어적인 KRX 주식 전략",
            "trace_id": "trc_test",
            "debug_ref": "dbg_test",
        }
    )

    traces = state["internal_payload"].node_trace
    assert [item.node for item in traces] == [
        NodeName.SUPERVISOR,
        NodeName.AMBIGUITY,
        NodeName.DATA,
        NodeName.RESEARCH,
        NodeName.BACKTEST_CODE,
        NodeName.BACKTEST,
        NodeName.SIGNAL,
        NodeName.RISK_MANAGER,
        NodeName.REPORT,
    ]
    assert state["public_payload"].workspace.activeStrategy.strategy_id == "strategy_defensive_quality"


def test_scenarios_validate_without_workspace_for_non_ready_cases():
    ambiguous = public_response(run_quantagent("저평가주 사줘"))
    unknown = public_response(run_quantagent("눌림목 매매 전략"))
    conflict = public_response(run_quantagent("변동성 낮고 급등하는 종목"))
    infeasible = public_response(run_quantagent("옵션 주문 전략"))

    assert ambiguous.scenario.scenario == ScenarioCode.C1_INPUT_AMBIGUOUS
    assert ambiguous.workspace is None
    assert ambiguous.scenario.options
    assert unknown.scenario.scenario == ScenarioCode.C2_TERM_UNKNOWN
    assert unknown.scenario.termDefinition is not None
    assert conflict.scenario.scenario == ScenarioCode.C4_CONFLICTING
    assert conflict.scenario.conflict is not None
    assert infeasible.scenario.scenario == ScenarioCode.C5_INFEASIBLE
    assert infeasible.scenario.infeasible is not None


def test_public_payload_rejects_internal_payload_extra_field():
    payload = public_response(run_quantagent("RSI 반등 전략")).model_dump()
    payload["internal_payload"] = {"leak": True}

    try:
        PublicRunPayload.model_validate(payload)
    except Exception as exc:
        assert "internal_payload" in str(exc)
    else:
        raise AssertionError("PublicRunPayload must reject internal_payload")


def test_in_process_job_polling_keeps_trace_and_result():
    store = InMemoryJobStore()
    record = submit_job("거래량 증가 반도체 전략", store=store)
    fetched = get_job(record.job_id, store=store)

    assert fetched is not None
    assert fetched.status.value == "succeeded"
    assert fetched.trace_id.startswith("trc_")
    assert fetched.debug_ref.startswith("dbg_")
    assert fetched.result is not None
    assert fetched.result.workspace is not None
