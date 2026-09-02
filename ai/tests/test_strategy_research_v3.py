from __future__ import annotations

from datetime import date, timedelta

import pytest

from ai_graph.llm.base import LLMJsonRequest, LLMTimeoutError
from ai_graph.nodes.strategy_research import (
    StrategyResearchError,
    research_strategy_execution_spec,
)
from ai_graph.research_contract import RuleDraftSigner, build_rule_draft
from ai_graph.schemas import ResearchCandidateExecutionSpecV3


class _ResearchClient:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.requests: list[LLMJsonRequest] = []

    def generate_json(self, request: LLMJsonRequest) -> dict:
        self.requests.append(request)
        return self.response


def _donchian_response(*, required_metrics: list[str] | None = None) -> dict:
    return {
        "resolution_summary": "돈치안 돌파는 최근 고가 범위를 상향 이탈한 종목을 추세 후보로 보는 규칙으로 해석했습니다.",
        "sources": [
            {
                "source_id": "source-1",
                "title": "Donchian channel definition",
                "url": "https://example.com/donchian",
                "claim": "돈치안 채널은 일정 기간의 최고가와 최저가로 범위를 구성합니다.",
            }
        ],
        "candidates": [
            {
                "candidate_id": "research-donchian-breakout-20",
                "title": "20일 돈치안 상단 돌파",
                "hypothesis": "20일 최고가 부근 상향 돌파 뒤에 추세가 이어질 수 있습니다.",
                "counter_hypothesis": "횡보장에서는 돌파가 잦은 손절로 이어질 수 있습니다.",
                "entry_conditions": [
                    {
                        "left": "close",
                        "operator": "gte",
                        "right": "high",
                        "window": 20,
                        "aggregate": "max",
                        "scale": 0.995,
                    }
                ],
                "exit_conditions": [
                    {
                        "left": "close",
                        "operator": "lte",
                        "right": "sma20",
                    }
                ],
                "required_metrics": required_metrics or ["close", "high", "sma20"],
                "assumptions": ["KRX 일봉 종가 기준으로 다음 거래일 체결을 가정합니다."],
                "source_ids": ["source-1"],
            }
        ],
    }


def test_unknown_strategy_uses_web_research_then_seals_the_researched_conditions() -> None:
    client = _ResearchClient(_donchian_response())

    spec = research_strategy_execution_spec(
        query="돈치안 채널 돌파 전략으로 검증해줘",
        available_metrics=["sma20"],
        llm_client=client,
    )

    assert spec.classification == "research_required"
    assert spec.candidates[0].candidate_id == "research-donchian-breakout-20"
    assert spec.candidates[0].entry_conditions[0].left == "close"
    candidate_metrics = {
        condition.left
        for condition in [
            *spec.candidates[0].entry_conditions,
            *spec.candidates[0].exit_conditions,
        ]
    }
    assert "rsi" not in candidate_metrics
    assert len(client.requests) == 1
    request = client.requests[0]
    assert request.enable_web_search is True
    assert request.stream_response is False
    assert request.reasoning_effort == "low"
    assert request.max_tool_calls == 1
    assert request.task_type == "strategy_research_resolution"
    assert "Do not create Python, SQL" in request.system_prompt


def test_researcher_cannot_replace_an_unsupported_strategy_with_a_catalogue_rule() -> None:
    client = _ResearchClient(_donchian_response(required_metrics=["cointegration_score"]))

    with pytest.raises(StrategyResearchError, match="unsupported metrics"):
        research_strategy_execution_spec(
            query="공적분 페어 트레이딩으로 검증해줘",
            available_metrics=["sma20"],
            llm_client=client,
        )


def test_researcher_normalizes_provider_display_label_aliases_without_touching_conditions() -> None:
    response = _donchian_response()
    response["sources"][0]["source_name"] = response["sources"][0].pop("title")
    response["candidates"][0]["strategy_name"] = response["candidates"][0].pop("title")

    spec = research_strategy_execution_spec(
        query="돈치안 채널 돌파 전략으로 검증해줘",
        available_metrics=["sma20"],
        llm_client=_ResearchClient(response),
    )

    assert spec.sources[0].title == "Donchian channel definition"
    assert spec.candidates[0].title == "20일 돈치안 상단 돌파"
    assert spec.candidates[0].entry_conditions[0].left == "close"


def test_researcher_derives_only_display_titles_when_provider_omits_them() -> None:
    response = _donchian_response()
    response["sources"][0].pop("title")
    response["candidates"][0].pop("title")

    spec = research_strategy_execution_spec(
        query="돈치안 채널 돌파 전략으로 검증해줘",
        available_metrics=["sma20"],
        llm_client=_ResearchClient(response),
    )

    assert spec.sources[0].title == "example.com"
    assert spec.candidates[0].title == "돈치안 채널 돌파 전략으로 검증해줘 — 검증 후보"
    assert spec.candidates[0].entry_conditions[0].left == "close"


def test_researcher_normalizes_provider_only_identifiers_without_touching_conditions() -> None:
    response = _donchian_response()
    response["sources"][0]["source_id"] = "web-source-abc"
    response["candidates"][0]["candidate_id"] = "donchian_breakout"
    response["candidates"][0]["source_ids"] = ["web-source-abc"]

    spec = research_strategy_execution_spec(
        query="돈치안 채널 돌파 전략으로 검증해줘",
        available_metrics=["sma20"],
        llm_client=_ResearchClient(response),
    )

    assert spec.sources[0].source_id == "source-1"
    assert spec.candidates[0].candidate_id == "research-candidate-1"
    assert spec.candidates[0].source_ids == ["source-1"]
    assert spec.candidates[0].entry_conditions[0].left == "close"


def test_researcher_normalizes_unambiguous_rank_percentage_to_fraction() -> None:
    response = _donchian_response()
    response["candidates"][0]["entry_conditions"][0]["universe_rank_pct"] = 20

    spec = research_strategy_execution_spec(
        query="상위 20% 돈치안 돌파 종목을 검증해줘",
        available_metrics=["sma20"],
        llm_client=_ResearchClient(response),
    )

    assert spec.candidates[0].entry_conditions[0].universe_rank_pct == 0.2


def test_researcher_normalizes_market_relative_comparison_to_excess_return_threshold() -> None:
    response = _donchian_response(required_metrics=["relative_strength_20d", "market_relative_strength_20d", "sma20"])
    response["candidates"][0]["entry_conditions"] = [
        {
            "left": "relative_strength_20d",
            "operator": "gt",
            "right": "market_relative_strength_20d",
            "universe_rank_pct": 20,
        }
    ]
    response["candidates"][0]["exit_conditions"] = [
        {
            "left": "relative_strength_20d",
            "operator": "lte",
            "right": "market_relative_strength_20d",
        }
    ]

    spec = research_strategy_execution_spec(
        query="시장지수보다 최근 1개월 상대강도가 높은 주도주를 검증해줘",
        available_metrics=["close", "sma20", "relative_strength_20d"],
        llm_client=_ResearchClient(response),
    )

    candidate = spec.candidates[0]
    assert candidate.entry_conditions[0].right == 0
    assert candidate.entry_conditions[0].universe_rank_pct == 0.2
    assert candidate.exit_conditions[0].right == 0
    assert candidate.required_metrics == ["relative_strength_20d", "sma20"]


def test_researcher_repairs_one_invalid_structured_candidate_then_seals_v3() -> None:
    invalid = _donchian_response(required_metrics=["cointegration_score"])
    repaired = _donchian_response()

    class SequencedResearchClient:
        def __init__(self) -> None:
            self.requests: list[LLMJsonRequest] = []
            self._responses = [invalid, repaired]

        def generate_json(self, request: LLMJsonRequest) -> dict:
            self.requests.append(request)
            return self._responses.pop(0)

    client = SequencedResearchClient()
    spec = research_strategy_execution_spec(
        query="돈치안 채널 돌파 전략으로 검증해줘",
        available_metrics=["sma20"],
        llm_client=client,
    )

    assert spec.candidates[0].candidate_id == "research-donchian-breakout-20"
    assert [request.task_type for request in client.requests] == [
        "strategy_research_resolution",
        "strategy_research_resolution_repair",
    ]
    repair_context = client.requests[1].variables_jsonb["untrusted_quoted_context"]
    assert repair_context["previous_validation_failure"]["code"] == "research_metric_unsupported"


def test_researcher_does_not_spend_a_semantic_repair_on_provider_timeout() -> None:
    class TimeoutResearchClient:
        def __init__(self) -> None:
            self.requests: list[LLMJsonRequest] = []

        def generate_json(self, request: LLMJsonRequest) -> dict:
            self.requests.append(request)
            raise LLMTimeoutError("provider timed out")

    client = TimeoutResearchClient()
    with pytest.raises(StrategyResearchError) as raised:
        research_strategy_execution_spec(
            query="돈치안 채널 돌파 전략으로 검증해줘",
            available_metrics=["sma20"],
            llm_client=client,
        )

    assert raised.value.cause_code == "research_provider_failure"
    assert len(client.requests) == 1


def test_researcher_can_seal_a_range_rule_when_the_compiler_supports_it() -> None:
    from ai_graph.nodes.condition_compiler import compile_conditions

    response = _donchian_response(required_metrics=["rsi", "sma20"])
    response["candidates"][0]["entry_conditions"] = [
        {"left": "rsi", "operator": "between", "right": [25, 35]}
    ]
    spec = research_strategy_execution_spec(
        query="RSI가 25에서 35 사이일 때 진입하는 전략을 검증해줘",
        available_metrics=["rsi", "sma20"],
        llm_client=_ResearchClient(response),
    )

    compiled = compile_conditions(spec.candidates[0].entry_conditions)

    assert compiled is not None
    assert "25.0" in compiled.per_stock
    assert "35.0" in compiled.per_stock


def test_rule_draft_binds_the_researched_contract_before_job_admission() -> None:
    client = _ResearchClient(_donchian_response())
    signer = RuleDraftSigner("test-research-v3-secret")

    draft = build_rule_draft(
        query="돈치안 채널 돌파 전략으로 검증해줘",
        user_id="user-1",
        signer=signer,
        available_metrics=["sma20"],
        llm_client=client,
        use_llm=True,
    )

    assert draft.is_executable is True
    assert draft.canonical_rule is None
    assert draft.exploration is None
    assert isinstance(draft.strategy_execution_spec, ResearchCandidateExecutionSpecV3)
    assert draft.strategy_execution_spec.candidates[0].title == "20일 돈치안 상단 돌파"
    signer.verify(
        token=draft.parse_token or "",
        rule=draft.strategy_execution_spec,
        user_id="user-1",
    )


def test_graph_compiles_the_sealed_research_conditions_without_a_template_substitution() -> None:
    from ai_graph.graph import _strategy_spec_from_execution_spec

    spec = research_strategy_execution_spec(
        query="돈치안 채널 돌파 전략으로 검증해줘",
        available_metrics=["sma20"],
        llm_client=_ResearchClient(_donchian_response()),
    )

    strategy = _strategy_spec_from_execution_spec(spec)

    assert strategy.selection_mode == "user_defined"
    assert strategy.name == "20일 돈치안 상단 돌파"
    assert strategy.entry_conditions == spec.candidates[0].entry_conditions
    assert strategy.exit_conditions == spec.candidates[0].exit_conditions
    assert strategy.risk_constraints["research_snapshot_hash"] == spec.research_snapshot_hash


def test_sealed_research_skips_non_authoritative_current_screening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Current screening cards must not delay the V3 PIT backtest path.

    A present-day screen is display enrichment only. The historical execution still
    receives the full PIT universe through the data loader; this checks that the graph
    asks that loader not to issue the unrelated current-screen query as well.
    """

    from ai_graph.graph import data_node

    spec = research_strategy_execution_spec(
        query="돈치안 채널 돌파 전략으로 검증해줘",
        available_metrics=["sma20"],
        llm_client=_ResearchClient(_donchian_response()),
    )
    captured: dict[str, object] = {}

    def stop_after_capture(
        query: str, trace_id: str, *, screen_current: bool = True
    ) -> object:
        captured.update(
            {"query": query, "trace_id": trace_id, "screen_current": screen_current}
        )
        raise RuntimeError("data loader captured")

    monkeypatch.setattr("ai_graph.graph.load_pipeline_data_from_env", stop_after_capture)

    with pytest.raises(RuntimeError, match="data loader captured"):
        data_node(
            {
                "user_query": "돈치안 채널 돌파 전략으로 검증해줘",
                "trace_id": "sealed-v3-screening",
                "execution_spec": spec.model_dump(mode="json"),
            }
        )

    assert captured["screen_current"] is False


def test_data_plan_reads_the_sealed_ast_not_only_the_researcher_metric_summary() -> None:
    from ai_graph.graph import _data_requirements_from_sealed_spec

    response = _donchian_response(required_metrics=["close"])
    response["candidates"][0]["entry_conditions"] = [
        {"left": "roe", "operator": "gte", "right": 0.1}
    ]
    spec = research_strategy_execution_spec(
        query="ROE가 높은 종목의 추세 전략으로 검증해줘",
        available_metrics=["roe", "sma20"],
        llm_client=_ResearchClient(response),
    )

    requirements = _data_requirements_from_sealed_spec(spec, fallback=[])

    assert {item.family for item in requirements} == {"ohlcv_ta", "fundamentals"}


def test_researched_strategy_backtests_only_its_sealed_condition_candidate() -> None:
    from ai_graph.graph import _strategy_spec_from_execution_spec
    from ai_graph.nodes.backtest_code import Loop3Request, generate_loop3_candidates

    spec = research_strategy_execution_spec(
        query="돈치안 채널 돌파 전략으로 검증해줘",
        available_metrics=["sma20"],
        llm_client=_ResearchClient(_donchian_response()),
    )
    result = generate_loop3_candidates(
        Loop3Request(
            strategy=_strategy_spec_from_execution_spec(spec),
            variant="A",
            trace_id="trace-research-v3",
            server_only=True,
        )
    )

    assert len(result.candidates) == 1
    assert {candidate.parameters.profile for candidate in result.candidates} == {
        "compiled_conditions"
    }
    assert result.strategy_ir.entry_conditions == spec.candidates[0].entry_conditions
    assert result.strategy_ir.exit_conditions == spec.candidates[0].exit_conditions


def test_researched_v3_candidate_reaches_backtest_module_without_python_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lock the complete V3 compiler → real engine hand-off.

    A researched candidate may never fall through to executable generated Python or a
    generic profile.  The conditions become vector actions, then the authoritative
    ``backtest_module`` engine receives those actions and computes the result.
    """

    from ai_graph.graph import _strategy_spec_from_execution_spec
    from ai_graph.nodes import backtest as backtest_node
    from ai_graph.nodes.backtest_code import Loop3Request, generate_loop3_candidates

    spec = research_strategy_execution_spec(
        query="돈치안 채널 돌파 전략으로 검증해줘",
        available_metrics=["sma20"],
        llm_client=_ResearchClient(_donchian_response()),
    )
    strategy = _strategy_spec_from_execution_spec(spec)
    generated = generate_loop3_candidates(
        Loop3Request(strategy=strategy, variant="A", trace_id="trace-v3-engine", server_only=True)
    )
    candidate = generated.candidates[0]
    engine_calls = []
    actual_run = backtest_node.run_engine_backtest

    def capture_engine(*args, **kwargs):
        engine_calls.append((args, kwargs))
        return actual_run(*args, **kwargs)

    def python_fallback_must_not_run(*_args, **_kwargs):
        raise AssertionError("researched V3 candidate must not execute Python fallback code")

    monkeypatch.setattr(backtest_node, "run_engine_backtest", capture_engine)
    monkeypatch.setattr(backtest_node, "_execute_candidate_code", python_fallback_must_not_run)
    # This contract asserts the engine call itself, so a prior test's on-disk result
    # cache must not bypass the execution boundary.
    monkeypatch.setattr(backtest_node._DiskEvaluationCache, "load", lambda *_args: None)

    result = backtest_node.run_candidate_backtest(strategy, [candidate])

    assert result.selected_candidate.parameters is not None
    assert result.selected_candidate.parameters.profile == "compiled_conditions"
    assert candidate.strategy_ir is not None
    assert candidate.strategy_ir.entry_conditions == spec.candidates[0].entry_conditions
    assert candidate.strategy_ir.exit_conditions == spec.candidates[0].exit_conditions
    assert len(engine_calls) >= 1
    # ``generated_actions`` are the direct, deterministic evaluation of the sealed
    # AST. The engine only sees those actions; it does not receive a free-form prompt.
    assert engine_calls[0][1]["generated_actions"] is not None


def test_historical_missing_sealed_metric_stops_before_backtest_code_generation() -> None:
    from ai_graph.graph import research_node

    response = _donchian_response(required_metrics=["close"])
    response["candidates"][0]["entry_conditions"] = [
        {"left": "roe", "operator": "gte", "right": 0.1}
    ]
    spec = research_strategy_execution_spec(
        query="ROE가 높은 종목의 추세 전략으로 검증해줘",
        available_metrics=["roe", "sma20"],
        llm_client=_ResearchClient(response),
    )
    start = date(2024, 1, 1)
    rows = [
        {
            "ticker": "005930",
            "date": (start + timedelta(days=index)).isoformat(),
            "open": 100.0 + index,
            "high": 101.0 + index,
            "low": 99.0 + index,
            "close": 100.0 + index,
            "volume": 1_000.0,
            "traded_value": 100_000.0,
        }
        for index in range(25)
    ]

    output = research_node(
        {
            "trace_id": "trace-missing-v3-feature",
            "user_query": "ROE가 높은 종목의 추세 전략으로 검증해줘",
            "execution_spec": spec.model_dump(mode="json"),
            "price_rows": rows,
        }
    )

    assert output["status"] == "need_clarification"
    assert "roe" in output["ambiguity"]["reason"]
    assert "research_compile" not in output
