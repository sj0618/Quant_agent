from __future__ import annotations

import math
import os
import sys
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from multiprocessing import get_context
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai_graph.schemas import (
    BacktestEquityPoint,
    BacktestMetrics,
    CandidateBacktestResult,
    CodeCandidate,
)
from ai_graph.schemas import StrategySpec as AIStrategySpec
from ai_graph.nodes.backtest_code import generate_self_improvement_candidates
from ai_graph.progress import report_activity
from ai_graph.nodes.position_sizing import (
    applied_max_positions as _shared_applied_max_positions,
    available_ticker_count as _shared_available_ticker_count,
    requested_max_positions as _shared_requested_max_positions,
)
from ai_graph.security.ast_validator import validate_backtest_code


BACKTEST_MODULE_SOURCE_ROOT = Path(__file__).resolve().parents[3] / "backtest_module"
DEFAULT_FIXTURE_TICKER = "005930"
DEFAULT_FIXTURE_MARKET = "KRX"
DEFAULT_FIXTURE_VOLUME = 1_000_000.0
DEFAULT_INITIAL_CAPITAL = 1_000_000.0
METRIC_ROUND_DIGITS = 6
MIN_RETURNS_FOR_SPLIT = 4
BACKTEST_SPLIT_FRACTION = 0.5
PUBLIC_EQUITY_CURVE_POINTS = 12
MIN_OBJECTIVE_TRADES = 5
# Below this many matched names, a backtest describes the names, not the strategy, and
# tuning dozens of rule variants against them is fitting noise. Warn rather than pretend.
MIN_RELIABLE_TICKERS = 5
# A long-only equity portfolio held through a decade of Korean market drawdowns does
# not keep Sharpe above 1.0 or cap losses at 10% - those are hedge-fund thresholds, and
# requiring them meant every run "missed the objective" and paid for two self-improvement
# rounds no matter how well it did. A run returning 72% cumulative still scored negative.
# These are floors for "worth showing", not for "excellent".
MIN_OBJECTIVE_SHARPE = 0.3
MAX_OBJECTIVE_DRAWDOWN = -0.35
GENERATED_SIGNAL_METRIC = "generated_signal"
BUY_SIGNAL_VALUE = 1.0
SELL_SIGNAL_VALUE = -1.0
HOLD_SIGNAL_VALUE = 0.0
EXECUTION_AUDIT_TAIL_LIMIT = 20
AI_BACKTEST_WORKERS_ENV = "AI_BACKTEST_WORKERS"
DEFAULT_BACKTEST_WORKERS = 4
PRICE_FIELD_NAMES = frozenset(
    {"date", "ticker", "name", "market", "open", "high", "low", "close", "volume"}
)
ALLOWED_RUNTIME_IMPORTS = frozenset({"datetime", "math", "statistics"})
DEFAULT_BACKTEST_PRICE_ROWS: tuple[dict[str, object], ...] = (
    {
        "date": "2026-01-02",
        "ticker": DEFAULT_FIXTURE_TICKER,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.0,
        "volume": DEFAULT_FIXTURE_VOLUME,
        "rsi": 25.0,
    },
    {
        "date": "2026-01-03",
        "ticker": DEFAULT_FIXTURE_TICKER,
        "open": 102.0,
        "high": 103.0,
        "low": 101.0,
        "close": 102.0,
        "volume": DEFAULT_FIXTURE_VOLUME * 1.6,
        "rsi": 50.0,
    },
    {
        "date": "2026-01-04",
        "ticker": DEFAULT_FIXTURE_TICKER,
        "open": 101.0,
        "high": 102.0,
        "low": 100.0,
        "close": 101.0,
        "volume": DEFAULT_FIXTURE_VOLUME,
        "rsi": 75.0,
    },
    {
        "date": "2026-01-05",
        "ticker": DEFAULT_FIXTURE_TICKER,
        "open": 105.0,
        "high": 106.0,
        "low": 104.0,
        "close": 105.0,
        "volume": DEFAULT_FIXTURE_VOLUME,
        "rsi": 50.0,
    },
)
SIGNAL_METRIC_VALUES = {
    "BUY": BUY_SIGNAL_VALUE,
    "SELL": SELL_SIGNAL_VALUE,
    "HOLD": HOLD_SIGNAL_VALUE,
}


def summarize_backtest(backtest: Mapping[str, Any]) -> dict[str, Any]:
    selected = backtest.get("selected_candidate") or {}
    selected_id = selected.get("candidate_id")
    return {
        "selected_candidate_id": selected_id,
        "metrics": selected.get("metrics") or {},
        "engine_summary": backtest.get("engine_summary")
        or (backtest.get("engine_summaries_by_candidate") or {}).get(selected_id, {}),
        "objective_score": (backtest.get("objective_scores_by_candidate") or {}).get(selected_id),
    }


def _ensure_backtest_module_source_path() -> None:
    package_root = BACKTEST_MODULE_SOURCE_ROOT / "backtest_module"
    if not package_root.is_dir():
        return
    source_path = str(BACKTEST_MODULE_SOURCE_ROOT)
    if source_path not in sys.path:
        sys.path.insert(0, source_path)


try:
    from backtest_module import (
        Condition as EngineCondition,
        ConditionOperator as EngineConditionOperator,
        PositionSizing as EnginePositionSizing,
        RiskControls as EngineRiskControls,
        StrategySpec as EngineStrategySpec,
    )
    from backtest_module.backtest import (
        BacktestRunConfig as EngineBacktestRunConfig,
        OhlcvBar as EngineOhlcvBar,
        TalibIndicatorConfig as EngineTalibIndicatorConfig,
        run_backtest as run_engine_backtest,
    )
    from backtest_module.performance import (
        QUANTSTATS_REQUIRED_MESSAGE,
        quantstats_sharpe_from_returns,
        returns_from_equity_curve,
    )
except ImportError:
    _ensure_backtest_module_source_path()
    sys.modules.pop("backtest_module", None)
    from backtest_module import (
        Condition as EngineCondition,
        ConditionOperator as EngineConditionOperator,
        PositionSizing as EnginePositionSizing,
        RiskControls as EngineRiskControls,
        StrategySpec as EngineStrategySpec,
    )
    from backtest_module.backtest import (
        BacktestRunConfig as EngineBacktestRunConfig,
        OhlcvBar as EngineOhlcvBar,
        TalibIndicatorConfig as EngineTalibIndicatorConfig,
        run_backtest as run_engine_backtest,
    )
    from backtest_module.performance import (
        QUANTSTATS_REQUIRED_MESSAGE,
        quantstats_sharpe_from_returns,
        returns_from_equity_curve,
    )


class GeneratedSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str = Field(min_length=1)
    ticker: str | None = None
    action: str = Field(pattern="^(BUY|SELL|HOLD)$")
    price: float = Field(gt=0.0)


@dataclass(frozen=True)
class _CandidateEvaluation:
    candidate: CodeCandidate
    engine_summary: dict[str, Any] | None = None
    equity_curve: list[BacktestEquityPoint] | None = None
    objective_score: float | None = None
    quantstats_dependency_error: bool = False


_WORKER_STRATEGY: AIStrategySpec | None = None
_WORKER_PRICE_ROWS: Sequence[Mapping[str, Any]] | None = None


def _initialize_candidate_worker(
    strategy_payload: Mapping[str, Any],
    price_rows: Sequence[Mapping[str, Any]],
) -> None:
    global _WORKER_STRATEGY, _WORKER_PRICE_ROWS
    _WORKER_STRATEGY = AIStrategySpec.model_validate(strategy_payload)
    _WORKER_PRICE_ROWS = price_rows


def _evaluate_candidate_worker(candidate_payload: Mapping[str, Any]) -> _CandidateEvaluation:
    if _WORKER_STRATEGY is None or _WORKER_PRICE_ROWS is None:
        raise RuntimeError("candidate worker was not initialized")
    return _evaluate_candidate(
        _WORKER_STRATEGY,
        CodeCandidate.model_validate(candidate_payload),
        _WORKER_PRICE_ROWS,
    )


class _CandidateBacktestSession:
    """Reuse one worker pool and completed candidate results across improvement rounds."""

    def __init__(
        self,
        strategy: AIStrategySpec,
        price_rows: Sequence[Mapping[str, Any]],
    ) -> None:
        self.strategy = strategy
        self.price_rows = price_rows
        self._cache: dict[tuple[str, str, bool], _CandidateEvaluation] = {}
        self._executor: ProcessPoolExecutor | None = None

    def __enter__(self) -> _CandidateBacktestSession:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._executor = None

    def evaluate(self, candidates: Sequence[CodeCandidate]) -> list[_CandidateEvaluation]:
        missing: list[CodeCandidate] = []
        for candidate in candidates:
            key = _candidate_cache_key(candidate)
            if key not in self._cache:
                missing.append(candidate)

        if missing:
            worker_count = _candidate_worker_count(len(missing))
            if worker_count == 1:
                evaluations = [
                    _evaluate_candidate(self.strategy, candidate, self.price_rows)
                    for candidate in missing
                ]
            else:
                if self._executor is None:
                    self._executor = ProcessPoolExecutor(
                        max_workers=worker_count,
                        mp_context=get_context("spawn"),
                        initializer=_initialize_candidate_worker,
                        initargs=(self.strategy.model_dump(mode="python"), self.price_rows),
                    )
                evaluations = list(
                    self._executor.map(
                        _evaluate_candidate_worker,
                        [candidate.model_dump(mode="python") for candidate in missing],
                        chunksize=1,
                    )
                )
            for candidate, evaluation in zip(missing, evaluations, strict=True):
                self._cache[_candidate_cache_key(candidate)] = evaluation

        return [self._cache[_candidate_cache_key(candidate)] for candidate in candidates]


def _candidate_worker_count(candidate_count: int) -> int:
    configured = os.getenv(AI_BACKTEST_WORKERS_ENV)
    try:
        requested = int(configured) if configured is not None else DEFAULT_BACKTEST_WORKERS
    except ValueError:
        requested = DEFAULT_BACKTEST_WORKERS
    available_cpus = os.cpu_count() or 1
    return max(1, min(candidate_count, requested, available_cpus))


def _candidate_cache_key(candidate: CodeCandidate) -> tuple[str, str, bool]:
    code_hash = sha256(candidate.code.encode("utf-8")).hexdigest()
    return candidate.candidate_id, code_hash, candidate.validation_ok


def _evaluate_candidate(
    strategy_a: AIStrategySpec,
    candidate: CodeCandidate,
    rows: Sequence[Mapping[str, Any]],
) -> _CandidateEvaluation:
    if not candidate.validation_ok:
        return _CandidateEvaluation(candidate=candidate)
    try:
        engine_result = _run_candidate_backtest(strategy_a, candidate, rows)
    except Exception as exc:
        if _is_quantstats_dependency_error(exc):
            return _CandidateEvaluation(candidate=candidate, quantstats_dependency_error=True)
        return _CandidateEvaluation(
            candidate=candidate.model_copy(
                update={
                    "validation_ok": False,
                    "violations": [*candidate.violations, f"engine backtest failed: {exc}"],
                }
            )
        )

    metrics = _metrics_from_engine_result(engine_result)
    enriched_candidate = candidate.model_copy(update={"metrics": metrics})
    engine_summary = dict(engine_result.summary)
    engine_summary["buy_signal_count"] = _signal_action_count(engine_result, "BUY")
    engine_summary["sell_signal_count"] = _signal_action_count(engine_result, "SELL")
    execution_audit = _execution_audit(engine_result)
    engine_summary["execution_audit"] = execution_audit
    available_ticker_count = _available_ticker_count(rows)
    requested_max_positions = _requested_max_positions(strategy_a)
    applied_max_positions = _applied_max_positions(strategy_a, available_ticker_count)
    engine_summary["ai_backtest_context"] = {
        "available_ticker_count": available_ticker_count,
        "requested_max_positions": requested_max_positions,
        "applied_max_positions": applied_max_positions,
        "exposure_normalized": applied_max_positions != requested_max_positions,
    }
    engine_summary["effective_trade_count"] = max(
        _summary_float_default(engine_summary, "trade_count", 0.0),
        float(execution_audit["executed_buy_count"]),
    )
    return _CandidateEvaluation(
        candidate=enriched_candidate,
        engine_summary=engine_summary,
        equity_curve=_public_equity_curve(engine_result),
        objective_score=_objective_score(metrics, engine_summary, rows),
    )


def run_candidate_backtest(
    strategy_a: AIStrategySpec,
    candidates: list[CodeCandidate],
    *,
    price_rows: Sequence[Mapping[str, Any]] | None = None,
    feature_coverage: Mapping[str, Any] | None = None,
    fallback_reasons: Sequence[str] | None = None,
    _session: _CandidateBacktestSession | None = None,
) -> CandidateBacktestResult:
    if not candidates:
        raise ValueError("at least one candidate is required")

    rows = _session.price_rows if _session is not None else _price_rows(price_rows)
    owns_session = _session is None
    session = _session or _CandidateBacktestSession(strategy_a, rows)
    enriched_candidates: list[CodeCandidate] = []
    engine_summaries_by_candidate: dict[str, dict[str, Any]] = {}
    equity_curves_by_candidate: dict[str, list[BacktestEquityPoint]] = {}
    objective_scores_by_candidate: dict[str, float] = {}

    try:
        evaluations = session.evaluate(candidates)
        for evaluation in evaluations:
            if evaluation.quantstats_dependency_error:
                raise ModuleNotFoundError(QUANTSTATS_REQUIRED_MESSAGE)
            candidate = evaluation.candidate
            enriched_candidates.append(candidate)
            if (
                not candidate.validation_ok
                or candidate.metrics is None
                or evaluation.engine_summary is None
                or evaluation.equity_curve is None
                or evaluation.objective_score is None
            ):
                continue
            engine_summaries_by_candidate[candidate.candidate_id] = evaluation.engine_summary
            equity_curves_by_candidate[candidate.candidate_id] = evaluation.equity_curve
            objective_scores_by_candidate[candidate.candidate_id] = evaluation.objective_score
    finally:
        if owns_session:
            session.close()

    valid_candidates = [
        candidate
        for candidate in enriched_candidates
        if candidate.validation_ok and candidate.metrics is not None
    ]
    if not valid_candidates:
        if any(
            QUANTSTATS_REQUIRED_MESSAGE in violation
            for candidate in enriched_candidates
            for violation in getattr(candidate, "violations", [])
        ):
            raise ModuleNotFoundError(QUANTSTATS_REQUIRED_MESSAGE)
        raise ValueError("at least one candidate must pass validation and engine backtest")

    selected = max(
        valid_candidates,
        key=lambda candidate: (
            objective_scores_by_candidate.get(candidate.candidate_id, float("-inf")),
            *_candidate_rank(candidate),
        ),
    )

    return CandidateBacktestResult(
        strategy_a=strategy_a,
        candidates=enriched_candidates,
        selected_candidate=selected,
        equity_curve=equity_curves_by_candidate[selected.candidate_id],
        engine_summary=engine_summaries_by_candidate[selected.candidate_id],
        engine_summaries_by_candidate=engine_summaries_by_candidate,
        objective_scores_by_candidate=objective_scores_by_candidate,
        backtest_payload=_backtest_payload(strategy_a, rows),
        feature_coverage=dict(feature_coverage or {}),
        fallback_reasons=list(fallback_reasons or ()),
    )


def backtest_node(state: dict[str, Any]) -> dict[str, Any]:
    strategy_a = AIStrategySpec.model_validate(state["strategy_spec"])
    candidates = [
        CodeCandidate.model_validate(candidate)
        for candidate in state["backtest_code"]["candidates"]
    ]
    price_rows = state["price_rows"] if "price_rows" in state else state.get("market_prices")
    rows = _price_rows(price_rows)
    ticker_count = _available_ticker_count(rows)
    max_positions = _applied_max_positions(strategy_a, ticker_count)

    # Backtesting is pure computation with no provider stream behind it, so without
    # these the live view has nothing to show for the minutes this node runs.
    report_activity(
        "step",
        label=f"백테스트 실행 · 후보 {len(candidates)}개",
        detail=f"종목 {ticker_count}개 · 최대 보유 {max_positions}종목",
    )
    if ticker_count < MIN_RELIABLE_TICKERS:
        # A backtest over a handful of names measures those names, not the strategy - the
        # result rides on their idiosyncratic history and does not generalise. Say so
        # rather than presenting a two-stock curve as if it validated the rule.
        report_activity(
            "step",
            label="표본 부족 경고",
            detail=(
                f"조건에 맞는 종목이 {ticker_count}개뿐이라 백테스트 신뢰도가 낮습니다. "
                "결과는 이 종목들의 과거에 크게 좌우됩니다."
            ),
        )
    with _CandidateBacktestSession(strategy_a, rows) as session:
        result = run_candidate_backtest(
            strategy_a,
            candidates,
            price_rows=rows,
            feature_coverage=state.get("backtest_code", {}).get("feature_mapping", {}),
            fallback_reasons=state.get("backtest_code", {}).get("fallback_reasons", []),
            _session=session,
        )
        report_activity(
            "step",
            label="백테스트 1차 완료",
            detail=_selected_candidate_detail(result),
        )
        all_candidates = candidates
        fallback_reasons = list(state.get("backtest_code", {}).get("fallback_reasons", []))
        for iteration in range(1, 3):
            if _passes_objective_floor(result):
                break
            improved = generate_self_improvement_candidates(
                strategy_a,
                state.get("backtest_code", {}).get("code_plan", {}),
                start_index=len(all_candidates) + 1,
                iteration=iteration,
                max_positions=max_positions,
            )
            all_candidates = [*all_candidates, *improved]
            fallback_reasons.append(
                f"self-improvement iteration {iteration}: generated {len(improved)} threshold-adjusted candidates"
            )
            report_activity(
                "step",
                label=f"목표 미달 · 자가개선 {iteration}차",
                detail=f"신규 임계값 조정 후보 {len(improved)}개 평가 (누적 {len(all_candidates)}개)",
            )
            next_result = run_candidate_backtest(
                strategy_a,
                all_candidates,
                price_rows=rows,
                feature_coverage=state.get("backtest_code", {}).get("feature_mapping", {}),
                fallback_reasons=fallback_reasons,
                _session=session,
            )
            improved_score = _selected_objective_score(next_result)
            if improved_score > _selected_objective_score(result):
                result = next_result
                report_activity(
                    "step",
                    label=f"자가개선 {iteration}차 완료",
                    detail=_selected_candidate_detail(result),
                )
            else:
                # No improvement from another 36 variants means more of them will not help
                # either - they just add rules fitted to the same noise. Stop rather than
                # grind through a third round that can only overfit further.
                report_activity(
                    "step",
                    label=f"자가개선 {iteration}차 · 개선 없음",
                    detail="추가 변형이 성과를 높이지 못해 최적화를 중단합니다.",
                )
                break
    return {"backtest": result.model_dump()}


def _selected_candidate_detail(result: CandidateBacktestResult) -> str:
    parts = [f"선택 후보 {result.selected_candidate.candidate_id}"]
    score = _selected_objective_score(result)
    if math.isfinite(score):
        parts.append(f"목표점수 {score:.3f}")
    if result.equity_curve:
        parts.append(f"누적수익 {result.equity_curve[-1].cumulative_return:.2%}")
    return " · ".join(parts)


def _run_candidate_backtest(
    strategy: AIStrategySpec,
    candidate: CodeCandidate,
    price_rows: Sequence[Mapping[str, Any]],
):
    generated_signals = _execute_candidate_code(candidate, price_rows)
    ohlcv_rows, base_metric_rows = _engine_market_rows(price_rows)
    metric_rows = _merge_generated_signals(base_metric_rows, generated_signals)
    engine_spec = _engine_strategy_spec(
        strategy,
        candidate,
        available_ticker_count=_available_ticker_count(price_rows),
    )
    return run_engine_backtest(
        engine_spec,
        ohlcv_rows=ohlcv_rows,
        metric_rows=metric_rows,
        config=EngineBacktestRunConfig(
            initial_capital=DEFAULT_INITIAL_CAPITAL,
            write_outputs=False,
            talib=EngineTalibIndicatorConfig(enabled=False, mode="none"),
        ),
    )


def _execute_candidate_code(
    candidate: CodeCandidate, price_rows: Sequence[Mapping[str, Any]]
) -> list[GeneratedSignal]:
    validation = validate_backtest_code(candidate.code)
    validation.raise_for_violations()

    namespace: dict[str, Any] = {}
    exec(candidate.code, {"__builtins__": _safe_builtins()}, namespace)
    build_signals = namespace.get("build_signals")
    if not callable(build_signals):
        raise ValueError(f"candidate {candidate.candidate_id} build_signals is not callable")

    raw_signals = build_signals([dict(row) for row in price_rows])
    if not isinstance(raw_signals, Sequence):
        raise ValueError(f"candidate {candidate.candidate_id} must return a signal sequence")
    return [_generated_signal_from_raw(signal) for signal in raw_signals]


def _generated_signal_from_raw(signal: object) -> GeneratedSignal:
    if isinstance(signal, Mapping):
        normalized = dict(signal)
        action = normalized.get("action")
        if isinstance(action, str):
            normalized["action"] = action.upper()
        ticker = normalized.get("ticker")
        if ticker is not None:
            normalized["ticker"] = str(ticker).zfill(6)
        return GeneratedSignal.model_validate(normalized)
    return GeneratedSignal.model_validate(signal)


def _engine_market_rows(
    price_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[Any], list[dict[str, object]]]:
    ohlcv_rows: list[Any] = []
    metric_rows: list[dict[str, object]] = []
    tickers: set[str] = set()

    for raw in price_rows:
        if "date" not in raw or "close" not in raw:
            raise ValueError("price rows must include date and close")
        row_date = date.fromisoformat(str(raw["date"]))
        ticker = str(raw.get("ticker") or DEFAULT_FIXTURE_TICKER).zfill(6)
        tickers.add(ticker)
        close = _finite_float(raw["close"], "close")
        open_price = _finite_float(raw.get("open", close), "open")
        high = _finite_float(raw.get("high", max(open_price, close)), "high")
        low = _finite_float(raw.get("low", min(open_price, close)), "low")
        volume = _finite_float(raw.get("volume", DEFAULT_FIXTURE_VOLUME), "volume")
        ohlcv_rows.append(
            EngineOhlcvBar(
                date=row_date,
                ticker=ticker,
                name=str(raw.get("name") or ""),
                market=str(raw.get("market") or DEFAULT_FIXTURE_MARKET),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
        metric_row: dict[str, object] = {"date": row_date.isoformat(), "ticker": ticker}
        for key, value in raw.items():
            if str(key) in PRICE_FIELD_NAMES or not _is_numeric_metric(value):
                continue
            metric_row[str(key)] = float(value)
        metric_rows.append(metric_row)

    return ohlcv_rows, metric_rows


def _merge_generated_signals(
    metric_rows: list[dict[str, object]], generated_signals: list[GeneratedSignal]
) -> list[dict[str, object]]:
    metrics_by_key = {(str(row["date"]), str(row["ticker"]).zfill(6)): row for row in metric_rows}
    tickers_by_date: dict[str, list[str]] = {}
    for row in metric_rows:
        tickers_by_date.setdefault(str(row["date"]), []).append(str(row["ticker"]).zfill(6))
    for signal in generated_signals:
        if signal.ticker is None:
            tickers_for_date = tickers_by_date.get(signal.date, [])
            if not tickers_for_date:
                raise ValueError(
                    f"generated signal date {signal.date} is not present in price rows"
                )
            if len(tickers_for_date) > 1:
                raise ValueError(f"generated signal date {signal.date} is ambiguous without ticker")
            for ticker in tickers_for_date:
                metrics_by_key[(signal.date, ticker)][GENERATED_SIGNAL_METRIC] = (
                    SIGNAL_METRIC_VALUES[signal.action]
                )
            continue
        key = (signal.date, signal.ticker)
        if key not in metrics_by_key:
            raise ValueError(
                f"generated signal {signal.date}/{signal.ticker} is not present in price rows"
            )
        metrics_by_key[key][GENERATED_SIGNAL_METRIC] = SIGNAL_METRIC_VALUES[signal.action]
    for row in metric_rows:
        row.setdefault(GENERATED_SIGNAL_METRIC, HOLD_SIGNAL_VALUE)
    return metric_rows


def _engine_strategy_spec(
    strategy: AIStrategySpec,
    candidate: CodeCandidate,
    *,
    available_ticker_count: int | None = None,
):
    return EngineStrategySpec(
        strategy_id=f"{strategy.strategy_id}_{candidate.candidate_id.lower()}",
        strategy_name=f"{strategy.name} {candidate.candidate_id}",
        description="Generated candidate signals executed by backtest_module.",
        entry_rules=[
            EngineCondition(
                left=GENERATED_SIGNAL_METRIC,
                operator=EngineConditionOperator.EQ,
                right=BUY_SIGNAL_VALUE,
                description="generated BUY signal",
            )
        ],
        exit_rules=[
            EngineCondition(
                left=GENERATED_SIGNAL_METRIC,
                operator=EngineConditionOperator.EQ,
                right=SELL_SIGNAL_VALUE,
                description="generated SELL signal",
            )
        ],
        position_sizing=_engine_position_sizing(
            strategy,
            available_ticker_count=available_ticker_count,
        ),
        risk_controls=_engine_risk_controls(strategy),
    )


def _engine_position_sizing(
    strategy: AIStrategySpec,
    *,
    available_ticker_count: int | None = None,
):
    applied_max_positions = _applied_max_positions(strategy, available_ticker_count)
    return EnginePositionSizing(max_positions=applied_max_positions)


def _engine_risk_controls(strategy: AIStrategySpec):
    raw = strategy.risk_constraints
    controls = EngineRiskControls()
    stop_loss_pct = _optional_positive_float(
        raw.get("stop_loss_pct"), "stop_loss_pct", upper_bound=1.0
    )
    take_profit_pct = _optional_positive_float(raw.get("take_profit_pct"), "take_profit_pct")
    max_position_pct = _optional_positive_float(
        raw.get("max_position_pct"), "max_position_pct", upper_bound=1.0
    )
    if stop_loss_pct is not None:
        controls = controls.model_copy(update={"stop_loss_pct": stop_loss_pct})
    if take_profit_pct is not None:
        controls = controls.model_copy(update={"take_profit_pct": take_profit_pct})
    if max_position_pct is not None:
        controls = controls.model_copy(update={"max_single_position_pct": max_position_pct})
    return controls


def _requested_max_positions(strategy: AIStrategySpec) -> int:
    max_position_pct = _optional_positive_float(
        strategy.risk_constraints.get("max_position_pct"),
        "max_position_pct",
        upper_bound=1.0,
    )
    return _shared_requested_max_positions(max_position_pct)


def _applied_max_positions(
    strategy: AIStrategySpec, available_ticker_count: int | None = None
) -> int:
    max_position_pct = _optional_positive_float(
        strategy.risk_constraints.get("max_position_pct"),
        "max_position_pct",
        upper_bound=1.0,
    )
    return _shared_applied_max_positions(max_position_pct, available_ticker_count)


def _available_ticker_count(price_rows: Sequence[Mapping[str, Any]]) -> int:
    return _shared_available_ticker_count(price_rows)


def _execution_audit(engine_result: Any) -> dict[str, Any]:
    events = [event.as_dict() for event in getattr(engine_result, "order_audit", [])]
    executed_buy_count = sum(
        1
        for event in events
        if str(event.get("status")) == "executed" and str(event.get("side")) == "buy"
    )
    executed_sell_count = sum(
        1
        for event in events
        if str(event.get("status")) == "executed" and str(event.get("side")) == "sell"
    )
    blocked_count = sum(
        1
        for event in events
        if str(event.get("status")).startswith("skipped")
        or str(event.get("status")) == "ignored_missing_position"
    )
    unfilled_end_count = sum(1 for event in events if str(event.get("status")) == "unfilled_end")
    return {
        "submitted_count": sum(1 for event in events if str(event.get("status")) == "submitted"),
        "executed_buy_count": executed_buy_count,
        "executed_sell_count": executed_sell_count,
        "blocked_count": blocked_count,
        "unfilled_end_count": unfilled_end_count,
        "completed_trade_count": len(getattr(engine_result, "trades", [])),
        "has_real_fills": executed_buy_count > 0 or executed_sell_count > 0,
        "recent_events": events[-EXECUTION_AUDIT_TAIL_LIMIT:],
    }


def _metrics_from_engine_result(engine_result) -> BacktestMetrics:
    summary = engine_result.summary
    metric_warnings = _summary_warning_list(summary)
    daily_returns = returns_from_equity_curve(engine_result.equity_curve)
    sharpe = _summary_float_default(
        summary, "sharpe", _summary_float_default(summary, "daily_sharpe_like", 0.0)
    )
    in_sample_sharpe, out_sample_sharpe = _split_sharpes(daily_returns, metric_warnings)
    degradation = _degradation(in_sample_sharpe, out_sample_sharpe)
    return BacktestMetrics(
        sharpe_ratio=round(sharpe, METRIC_ROUND_DIGITS),
        max_drawdown=round(_summary_float(summary, "max_drawdown"), METRIC_ROUND_DIGITS),
        win_rate=round(_summary_float(summary, "win_rate"), METRIC_ROUND_DIGITS),
        total_return=round(
            _summary_float_default(
                summary, "total_return", _summary_float_default(summary, "period_return", 0.0)
            ),
            METRIC_ROUND_DIGITS,
        ),
        in_sample_sharpe=round(in_sample_sharpe, METRIC_ROUND_DIGITS),
        out_sample_sharpe=round(out_sample_sharpe, METRIC_ROUND_DIGITS),
        degradation=round(degradation, METRIC_ROUND_DIGITS),
    )


def _public_equity_curve(engine_result) -> list[BacktestEquityPoint]:
    summary = engine_result.summary
    initial_capital = _summary_float(summary, "initial_capital")
    if initial_capital == 0:
        return []

    sampled_points = _sample_points(engine_result.equity_curve, PUBLIC_EQUITY_CURVE_POINTS)
    return [
        BacktestEquityPoint(
            date=str(point.date),
            cumulative_return=round(
                (float(point.total_equity) / initial_capital) - 1,
                METRIC_ROUND_DIGITS,
            ),
        )
        for point in sampled_points
    ]


def _sample_points(points: Sequence[Any], max_points: int) -> list[Any]:
    if len(points) <= max_points:
        return list(points)

    last_index = len(points) - 1
    step = last_index / (max_points - 1)
    indices = sorted({round(index * step) for index in range(max_points)})
    if indices[0] != 0:
        indices.insert(0, 0)
    if indices[-1] != last_index:
        indices.append(last_index)
    return [points[index] for index in indices]


def _split_sharpes(
    daily_returns: list[float], metric_warnings: list[dict[str, str]]
) -> tuple[float, float]:
    if len(daily_returns) < MIN_RETURNS_FOR_SPLIT:
        full_sample = _sharpe_like(
            daily_returns, metric_name="full_sample_sharpe", metric_warnings=metric_warnings
        )
        return full_sample, full_sample
    split_index = max(1, int(len(daily_returns) * BACKTEST_SPLIT_FRACTION))
    return (
        _sharpe_like(
            daily_returns[:split_index],
            metric_name="in_sample_sharpe",
            metric_warnings=metric_warnings,
        ),
        _sharpe_like(
            daily_returns[split_index:],
            metric_name="out_sample_sharpe",
            metric_warnings=metric_warnings,
        ),
    )


def _sharpe_like(
    daily_returns: list[float],
    *,
    metric_name: str = "sharpe",
    metric_warnings: list[dict[str, str]] | None = None,
) -> float:
    return quantstats_sharpe_from_returns(
        daily_returns,
        metric_name=metric_name,
        metric_warnings=metric_warnings,
    )


def _degradation(in_sample_sharpe: float, out_sample_sharpe: float) -> float:
    if in_sample_sharpe == 0:
        return 0.0
    return max(0.0, (in_sample_sharpe - out_sample_sharpe) / abs(in_sample_sharpe))


def _candidate_rank(candidate: CodeCandidate) -> tuple[float, float, float]:
    metrics = _candidate_metrics(candidate)
    return (metrics.sharpe_ratio, metrics.total_return, metrics.max_drawdown)


def _candidate_metrics(candidate: CodeCandidate) -> BacktestMetrics:
    if candidate.metrics is None:
        raise ValueError(f"candidate {candidate.candidate_id} has no backtest metrics")
    return candidate.metrics


def _signal_action_count(engine_result: Any, action: str) -> int:
    return sum(
        1
        for signal in getattr(engine_result, "signals", [])
        if str(getattr(signal, "action", "")).upper().endswith(action)
    )


def _passes_objective_floor(result: CandidateBacktestResult) -> bool:
    metrics = _candidate_metrics(result.selected_candidate)
    trade_count = _summary_float_default(result.engine_summary, "effective_trade_count", 0.0)
    benchmark_return = _summary_float_default(result.backtest_payload, "benchmark_return", 0.0)
    return (
        trade_count >= MIN_OBJECTIVE_TRADES
        and metrics.sharpe_ratio >= MIN_OBJECTIVE_SHARPE
        and metrics.max_drawdown >= MAX_OBJECTIVE_DRAWDOWN
        and metrics.total_return > benchmark_return
    )


def _selected_objective_score(result: CandidateBacktestResult) -> float:
    return result.objective_scores_by_candidate.get(
        result.selected_candidate.candidate_id, float("-inf")
    )


def _objective_score(
    metrics: BacktestMetrics,
    engine_summary: Mapping[str, Any],
    price_rows: Sequence[Mapping[str, Any]],
) -> float:
    trade_count = _summary_float_default(engine_summary, "effective_trade_count", 0.0)
    benchmark_return = _benchmark_return(price_rows)
    calmar = _calmar_ratio(metrics.total_return, metrics.max_drawdown)
    profit_factor = _profit_factor(engine_summary)
    turnover_penalty = min(1.0, trade_count / max(1.0, len(price_rows)))
    # Selection is driven by out-of-sample performance, not the full-period Sharpe.
    # With dozens of threshold variants scored on the same history, the highest
    # full-period Sharpe is usually the one that best fit the noise - it proves nothing
    # about the half of the data it was not chosen on. Leading with out_sample_sharpe,
    # and penalising the in-sample-to-out-sample drop far more heavily, makes the winner
    # the candidate that generalised rather than the one that memorised.
    score = (
        0.70 * metrics.out_sample_sharpe
        + 0.30 * metrics.sharpe_ratio
        + 0.05 * calmar
        + 0.03 * profit_factor
        + 0.02 * metrics.total_return
        - 0.08 * turnover_penalty
        - 0.30 * metrics.degradation
    )
    if trade_count < MIN_OBJECTIVE_TRADES:
        score -= (MIN_OBJECTIVE_TRADES - trade_count) * 0.05
    if metrics.max_drawdown < MAX_OBJECTIVE_DRAWDOWN:
        # Was 2x, which let a single deep drawdown swamp every other term and drove the
        # score negative for otherwise strong candidates.
        score -= abs(metrics.max_drawdown - MAX_OBJECTIVE_DRAWDOWN)
    if metrics.sharpe_ratio < MIN_OBJECTIVE_SHARPE:
        score -= (MIN_OBJECTIVE_SHARPE - metrics.sharpe_ratio) * 0.25
    if metrics.total_return <= benchmark_return:
        # Trailing the benchmark should cost something, but the raw return gap is on a
        # different scale from the Sharpe term that leads this score - a 50-point gap
        # used to dominate everything else. Cap what it can take away.
        score -= min(abs(benchmark_return - metrics.total_return), 0.5) + 0.05
    return round(score, METRIC_ROUND_DIGITS)


def _calmar_ratio(total_return: float, max_drawdown: float) -> float:
    drawdown = abs(max_drawdown)
    if drawdown == 0:
        return 0.0
    return total_return / drawdown


def _profit_factor(engine_summary: Mapping[str, Any]) -> float:
    win_rate = _summary_float_default(
        engine_summary,
        "trade_win_rate",
        _summary_float_default(engine_summary, "win_rate", 0.0),
    )
    if win_rate <= 0:
        return 0.0
    if win_rate >= 1:
        return 2.0
    return min(3.0, win_rate / max(1.0 - win_rate, 0.01))


def _benchmark_return(price_rows: Sequence[Mapping[str, Any]]) -> float:
    if len(price_rows) < 2:
        return 0.0
    rows_by_ticker: dict[str, list[Mapping[str, Any]]] = {}
    for row in price_rows:
        ticker = str(row.get("ticker") or DEFAULT_FIXTURE_TICKER).zfill(6)
        rows_by_ticker.setdefault(ticker, []).append(row)
    returns: list[float] = []
    for ticker, rows in rows_by_ticker.items():
        sorted_rows = sorted(rows, key=lambda item: str(item["date"]))
        if len(sorted_rows) < 2:
            continue
        first = _finite_float(sorted_rows[0]["close"], f"{ticker}_benchmark_first_close")
        last = _finite_float(sorted_rows[-1]["close"], f"{ticker}_benchmark_last_close")
        if first:
            returns.append(last / first - 1)
    if not returns:
        return 0.0
    return sum(returns) / len(returns)


def _backtest_payload(
    strategy: AIStrategySpec, rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    tickers = sorted({str(row.get("ticker") or DEFAULT_FIXTURE_TICKER).zfill(6) for row in rows})
    payload = {
        "strategy_id": strategy.strategy_id,
        "market": strategy.market,
        "tickers": tickers,
        "price_rows": len(rows),
        "first_date": str(rows[0].get("date")) if rows else None,
        "last_date": str(rows[-1].get("date")) if rows else None,
        "benchmark_return": round(_benchmark_return(rows), METRIC_ROUND_DIGITS),
    }
    fingerprint = repr(sorted(payload.items())).encode("utf-8")
    return {**payload, "payload_hash": sha256(fingerprint).hexdigest()[:16]}


def _price_rows(
    rows: Sequence[Mapping[str, Any]] | None,
) -> Sequence[Mapping[str, Any]]:
    return rows if rows is not None else DEFAULT_BACKTEST_PRICE_ROWS


def _safe_builtins() -> dict[str, Any]:
    return {
        "__import__": _safe_import,
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "float": float,
        "int": int,
        "isinstance": isinstance,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "range": range,
        "round": round,
        "sorted": sorted,
        "sum": sum,
        "zip": zip,
    }


def _safe_import(
    name: str,
    globals_: Mapping[str, Any] | None = None,
    locals_: Mapping[str, Any] | None = None,
    fromlist: Sequence[str] = (),
    level: int = 0,
) -> Any:
    if level != 0 or name not in ALLOWED_RUNTIME_IMPORTS:
        raise ImportError(f"import '{name}' is not allowed in generated backtest code")
    return __import__(name, globals_, locals_, fromlist, level)


def _finite_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{field_name} must be finite")
    return parsed


def _optional_positive_float(
    value: Any, field_name: str, *, upper_bound: float | None = None
) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    parsed = _finite_float(value, field_name)
    if parsed <= 0:
        raise ValueError(f"{field_name} must be positive")
    if upper_bound is not None and parsed > upper_bound:
        raise ValueError(f"{field_name} must be <= {upper_bound}")
    return parsed


def _summary_float(summary: Mapping[str, Any], key: str) -> float:
    if key not in summary:
        raise ValueError(f"engine summary missing {key}")
    return _finite_float(summary[key], key)


def _summary_float_default(summary: Mapping[str, Any], key: str, default: float) -> float:
    if key not in summary:
        return default
    value = summary[key]
    if value in (None, ""):
        return default
    try:
        return _finite_float(value, key)
    except (TypeError, ValueError):
        return default


def _summary_warning_list(summary: Mapping[str, Any]) -> list[dict[str, str]]:
    warnings = summary.get("metric_warnings")
    if isinstance(warnings, list):
        return warnings
    return []


def _is_numeric_metric(value: Any) -> bool:
    if isinstance(value, bool) or value in (None, ""):
        return False
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(parsed)


def _is_quantstats_dependency_error(exc: BaseException) -> bool:
    return isinstance(exc, ModuleNotFoundError) and QUANTSTATS_REQUIRED_MESSAGE in str(exc)
