from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_graph.llm import LLMClient, LLMClientError, create_llm_client
from ai_graph.llm.mock import MOCK_BACKTEST_CODE_CANDIDATES, MockBacktestCodeLLM
from ai_graph.llm.prompts import BacktestCodeLLMOutput, build_backtest_code_json_request
from ai_graph.schemas import CodeCandidate, StrategySpec
from ai_graph.security.ast_validator import validate_backtest_code


MOCK_BACKTEST_CODE_LLM = MockBacktestCodeLLM()
SAFE_RSI_CODE = MOCK_BACKTEST_CODE_CANDIDATES[0]
CONSERVATIVE_RSI_CODE = MOCK_BACKTEST_CODE_CANDIDATES[1]
SMOOTHED_RSI_CODE = MOCK_BACKTEST_CODE_CANDIDATES[2]


class Loop3Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: StrategySpec
    variant: str = Field(pattern="^(A|B)$")
    trace_id: str = Field(min_length=1)


class Loop3Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant: str
    candidates: list[CodeCandidate] = Field(min_length=3, max_length=3)
    selected_candidate: CodeCandidate
    fallback_reasons: list[str] = Field(default_factory=list)


def generate_loop3_candidates(
    request: Loop3Request, *, llm_client: LLMClient | None = None
) -> Loop3Result:
    client = llm_client or create_llm_client()
    output = _generate_backtest_code_output(client, request)
    candidates: list[CodeCandidate] = []
    for index, code in enumerate(output.candidates[:3], start=1):
        validation = validate_backtest_code(code)
        candidates.append(
            CodeCandidate(
                candidate_id=f"{request.variant}{index}",
                variant=request.variant,  # type: ignore[arg-type]
                code=code,
                validation_ok=validation.ok,
                violations=[violation.message for violation in validation.violations],
                metrics=None,
            )
        )
    if len(candidates) != 3:
        raise ValueError("Loop3 requires exactly three candidates")
    valid_candidates = [candidate for candidate in candidates if candidate.validation_ok]
    if not valid_candidates:
        raise ValueError("all generated candidates failed AST validation")
    selected = valid_candidates[0]
    return Loop3Result(
        variant=request.variant,
        candidates=candidates,
        selected_candidate=selected,
        fallback_reasons=output.fallback_reasons,
    )


def backtest_code_node(state: dict) -> dict:
    strategy_a = StrategySpec.model_validate(state["strategy_spec"])
    strategy_b = StrategySpec.model_validate(
        state.get("improved_strategy_spec") or state["strategy_spec"]
    )
    result_a = generate_loop3_candidates(
        Loop3Request(strategy=strategy_a, variant="A", trace_id=state["trace_id"])
    )
    result_b = generate_loop3_candidates(
        Loop3Request(strategy=strategy_b, variant="B", trace_id=state["trace_id"])
    )
    candidates = result_a.candidates + result_b.candidates
    selected = next(candidate for candidate in candidates if candidate.validation_ok)
    return {
        "backtest_code": {
            "candidates": [candidate.model_dump() for candidate in candidates],
            "selected_candidate": selected.model_dump(),
            "fallback_reasons": result_a.fallback_reasons + result_b.fallback_reasons,
        }
    }


def _generate_backtest_code_output(
    client: LLMClient, request: Loop3Request
) -> BacktestCodeLLMOutput:
    try:
        llm_request = build_backtest_code_json_request(request.strategy, request.variant)
        raw_output = client.generate_json(llm_request)
        return BacktestCodeLLMOutput.model_validate(raw_output)
    except (LLMClientError, ValidationError) as exc:
        return BacktestCodeLLMOutput(
            candidates=MOCK_BACKTEST_CODE_LLM.generate_backtest_candidates(
                request.strategy, request.variant
            ),
            fallback_reasons=[f"{type(exc).__name__}: {exc}"],
        )
