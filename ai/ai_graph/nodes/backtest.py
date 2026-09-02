from __future__ import annotations

import json
import logging
import math
import os
import pickle
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from multiprocessing import get_all_start_methods, get_context
from pathlib import Path
from tempfile import gettempdir
from threading import Lock
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai_graph.nodes.backtest_code import generate_self_improvement_candidates
from ai_graph.nodes.backtest_features import FEATURE_DEFINITION_VERSION, PreparedFeatureStore
from ai_graph.nodes.position_sizing import (
    available_ticker_count as _shared_available_ticker_count,
)
from ai_graph.nodes.position_sizing import (
    required_max_position_pct,
)
from ai_graph.progress import (
    AnalysisCancelled,
    deadline_remaining_seconds,
    raise_if_cancelled,
    raise_if_past_deadline,
    report_activity,
)
from ai_graph.quant_strategy import AUTOMATIC_TOURNAMENT_PROFILES
from ai_graph.research_eligibility import MISSING_EXECUTION_ASSUMPTION
from ai_graph.schemas import (
    BacktestEquityPoint,
    BacktestMetrics,
    CandidateBacktestResult,
    CodeCandidate,
    WalkForwardFoldSelection,
    WalkForwardPolicyResult,
)
from ai_graph.schemas import StrategySpec as AIStrategySpec
from ai_graph.security.ast_validator import validate_backtest_code
from ai_graph.source_manifest import is_release_profile
from ai_graph.validation_gates import objective_floor_is_enforced, validation_gate_mode

_logger = logging.getLogger(__name__)

BACKTEST_MODULE_SOURCE_ROOT = Path(__file__).resolve().parents[3] / "backtest_module"
DEFAULT_FIXTURE_TICKER = "005930"
DEFAULT_FIXTURE_MARKET = "KRX"
DEFAULT_FIXTURE_VOLUME = 1_000_000.0
DEFAULT_INITIAL_CAPITAL = 1_000_000.0
CANONICAL_ANALYSIS_INITIAL_CAPITAL = 100_000_000.0
METRIC_ROUND_DIGITS = 6
MIN_RETURNS_FOR_SPLIT = 4
PRIMARY_BENCHMARK_LABEL = "공식 KOSPI/KOSDAQ TR"
PRIMARY_BENCHMARK_METHOD = "official_kospi_kosdaq_total_return"
AUXILIARY_BENCHMARK_LABEL = "동일가중 매수-보유 보조 프록시"
AUXILIARY_BENCHMARK_METHOD = "fixed_universe_equal_weight_buy_and_hold"
AUXILIARY_BENCHMARK_WARNING = (
    "공식 KOSPI/KOSDAQ 총수익률(TR) 시계열과 월초 목표 비중이 입력되지 않아 "
    "동일가중 보조 프록시만 계산했습니다. 공식 벤치마크로 해석할 수 없습니다."
)
PRIMARY_BENCHMARK_MISSING_INPUT_REASON = (
    "official KOSPI and KOSDAQ total-return series with target weights were not supplied"
)
PRIMARY_BENCHMARK_SOURCE_UNAVAILABLE_REASON = "official_benchmark_source_unavailable"
OFFICIAL_BENCHMARK_MIN_SESSION_COVERAGE = 0.99
# Legacy graph exports now describe the authoritative primary benchmark contract.
BENCHMARK_LABEL = PRIMARY_BENCHMARK_LABEL
BENCHMARK_METHOD = PRIMARY_BENCHMARK_METHOD
BENCHMARK_WARNING = AUXILIARY_BENCHMARK_WARNING
# Candidates are selected using only the first 70% of the history. The final 30%
# is a hold-out, not a rolling walk-forward validation.
BACKTEST_SPLIT_FRACTION = 0.7
WALK_FORWARD_WARMUP_MONTHS = 1
WALK_FORWARD_TRAIN_MONTHS = 12
WALK_FORWARD_VALIDATION_MONTHS = 3
WALK_FORWARD_EVALUATION_MONTHS = 1
WALK_FORWARD_ROLL_MONTHS = 1
WALK_FORWARD_MIN_VALID_FOLDS = 24
WALK_FORWARD_MIN_UNIQUE_EVALUATION_MONTHS = 24
WALK_FORWARD_MIN_UNIQUE_EVALUATION_SESSIONS = 480
# Kept as an internal spelling for callers that imported the old constant.
WALK_FORWARD_MIN_SESSIONS = WALK_FORWARD_MIN_UNIQUE_EVALUATION_SESSIONS
INSUFFICIENT_WALK_FORWARD_SAMPLE = "INSUFFICIENT_WALK_FORWARD_SAMPLE"
READY_WALK_FORWARD = "READY_WALK_FORWARD"
UNSAFE_WALK_FORWARD_CANDIDATE = "UNSAFE_WALK_FORWARD_CANDIDATE"
# A quarter is short enough to expose regime-specific wins/losses instead of letting a
# ten-year total hide them. A strategy may win by a lot in some blocks, but losing at
# least half of these fixed, non-overlapping blocks is still an automatic failure.
BENCHMARK_EVALUATION_PERIOD_DAYS = 63
MAX_AUTOMATIC_BENCHMARK_LOSS_RATE = 0.50
PUBLIC_EQUITY_CURVE_POINTS = 12
MIN_OBJECTIVE_TRADES = 5
# Below this many matched names, a backtest describes the names, not the strategy, and
# tuning dozens of rule variants against them is fitting noise. Warn rather than pretend.
MIN_RELIABLE_TICKERS = 5
# Performance thresholds remain selection policy only; data reliability is reported
# independently through coverage and walk-forward metadata.
MIN_OBJECTIVE_SHARPE = 0.0
MAX_OBJECTIVE_DRAWDOWN = -0.50
# The winner's in-sample Sharpe, less what an argmax over the same number of skill-free
# candidates would be expected to reach. Zero is the honest floor: below it the result is
# not distinguishable from having tried N things and kept the luckiest one.
MIN_SELECTION_ADJUSTED_SHARPE = 0.0
# Fallbacks for the engine's cost model, used only when a summary does not carry one.
# They mirror backtest_module.models.CostModel's defaults.
DEFAULT_COMMISSION_PCT = 0.00015
DEFAULT_TAX_PCT = 0.0023
DEFAULT_SLIPPAGE_PCT = 0.001
DEFAULT_MAX_POSITIONS_FOR_COST = 10
# Calibrated so the penalty keeps its old magnitude at the turnover candidates actually
# run (measured: 47 trades a year over 10 slots, which is 2.2% of equity in costs, and
# the old saturated penalty was 0.08). What changes is that it no longer has a ceiling,
# so 86 trades a year now scores worse than 24 instead of identically.
TURNOVER_PENALTY_WEIGHT = 3.7
# A candidate trading more than this is not selectable. Same knee the old penalty used,
# kept unchanged so the ceiling is not a number fitted to the experiment that validated
# it. See _within_turnover_cap for the measurement.
MAX_SELECTABLE_ANNUAL_TURNOVER = 24.0
GENERATED_SIGNAL_METRIC = "generated_signal"
BUY_SIGNAL_VALUE = 1.0
SELL_SIGNAL_VALUE = -1.0
HOLD_SIGNAL_VALUE = 0.0
EXECUTION_AUDIT_TAIL_LIMIT = 20
AI_BACKTEST_WORKERS_ENV = "AI_BACKTEST_WORKERS"
DEFAULT_BACKTEST_WORKERS = 2
AI_BACKTEST_ALLOW_SPAWN_PARALLEL_ENV = "AI_BACKTEST_ALLOW_SPAWN_PARALLEL"
AI_BACKTEST_CANDIDATE_TIMEOUT_ENV = "AI_BACKTEST_CANDIDATE_TIMEOUT_SECONDS"
DEFAULT_CANDIDATE_TIMEOUT_SECONDS = 180.0
AI_BACKTEST_WALL_BUDGET_ENV = "AI_BACKTEST_WALL_BUDGET_SECONDS"
DEFAULT_WALL_BUDGET_SECONDS = 540.0
# A small, bounded second refinement lets the search test a different parameter
# neighbourhood while the hold-out remains unavailable to selection.
MAX_SELF_IMPROVEMENT_ROUNDS = 2
SERIAL_EVALUATION_WORK_ITEMS = 250_000
BACKTEST_ENGINE_VERSION = "candidate-engine.v3"
# v6 adds the source-notional capacity claim to persisted summaries. Cached v5
# evaluations predate that claim and could otherwise be reused as if capacity had
# been checked (or not checked) under the new contract.
BACKTEST_CACHE_SCHEMA_VERSION = "candidate-cache.v6"
BACKTEST_CACHE_DIR_ENV = "AI_BACKTEST_CACHE_DIR"
BACKTEST_CACHE_TTL_ENV = "AI_BACKTEST_CACHE_TTL_SECONDS"
BACKTEST_CACHE_MAX_BYTES_ENV = "AI_BACKTEST_CACHE_MAX_BYTES"
DEFAULT_CACHE_TTL_SECONDS = 86_400
DEFAULT_CACHE_MAX_BYTES = 2 * 1024 * 1024 * 1024
# How many stores between disk sweeps. Cleanup no longer runs on construction, so a
# fresh session never scans the whole cache dir; the sweep is amortized across writes.
# ponytail: write-count amortization, switch to a byte counter if TTL eviction must be prompt.
CACHE_CLEANUP_WRITE_INTERVAL = 64
PRICE_FIELD_NAMES = frozenset(
    {
        "date",
        "ticker",
        "name",
        "market",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "raw_open",
        "raw_high",
        "raw_low",
        "raw_close",
        "raw_volume",
        "raw_notional",
    }
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
        "raw_notional": DEFAULT_FIXTURE_VOLUME * 100.0,
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
        "raw_notional": DEFAULT_FIXTURE_VOLUME * 1.6 * 102.0,
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
        "raw_notional": DEFAULT_FIXTURE_VOLUME * 101.0,
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
        "raw_notional": DEFAULT_FIXTURE_VOLUME * 105.0,
        "rsi": 50.0,
    },
)
SIGNAL_METRIC_VALUES = {
    "BUY": BUY_SIGNAL_VALUE,
    "SELL": SELL_SIGNAL_VALUE,
    "HOLD": HOLD_SIGNAL_VALUE,
}

VERBOSE_ENGINE_SUMMARY_KEYS = frozenset(
    {
        "metrics",
        "monthly_returns",
        "drawdown_details",
        "drawdown_series",
        "rolling_volatility",
        "rolling_sharpe",
        "rolling_sortino",
        "rolling_greeks",
        "montecarlo",
        "montecarlo_mean",
        "montecarlo_cagr",
        "montecarlo_drawdown",
        "montecarlo_sharpe",
        "outliers",
        "excluded_tickers",
        "excluded_ticker_jsonb",
        "indicator_report",
        "indicator_report_jsonb",
        "_storage_execution_ledger",
    }
)


def _public_engine_summary(engine_summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in engine_summary.items()
        if key not in VERBOSE_ENGINE_SUMMARY_KEYS
    }


def _performance_method_manifest(
    strategy: AIStrategySpec,
    candidate: CodeCandidate,
    rows: Sequence[Mapping[str, Any]],
    engine_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Emit the provenance required before a run's values become public.

    This intentionally uses facts generated by the engine invocation (input dates,
    actual summary, selected candidate and configured costs), not an API caller's
    labels.  The projection validates this record independently and publishes no
    performance object when it is incomplete.
    """

    dates = sorted(
        {str(row.get("date")) for row in rows if row.get("date") is not None}
    )
    tickers = sorted(
        {str(row.get("ticker")) for row in rows if row.get("ticker") is not None}
    )
    parameters = candidate.parameters
    cost_model = engine_summary.get("cost_model")
    costs = cost_model if isinstance(cost_model, Mapping) else {}
    capacity = engine_summary.get("execution_capacity")
    capacity_enabled = bool(capacity.get("enabled")) if isinstance(capacity, Mapping) else False
    capacity_reason = (
        str(capacity.get("reason_code"))
        if isinstance(capacity, Mapping) and capacity.get("reason_code")
        else None
    )
    capacity_clause = (
        "execution_capacity=source_raw_notional_validated"
        if capacity_enabled
        else "execution_capacity=not_evaluated"
        + (
            f"({capacity_reason})"
            if capacity_reason
            else "(source_raw_notional_not_recorded)"
        )
    )
    cost_liquidity = "cost_model=" + json.dumps(
        costs, sort_keys=True, separators=(",", ":")
    )
    if costs:
        cost_liquidity += "; " + capacity_clause
    candidate_rule = (
        str(parameters.blueprint_id or parameters.profile)
        if parameters is not None
        else candidate.candidate_id
    )
    substituted = not _is_user_rule(candidate)
    summary_identity = {
        "candidate_id": candidate.candidate_id,
        "dates": dates,
        "trade_count": engine_summary.get("effective_trade_count"),
        "initial_capital": engine_summary.get("initial_capital"),
        "execution_capacity": capacity,
    }
    return {
        "evaluated_rule": candidate_rule,
        "rule_version": (
            str(parameters.blueprint_id)
            if parameters is not None and parameters.blueprint_id
            else FEATURE_DEFINITION_VERSION
        ),
        "substituted": substituted,
        "market": strategy.market,
        "universe": f"engine_input_tickers:{len(tickers)}",
        "start_date": dates[0] if dates else "unavailable",
        "end_date": dates[-1] if dates else "unavailable",
        "eod_basis": "input_ohlcv_eod_dates",
        "initial_capital": float(engine_summary.get("initial_capital") or 0.0),
        "rebalance_timing": (
            f"every_{parameters.rebalance_interval_days}_trading_days"
            if parameters is not None
            else "engine_default"
        ),
        "fill_timing": str(
            engine_summary.get("execution_timing") or MISSING_EXECUTION_ASSUMPTION
        ),
        "corporate_action_method": "engine_corporate_action_event_policy",
        "cost_tax_slippage_liquidity": cost_liquidity,
        "observations": len(dates),
        "trades": max(0, int(_summary_float_default(engine_summary, "effective_trade_count", 0.0))),
        "benchmark_method": "official_kospi_kosdaq_total_return_or_explicitly_unavailable",
        "data_version": f"feature-definition:{FEATURE_DEFINITION_VERSION}",
        "result_version": sha256(
            json.dumps(summary_identity, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest(),
        "execution_version": "ai_graph_backtest_engine.v1",
        "historical_simulation_warning": "Historical simulation is not a guarantee of future returns.",
    }


def _is_user_rule(candidate: Any) -> bool:
    """Whether this candidate trades the strategy's own compiled conditions."""

    parameters = getattr(candidate, "parameters", None)
    profile = getattr(parameters, "profile", None)
    blueprint_id = getattr(parameters, "blueprint_id", None)
    if profile is None and isinstance(parameters, Mapping):
        profile = parameters.get("profile")
        blueprint_id = parameters.get("blueprint_id")
    return profile == "compiled_conditions" and not blueprint_id


def rule_provenance(
    backtest: Mapping[str, Any],
    entry_conditions: Sequence[Mapping[str, Any]] | None,
    *,
    selection_mode: str | None = None,
) -> dict[str, Any]:
    """Which rule the backtest actually traded, stated by the backtest.

    `compiled_conditions` means the user's concrete rule was traded. Profiles recorded
    in the catalog blueprints are also intended rules when the user delegated selection.
    Any other generic profile is a substitution that must remain visible. The legacy
    three-profile menu is accepted only for older results without catalog metadata.
    """

    from ai_graph.nodes.condition_compiler import compile_conditions
    from ai_graph.schemas import Condition

    selected = backtest.get("selected_candidate") or {}
    profile = ((selected.get("parameters") or {}).get("profile")) or "unknown"
    blueprint_id = (selected.get("parameters") or {}).get("blueprint_id")
    requested = [str(c.get("left")) for c in (entry_conditions or []) if c.get("left")]
    catalog_profiles = {
        str(item.get("profile"))
        for item in (backtest.get("generated_strategy_blueprints") or [])
        if isinstance(item, Mapping) and item.get("profile")
    }
    intended_automatic_profile = selection_mode == "automatic" and (
        bool(blueprint_id)
        or profile in catalog_profiles
        or (not catalog_profiles and profile in AUTOMATIC_TOURNAMENT_PROFILES)
    )
    substituted = profile != "compiled_conditions" and not intended_automatic_profile

    untranslatable: list[str] = []
    if substituted and entry_conditions:
        for raw in entry_conditions:
            try:
                one = Condition.model_validate(raw)
            except Exception:
                untranslatable.append(str(raw.get("left")))
                continue
            if compile_conditions([one]) is None:
                untranslatable.append(one.left)

    # Two very different substitutions were being reported as one. "Could not be
    # translated" means the user's rule never ran. "Scored lower" means it ran and lost
    # to a generic template on the objective function - the user's strategy was
    # evaluated, and then something else was recommended in its place. Asserting the
    # first when the second happened is the same presumed-cause error this record exists
    # to remove.
    ran_own_rule = any(
        ((c.get("parameters") or {}).get("profile")) == "compiled_conditions"
        and not ((c.get("parameters") or {}).get("blueprint_id"))
        for c in (backtest.get("candidates") or [])
    )
    if not substituted:
        reason = None
    elif untranslatable:
        reason = (
            "생성된 조건 중 백테스트가 평가할 수 없는 항목이 있어 일반 템플릿으로 "
            "대체했습니다: " + ", ".join(untranslatable)
        )
    elif ran_own_rule:
        reason = (
            "사용자 조건도 후보로 백테스트했지만 목적함수 점수가 더 낮아 "
            "일반 템플릿이 선택됐습니다."
        )
    else:
        reason = "사용자 조건이 백테스트 후보에 포함되지 않았습니다."
    if intended_automatic_profile and blueprint_id:
        evaluated_rule = f"automatic_blueprint:{blueprint_id}"
    elif profile == "compiled_conditions":
        evaluated_rule = "user_conditions"
    elif intended_automatic_profile:
        evaluated_rule = f"automatic_profile:{profile}"
    else:
        evaluated_rule = f"template:{profile}"
    return {
        "evaluated_rule": evaluated_rule,
        "substituted": substituted,
        "requested_conditions": requested,
        "untranslatable_conditions": untranslatable,
        "reason": reason,
    }


def summarize_backtest(backtest: Mapping[str, Any]) -> dict[str, Any]:
    selected = backtest.get("selected_candidate") or {}
    selected_id = selected.get("candidate_id")
    engine_summary = backtest.get("engine_summary") or (
        backtest.get("engine_summaries_by_candidate") or {}
    ).get(selected_id, {})
    return {
        "selected_candidate_id": selected_id,
        "metrics": selected.get("metrics") or {},
        # Full metrics carry multi-year rolling series and 250 Monte Carlo paths. They
        # made one report prompt 2.18 million characters and guaranteed an AOAI
        # response-start timeout. The scalar summary plus selected public metrics are
        # sufficient for interpretation; detailed arrays remain in debug artifacts.
        "engine_summary": _public_engine_summary(engine_summary),
        "objective_score": (backtest.get("objective_scores_by_candidate") or {}).get(selected_id),
        "headline": _headline_metrics(selected.get("metrics") or {}),
    }


def _headline_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    """The numbers a reader may treat as a forecast, taken from the hold-out only.

    `sharpe_ratio`, `total_return` and `max_drawdown` span the whole period, of which the
    first 70% is what selection optimised against. Presenting them as the result of the
    backtest states an in-sample fit as though it were an out-of-sample finding. The
    hold-out figures are the same run, restricted to the part no candidate was chosen on.

    `basis` and `candidates_evaluated` travel with the numbers so the reader is never
    left to assume which period they cover or how wide the search behind them was.
    """

    return {
        "basis": "hold_out",
        "hold_out_fraction": round(1.0 - BACKTEST_SPLIT_FRACTION, 4),
        "total_return": metrics.get("out_sample_return"),
        "sharpe_ratio": metrics.get("out_sample_sharpe"),
        "max_drawdown": metrics.get("out_sample_max_drawdown"),
        "candidates_evaluated": metrics.get("candidates_evaluated"),
        "selection_adjusted_sharpe": metrics.get("selection_adjusted_sharpe"),
        # Kept alongside, explicitly labelled, so the in-sample figures remain available
        # without being the ones on the headline.
        "in_sample": {
            "total_return": metrics.get("in_sample_return"),
            "sharpe_ratio": metrics.get("in_sample_sharpe"),
            "max_drawdown": metrics.get("in_sample_max_drawdown"),
        },
        "full_period": {
            "total_return": metrics.get("total_return"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "max_drawdown": metrics.get("max_drawdown"),
        },
    }


def _ensure_backtest_module_source_path() -> None:
    package_root = BACKTEST_MODULE_SOURCE_ROOT / "backtest_module"
    if not package_root.is_dir():
        return
    source_path = str(BACKTEST_MODULE_SOURCE_ROOT)
    while source_path in sys.path:
        sys.path.remove(source_path)
    sys.path.insert(0, source_path)


try:
    from backtest_module import (
        Condition as EngineCondition,
    )
    from backtest_module import (
        ConditionOperator as EngineConditionOperator,
    )
    from backtest_module import (
        PositionSizing as EnginePositionSizing,
    )
    from backtest_module import (
        RiskControls as EngineRiskControls,
    )
    from backtest_module import (
        StrategySpec as EngineStrategySpec,
    )
    from backtest_module.backtest import (
        BacktestRunConfig as EngineBacktestRunConfig,
    )
    from backtest_module.backtest import (
        OhlcvBar as EngineOhlcvBar,
    )
    from backtest_module.backtest import (
        PreparedMarketData as EnginePreparedMarketData,
    )
    from backtest_module.backtest import (
        TalibIndicatorConfig as EngineTalibIndicatorConfig,
    )
    from backtest_module.backtest import (
        prepare_market_data as prepare_engine_market_data,
    )
    from backtest_module.backtest import (
        run_backtest as run_engine_backtest,
    )
    from backtest_module.performance import (
        QUANTSTATS_REQUIRED_MESSAGE,
        quantstats_sharpe_from_returns,
        returns_from_equity_curve,
    )
except ImportError:
    _ensure_backtest_module_source_path()
    for module_name in list(sys.modules):
        if module_name == "backtest_module" or module_name.startswith("backtest_module."):
            sys.modules.pop(module_name, None)
    from backtest_module import (
        Condition as EngineCondition,
    )
    from backtest_module import (
        ConditionOperator as EngineConditionOperator,
    )
    from backtest_module import (
        PositionSizing as EnginePositionSizing,
    )
    from backtest_module import (
        RiskControls as EngineRiskControls,
    )
    from backtest_module import (
        StrategySpec as EngineStrategySpec,
    )
    from backtest_module.backtest import (
        BacktestRunConfig as EngineBacktestRunConfig,
    )
    from backtest_module.backtest import (
        OhlcvBar as EngineOhlcvBar,
    )
    from backtest_module.backtest import (
        PreparedMarketData as EnginePreparedMarketData,
    )
    from backtest_module.backtest import (
        TalibIndicatorConfig as EngineTalibIndicatorConfig,
    )
    from backtest_module.backtest import (
        prepare_market_data as prepare_engine_market_data,
    )
    from backtest_module.backtest import (
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
    # Optional entry strength for scarce same-session slots.  Missing scores preserve
    # the engine's deterministic ticker-order fallback instead of inventing a rank.
    score: float | None = None


@dataclass(frozen=True)
class _BenchmarkPeriodStats:
    count: int
    win_rate: float
    loss_rate: float


@dataclass(frozen=True)
class _CandidateEvaluation:
    candidate: CodeCandidate
    engine_summary: dict[str, Any] | None = None
    equity_curve: list[BacktestEquityPoint] | None = None
    objective_score: float | None = None
    quantstats_dependency_error: bool = False
    diagnostics: dict[str, Any] | None = None
    ticker_actions: list[dict[str, Any]] = field(default_factory=list)


def _is_cacheable_evaluation(evaluation: _CandidateEvaluation) -> bool:
    """Keep only complete, dependency-independent candidate results on disk.

    A missing optional dependency is an observation about the process that created the
    evaluation, not about the strategy, rows, or candidate fingerprint.  Persisting it
    made a repaired environment keep raising the old ``quantstats`` failure through the
    isolated Python-fallback path.  Incomplete/failed evaluations likewise cannot be a
    deterministic reusable result.
    """

    return bool(
        not evaluation.quantstats_dependency_error
        and evaluation.candidate.validation_ok
        and evaluation.candidate.metrics is not None
        and evaluation.engine_summary is not None
        and evaluation.equity_curve is not None
        and evaluation.objective_score is not None
    )


@dataclass(frozen=True)
class _CandidateTaskResult:
    evaluation: _CandidateEvaluation
    generated_actions: Sequence[int] | None
    generated_scores: Sequence[float] | None
    action_build_seconds: float
    action_cache_hit: bool
    worker_pid: int
    feature_cached_lookbacks: tuple[int, ...]
    feature_estimated_bytes: int


@dataclass(frozen=True)
class _BenchmarkContext:
    daily_returns: tuple[float, ...]
    selection_days: int
    selection_return: float
    total_return: float | None
    primary_available: bool
    primary_unavailable_reason: str | None
    auxiliary_label: str
    primary_coverage: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class _WalkForwardFold:
    fold_index: int
    warmup_sessions: tuple[str, ...]
    train_sessions: tuple[str, ...]
    validation_sessions: tuple[str, ...]
    evaluation_sessions: tuple[str, ...]

    @property
    def evaluation_month(self) -> str:
        return self.evaluation_sessions[0][:7]


@dataclass(frozen=True)
class _SplitPolicy:
    warmup_sessions: tuple[str, ...]
    folds: tuple[_WalkForwardFold, ...]
    final_lockbox_sessions: tuple[str, ...]


@dataclass(frozen=True)
class _WalkForwardSample:
    session_count: int
    valid_fold_count: int
    unique_evaluation_month_count: int
    unique_evaluation_session_count: int
    status: str


@dataclass(frozen=True)
class _PreparedMarketCacheEntry:
    price_rows: tuple[Mapping[str, Any], ...]
    prepared_market: EnginePreparedMarketData


class _DigestWriter:
    def __init__(self, digest: Any) -> None:
        self.digest = digest

    def write(self, payload: bytes) -> int:
        self.digest.update(payload)
        return len(payload)


# ponytail: one process-local entry bounds retained memory; use a shared cache only
# when cross-process hit rates justify serializing the full prepared market.
_PREPARED_MARKET_CACHE: tuple[tuple[str, str], _PreparedMarketCacheEntry] | None = None
_PREPARED_MARKET_CACHE_LOCK = Lock()


def _get_prepared_market(key: tuple[str, str]) -> _PreparedMarketCacheEntry | None:
    with _PREPARED_MARKET_CACHE_LOCK:
        cached = _PREPARED_MARKET_CACHE
    return cached[1] if cached is not None and cached[0] == key else None


def _store_prepared_market(key: tuple[str, str], entry: _PreparedMarketCacheEntry) -> None:
    global _PREPARED_MARKET_CACHE
    with _PREPARED_MARKET_CACHE_LOCK:
        _PREPARED_MARKET_CACHE = (key, entry)


def _clear_prepared_market_cache() -> None:
    global _PREPARED_MARKET_CACHE
    with _PREPARED_MARKET_CACHE_LOCK:
        _PREPARED_MARKET_CACHE = None


_WORKER_STRATEGY: AIStrategySpec | None = None
_WORKER_PRICE_ROWS: Sequence[Mapping[str, Any]] | None = None
_WORKER_PREPARED_MARKET: EnginePreparedMarketData | None = None
_WORKER_FEATURE_STORE: PreparedFeatureStore | None = None
_WORKER_BENCHMARK_CONTEXT: _BenchmarkContext | None = None


def _initialize_candidate_worker(
    strategy_payload: Mapping[str, Any],
    price_rows: Sequence[Mapping[str, Any]],
    prepared_market: EnginePreparedMarketData,
    feature_store: PreparedFeatureStore,
    benchmark_context: _BenchmarkContext,
) -> None:
    global _WORKER_STRATEGY, _WORKER_PRICE_ROWS, _WORKER_PREPARED_MARKET
    global _WORKER_FEATURE_STORE, _WORKER_BENCHMARK_CONTEXT
    _WORKER_STRATEGY = AIStrategySpec.model_validate(strategy_payload)
    _WORKER_PRICE_ROWS = price_rows
    _WORKER_PREPARED_MARKET = prepared_market
    _WORKER_FEATURE_STORE = feature_store
    _WORKER_BENCHMARK_CONTEXT = benchmark_context


def _evaluate_candidate_worker(
    task: tuple[Mapping[str, Any], Sequence[int] | None, Sequence[float] | None, str],
) -> _CandidateTaskResult:
    if (
        _WORKER_STRATEGY is None
        or _WORKER_PRICE_ROWS is None
        or _WORKER_PREPARED_MARKET is None
        or _WORKER_FEATURE_STORE is None
        or _WORKER_BENCHMARK_CONTEXT is None
    ):
        raise RuntimeError("candidate worker was not initialized")
    candidate_payload, actions, scores, metrics_mode = task
    return _evaluate_candidate_task(
        _WORKER_STRATEGY,
        CodeCandidate.model_validate(candidate_payload),
        _WORKER_PRICE_ROWS,
        prepared_market=_WORKER_PREPARED_MARKET,
        feature_store=_WORKER_FEATURE_STORE,
        benchmark_context=_WORKER_BENCHMARK_CONTEXT,
        generated_actions=actions,
        generated_scores=scores,
        metrics_mode=metrics_mode,
    )


class BacktestCacheConfigurationError(RuntimeError):
    """Raised when the disk cache directory is not configured under a release profile."""


class _DiskEvaluationCache:
    def __init__(self) -> None:
        configured = os.getenv(BACKTEST_CACHE_DIR_ENV)
        if not configured and is_release_profile():
            # A shared /tmp fallback under a release profile silently mixes cache
            # entries across deployments and is wiped by the host at will. Fail
            # closed and make the operator point at a persistent directory.
            raise BacktestCacheConfigurationError(
                f"{BACKTEST_CACHE_DIR_ENV} must point at a persistent directory under a "
                "release profile; refusing to fall back to a shared temp directory."
            )
        self.root = (
            Path(configured) if configured else Path(gettempdir()) / "quantagent-backtest-v2"
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = _positive_int_env(BACKTEST_CACHE_TTL_ENV, DEFAULT_CACHE_TTL_SECONDS)
        self.max_bytes = _positive_int_env(BACKTEST_CACHE_MAX_BYTES_ENV, DEFAULT_CACHE_MAX_BYTES)
        # No sweep on construction: cleanup is amortized across writes in store().
        self._writes_since_cleanup = 0

    def load(
        self,
        key: str,
        candidate: CodeCandidate,
    ) -> _CandidateEvaluation | None:
        path = self.root / f"{key}.json"
        try:
            if not path.is_file():
                return None
            if time.time() - path.stat().st_mtime > self.ttl_seconds:
                path.unlink(missing_ok=True)
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != BACKTEST_CACHE_SCHEMA_VERSION:
                path.unlink(missing_ok=True)
                return None
            stored = CodeCandidate.model_validate(payload["candidate"])
            rebound = candidate.model_copy(
                update={
                    "validation_ok": stored.validation_ok,
                    "violations": stored.violations,
                    "metrics": stored.metrics,
                }
            )
            diagnostics = dict(payload.get("diagnostics") or {})
            diagnostics["cache_hit"] = True
            diagnostics["cache_level"] = "disk"
            evaluation = _CandidateEvaluation(
                candidate=rebound,
                engine_summary=payload.get("engine_summary"),
                equity_curve=[
                    BacktestEquityPoint.model_validate(item)
                    for item in payload.get("equity_curve") or []
                ]
                or None,
                objective_score=payload.get("objective_score"),
                quantstats_dependency_error=bool(payload.get("quantstats_dependency_error", False)),
                diagnostics=diagnostics,
                ticker_actions=list(payload.get("ticker_actions") or []),
            )
            if not _is_cacheable_evaluation(evaluation):
                path.unlink(missing_ok=True)
                return None
            return evaluation
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            path.unlink(missing_ok=True)
            return None

    def store(self, key: str, evaluation: _CandidateEvaluation) -> int:
        if not _is_cacheable_evaluation(evaluation):
            return 0
        path = self.root / f"{key}.json"
        temporary = self.root / f".{key}.{os.getpid()}.tmp"
        payload = {
            "schema_version": BACKTEST_CACHE_SCHEMA_VERSION,
            "candidate": evaluation.candidate.model_dump(mode="json"),
            "engine_summary": evaluation.engine_summary,
            "equity_curve": [
                point.model_dump(mode="json") for point in evaluation.equity_curve or []
            ],
            "objective_score": evaluation.objective_score,
            "quantstats_dependency_error": evaluation.quantstats_dependency_error,
            "diagnostics": evaluation.diagnostics or {},
            # Without this a cache hit returns an evaluation with no per-stock verdict, so
            # a re-run of the same strategy would show performance and no recommendations.
            "ticker_actions": evaluation.ticker_actions,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        try:
            temporary.write_text(encoded, encoding="utf-8")
            os.replace(temporary, path)
            size = path.stat().st_size
        finally:
            temporary.unlink(missing_ok=True)
        self._writes_since_cleanup += 1
        if self._writes_since_cleanup >= CACHE_CLEANUP_WRITE_INTERVAL:
            self._writes_since_cleanup = 0
            self._cleanup()
        return size

    def _cleanup(self) -> None:
        now = time.time()
        files: list[tuple[float, int, Path]] = []
        for path in self.root.glob("*.json"):
            try:
                stat = path.stat()
            except OSError:
                continue
            if now - stat.st_mtime > self.ttl_seconds:
                path.unlink(missing_ok=True)
                continue
            files.append((stat.st_mtime, stat.st_size, path))
        total = sum(size for _, size, _ in files)
        for _, size, path in sorted(files):
            if total <= self.max_bytes:
                break
            path.unlink(missing_ok=True)
            total -= size


class _CandidateBacktestSession:
    """Reuse prepared columns, one worker pool, and candidate results across rounds."""

    def __init__(
        self,
        strategy: AIStrategySpec,
        price_rows: Sequence[Mapping[str, Any]],
        *,
        official_benchmark: Mapping[str, Any] | None = None,
    ) -> None:
        prep_started = time.perf_counter()
        self.strategy = strategy
        self.official_benchmark = official_benchmark
        phases: dict[str, float] = {}

        started = time.perf_counter()
        self.data_fingerprint, self.data_descriptor = _data_fingerprint(price_rows)
        self.strategy_fingerprint = _strategy_fingerprint(strategy)
        phases["fingerprint_seconds"] = time.perf_counter() - started

        cache_key = (self.data_fingerprint, self.strategy_fingerprint)
        started = time.perf_counter()
        cached = _get_prepared_market(cache_key)
        phases["cache_lookup_seconds"] = time.perf_counter() - started

        started = time.perf_counter()
        if cached is None:
            self.feature_store = PreparedFeatureStore(
                price_rows,
                rows_are_sorted=bool(self.data_descriptor["rows_are_sorted"]),
            )
            self.price_rows = self.feature_store.rows
        else:
            self.price_rows = cached.price_rows
            self.feature_store = PreparedFeatureStore(
                self.price_rows,
                rows_are_sorted=True,
            )
        phases["feature_store_seconds"] = time.perf_counter() - started

        self.prepared_market_cache_hit = cached is not None
        if cached is not None:
            self.prepared_market = cached.prepared_market
            phases["engine_row_conversion_seconds"] = 0.0
            phases["engine_market_index_seconds"] = 0.0
        else:
            started = time.perf_counter()
            ohlcv_rows, metric_rows = _engine_market_rows(self.price_rows)
            phases["engine_row_conversion_seconds"] = time.perf_counter() - started

            preparation_candidate = CodeCandidate(
                candidate_id="prepare",
                variant="A",
                code="def build_signals(prices):\n    return []\n",
                validation_ok=True,
            )
            preparation_spec = _engine_strategy_spec(
                strategy,
                preparation_candidate,
                available_ticker_count=_available_ticker_count(self.price_rows),
                execution_capacity_enabled=_execution_capacity_enabled(self.price_rows),
            )
            engine_config = EngineBacktestRunConfig(
                initial_capital=CANONICAL_ANALYSIS_INITIAL_CAPITAL,
                write_outputs=False,
                talib=EngineTalibIndicatorConfig(enabled=False, mode="none"),
                metrics_mode="selection",
            )
            started = time.perf_counter()
            self.prepared_market = prepare_engine_market_data(
                preparation_spec,
                ohlcv_rows=ohlcv_rows,
                metric_rows=metric_rows,
                config=engine_config,
                inputs_normalized=True,
            )
            phases["engine_market_index_seconds"] = time.perf_counter() - started
            _store_prepared_market(
                cache_key,
                _PreparedMarketCacheEntry(
                    price_rows=self.price_rows,
                    prepared_market=self.prepared_market,
                ),
            )

        started = time.perf_counter()
        self.benchmark_context = _build_benchmark_context(
            self.price_rows, official_benchmark
        )
        phases["benchmark_context_seconds"] = time.perf_counter() - started

        self.preparation_phases = {name: round(seconds, 6) for name, seconds in phases.items()}
        self.preparation_seconds = time.perf_counter() - prep_started
        self._base_feature_estimated_bytes = self.feature_store.stats().estimated_bytes
        self._cache: dict[tuple[str, bool, str], _CandidateEvaluation] = {}
        self._action_cache: dict[str, Sequence[int]] = {}
        self._score_cache: dict[str, Sequence[float]] = {}
        self._worker_feature_bytes: dict[int, int] = {}
        self._worker_feature_lookbacks: set[int] = set()
        self._disk_cache = _DiskEvaluationCache()
        self._executor: ProcessPoolExecutor | None = None
        self._executor_workers = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.disk_cache_bytes_written = 0
        self.evaluation_rounds: list[dict[str, Any]] = []

    def __enter__(self) -> _CandidateBacktestSession:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._executor = None
            self._executor_workers = 0

    def evaluate(
        self,
        candidates: Sequence[CodeCandidate],
        *,
        metrics_mode: str = "selection",
    ) -> list[_CandidateEvaluation]:
        round_started = time.perf_counter()
        missing: list[CodeCandidate] = []
        missing_keys: set[tuple[str, bool, str]] = set()
        cache_levels: dict[tuple[str, bool, str], str] = {}
        round_worker_count = 0
        action_build_seconds = 0.0
        memory_hits = 0
        disk_hits = 0
        for candidate in candidates:
            memory_key = _candidate_cache_key(candidate, metrics_mode)
            if memory_key in self._cache:
                cache_levels[memory_key] = "memory"
                memory_hits += 1
                self.cache_hits += 1
                continue
            disk_key = self._disk_cache_key(candidate, metrics_mode)
            cached = self._disk_cache.load(disk_key, candidate)
            if cached is not None:
                self._cache[memory_key] = cached
                cache_levels[memory_key] = "disk"
                disk_hits += 1
                self.cache_hits += 1
                continue
            if memory_key not in missing_keys:
                missing.append(candidate)
                missing_keys.add(memory_key)
            self.cache_misses += 1

        round_action_cache_hits = sum(
            _candidate_identity(candidate) in self._action_cache for candidate in missing
        )
        if missing:
            round_worker_count = _candidate_worker_count(
                len(missing),
                row_count=len(self.price_rows),
            )
            tasks = [
                (
                    candidate.model_dump(mode="python"),
                    self._action_cache.get(_candidate_identity(candidate)),
                    self._score_cache.get(_candidate_identity(candidate)),
                    metrics_mode,
                )
                for candidate in missing
            ]
            requires_isolation = any(
                candidate.representation == "python_fallback" for candidate in missing
            )
            reuse_executor = self._executor is not None
            if round_worker_count == 1 and not requires_isolation and not reuse_executor:
                task_results = [
                    _evaluate_candidate_task(
                        self.strategy,
                        candidate,
                        self.price_rows,
                        prepared_market=self.prepared_market,
                        feature_store=self.feature_store,
                        benchmark_context=self.benchmark_context,
                        generated_actions=self._action_cache.get(_candidate_identity(candidate)),
                        generated_scores=self._score_cache.get(_candidate_identity(candidate)),
                        metrics_mode=metrics_mode,
                    )
                    for candidate in missing
                ]
            else:
                task_results = self._evaluate_parallel(
                    tasks,
                    missing,
                    (self._executor_workers if reuse_executor else max(1, round_worker_count)),
                )
            action_seconds_by_pid: dict[int, float] = {}
            for result in task_results:
                if result.action_build_seconds > 0.0:
                    action_seconds_by_pid[result.worker_pid] = (
                        action_seconds_by_pid.get(result.worker_pid, 0.0)
                        + result.action_build_seconds
                    )
                if result.generated_actions is not None:
                    identity = _candidate_identity(result.evaluation.candidate)
                    self._action_cache[identity] = result.generated_actions
                    if result.generated_scores is not None:
                        self._score_cache[identity] = result.generated_scores
                if result.worker_pid != os.getpid():
                    self._worker_feature_bytes[result.worker_pid] = max(
                        self._worker_feature_bytes.get(result.worker_pid, 0),
                        result.feature_estimated_bytes,
                    )
                    self._worker_feature_lookbacks.update(result.feature_cached_lookbacks)
            action_build_seconds = max(action_seconds_by_pid.values(), default=0.0)
            action_build_total_seconds = sum(action_seconds_by_pid.values())
            for candidate, result in zip(missing, task_results, strict=True):
                evaluation = result.evaluation
                memory_key = _candidate_cache_key(candidate, metrics_mode)
                self._cache[memory_key] = evaluation
                disk_key = self._disk_cache_key(candidate, metrics_mode)
                try:
                    self.disk_cache_bytes_written += self._disk_cache.store(disk_key, evaluation)
                except (OSError, TypeError, ValueError):
                    pass
        else:
            action_build_total_seconds = 0.0
            action_seconds_by_pid = {}

        self.evaluation_rounds.append(
            {
                "metrics_mode": metrics_mode,
                "requested_candidates": len(candidates),
                "new_candidates": len(missing),
                "cached_candidates": memory_hits + disk_hits,
                "memory_cache_hits": memory_hits,
                "disk_cache_hits": disk_hits,
                "worker_count": round_worker_count,
                "action_build_seconds": round(action_build_seconds, 6),
                "action_build_total_seconds": round(action_build_total_seconds, 6),
                "action_worker_pids": sorted(action_seconds_by_pid),
                "action_cache_hits": round_action_cache_hits,
                "cumulative_candidates": len(
                    {key[0] for key in self._cache if key[2] == "selection"}
                ),
                "wall_seconds": round(time.perf_counter() - round_started, 6),
            }
        )
        return [
            _rebind_evaluation(
                self._cache[_candidate_cache_key(candidate, metrics_mode)],
                candidate,
                cache_level=cache_levels.get(_candidate_cache_key(candidate, metrics_mode)),
            )
            for candidate in candidates
        ]

    def _evaluate_parallel(
        self,
        tasks: list[
            tuple[Mapping[str, Any], Sequence[int] | None, Sequence[float] | None, str]
        ],
        candidates: list[CodeCandidate],
        worker_count: int,
    ) -> list[_CandidateTaskResult]:
        if self._executor is not None and self._executor_workers != worker_count:
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._executor = None
            self._executor_workers = 0
        if self._executor is None:
            start_method = "fork" if "fork" in get_all_start_methods() else "spawn"
            self._executor = ProcessPoolExecutor(
                max_workers=worker_count,
                mp_context=get_context(start_method),
                initializer=_initialize_candidate_worker,
                initargs=(
                    self.strategy.model_dump(mode="python"),
                    self.price_rows,
                    self.prepared_market,
                    self.feature_store,
                    self.benchmark_context,
                ),
            )
            self._executor_workers = worker_count
        futures = [self._executor.submit(_evaluate_candidate_worker, task) for task in tasks]
        timeout = _candidate_timeout_seconds()
        # Collect completed work immediately. Previously a slow first submission hid
        # already-finished later candidates and caused all of them to be marked timed
        # out. One timeout window is allowed for each worker wave so queued candidates
        # still receive a full execution budget.
        wave_count = max(1, math.ceil(len(futures) / max(1, worker_count)))
        # `timeout * wave_count` grows with the candidate count, so on its own this is not
        # a bound at all. Whatever the request has left is the real ceiling; without the
        # clamp a single wide round can outlast the whole request budget.
        wave_budget = timeout * wave_count
        request_remaining = deadline_remaining_seconds()
        if request_remaining is not None:
            wave_budget = min(wave_budget, max(0.0, request_remaining))
        deadline = time.perf_counter() + wave_budget
        evaluations: list[_CandidateTaskResult | None] = [None] * len(futures)
        future_indexes: dict[Future[_CandidateTaskResult], int] = {
            future: index for index, future in enumerate(futures)
        }
        pending: set[Future[_CandidateTaskResult]] = set(futures)
        while pending:
            # Stop before the next wave when the run was cancelled, so a cancel does
            # not have to wait for every already-queued candidate to finish.
            try:
                raise_if_cancelled()
            except AnalysisCancelled:
                self._terminate_executor()
                for unresolved in pending:
                    unresolved.cancel()
                raise
            remaining_seconds = deadline - time.perf_counter()
            if remaining_seconds <= 0:
                break
            completed, pending = wait(
                pending,
                timeout=remaining_seconds,
                return_when=FIRST_COMPLETED,
            )
            if not completed:
                break
            try:
                for future in completed:
                    evaluations[future_indexes[future]] = future.result()
            except BaseException:
                self._terminate_executor()
                for unresolved in pending:
                    unresolved.cancel()
                raise

        if pending:
            self._terminate_executor()
            for future in pending:
                future.cancel()
                index = future_indexes[future]
                evaluations[index] = _CandidateTaskResult(
                    evaluation=_timeout_evaluation(candidates[index], timeout),
                    generated_actions=None,
                    generated_scores=None,
                    action_build_seconds=0.0,
                    action_cache_hit=False,
                    worker_pid=0,
                    feature_cached_lookbacks=(),
                    feature_estimated_bytes=0,
                )

        if any(evaluation is None for evaluation in evaluations):
            raise RuntimeError("candidate worker completed without an evaluation")
        return [evaluation for evaluation in evaluations if evaluation is not None]

    def _terminate_executor(self) -> None:
        executor = self._executor
        if executor is None:
            return
        processes = list(getattr(executor, "_processes", {}).values())
        executor.shutdown(wait=False, cancel_futures=True)
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
        self._executor = None
        self._executor_workers = 0

    def _disk_cache_key(self, candidate: CodeCandidate, metrics_mode: str) -> str:
        payload = {
            "cache_schema": BACKTEST_CACHE_SCHEMA_VERSION,
            "engine_version": BACKTEST_ENGINE_VERSION,
            "feature_version": FEATURE_DEFINITION_VERSION,
            "data_version": self.data_fingerprint,
            "universe": self.data_descriptor,
            "strategy_sha": self.strategy_fingerprint,
            "candidate_sha": _candidate_identity(candidate),
            "validation_ok": candidate.validation_ok,
            "metrics_mode": metrics_mode,
            "benchmark": {
                "available": self.benchmark_context.primary_available,
                "return": self.benchmark_context.total_return,
            },
        }
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return sha256(encoded.encode("utf-8")).hexdigest()

    def execution_stats(self) -> dict[str, Any]:
        feature_stats = self.feature_store.stats()
        worker_feature_bytes = sum(
            max(0, size - self._base_feature_estimated_bytes)
            for size in self._worker_feature_bytes.values()
        )
        return {
            "engine_version": BACKTEST_ENGINE_VERSION,
            "feature_version": FEATURE_DEFINITION_VERSION,
            "data_fingerprint": self.data_fingerprint,
            "feature_preparation_seconds": round(self.preparation_seconds, 6),
            "feature_preparation_phases": dict(self.preparation_phases),
            "prepared_market_cache_hit": self.prepared_market_cache_hit,
            "feature_estimated_bytes": feature_stats.estimated_bytes + worker_feature_bytes,
            "feature_cached_lookbacks": sorted(
                {*feature_stats.cached_lookbacks, *self._worker_feature_lookbacks}
            ),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "disk_cache_bytes_written": self.disk_cache_bytes_written,
            "rounds": list(self.evaluation_rounds),
        }


def _candidate_worker_count(candidate_count: int, *, row_count: int = 0) -> int:
    requested = _configured_worker_limit()
    available_cpus = os.cpu_count() or 1
    if candidate_count * row_count < SERIAL_EVALUATION_WORK_ITEMS:
        return 1
    requested = max(1, min(candidate_count, requested, available_cpus))
    if requested <= 1:
        return 1
    # fork shares prepared market data copy-on-write. spawn serializes the same large
    # object into every worker; the measured Windows production input tripled RSS for
    # only a small wall-time gain. Keep spawn serial unless an operator explicitly opts
    # into that memory trade-off.
    if "fork" not in get_all_start_methods() and not _truthy_env(
        AI_BACKTEST_ALLOW_SPAWN_PARALLEL_ENV
    ):
        return 1
    return requested


def _configured_worker_limit() -> int:
    configured = os.getenv(AI_BACKTEST_WORKERS_ENV)
    try:
        requested = int(configured) if configured is not None else DEFAULT_BACKTEST_WORKERS
    except ValueError:
        requested = DEFAULT_BACKTEST_WORKERS
    return max(1, requested)


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _candidate_cache_key(
    candidate: CodeCandidate, metrics_mode: str = "selection"
) -> tuple[str, bool, str]:
    return _candidate_identity(candidate), candidate.validation_ok, metrics_mode


def _candidate_identity(candidate: CodeCandidate) -> str:
    if (
        candidate.representation == "structured"
        and candidate.strategy_ir is not None
        and candidate.parameters is not None
    ):
        payload: Any = {
            "strategy_ir": candidate.strategy_ir.model_dump(mode="json"),
            "parameters": candidate.parameters.model_dump(mode="json"),
        }
    else:
        payload = {"code_sha": sha256(candidate.code.encode("utf-8")).hexdigest()}
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _rebind_evaluation(
    evaluation: _CandidateEvaluation,
    candidate: CodeCandidate,
    *,
    cache_level: str | None = None,
) -> _CandidateEvaluation:
    rebound = candidate.model_copy(
        update={
            "validation_ok": evaluation.candidate.validation_ok,
            "violations": evaluation.candidate.violations,
            "metrics": evaluation.candidate.metrics,
        }
    )
    diagnostics = dict(evaluation.diagnostics or {})
    diagnostics["candidate_id"] = candidate.candidate_id
    if cache_level is not None:
        diagnostics["cache_hit"] = True
        diagnostics["cache_level"] = cache_level
    return _CandidateEvaluation(
        candidate=rebound,
        engine_summary=evaluation.engine_summary,
        equity_curve=evaluation.equity_curve,
        objective_score=evaluation.objective_score,
        quantstats_dependency_error=evaluation.quantstats_dependency_error,
        diagnostics=diagnostics,
        # Identical code is evaluated once and rebound to every candidate id that shares
        # it. Leaving this out meant the shared evaluation kept its per-stock verdict and
        # every rebound copy silently lost it.
        ticker_actions=[
            {**action, "source_candidate_id": candidate.candidate_id}
            for action in evaluation.ticker_actions
        ],
    )


def _data_fingerprint(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[str, dict[str, Any]]:
    tickers: set[str] = set()
    first_date: str | None = None
    last_date: str | None = None
    previous_sort_key: tuple[str, str] | None = None
    rows_are_sorted = True
    for row in rows:
        ticker = str(row.get("ticker") or DEFAULT_FIXTURE_TICKER).zfill(6)
        row_date = str(row.get("date") or "")
        tickers.add(ticker)
        first_date = row_date if first_date is None else min(first_date, row_date)
        last_date = row_date if last_date is None else max(last_date, row_date)
        sort_key = (row_date, ticker)
        if previous_sort_key is not None and sort_key < previous_sort_key:
            rows_are_sorted = False
        previous_sort_key = sort_key

    digest = sha256()
    try:
        pickle.Pickler(_DigestWriter(digest), protocol=pickle.HIGHEST_PROTOCOL).dump(rows)
    except (AttributeError, pickle.PicklingError, TypeError):
        digest = sha256()
        for row in rows:
            encoded = json.dumps(
                dict(row),
                ensure_ascii=True,
                default=str,
                separators=(",", ":"),
                sort_keys=True,
            )
            digest.update(encoded.encode("utf-8"))
            digest.update(b"\n")
    descriptor = {
        "row_count": len(rows),
        "ticker_count": len(tickers),
        "tickers_sha": sha256(",".join(sorted(tickers)).encode("utf-8")).hexdigest(),
        "first_date": first_date,
        "last_date": last_date,
        "rows_are_sorted": rows_are_sorted,
    }
    return digest.hexdigest(), descriptor


def _strategy_fingerprint(strategy: AIStrategySpec) -> str:
    payload = json.dumps(
        strategy.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _candidate_timeout_seconds() -> float:
    try:
        value = float(
            os.getenv(
                AI_BACKTEST_CANDIDATE_TIMEOUT_ENV,
                str(DEFAULT_CANDIDATE_TIMEOUT_SECONDS),
            )
        )
    except ValueError:
        return DEFAULT_CANDIDATE_TIMEOUT_SECONDS
    return value if value > 0.0 else DEFAULT_CANDIDATE_TIMEOUT_SECONDS


def _wall_budget_seconds() -> float:
    try:
        value = float(
            os.getenv(
                AI_BACKTEST_WALL_BUDGET_ENV,
                str(DEFAULT_WALL_BUDGET_SECONDS),
            )
        )
    except ValueError:
        return DEFAULT_WALL_BUDGET_SECONDS
    return value if value > 0.0 else DEFAULT_WALL_BUDGET_SECONDS


def _timeout_evaluation(
    candidate: CodeCandidate,
    timeout_seconds: float,
) -> _CandidateEvaluation:
    message = f"candidate execution exceeded {timeout_seconds:g}s timeout"
    return _CandidateEvaluation(
        candidate=candidate.model_copy(
            update={
                "validation_ok": False,
                "violations": [*candidate.violations, message],
            }
        ),
        diagnostics={
            "candidate_id": candidate.candidate_id,
            "stage": "candidate_evaluation",
            "cache_hit": False,
            "error_type": "TimeoutError",
            "timeout_seconds": timeout_seconds,
        },
    )


def _peak_rss_bytes() -> int | None:
    try:
        import psutil

        process = psutil.Process()
        total = int(process.memory_info().rss)
        for child in process.children(recursive=True):
            try:
                total += int(child.memory_info().rss)
            except psutil.Error:
                continue
        return total
    except (ImportError, OSError):
        return None


def _evaluate_candidate_task(
    strategy_a: AIStrategySpec,
    candidate: CodeCandidate,
    rows: Sequence[Mapping[str, Any]],
    *,
    prepared_market: EnginePreparedMarketData,
    feature_store: PreparedFeatureStore,
    benchmark_context: _BenchmarkContext,
    generated_actions: Sequence[int] | None,
    generated_scores: Sequence[float] | None,
    metrics_mode: str,
) -> _CandidateTaskResult:
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    worker_pid = os.getpid()
    action_cache_hit = generated_actions is not None
    action_build_started = time.perf_counter()
    actions = generated_actions
    scores = generated_scores
    if not candidate.validation_ok:
        feature_stats = feature_store.stats()
        return _CandidateTaskResult(
            evaluation=_CandidateEvaluation(
                candidate=candidate,
                diagnostics={
                    "candidate_id": candidate.candidate_id,
                    "stage": "validation",
                    "input_rows": len(rows),
                    "generated_signals": 0,
                    "cache_hit": False,
                    "wall_seconds": 0.0,
                    "cpu_seconds": 0.0,
                    "action_build_seconds": 0.0,
                    "action_cache_hit": action_cache_hit,
                    "worker_pid": worker_pid,
                },
            ),
            generated_actions=actions,
            generated_scores=scores,
            action_build_seconds=0.0,
            action_cache_hit=action_cache_hit,
            worker_pid=worker_pid,
            feature_cached_lookbacks=feature_stats.cached_lookbacks,
            feature_estimated_bytes=feature_stats.estimated_bytes,
        )
    try:
        if actions is None:
            if (
                candidate.representation == "structured"
                and candidate.strategy_ir is not None
                and candidate.parameters is not None
            ):
                actions = feature_store.build_actions(
                    candidate.strategy_ir,
                    candidate.parameters,
                )
            else:
                generated_signals = _execute_candidate_code(candidate, rows)
                actions, scores = _compact_actions_from_signals(prepared_market, generated_signals)
        action_build_seconds = (
            0.0 if action_cache_hit else time.perf_counter() - action_build_started
        )
        engine_result = _run_candidate_backtest(
            strategy_a,
            candidate,
            rows,
            prepared_market=prepared_market,
            generated_actions=actions,
            generated_scores=scores,
            metrics_mode=metrics_mode,
        )
    except Exception as exc:
        action_build_seconds = (
            0.0 if action_cache_hit else time.perf_counter() - action_build_started
        )
        diagnostics = {
            "candidate_id": candidate.candidate_id,
            "stage": "candidate_evaluation",
            "input_rows": len(rows),
            "generated_signals": len(actions or ()),
            "cache_hit": False,
            "wall_seconds": round(time.perf_counter() - wall_started, 6),
            "cpu_seconds": round(time.process_time() - cpu_started, 6),
            "error_type": type(exc).__name__,
            "action_build_seconds": round(action_build_seconds, 6),
            "action_cache_hit": action_cache_hit,
            "worker_pid": worker_pid,
        }
        feature_stats = feature_store.stats()
        if _is_quantstats_dependency_error(exc):
            evaluation = _CandidateEvaluation(
                candidate=candidate, quantstats_dependency_error=True, diagnostics=diagnostics
            )
        else:
            evaluation = _CandidateEvaluation(
                candidate=candidate.model_copy(
                    update={
                        "validation_ok": False,
                        "violations": [*candidate.violations, f"engine backtest failed: {exc}"],
                    }
                ),
                diagnostics=diagnostics,
            )
        return _CandidateTaskResult(
            evaluation=evaluation,
            generated_actions=actions,
            generated_scores=scores,
            action_build_seconds=action_build_seconds,
            action_cache_hit=action_cache_hit,
            worker_pid=worker_pid,
            feature_cached_lookbacks=feature_stats.cached_lookbacks,
            feature_estimated_bytes=feature_stats.estimated_bytes,
        )

    metrics = _metrics_from_engine_result(
        engine_result,
        benchmark_returns=benchmark_context.daily_returns,
    )
    metrics = _mask_unavailable_walk_forward_metrics(
        metrics, _walk_forward_sample(rows).status
    )
    enriched_candidate = candidate.model_copy(update={"metrics": metrics})
    engine_summary = dict(engine_result.summary)
    execution_capacity_enabled = _execution_capacity_enabled(rows)
    engine_summary["execution_capacity"] = _execution_capacity_metadata(
        execution_capacity_enabled
    )
    engine_summary["buy_signal_count"] = _signal_action_count(engine_result, "BUY")
    engine_summary["sell_signal_count"] = _signal_action_count(engine_result, "SELL")
    execution_audit = _execution_audit(engine_result)
    engine_summary["execution_audit"] = execution_audit
    engine_summary["_storage_execution_ledger"] = _storage_execution_ledger(engine_result)
    available_ticker_count = _available_ticker_count(rows)
    requested_max_positions = _requested_max_positions(strategy_a)
    applied_max_positions = _applied_max_positions(strategy_a, available_ticker_count)
    engine_summary["ai_backtest_context"] = {
        "analysis_initial_capital_krw": CANONICAL_ANALYSIS_INITIAL_CAPITAL,
        "initial_capital_contract": "canonical_analysis_job_sealed_primary_contract",
        "available_ticker_count": available_ticker_count,
        "requested_max_positions": requested_max_positions,
        "applied_max_positions": applied_max_positions,
        "max_position_pct": _strategy_max_position_pct(strategy_a),
        "sizing_contract": "strategy_risk_constraints.max_position_pct",
        "gross_exposure_limit": 1.0,
        "cash_floor": 0.0,
        "leverage_allowed": False,
        "exposure_normalized": applied_max_positions != requested_max_positions,
    }
    split_policy = _walk_forward_split_policy(rows)
    walk_forward = _walk_forward_sample(rows)
    engine_summary["walk_forward_sample"] = _walk_forward_metadata(
        walk_forward, split_policy
    )
    engine_summary["benchmark_provenance"] = _benchmark_provenance(benchmark_context)
    public_metric_availability = _undefined_metric_availability(
        _summary_warning_list(engine_summary)
    )
    if walk_forward.status in {
        INSUFFICIENT_WALK_FORWARD_SAMPLE,
        UNSAFE_WALK_FORWARD_CANDIDATE,
    }:
        public_metric_availability.update(
            {
                "out_sample_return": {
                    "value": None,
                    "unavailable_reason": walk_forward.status,
                },
                "out_sample_sharpe": {
                    "value": None,
                    "unavailable_reason": walk_forward.status,
                },
                "benchmark_comparison": {
                    "value": None,
                    "unavailable_reason": walk_forward.status,
                },
            }
        )
    if public_metric_availability:
        engine_summary["public_metric_availability"] = public_metric_availability
    engine_summary["effective_trade_count"] = max(
        _summary_float_default(engine_summary, "trade_count", 0.0),
        float(execution_audit["executed_buy_count"]),
    )
    # This is produced beside the measured engine result, rather than reconstructed
    # by an HTTP serializer.  The public projection will fail closed if any field is
    # absent or malformed.
    engine_summary["performance_method_manifest"] = _performance_method_manifest(
        strategy_a,
        candidate,
        rows,
        engine_summary,
    )
    engine_summary["selection_buy_count"] = _selection_signal_action_count(
        engine_result, rows, "BUY"
    )
    evaluation = _CandidateEvaluation(
        candidate=enriched_candidate,
        engine_summary=engine_summary,
        equity_curve=_public_equity_curve(engine_result),
        objective_score=_objective_score(
            metrics,
            engine_summary,
            rows,
            benchmark_context=benchmark_context,
        ),
        ticker_actions=_ticker_actions(engine_result, rows, candidate.candidate_id),
        diagnostics={
            "candidate_id": candidate.candidate_id,
            "stage": "candidate_evaluation",
            "metrics_mode": metrics_mode,
            "input_rows": len(rows),
            "generated_signals": len(actions or ()),
            "cache_hit": False,
            "wall_seconds": round(time.perf_counter() - wall_started, 6),
            "cpu_seconds": round(time.process_time() - cpu_started, 6),
            "peak_rss_bytes": _peak_rss_bytes(),
            "action_build_seconds": round(action_build_seconds, 6),
            "action_cache_hit": action_cache_hit,
            "worker_pid": worker_pid,
        },
    )
    feature_stats = feature_store.stats()
    return _CandidateTaskResult(
        evaluation=evaluation,
        generated_actions=actions,
        generated_scores=scores,
        action_build_seconds=action_build_seconds,
        action_cache_hit=action_cache_hit,
        worker_pid=worker_pid,
        feature_cached_lookbacks=feature_stats.cached_lookbacks,
        feature_estimated_bytes=feature_stats.estimated_bytes,
    )


def run_candidate_backtest(
    strategy_a: AIStrategySpec,
    candidates: list[CodeCandidate],
    *,
    price_rows: Sequence[Mapping[str, Any]] | None = None,
    feature_coverage: Mapping[str, Any] | None = None,
    fallback_reasons: Sequence[str] | None = None,
    _session: _CandidateBacktestSession | None = None,
    _walk_forward_enabled: bool = True,
) -> CandidateBacktestResult:
    if not candidates:
        raise ValueError("at least one candidate is required")

    rows = _session.price_rows if _session is not None else _price_rows(price_rows)
    sample = _walk_forward_sample(rows)
    if _walk_forward_enabled and sample.status == READY_WALK_FORWARD:
        return _run_walk_forward_candidate_backtest(
            strategy_a,
            candidates,
            rows,
            feature_coverage=feature_coverage,
            fallback_reasons=fallback_reasons,
            benchmark_context=(
                _session.benchmark_context if _session is not None else None
            ),
        )
    owns_session = _session is None
    session = _session or _CandidateBacktestSession(strategy_a, rows)
    enriched_candidates: list[CodeCandidate] = []
    engine_summaries_by_candidate: dict[str, dict[str, Any]] = {}
    equity_curves_by_candidate: dict[str, list[BacktestEquityPoint]] = {}
    objective_scores_by_candidate: dict[str, float] = {}
    diagnostics_by_candidate: dict[str, dict[str, Any]] = {}
    ticker_actions_by_candidate: dict[str, list[dict[str, Any]]] = {}

    try:
        evaluations = session.evaluate(candidates)
        for evaluation in evaluations:
            if evaluation.quantstats_dependency_error:
                raise ModuleNotFoundError(QUANTSTATS_REQUIRED_MESSAGE)
            candidate = evaluation.candidate
            enriched_candidates.append(candidate)
            if evaluation.diagnostics is not None:
                diagnostics_by_candidate[candidate.candidate_id] = evaluation.diagnostics
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
            ticker_actions_by_candidate[candidate.candidate_id] = evaluation.ticker_actions
    except BaseException:
        if owns_session:
            session.close()
        raise

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
            if owns_session:
                session.close()
            raise ModuleNotFoundError(QUANTSTATS_REQUIRED_MESSAGE)
        if owns_session:
            session.close()
        raise ValueError("at least one candidate must pass validation and engine backtest")

    # The recommendation must be the strategy the user asked for. Selection used to be
    # a plain argmax over every candidate, so a generic template that happened to score
    # higher replaced the user's own rule - and the report then presented that template's
    # performance as the answer. Measured on five prompts, the user's rule ran and lost
    # on three of them; nothing in the result said so.
    #
    # Optimisation belongs inside the user's rule, not instead of it: variants of their
    # compiled conditions compete with each other, and the generic profiles stay in the
    # run only as baselines to compare against.
    own_rule = [c for c in valid_candidates if _is_user_rule(c)]
    selectable = own_rule or valid_candidates
    selectable = _within_turnover_cap(selectable, engine_summaries_by_candidate, rows)
    selected = max(
        selectable,
        key=lambda candidate: (
            objective_scores_by_candidate.get(candidate.candidate_id, float("-inf")),
            *_candidate_rank(candidate),
        ),
    )
    try:
        detailed = session.evaluate([selected], metrics_mode="full")[0]
    except BaseException:
        if owns_session:
            session.close()
        raise
    if detailed.quantstats_dependency_error:
        if owns_session:
            session.close()
        raise ModuleNotFoundError(QUANTSTATS_REQUIRED_MESSAGE)
    if (
        detailed.candidate.validation_ok
        and detailed.candidate.metrics is not None
        and detailed.engine_summary is not None
        and detailed.equity_curve is not None
        and detailed.objective_score is not None
    ):
        selected = detailed.candidate
        enriched_candidates = [
            selected if item.candidate_id == selected.candidate_id else item
            for item in enriched_candidates
        ]
        engine_summaries_by_candidate[selected.candidate_id] = detailed.engine_summary
        equity_curves_by_candidate[selected.candidate_id] = detailed.equity_curve
        objective_scores_by_candidate[selected.candidate_id] = detailed.objective_score
        ticker_actions_by_candidate[selected.candidate_id] = detailed.ticker_actions
        if detailed.diagnostics is not None:
            diagnostics_by_candidate[selected.candidate_id] = detailed.diagnostics

    try:
        result = CandidateBacktestResult(
            strategy_a=strategy_a,
            candidates=enriched_candidates,
            selected_candidate=selected,
            equity_curve=equity_curves_by_candidate[selected.candidate_id],
            engine_summary=engine_summaries_by_candidate[selected.candidate_id],
            engine_summaries_by_candidate=engine_summaries_by_candidate,
            objective_scores_by_candidate=objective_scores_by_candidate,
            ticker_actions=ticker_actions_by_candidate.get(selected.candidate_id, []),
            backtest_payload=_backtest_payload(
                strategy_a,
                rows,
                benchmark_context=session.benchmark_context,
            ),
            feature_coverage=dict(feature_coverage or {}),
            fallback_reasons=list(fallback_reasons or ()),
            execution_stats={
                **session.execution_stats(),
                "candidates": diagnostics_by_candidate,
            },
        )
        return _attach_walk_forward_artifact(result, len(candidates))
    finally:
        if owns_session:
            session.close()


def _rows_for_sessions(
    rows: Sequence[Mapping[str, Any]], sessions: Sequence[str]
) -> list[Mapping[str, Any]]:
    allowed = set(sessions)
    return sorted(
        (row for row in rows if str(row.get("date")) in allowed),
        key=lambda row: (str(row.get("date")), str(row.get("ticker", ""))),
    )


def _fold_engine(
    strategy: AIStrategySpec,
    candidate: CodeCandidate,
    context_rows: Sequence[Mapping[str, Any]],
    engine_rows: Sequence[Mapping[str, Any]],
    tradable_sessions: set[str],
):
    store = PreparedFeatureStore(context_rows, rows_are_sorted=True)
    action_map = {
        (str(row.get("date")), str(row.get("ticker", "")).zfill(6)): action
        for row, action in zip(
            store.rows,
            store.build_actions(candidate.strategy_ir, candidate.parameters),
            strict=True,
        )
    }
    ohlcv_rows, metric_rows = _engine_market_rows(engine_rows)
    spec = _engine_strategy_spec(
        strategy,
        candidate,
        available_ticker_count=_available_ticker_count(engine_rows),
        execution_capacity_enabled=_execution_capacity_enabled(engine_rows),
    )
    prepared = prepare_engine_market_data(
        spec, ohlcv_rows=ohlcv_rows, metric_rows=metric_rows,
        config=EngineBacktestRunConfig(initial_capital=CANONICAL_ANALYSIS_INITIAL_CAPITAL, write_outputs=False, talib=EngineTalibIndicatorConfig(enabled=False, mode="none"), metrics_mode="selection"),
        inputs_normalized=True,
    )
    actions = [
        action_map.get((str(row.date), str(row.ticker).zfill(6)), HOLD_SIGNAL_VALUE)
        if str(row.date) in tradable_sessions else HOLD_SIGNAL_VALUE
        for row in prepared.ohlcv_rows
    ]
    return _run_candidate_backtest(strategy, candidate, engine_rows, prepared_market=prepared, generated_actions=actions, metrics_mode="selection")


def _complete_target_returns(
    engine_result: Any, targets: set[str]
) -> dict[str, float] | None:
    """Read every engine equity point; public curve sampling must never gate execution."""
    returns: dict[str, float] = {}
    for point in getattr(engine_result, "equity_curve", ()):
        point_date = str(getattr(point, "date", ""))
        if point_date in targets:
            returns[point_date] = _finite_float(
                getattr(point, "daily_return", None),
                f"walk_forward_daily_return[{point_date}]",
            )
    return returns if set(returns) == targets else None


def _full_target_fills(engine_result: Any, targets: set[str]) -> list[dict[str, Any]]:
    return [
        payload
        for event in getattr(engine_result, "order_audit", ())
        if (payload := event.as_dict()).get("status") == "executed"
        and str(payload.get("date", payload.get("session", ""))) in targets
    ]


def _walk_forward_aggregate_metrics(returns: Sequence[float]) -> BacktestMetrics:
    total_return = _compound_returns(returns)
    sharpe = _native_sharpe_like(list(returns))
    return BacktestMetrics(
        sharpe_ratio=round(sharpe, METRIC_ROUND_DIGITS),
        max_drawdown=round(_max_drawdown_from_returns(returns), METRIC_ROUND_DIGITS),
        win_rate=(sum(value > 0.0 for value in returns) / len(returns) if returns else 0.0),
        total_return=round(total_return, METRIC_ROUND_DIGITS),
        in_sample_sharpe=0.0,
        out_sample_sharpe=round(sharpe, METRIC_ROUND_DIGITS),
        degradation=0.0,
        out_sample_return=round(total_return, METRIC_ROUND_DIGITS),
    )

def _run_walk_forward_candidate_backtest(
    strategy: AIStrategySpec,
    candidates: list[CodeCandidate],
    rows: Sequence[Mapping[str, Any]],
    *,
    feature_coverage: Mapping[str, Any] | None,
    fallback_reasons: Sequence[str] | None,
    benchmark_context: _BenchmarkContext | None = None,
) -> CandidateBacktestResult:
    if any(candidate.representation != "structured" for candidate in candidates):
        result = run_candidate_backtest(strategy, candidates, price_rows=rows, feature_coverage=feature_coverage, fallback_reasons=fallback_reasons, _walk_forward_enabled=False)
        masked = result.selected_candidate.model_copy(update={"metrics": _mask_unavailable_walk_forward_metrics(result.selected_candidate.metrics, UNSAFE_WALK_FORWARD_CANDIDATE)})
        return _attach_walk_forward_artifact(
            result.model_copy(
                update={
                    "selected_candidate": masked,
                    "walk_forward": WalkForwardPolicyResult(
                        status="unsafe_candidate",
                        unavailable_reason=UNSAFE_WALK_FORWARD_CANDIDATE,
                    ),
                }
            ),
            len(candidates),
        )

    claimed: set[str] = set()
    returns_by_session: dict[str, float] = {}
    selections: list[WalkForwardFoldSelection] = []
    fills: list[dict[str, Any]] = []
    evaluation_ledgers: list[dict[str, Any]] = []
    returns_by_candidate: dict[str, dict[str, float]] = {
        candidate.candidate_id: {} for candidate in candidates
    }
    fills_by_candidate: dict[str, list[dict[str, Any]]] = {
        candidate.candidate_id: [] for candidate in candidates
    }
    folds_by_candidate: dict[str, int] = {candidate.candidate_id: 0 for candidate in candidates}
    deduped = 0
    selected: CodeCandidate | None = None
    policy = _walk_forward_split_policy(rows)
    for fold in policy.folds:
        selection_sessions = (*fold.warmup_sessions, *fold.train_sessions, *fold.validation_sessions)
        selection_rows = _rows_for_sessions(rows, selection_sessions)
        # Selection engine sees warmup for features, but warmup orders are HOLD.
        eligible: list[CodeCandidate] = []
        for proposed in candidates:
            if not proposed.validation_ok:
                continue
            selection_engine = _fold_engine(
                strategy,
                proposed,
                selection_rows,
                selection_rows,
                set((*fold.train_sessions, *fold.validation_sessions)),
            )
            if not getattr(selection_engine, "equity_curve", None):
                continue
            metrics = _metrics_from_engine_result(selection_engine)
            eligible.append(proposed.model_copy(update={"metrics": metrics}))
        if not eligible:
            continue
        own = [candidate for candidate in eligible if _is_user_rule(candidate)]
        candidate = max(own or eligible, key=_candidate_rank)

        targets = tuple(session for session in fold.evaluation_sessions if session not in claimed)
        deduped += len(fold.evaluation_sessions) - len(targets)
        if not targets:
            continue
        target_set = set(targets)
        context_rows = _rows_for_sessions(rows, (*selection_sessions, *targets))
        # Fresh engine gets bridge + target only; actions retain all causal feature history.
        engine_rows = _rows_for_sessions(rows, (*fold.validation_sessions[-1:], *targets))
        fold_results: dict[str, tuple[dict[str, float], Any]] = {}
        eligible_by_id = {item.candidate_id: item for item in eligible}
        evaluation_candidates = [
            eligible_by_id.get(proposed.candidate_id, proposed)
            for proposed in candidates
            if proposed.validation_ok
        ]
        for evaluation_candidate in evaluation_candidates:
            candidate_engine = _fold_engine(
                strategy,
                evaluation_candidate,
                context_rows,
                engine_rows,
                target_set,
            )
            candidate_returns = _complete_target_returns(candidate_engine, target_set)
            if candidate_returns is not None:
                fold_results[evaluation_candidate.candidate_id] = (
                    candidate_returns,
                    candidate_engine,
                )
        selected_result = fold_results.get(candidate.candidate_id)
        if selected_result is None:
            continue
        target_returns, evaluation_engine = selected_result
        claimed.update(target_set)
        returns_by_session.update(target_returns)
        fills.extend(_full_target_fills(evaluation_engine, target_set))
        evaluation_ledgers.append(_storage_execution_ledger(evaluation_engine))
        for candidate_id, (candidate_returns, candidate_engine) in fold_results.items():
            returns_by_candidate[candidate_id].update(candidate_returns)
            fills_by_candidate[candidate_id].extend(
                _full_target_fills(candidate_engine, target_set)
            )
            folds_by_candidate[candidate_id] += 1
        selected = candidate
        digest = sha256(json.dumps({"fold": fold.fold_index, "candidate": _candidate_identity(candidate), "train": fold.train_sessions, "validation": fold.validation_sessions}, sort_keys=True).encode()).hexdigest()
        selections.append(WalkForwardFoldSelection(fold_index=fold.fold_index, selection_hash=digest, candidate_id=candidate.candidate_id, evaluation_sessions=list(targets)))

    months = {session[:7] for session in returns_by_session}
    ready = len(selections) >= WALK_FORWARD_MIN_VALID_FOLDS and len(months) >= WALK_FORWARD_MIN_UNIQUE_EVALUATION_MONTHS and len(returns_by_session) >= WALK_FORWARD_MIN_UNIQUE_EVALUATION_SESSIONS and len(returns_by_session) == len(claimed)
    ordered_sessions = sorted(returns_by_session) if ready else []
    daily_returns = {session: returns_by_session[session] for session in ordered_sessions}
    equity = 1.0
    curve: list[BacktestEquityPoint] = []
    for session in ordered_sessions:
        equity *= 1.0 + daily_returns[session]
        curve.append(BacktestEquityPoint(date=session, cumulative_return=round(equity - 1.0, METRIC_ROUND_DIGITS)))
    if selected is None:
        raise ValueError("walk-forward produced no complete evaluation fold")
    costs = sum(
        sum(
            float(fill.get(key, 0.0) or 0.0)
            for key in ("commission_cost", "tax_cost", "slippage_cost")
        )
        for fill in fills
    )
    aggregate_metrics = (
        _walk_forward_aggregate_metrics(list(daily_returns.values())) if ready else None
    )
    engine_summaries_by_candidate: dict[str, dict[str, Any]] = {}
    for proposed in candidates:
        candidate_returns = returns_by_candidate[proposed.candidate_id]
        candidate_months = {session[:7] for session in candidate_returns}
        candidate_ready = bool(
            folds_by_candidate[proposed.candidate_id] >= WALK_FORWARD_MIN_VALID_FOLDS
            and len(candidate_months) >= WALK_FORWARD_MIN_UNIQUE_EVALUATION_MONTHS
            and len(candidate_returns) >= WALK_FORWARD_MIN_UNIQUE_EVALUATION_SESSIONS
            and len(candidate_returns) == len(claimed)
        )
        candidate_fills = fills_by_candidate[proposed.candidate_id]
        candidate_costs = sum(
            sum(
                float(fill.get(key, 0.0) or 0.0)
                for key in ("commission_cost", "tax_cost", "slippage_cost")
            )
            for fill in candidate_fills
        )
        candidate_metrics = (
            _walk_forward_aggregate_metrics(
                [candidate_returns[session] for session in sorted(candidate_returns)]
            )
            if candidate_ready
            else None
        )
        engine_summaries_by_candidate[proposed.candidate_id] = {
            "walk_forward_policy": "rolling_selection_policy",
            "aggregate_oos_result": (
                {
                    "availability": "available",
                    "total_return": candidate_metrics.out_sample_return,
                    "sharpe_ratio": candidate_metrics.out_sample_sharpe,
                    "max_drawdown": candidate_metrics.max_drawdown,
                    "evaluation_session_count": len(candidate_returns),
                    "trade_count": len(candidate_fills),
                    "costs": candidate_costs,
                    "after_costs": True,
                }
                if candidate_metrics is not None
                else {
                    "availability": (
                        "unavailable" if proposed.validation_ok else "failed"
                    ),
                    "reason": (
                        INSUFFICIENT_WALK_FORWARD_SAMPLE
                        if proposed.validation_ok
                        else "candidate_validation_failed"
                    ),
                    "evaluation_session_count": len(candidate_returns),
                    "trade_count": len(candidate_fills),
                    "costs": candidate_costs,
                    "after_costs": True,
                }
            ),
        }
    execution_capacity_enabled = _execution_capacity_enabled(rows)
    engine_summary = {
        "walk_forward_sample": _walk_forward_metadata(_walk_forward_sample(rows), policy),
        "walk_forward_policy": "rolling_selection_policy",
        "initial_capital": CANONICAL_ANALYSIS_INITIAL_CAPITAL,
        "execution_timing": "next_open",
        "cost_model": {
            "commission_pct": float(
                strategy.risk_constraints.get("commission_pct", DEFAULT_COMMISSION_PCT)
            ),
            "tax_pct": float(strategy.risk_constraints.get("tax_pct", DEFAULT_TAX_PCT)),
            "slippage_pct": float(
                strategy.risk_constraints.get("slippage_pct", DEFAULT_SLIPPAGE_PCT)
            ),
        },
        "effective_trade_count": len(fills),
        "execution_capacity": _execution_capacity_metadata(
            execution_capacity_enabled
        ),
        "_storage_execution_ledger": _merge_storage_execution_ledgers(evaluation_ledgers),
    }
    engine_summary["performance_method_manifest"] = _performance_method_manifest(
        strategy,
        selected,
        rows,
        engine_summary,
    )
    result = CandidateBacktestResult(
        strategy_a=strategy,
        candidates=candidates,
        selected_candidate=selected,
        equity_curve=curve,
        engine_summary=engine_summary,
        engine_summaries_by_candidate=engine_summaries_by_candidate,
        backtest_payload=_backtest_payload(
            strategy,
            rows,
            benchmark_context=benchmark_context or _build_benchmark_context(rows),
        ),
        feature_coverage=dict(feature_coverage or {}),
        fallback_reasons=list(fallback_reasons or ()),
        execution_stats={
            "walk_forward": True,
            "evaluation_sessions": len(claimed),
        },
        walk_forward=WalkForwardPolicyResult(
            status="ready" if ready else "insufficient",
            unavailable_reason=None if ready else INSUFFICIENT_WALK_FORWARD_SAMPLE,
            fold_selections=selections,
            unique_evaluation_session_count=len(daily_returns),
            daily_returns=daily_returns,
            aggregate_metrics=aggregate_metrics,
            equity_curve=curve,
            fills=fills if ready else [],
            costs=costs if ready else 0.0,
            deduped_session_count=deduped,
        ),
    )
    return _attach_walk_forward_artifact(result, len(candidates))


def backtest_node(state: dict[str, Any]) -> dict[str, Any]:
    node_started = time.perf_counter()
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
    with _CandidateBacktestSession(
        strategy_a,
        rows,
        official_benchmark=state.get("official_benchmark"),
    ) as session:
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
        seen_candidates = {_candidate_identity(candidate) for candidate in all_candidates}
        fallback_reasons = list(state.get("backtest_code", {}).get("fallback_reasons", []))
        # Refinement operates only on the selection data. Once real walk-forward
        # evaluation is available, changing candidates after that evaluation would
        # leak evaluation evidence into the search. Otherwise retain the automatic
        # mode's established refinement budget.
        self_improvement_rounds = (
            0
            if _walk_forward_sample(rows).status == READY_WALK_FORWARD
            else MAX_SELF_IMPROVEMENT_ROUNDS
        )
        for iteration in range(1, self_improvement_rounds + 1):
            # The request-wide ceiling is checked here too, not only at node boundaries:
            # a self-improvement round can run for minutes, and stopping between rounds
            # keeps the candidates already evaluated instead of losing the node's work.
            raise_if_past_deadline()
            if time.perf_counter() - node_started >= _wall_budget_seconds():
                fallback_reasons.append(
                    f"self-improvement stopped after exceeding {_wall_budget_seconds():g}s wall budget"
                )
                break
            proposed = generate_self_improvement_candidates(
                strategy_a,
                state.get("backtest_code", {}).get("code_plan", {}),
                start_index=len(all_candidates) + 1,
                iteration=iteration,
                max_positions=max_positions,
            )
            improved = []
            for candidate in proposed:
                identity = _candidate_identity(candidate)
                if identity in seen_candidates:
                    continue
                seen_candidates.add(identity)
                improved.append(candidate)
                if len(improved) >= 6:
                    break
            if not improved:
                fallback_reasons.append(
                    f"self-improvement iteration {iteration}: no distinct candidates"
                )
                break
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
                report_activity(
                    "step",
                    label=f"자가개선 {iteration}차 · 개선 없음",
                    detail="선택 구간에서 개선은 없었습니다. 다음 제한 탐색 구간을 확인합니다.",
                )
        # The winner was chosen by argmax over every candidate tried, so its in-sample
        # numbers carry the bias of that search. N is only known here - the per-candidate
        # evaluations are cached and must not depend on how many siblings they had.
        result = _apply_selection_correction(result, len(all_candidates))
        result = result.model_copy(
            update={
                "fallback_reasons": fallback_reasons,
                "generated_strategy_blueprints": list(
                    state.get("backtest_code", {})
                    .get("code_plan", {})
                    .get("generated_strategies", [])
                ),
                "execution_stats": {
                    **result.execution_stats,
                    **session.execution_stats(),
                    "total_backtest_wall_seconds": round(time.perf_counter() - node_started, 6),
                    "configured_workers": _configured_worker_limit(),
                    "candidate_timeout_seconds": _candidate_timeout_seconds(),
                    "wall_budget_seconds": _wall_budget_seconds(),
                    "selection_policy": (
                        "performance_momentum_train_select_holdout_validate"
                        if strategy_a.selection_mode == "automatic"
                        else "bounded_candidate_refinement"
                    ),
                    "self_improvement_rounds_limit": self_improvement_rounds,
                },
            }
        )
    # The recommendation gate downstream needs to know whether this strategy's backtest
    # actually cleared the objective floor, not just what its metrics were.
    floor_reasons = objective_floor_reasons(result)
    return {
        "backtest": result.model_dump(),
        "strategy_validated": _passes_objective_floor(result),
        # Published whether or not the floor is enforcing, so the reader can see what the
        # acceptance check actually concluded rather than only its effect.
        "objective_floor": {
            "mode": validation_gate_mode(),
            "cleared": not floor_reasons,
            "reasons": floor_reasons,
        },
    }


def _apply_selection_correction(
    result: CandidateBacktestResult, candidate_count: int
) -> CandidateBacktestResult:
    """Record how wide the search was, and deflate the winner's Sharpe for it.

    Nothing about the run changes - the same candidate stays selected. What changes is
    that the headline now carries the size of the search that produced it, so an argmax
    over fifteen tries cannot be read as one strategy that happened to work.
    """

    metrics = result.selected_candidate.metrics
    if metrics is None:
        return result
    observations = max(1, metrics.in_sample_observations)
    adjusted = metrics.model_copy(
        update={
            "candidates_evaluated": max(1, candidate_count),
            "selection_adjusted_sharpe": round(
                metrics.in_sample_sharpe
                - _expected_max_sharpe(candidate_count, observations),
                METRIC_ROUND_DIGITS,
            ),
        }
    )
    return result.model_copy(
        update={
            "selected_candidate": result.selected_candidate.model_copy(
                update={"metrics": adjusted}
            )
        }
    )


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
    *,
    prepared_market: EnginePreparedMarketData,
    generated_actions: Sequence[int] | None,
    generated_scores: Sequence[float] | None = None,
    metrics_mode: str,
):
    actions = generated_actions
    scores = generated_scores
    if actions is None:
        generated_signals = _execute_candidate_code(candidate, price_rows)
        actions, scores = _compact_actions_from_signals(prepared_market, generated_signals)
    engine_spec = _engine_strategy_spec(
        strategy,
        candidate,
        available_ticker_count=_available_ticker_count(price_rows),
        execution_capacity_enabled=_execution_capacity_enabled(price_rows),
    )
    return run_engine_backtest(
        engine_spec,
        config=EngineBacktestRunConfig(
            initial_capital=CANONICAL_ANALYSIS_INITIAL_CAPITAL,
            write_outputs=False,
            talib=EngineTalibIndicatorConfig(enabled=False, mode="none"),
            metrics_mode=metrics_mode,
        ),
        prepared_market_data=prepared_market,
        generated_actions=actions,
        generated_scores=scores,
    )


def _compact_actions_from_signals(
    prepared_market: EnginePreparedMarketData,
    generated_signals: Sequence[GeneratedSignal],
) -> tuple[list[int], list[float]]:
    actions = [0] * len(prepared_market.ohlcv_rows)
    scores = [float("nan")] * len(prepared_market.ohlcv_rows)
    tickers_by_date: dict[str, list[str]] = {}
    for bar in prepared_market.ohlcv_rows:
        tickers_by_date.setdefault(bar.date.isoformat(), []).append(bar.ticker)
    for signal in generated_signals:
        ticker = signal.ticker
        if ticker is None:
            tickers = tickers_by_date.get(signal.date, [])
            if len(tickers) != 1:
                raise ValueError(f"generated signal date {signal.date} is ambiguous without ticker")
            ticker = tickers[0]
        key = (date.fromisoformat(signal.date), ticker)
        index = prepared_market.row_index_by_key.get(key)
        if index is None:
            raise ValueError(
                f"generated signal {signal.date}/{ticker} is not present in price rows"
            )
        actions[index] = int(SIGNAL_METRIC_VALUES[signal.action])
        if signal.action == "BUY" and signal.score is not None:
            scores[index] = float(signal.score)
    return actions, scores


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


def _storage_execution_ledger(engine_result: Any) -> dict[str, Any]:
    signals = [signal.as_dict() for signal in getattr(engine_result, "signals", [])]
    order_audit = [event.as_dict() for event in getattr(engine_result, "order_audit", [])]
    fills = [event for event in order_audit if event.get("status") == "executed"]
    trades = [trade.as_dict() for trade in getattr(engine_result, "trades", [])]
    positions: list[dict[str, Any]] = []
    quantities: dict[str, float] = defaultdict(float)
    for fill in fills:
        ticker = str(fill.get("ticker") or "")
        quantity = float(fill.get("filled_quantity") or 0)
        quantities[ticker] += quantity if fill.get("side") == "buy" else -quantity
        positions.append({"date": fill.get("date"), "ticker": ticker, "quantity": quantities[ticker], "fill_quantity": quantity, "side": fill.get("side"), "reason": fill.get("reason")})
    equity = [point.as_dict() for point in getattr(engine_result, "equity_curve", [])]
    ledger = {"signals": signals, "order_audit": order_audit, "fills": fills, "positions": positions, "trades": trades, "equity": equity}
    ledger["source_event_count"] = sum(len(value) for value in ledger.values() if isinstance(value, list))
    ledger["source_event_hash"] = sha256(
        json.dumps(
            {key: ledger[key] for key in ("signals", "order_audit", "fills", "positions", "trades", "equity")},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    return ledger


def _merge_storage_execution_ledgers(
    ledgers: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    keys = ("signals", "order_audit", "fills", "positions", "trades", "equity")
    merged: dict[str, Any] = {key: [] for key in keys}
    for ledger in ledgers:
        for key in keys:
            records = ledger.get(key, [])
            if isinstance(records, list):
                merged[key].extend(records)
    merged["source_event_count"] = sum(len(merged[key]) for key in keys)
    merged["source_event_hash"] = sha256(
        json.dumps(
            {key: merged[key] for key in keys},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    return merged

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
) -> tuple[list[Any], dict[tuple[date, str], dict[str, float]]]:
    ohlcv_rows: list[Any] = []
    metric_rows: dict[tuple[date, str], dict[str, float]] = {}

    raw_execution_declared = any(
        any(field in row for field in ("raw_open", "raw_high", "raw_low", "raw_close", "raw_volume"))
        for row in price_rows
    )
    for raw in price_rows:
        if "date" not in raw or "close" not in raw:
            raise ValueError("price rows must include date and adjusted close for signal generation")
        row_date = date.fromisoformat(str(raw["date"]))
        ticker = str(raw.get("ticker") or DEFAULT_FIXTURE_TICKER).zfill(6)
        if raw_execution_declared:
            required_raw_fields = ("raw_open", "raw_high", "raw_low", "raw_close", "raw_volume")
            missing = [field for field in required_raw_fields if raw.get(field) in (None, "")]
            if missing:
                raise ValueError(
                    f"raw_execution_unavailable:{row_date.isoformat()}/{ticker}:{','.join(missing)}"
                )
            open_price = _finite_float(raw["raw_open"], "raw_open")
            high = _finite_float(raw["raw_high"], "raw_high")
            low = _finite_float(raw["raw_low"], "raw_low")
            close = _finite_float(raw["raw_close"], "raw_close")
            volume = _finite_float(raw["raw_volume"], "raw_volume")
            raw_notional = raw.get("raw_notional")
            parsed_raw_notional = (
                None
                if raw_notional in (None, "")
                else _finite_float(raw_notional, "raw_notional")
            )
        else:
            # Price-only V3 plans explicitly use the official adjusted OHLCV series for
            # both signals and fills.  That is a source-backed execution basis, not a
            # fabricated raw quote; raw notional remains absent so capacity is not
            # claimed. Legacy fixture callers without a basis retain their historical
            # self-consistent fallback.
            close = _finite_float(raw["close"], "close")
            open_price = _finite_float(raw.get("open", close), "open")
            high = _finite_float(raw.get("high", max(open_price, close)), "high")
            low = _finite_float(raw.get("low", min(open_price, close)), "low")
            volume = _finite_float(raw.get("volume", DEFAULT_FIXTURE_VOLUME), "volume")
            raw_notional = raw.get("raw_notional")
            parsed_raw_notional = (
                None if raw_notional in (None, "") else _finite_float(raw_notional, "raw_notional")
            )
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
                raw_notional=parsed_raw_notional,
            )
        )
        metric_row: dict[str, float] = {}
        for key, value in raw.items():
            if str(key) in PRICE_FIELD_NAMES or not _is_numeric_metric(value):
                continue
            metric_row[str(key)] = float(value)
        metric_rows[(row_date, ticker)] = metric_row

    return ohlcv_rows, metric_rows


def _execution_capacity_enabled(price_rows: Sequence[Mapping[str, Any]]) -> bool:
    """Require source-provided traded value before claiming fill capacity.

    Raw OHLCV supports a costed next-open backtest. Raw traded value supports the
    additional participation-capacity constraint. When it is absent, leave it absent
    and disable only that constraint rather than creating a false close × volume value.
    """

    return bool(price_rows) and all(
        row.get("raw_notional") not in (None, "") for row in price_rows
    )


def _execution_capacity_metadata(enabled: bool) -> dict[str, bool | str | None]:
    """Record whether liquidity capacity was checked without inventing traded value."""

    if enabled:
        return {
            "enabled": True,
            "status": "source_raw_notional_validated",
            "reason_code": None,
            "detail": "Participation-capacity checks used source-provided traded value.",
        }
    return {
        "enabled": False,
        "status": "not_evaluated",
        "reason_code": "raw_notional_source_missing_or_uncovered",
        "detail": (
            "Price execution used raw OHLCV, but participation-capacity checks were "
            "not evaluated because source traded value is unavailable."
        ),
    }


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
    execution_capacity_enabled: bool = True,
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
        risk_controls=_engine_risk_controls(strategy, candidate=candidate),
        backtest={
            "cost_model": {
                "commission_pct": float(
                    strategy.risk_constraints.get("commission_pct", DEFAULT_COMMISSION_PCT)
                ),
                "tax_pct": float(
                    strategy.risk_constraints.get("tax_pct", DEFAULT_TAX_PCT)
                ),
                "slippage_pct": float(
                    strategy.risk_constraints.get("slippage_pct", DEFAULT_SLIPPAGE_PCT)
                ),
            },
            # Capacity is a separate claim from price execution. The engine can run
            # next-open fills using verified raw OHLCV even when source-provided KRX
            # traded value is unavailable. Never invent it from close × volume.
            "execution_capacity": {"enabled": execution_capacity_enabled},
        },
    )


def _engine_position_sizing(
    strategy: AIStrategySpec,
    *,
    available_ticker_count: int | None = None,
):
    applied_max_positions = _applied_max_positions(strategy, available_ticker_count)
    return EnginePositionSizing(max_positions=applied_max_positions)


def _engine_risk_controls(strategy: AIStrategySpec, *, candidate: CodeCandidate | None = None):
    """Risk controls for the engine, which is the only place a stop is applied.

    The candidate's own stop/target win when it has them: they are part of the search
    surface, and the action generator used to apply them itself. It no longer does -
    it only knows the signal-day close, while the engine knows the price actually paid
    at the next open - so the search values have to reach the engine or the search over
    them silently stops meaning anything.
    """

    raw = strategy.risk_constraints
    controls = EngineRiskControls()
    parameters = candidate.parameters if candidate is not None else None
    stop_loss_pct = _optional_positive_float(
        raw.get("stop_loss_pct"), "stop_loss_pct", upper_bound=1.0
    )
    take_profit_pct = _optional_positive_float(raw.get("take_profit_pct"), "take_profit_pct")
    if parameters is not None:
        stop_loss_pct = parameters.stop_loss_pct
        take_profit_pct = parameters.take_profit_pct
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
    return max(1, math.ceil(1.0 / _strategy_max_position_pct(strategy)))


def _applied_max_positions(
    strategy: AIStrategySpec, available_ticker_count: int | None = None
) -> int:
    requested = _requested_max_positions(strategy)
    if available_ticker_count is None or available_ticker_count <= 0:
        return requested
    return min(requested, available_ticker_count)


def _strategy_max_position_pct(strategy: AIStrategySpec) -> float:
    return required_max_position_pct(strategy.risk_constraints)


def _available_ticker_count(price_rows: Sequence[Mapping[str, Any]]) -> int:
    return _shared_available_ticker_count(price_rows)


def _ticker_actions(
    engine_result: Any, rows: Sequence[Mapping[str, Any]], candidate_id: str
) -> list[dict[str, Any]]:
    """Today's verdict per stock, taken from the run that was just validated.

    A backtest that ends yesterday already contains today's instruction: the last bar's
    signals are what the rule says now, and the engine's surviving positions are what the
    book holds now. Deriving the recommendation from anywhere else - re-evaluating the
    conditions in a separate code path, say - would produce a second answer that can
    disagree with the one the performance numbers came from.

    HOLD and SELL therefore need the position book, not the signal stream: the engine
    skips buys it has no cash or slot for, so a BUY signal does not mean a position
    exists. Only names the rule actually acts on are returned; a name the strategy is
    neither in nor entering has no recommendation to give, and the caller fills those in
    as WATCH against whatever list it is presenting.
    """

    dates = {str(row.get("date") or "") for row in rows}
    if not dates:
        return []
    as_of = max(dates)
    summary = getattr(engine_result, "summary", {}) or {}
    held_raw = summary.get("open_position_tickers")
    held = {str(t) for t in held_raw} if isinstance(held_raw, Sequence) and not isinstance(
        held_raw, (str, bytes)
    ) else set()

    last_signal: dict[str, str] = {}
    for signal in getattr(engine_result, "signals", []):
        if str(getattr(signal, "date", "")) != as_of:
            continue
        action = str(getattr(signal, "action", "")).upper()
        ticker = str(getattr(signal, "ticker", ""))
        if not ticker:
            continue
        if action.endswith("BUY"):
            last_signal[ticker] = "BUY"
        elif action.endswith("SELL"):
            last_signal[ticker] = "SELL"

    closes = {
        str(row.get("ticker")): row.get("close")
        for row in rows
        if str(row.get("date") or "") == as_of
    }
    names = {str(row.get("ticker")): row.get("name") for row in rows if row.get("name")}

    actions: list[dict[str, Any]] = []
    for ticker in sorted(held | set(last_signal)):
        signal = last_signal.get(ticker)
        if ticker in held:
            action = "SELL" if signal == "SELL" else "HOLD"
            reason = (
                "청산 조건 충족 - 보유 종목 매도"
                if signal == "SELL"
                else "청산 조건 미충족 - 보유 유지"
            )
        elif signal == "BUY":
            action, reason = "BUY", "진입 조건 충족 - 신규 매수"
        else:
            # A SELL on a name the book is not in is not an instruction to anyone.
            continue
        actions.append(
            {
                "ticker": ticker,
                "name": names.get(ticker) or ticker,
                "action": action,
                "reason": reason,
                "as_of_date": as_of,
                "close": closes.get(ticker),
                "source_candidate_id": candidate_id,
            }
        )
    return actions


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


def _expected_max_sharpe(candidate_count: int, observations: int) -> float:
    """The in-sample Sharpe a skill-free search over `candidate_count` tries would give.

    Picking the best of N candidates is an argmax over N noisy estimates, so the winner's
    in-sample Sharpe is biased upward even when nothing has any edge. This is the
    standard expected-maximum-of-N-normals approximation used for the deflated Sharpe
    ratio, scaled by the standard error of a Sharpe estimate over `observations` bars.

    Measured with candidates whose trades are random on real prices: mean return -3.7%,
    best-of-six +16.2%. Nearly twenty points of headline out of nothing.
    """

    if candidate_count <= 1 or observations <= 1:
        return 0.0
    # E[max of n standard normals], Gumbel approximation - accurate to ~1% for n >= 4
    # and conservative (too small, so it under-corrects) for the n = 2..3 the first
    # round uses.
    euler = 0.5772156649015329
    n = float(candidate_count)
    expected_max_z = (1.0 - euler) * _normal_quantile(1.0 - 1.0 / n) + euler * _normal_quantile(
        1.0 - 1.0 / (n * math.e)
    )
    # Standard error of an annualised Sharpe estimate over `observations` daily bars.
    return expected_max_z * math.sqrt(252.0 / observations)


def _normal_quantile(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation)."""

    if p <= 0.0 or p >= 1.0:
        return 0.0
    a = (-39.69683028665376, 220.9460984245205, -275.9285104469687,
         138.3577518672690, -30.66479806614716, 2.506628277459239)
    b = (-54.47609879822406, 161.5858368580409, -155.6989798598866,
         66.80131188771972, -13.28068155288572)
    c = (-0.007784894002430293, -0.3223964580411365, -2.400758277161838,
         -2.549732539343734, 4.374664141464968, 2.938163982698783)
    d = (0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416)
    plow, phigh = 0.02425, 1.0 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
        ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0
    )


def _metrics_from_engine_result(
    engine_result,
    *,
    price_rows: Sequence[Mapping[str, Any]] | None = None,
    benchmark_returns: Sequence[float] | None = None,
    candidate_count: int = 1,
) -> BacktestMetrics:
    summary = engine_result.summary
    metric_warnings = _summary_warning_list(summary)
    selection_mode = summary.get("metrics_mode") == "selection"
    daily_returns = (
        _native_returns_from_equity_curve(engine_result.equity_curve)
        if selection_mode
        else returns_from_equity_curve(engine_result.equity_curve)
    )
    sharpe = _summary_float_default(
        summary, "sharpe", _summary_float_default(summary, "daily_sharpe_like", 0.0)
    )
    in_sample_sharpe, out_sample_sharpe = _split_sharpes(
        daily_returns,
        metric_warnings,
        native=selection_mode,
    )
    degradation = _degradation(in_sample_sharpe, out_sample_sharpe)
    split_index = max(1, int(len(daily_returns) * BACKTEST_SPLIT_FRACTION))
    in_sample_returns = daily_returns[:split_index]
    out_sample_returns = daily_returns[split_index:]
    selection_adjusted_sharpe = in_sample_sharpe - _expected_max_sharpe(
        candidate_count, len(in_sample_returns)
    )
    resolved_benchmark_returns = (
        benchmark_returns
        if benchmark_returns is not None
        else _benchmark_daily_returns(price_rows or ())
    )
    comparison_length = min(len(daily_returns), len(resolved_benchmark_returns))
    strategy_comparison_returns = daily_returns[:comparison_length]
    benchmark_comparison_returns = resolved_benchmark_returns[:comparison_length]
    comparison_split_index = min(split_index, comparison_length)
    in_sample_benchmark_returns = benchmark_comparison_returns[:comparison_split_index]
    out_sample_benchmark_returns = benchmark_comparison_returns[comparison_split_index:]
    in_sample_benchmark_return = _compound_returns(in_sample_benchmark_returns)
    out_sample_benchmark_return = _compound_returns(out_sample_benchmark_returns)
    in_sample_return = _compound_returns(in_sample_returns)
    out_sample_return = _compound_returns(out_sample_returns)
    period_stats = _benchmark_period_stats(
        strategy_comparison_returns,
        benchmark_comparison_returns,
    )
    in_sample_period_stats = _benchmark_period_stats(
        strategy_comparison_returns[:comparison_split_index],
        in_sample_benchmark_returns,
    )
    out_sample_period_stats = _benchmark_period_stats(
        strategy_comparison_returns[comparison_split_index:],
        out_sample_benchmark_returns,
    )
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
        in_sample_return=round(in_sample_return, METRIC_ROUND_DIGITS),
        in_sample_max_drawdown=round(
            _max_drawdown_from_returns(in_sample_returns), METRIC_ROUND_DIGITS
        ),
        out_sample_return=round(out_sample_return, METRIC_ROUND_DIGITS),
        out_sample_max_drawdown=round(
            _max_drawdown_from_returns(out_sample_returns), METRIC_ROUND_DIGITS
        ),
        in_sample_observations=len(in_sample_returns),
        candidates_evaluated=max(1, candidate_count),
        selection_adjusted_sharpe=round(selection_adjusted_sharpe, METRIC_ROUND_DIGITS),
        in_sample_benchmark_return=round(in_sample_benchmark_return, METRIC_ROUND_DIGITS),
        out_sample_benchmark_return=round(out_sample_benchmark_return, METRIC_ROUND_DIGITS),
        in_sample_excess_return=round(
            in_sample_return - in_sample_benchmark_return,
            METRIC_ROUND_DIGITS,
        ),
        out_sample_excess_return=round(
            out_sample_return - out_sample_benchmark_return,
            METRIC_ROUND_DIGITS,
        ),
        benchmark_period_count=period_stats.count,
        benchmark_period_win_rate=round(period_stats.win_rate, METRIC_ROUND_DIGITS),
        benchmark_period_loss_rate=round(period_stats.loss_rate, METRIC_ROUND_DIGITS),
        in_sample_benchmark_period_count=in_sample_period_stats.count,
        in_sample_benchmark_period_win_rate=round(
            in_sample_period_stats.win_rate, METRIC_ROUND_DIGITS
        ),
        in_sample_benchmark_period_loss_rate=round(
            in_sample_period_stats.loss_rate, METRIC_ROUND_DIGITS
        ),
        out_sample_benchmark_period_count=out_sample_period_stats.count,
        out_sample_benchmark_period_win_rate=round(
            out_sample_period_stats.win_rate, METRIC_ROUND_DIGITS
        ),
        out_sample_benchmark_period_loss_rate=round(
            out_sample_period_stats.loss_rate, METRIC_ROUND_DIGITS
        ),
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
    daily_returns: list[float],
    metric_warnings: list[dict[str, str]],
    *,
    native: bool = False,
) -> tuple[float, float]:
    sharpe_function = _native_sharpe_like if native else _sharpe_like
    if len(daily_returns) < MIN_RETURNS_FOR_SPLIT:
        full_sample = sharpe_function(
            daily_returns, metric_name="full_sample_sharpe", metric_warnings=metric_warnings
        )
        return full_sample, full_sample
    split_index = max(1, int(len(daily_returns) * BACKTEST_SPLIT_FRACTION))
    return (
        sharpe_function(
            daily_returns[:split_index],
            metric_name="in_sample_sharpe",
            metric_warnings=metric_warnings,
        ),
        sharpe_function(
            daily_returns[split_index:],
            metric_name="out_sample_sharpe",
            metric_warnings=metric_warnings,
        ),
    )


def _compound_returns(daily_returns: Sequence[float]) -> float:
    return math.prod((1.0 + daily_return for daily_return in daily_returns), start=1.0) - 1.0


def _walk_forward_split_policy(price_rows: Sequence[Mapping[str, Any]]) -> _SplitPolicy:
    sessions_by_month: dict[str, list[str]] = defaultdict(list)
    for session in sorted(
        {str(row.get("date")) for row in price_rows if row.get("date") is not None}
    ):
        sessions_by_month[session[:7]].append(session)
    months = tuple(sorted(sessions_by_month))
    warmup_sessions = tuple(
        session
        for month in months[:WALK_FORWARD_WARMUP_MONTHS]
        for session in sessions_by_month[month]
    )
    folds: list[_WalkForwardFold] = []
    span = (
        WALK_FORWARD_TRAIN_MONTHS
        + WALK_FORWARD_VALIDATION_MONTHS
        + WALK_FORWARD_EVALUATION_MONTHS
    )
    for start in range(0, len(months) - (span + WALK_FORWARD_WARMUP_MONTHS) + 1, WALK_FORWARD_ROLL_MONTHS):
        warmup_months = months[start : start + WALK_FORWARD_WARMUP_MONTHS]
        train_start = start + WALK_FORWARD_WARMUP_MONTHS
        train_months = months[train_start : train_start + WALK_FORWARD_TRAIN_MONTHS]
        validation_start = train_start + WALK_FORWARD_TRAIN_MONTHS
        validation_months = months[validation_start : validation_start + WALK_FORWARD_VALIDATION_MONTHS]
        evaluation_months = months[validation_start + WALK_FORWARD_VALIDATION_MONTHS : validation_start + WALK_FORWARD_VALIDATION_MONTHS + WALK_FORWARD_EVALUATION_MONTHS]
        fold = _WalkForwardFold(
            fold_index=len(folds),
            warmup_sessions=tuple(session for month in warmup_months for session in sessions_by_month[month]),
            train_sessions=tuple(session for month in train_months for session in sessions_by_month[month]),
            validation_sessions=tuple(session for month in validation_months for session in sessions_by_month[month]),
            evaluation_sessions=tuple(session for month in evaluation_months for session in sessions_by_month[month]),
        )
        if fold.warmup_sessions and fold.train_sessions and fold.validation_sessions and fold.evaluation_sessions:
            folds.append(fold)
    final_lockbox_sessions = folds[-1].evaluation_sessions if folds else ()
    return _SplitPolicy(
        warmup_sessions=warmup_sessions,
        folds=tuple(folds),
        final_lockbox_sessions=final_lockbox_sessions,
    )


def _walk_forward_sample(price_rows: Sequence[Mapping[str, Any]]) -> _WalkForwardSample:
    sessions = {str(row.get("date")) for row in price_rows if row.get("date") is not None}
    policy = _walk_forward_split_policy(price_rows)
    evaluation_sessions = [session for fold in policy.folds for session in fold.evaluation_sessions]
    unique_evaluation_sessions = set(evaluation_sessions)
    evaluation_months = {session[:7] for session in unique_evaluation_sessions}
    meets_minimum = (
        len(policy.folds) >= WALK_FORWARD_MIN_VALID_FOLDS
        and len(evaluation_months) >= WALK_FORWARD_MIN_UNIQUE_EVALUATION_MONTHS
        and len(unique_evaluation_sessions) >= WALK_FORWARD_MIN_UNIQUE_EVALUATION_SESSIONS
    )
    return _WalkForwardSample(
        session_count=len(sessions),
        valid_fold_count=len(policy.folds),
        unique_evaluation_month_count=len(evaluation_months),
        unique_evaluation_session_count=len(unique_evaluation_sessions),
        status=READY_WALK_FORWARD if meets_minimum else INSUFFICIENT_WALK_FORWARD_SAMPLE,
    )


def _walk_forward_metadata(
    sample: _WalkForwardSample, policy: _SplitPolicy | None = None
) -> dict[str, Any]:
    return {
        "policy": "warmup_1m_train_12m_validation_3m_evaluation_1m_roll_1m",
        "session_count": sample.session_count,
        "valid_fold_count": sample.valid_fold_count,
        "unique_evaluation_month_count": sample.unique_evaluation_month_count,
        "unique_evaluation_session_count": sample.unique_evaluation_session_count,
        "minimums": {
            "unique_evaluation_sessions": WALK_FORWARD_MIN_UNIQUE_EVALUATION_SESSIONS,
            "valid_folds": WALK_FORWARD_MIN_VALID_FOLDS,
            "unique_evaluation_months": WALK_FORWARD_MIN_UNIQUE_EVALUATION_MONTHS,
        },
        "status": sample.status,
        # QV-OOS-01 asks for the seed behind candidate selection. There is none to
        # report: no path in `ai_graph` or `backtest_module` draws from an RNG, so a
        # run is reproducible from its inputs alone and `slot_priority` - score first,
        # ticker only as a tie-break - fixes the order whenever scores collide.
        # Emitting a number here would name a knob that does not exist, which is worse
        # than saying so; a reader checking reproducibility needs the basis, not a digit.
        "selection_seed": None,
        "selection_determinism": "deterministic_no_rng",
        "selection_tie_break": "slot_priority:(-score, ticker)",
        # Eligibility says the session boundary is large enough to calculate OOS
        # statistics. It is deliberately separate from availability: a real result
        # has not been calculated until the rolling evaluation engine supplies it.
        "aggregate_oos_eligible": sample.status == READY_WALK_FORWARD,
        "aggregate_oos_available": False,
        "aggregate_oos_result": {
            "availability": "unavailable",
            "reason": (
                "aggregate_oos_not_computed"
                if sample.status == READY_WALK_FORWARD
                else sample.status
            ),
        },
        "candidates_evaluated": None,
        "benchmark_comparison_available": False,
        "selection_scope": "train_validation_only",
        "final_lockbox_excluded_from_selection": True,
        "unavailable_reason": None if sample.status == READY_WALK_FORWARD else sample.status,
        "fold_evaluation_months": [
            fold.evaluation_month for fold in (policy.folds if policy else ())
        ],
        "final_lockbox_sessions": list(policy.final_lockbox_sessions) if policy else [],
    }


def _walk_forward_oos_result(
    walk_forward: WalkForwardPolicyResult | None,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose the result of rolling evaluation, or one stable reason it is absent."""

    if walk_forward is not None and walk_forward.aggregate_metrics is not None:
        metrics = walk_forward.aggregate_metrics
        return {
            "availability": "available",
            "total_return": metrics.out_sample_return,
            "sharpe_ratio": metrics.out_sample_sharpe,
            "max_drawdown": metrics.max_drawdown,
            "evaluation_session_count": walk_forward.unique_evaluation_session_count,
        }

    reason = (
        walk_forward.unavailable_reason
        if walk_forward is not None
        else metadata.get("unavailable_reason")
    )
    return {
        "availability": "unavailable",
        "reason": str(reason or "aggregate_oos_not_computed"),
    }


def _attach_walk_forward_artifact(
    result: CandidateBacktestResult,
    candidate_count: int,
) -> CandidateBacktestResult:
    """Bind search width and the actual OOS result to the same output artifact."""

    engine_summary = dict(result.engine_summary)
    existing = engine_summary.get("walk_forward_sample")
    if not isinstance(existing, Mapping):
        return result

    artifact = _walk_forward_artifact(existing, candidate_count, result.walk_forward)
    backtest_payload = dict(result.backtest_payload)
    backtest_payload["walk_forward_sample"] = artifact
    return result.model_copy(
        update={
            "engine_summary": {**engine_summary, "walk_forward_sample": artifact},
            "backtest_payload": backtest_payload,
        }
    )


def _walk_forward_artifact(
    metadata: Mapping[str, Any],
    candidate_count: int,
    walk_forward: WalkForwardPolicyResult | None,
) -> dict[str, Any]:
    """Return one OOS artifact containing boundaries, search width, and result."""

    oos_result = _walk_forward_oos_result(walk_forward, metadata)
    return {
        **metadata,
        "candidates_evaluated": max(1, candidate_count),
        "aggregate_oos_available": oos_result["availability"] == "available",
        "aggregate_oos_result": oos_result,
    }

def _benchmark_daily_returns(
    price_rows: Sequence[Mapping[str, Any]],
) -> list[float]:
    curve, _ = _equal_weight_benchmark_curve(price_rows)
    return _daily_returns_from_benchmark_curve(curve)


def _daily_returns_from_benchmark_curve(
    curve: Sequence[BacktestEquityPoint],
) -> list[float]:
    if len(curve) < 2:
        return []
    returns: list[float] = []
    previous_equity = 1.0 + float(curve[0].cumulative_return)
    for point in curve[1:]:
        current_equity = 1.0 + float(point.cumulative_return)
        if previous_equity <= 0.0:
            return []
        returns.append(current_equity / previous_equity - 1.0)
        previous_equity = current_equity
    return returns


def _build_benchmark_context(
    price_rows: Sequence[Mapping[str, Any]],
    official_benchmark: Mapping[str, Any] | None = None,
) -> _BenchmarkContext:
    """Keep auxiliary proxy legs separate from the optional official primary series."""

    auxiliary_curve, _ = _equal_weight_benchmark_curve(price_rows)
    selection_days = max(
        1,
        int(len({str(row.get("date")) for row in price_rows}) * BACKTEST_SPLIT_FRACTION),
    )
    selection_index = min(max(0, selection_days - 1), len(auxiliary_curve) - 1)
    selection_return = (
        float(auxiliary_curve[selection_index].cumulative_return) if auxiliary_curve else 0.0
    )
    total_return, coverage, unavailable_reason = _official_benchmark_total_return(
        price_rows, official_benchmark
    )
    return _BenchmarkContext(
        daily_returns=tuple(_daily_returns_from_benchmark_curve(auxiliary_curve)),
        selection_days=selection_days,
        selection_return=selection_return,
        total_return=total_return,
        primary_available=total_return is not None,
        primary_unavailable_reason=unavailable_reason,
        auxiliary_label=AUXILIARY_BENCHMARK_LABEL,
        primary_coverage=coverage,
    )


def _official_benchmark_total_return(
    price_rows: Sequence[Mapping[str, Any]],
    official_benchmark: Mapping[str, Any] | None,
) -> tuple[float | None, dict[str, Any] | None, str | None]:
    if not isinstance(official_benchmark, Mapping) or not official_benchmark:
        return None, None, PRIMARY_BENCHMARK_MISSING_INPUT_REASON
    if not official_benchmark.get("available"):
        # This value reaches public metric details.  The source adapter may have
        # caught a driver exception, so its explanatory text must never cross this
        # boundary even if an older adapter or persisted job supplied it.
        return None, None, PRIMARY_BENCHMARK_SOURCE_UNAVAILABLE_REASON

    sessions = sorted({str(row.get("date")) for row in price_rows if row.get("date")})
    if not sessions:
        return None, None, "the backtest window has no sessions to measure a benchmark over"
    kospi = _official_benchmark_levels(official_benchmark.get("kospi_tr"), sessions)
    kosdaq = _official_benchmark_levels(official_benchmark.get("kosdaq_tr"), sessions)
    covered = sorted(set(kospi) & set(kosdaq))
    coverage: dict[str, Any] = {
        "backtest_sessions": len(sessions),
        "covered_sessions": len(covered),
        "coverage_ratio": round(len(covered) / len(sessions), METRIC_ROUND_DIGITS),
        "minimum_coverage_ratio": OFFICIAL_BENCHMARK_MIN_SESSION_COVERAGE,
        "first_session": sessions[0],
        "last_session": sessions[-1],
        "first_session_covered": bool(covered) and covered[0] == sessions[0],
        "last_session_covered": bool(covered) and covered[-1] == sessions[-1],
    }
    if not covered:
        return None, coverage, (
            "official KOSPI and KOSDAQ TR levels share no session with the backtest window "
            f"({sessions[0]}..{sessions[-1]})"
        )
    if not coverage["first_session_covered"] or not coverage["last_session_covered"]:
        return None, coverage, (
            "official TR levels do not cover both endpoints of the backtest window "
            f"({sessions[0]}..{sessions[-1]}); covered {covered[0]}..{covered[-1]}"
        )
    if coverage["coverage_ratio"] < OFFICIAL_BENCHMARK_MIN_SESSION_COVERAGE:
        return None, coverage, (
            f"official TR levels cover {len(covered)}/{len(sessions)} backtest sessions, "
            f"below the required {OFFICIAL_BENCHMARK_MIN_SESSION_COVERAGE:.0%}"
        )
    weights = _lagged_official_benchmark_weights(
        official_benchmark.get("monthly_weights"), covered
    )
    try:
        _, total_return = _official_krx_tr_benchmark_curve(kospi, kosdaq, weights)
    except ValueError as error:
        return None, coverage, f"official benchmark curve could not be computed: {error}"
    if total_return is None:
        return None, coverage, "official benchmark curve produced no observations"
    return float(total_return), coverage, None


def _official_benchmark_levels(
    series: Any, sessions: Sequence[str]
) -> dict[str, float]:
    if not isinstance(series, Mapping):
        return {}
    wanted = set(sessions)
    levels: dict[str, float] = {}
    for raw_date, raw_value in series.items():
        session = str(raw_date)
        if session not in wanted:
            continue
        try:
            level = _finite_float(raw_value, "official benchmark TR level")
        except (TypeError, ValueError):
            continue
        if level > 0.0:
            levels[session] = level
    return levels


def _lagged_official_benchmark_weights(
    monthly_weights: Any, sessions: Sequence[str]
) -> dict[str, tuple[float, float]]:
    published: dict[str, tuple[float, float]] = {}
    if isinstance(monthly_weights, Mapping):
        for raw_month, raw_weights in monthly_weights.items():
            pair = _official_benchmark_weight_pair(raw_weights)
            if pair is not None:
                published[str(raw_month)[:7]] = pair
    lagged: dict[str, tuple[float, float]] = {}
    for session in sessions:
        month = str(session)[:7]
        if month in lagged:
            continue
        previous = _previous_month(month)
        if previous in published:
            lagged[month] = published[previous]
    return lagged


def _official_benchmark_weight_pair(value: Any) -> tuple[float, float] | None:
    if isinstance(value, Mapping):
        candidate = (value.get("kospi_weight"), value.get("kosdaq_weight"))
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes):
        if len(value) != 2:
            return None
        candidate = (value[0], value[1])
    else:
        return None
    try:
        return (
            _finite_float(candidate[0], "kospi_weight"),
            _finite_float(candidate[1], "kosdaq_weight"),
        )
    except (TypeError, ValueError):
        return None


def _previous_month(month: str) -> str:
    try:
        year, month_number = (int(part) for part in month.split("-", 1))
    except ValueError:
        return month
    if month_number == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month_number - 1:02d}"


def _benchmark_provenance(context: _BenchmarkContext) -> dict[str, Any]:
    return {
        "primary": {
            "label": PRIMARY_BENCHMARK_LABEL,
            "method": PRIMARY_BENCHMARK_METHOD,
            "available": context.primary_available,
            "official_series_and_lagged_weights": context.primary_available,
            "return": context.total_return if context.primary_available else None,
            "unavailable_reason": context.primary_unavailable_reason,
            "session_coverage": (
                dict(context.primary_coverage)
                if context.primary_coverage is not None
                else None
            ),
        },
        "auxiliary": {
            "label": context.auxiliary_label,
            "method": AUXILIARY_BENCHMARK_METHOD,
            "warning": AUXILIARY_BENCHMARK_WARNING,
        },
    }


def _official_krx_tr_benchmark_curve(
    kospi_tr: Mapping[str, float],
    kosdaq_tr: Mapping[str, float],
    lagged_target_weights: Mapping[str, tuple[float, float]],
) -> tuple[list[BacktestEquityPoint], float | None]:
    """Monthly-rebalanced KOSPI/KOSDAQ TR benchmark with fixed intra-month units.

    Each month's units are set from that month's first available TR observations and the
    target weights lagged from the prior month. Units then remain fixed until the next
    month, so daily weights drift with relative performance rather than being silently
    reset every session.
    """
    dates = sorted(set(kospi_tr) & set(kosdaq_tr))
    if not dates:
        return [], None
    units: tuple[float, float] | None = None
    active_month: str | None = None
    curve: list[BacktestEquityPoint] = []
    base_value: float | None = None
    # Missing monthly weights are a data-contract failure, never a 50/50 fallback.
    for current_date in dates:
        month = current_date[:7]
        if month != active_month:
            if month not in lagged_target_weights:
                raise ValueError(f"missing lagged official benchmark weights for {month}")
            weights = lagged_target_weights[month]
            kospi_weight, kosdaq_weight = (float(weights[0]), float(weights[1]))
            if (
                not math.isfinite(kospi_weight)
                or not math.isfinite(kosdaq_weight)
                or kospi_weight < 0.0
                or kosdaq_weight < 0.0
                or not math.isclose(kospi_weight + kosdaq_weight, 1.0, abs_tol=1e-9)
            ):
                raise ValueError(
                    "official benchmark target weights must be finite, non-negative, and sum to 1"
                )
            kospi_level = _finite_float(kospi_tr[current_date], "kospi_tr")
            kosdaq_level = _finite_float(kosdaq_tr[current_date], "kosdaq_tr")
            if kospi_level <= 0.0 or kosdaq_level <= 0.0:
                raise ValueError("official benchmark TR levels must be positive")
            portfolio_value = (
                1.0
                if units is None
                else units[0] * kospi_level + units[1] * kosdaq_level
            )
            units = (
                portfolio_value * kospi_weight / kospi_level,
                portfolio_value * kosdaq_weight / kosdaq_level,
            )
            active_month = month
        assert units is not None
        value = (
            units[0] * _finite_float(kospi_tr[current_date], "kospi_tr")
            + units[1] * _finite_float(kosdaq_tr[current_date], "kosdaq_tr")
        )
        if base_value is None:
            base_value = value
        curve.append(
            BacktestEquityPoint(
                date=current_date,
                cumulative_return=round(value / base_value - 1.0, METRIC_ROUND_DIGITS),
            )
        )
    return curve, curve[-1].cumulative_return


def _benchmark_period_stats(
    strategy_returns: Sequence[float],
    benchmark_returns: Sequence[float],
) -> _BenchmarkPeriodStats:
    """Compare fixed quarter blocks without cherry-picking favourable dates."""

    length = min(len(strategy_returns), len(benchmark_returns))
    wins = 0
    losses = 0
    count = 0
    for start in range(0, length, BENCHMARK_EVALUATION_PERIOD_DAYS):
        end = min(length, start + BENCHMARK_EVALUATION_PERIOD_DAYS)
        if end - start < BENCHMARK_EVALUATION_PERIOD_DAYS:
            break
        strategy_return = _compound_returns(strategy_returns[start:end])
        benchmark_return = _compound_returns(benchmark_returns[start:end])
        count += 1
        if strategy_return > benchmark_return + 1e-12:
            wins += 1
        elif strategy_return < benchmark_return - 1e-12:
            losses += 1
    if count == 0:
        return _BenchmarkPeriodStats(count=0, win_rate=0.0, loss_rate=0.0)
    return _BenchmarkPeriodStats(
        count=count,
        win_rate=wins / count,
        loss_rate=losses / count,
    )


def _max_drawdown_from_returns(daily_returns: Sequence[float]) -> float:
    equity = 1.0
    peak = equity
    max_drawdown = 0.0
    for daily_return in daily_returns:
        equity *= 1.0 + daily_return
        peak = max(peak, equity)
        if peak > 0.0:
            max_drawdown = min(max_drawdown, equity / peak - 1.0)
    return max_drawdown


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


def _native_returns_from_equity_curve(equity_curve: Sequence[Any]) -> list[float]:
    values = [float(point.total_equity) for point in equity_curve]
    return [
        current / previous - 1.0 for previous, current in zip(values, values[1:]) if previous != 0.0
    ]


def _native_sharpe_like(
    daily_returns: list[float],
    *,
    metric_name: str = "sharpe",
    metric_warnings: list[dict[str, str]] | None = None,
) -> float:
    if len(daily_returns) < 2:
        if metric_warnings is not None:
            metric_warnings.append({"metric": metric_name, "reason": "fewer than two returns"})
        return 0.0
    mean_return = sum(daily_returns) / len(daily_returns)
    variance = sum((value - mean_return) ** 2 for value in daily_returns) / (len(daily_returns) - 1)
    if variance <= 0.0:
        if metric_warnings is not None:
            metric_warnings.append({"metric": metric_name, "reason": "zero return variance"})
        return 0.0
    return mean_return / math.sqrt(variance) * math.sqrt(252.0)


def _mask_unavailable_walk_forward_metrics(
    metrics: BacktestMetrics, reason: str
) -> BacktestMetrics:
    if reason not in {
        INSUFFICIENT_WALK_FORWARD_SAMPLE,
        UNSAFE_WALK_FORWARD_CANDIDATE,
    }:
        return metrics
    return metrics.model_copy(
        update={
            "out_sample_sharpe": None,
            "out_sample_return": None,
            "in_sample_benchmark_return": None,
            "out_sample_benchmark_return": None,
            "in_sample_excess_return": None,
            "out_sample_excess_return": None,
            "benchmark_period_count": None,
            "benchmark_period_win_rate": None,
            "benchmark_period_loss_rate": None,
            "in_sample_benchmark_period_count": None,
            "in_sample_benchmark_period_win_rate": None,
            "in_sample_benchmark_period_loss_rate": None,
            "out_sample_benchmark_period_count": None,
            "out_sample_benchmark_period_win_rate": None,
            "out_sample_benchmark_period_loss_rate": None,
        }
    )

def _degradation(in_sample_sharpe: float, out_sample_sharpe: float) -> float:
    if in_sample_sharpe == 0:
        return 0.0
    return max(0.0, (in_sample_sharpe - out_sample_sharpe) / abs(in_sample_sharpe))


def _candidate_rank(candidate: CodeCandidate) -> tuple[float, float, float]:
    metrics = _candidate_metrics(candidate)
    # Tie-breakers are part of selection too; keep them inside the training slice.
    return (
        metrics.in_sample_sharpe,
        metrics.in_sample_return,
        metrics.in_sample_max_drawdown,
    )


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


def _selection_signal_action_count(
    engine_result: Any, rows: Sequence[Mapping[str, Any]], action: str
) -> int:
    dates = sorted({str(row.get("date")) for row in rows})
    if not dates:
        return 0
    cutoff = dates[max(0, int(len(dates) * BACKTEST_SPLIT_FRACTION) - 1)]
    return sum(
        1
        for signal in getattr(engine_result, "signals", [])
        if str(getattr(signal, "action", "")).upper().endswith(action)
        and str(getattr(signal, "date", "")) <= cutoff
    )


def objective_floor_reasons(result: CandidateBacktestResult) -> list[str]:
    """Every acceptance-floor check this result did not clear.

    Evaluated whatever the gate mode is. A check that only runs when it blocks is a check
    nobody can audit while it is switched off, and the verdict is published either way.
    """

    metrics = _candidate_metrics(result.selected_candidate)
    trade_count = _summary_float_default(result.engine_summary, "effective_trade_count", 0.0)
    reasons: list[str] = []
    if trade_count < MIN_OBJECTIVE_TRADES:
        reasons.append(
            f"거래 수 {trade_count:g}건이 최소 {MIN_OBJECTIVE_TRADES}건에 미달합니다"
        )
    # This gate is a report/acceptance check, so it uses the untouched hold-out.
    if metrics.out_sample_sharpe is None:
        reasons.append("미사용 구간 Sharpe 를 계산하지 못했습니다")
    elif metrics.out_sample_sharpe < MIN_OBJECTIVE_SHARPE:
        reasons.append(
            f"미사용 구간 Sharpe {metrics.out_sample_sharpe:.2f} 가 "
            f"기준 {MIN_OBJECTIVE_SHARPE:g} 에 미달합니다"
        )
    if metrics.max_drawdown < MAX_OBJECTIVE_DRAWDOWN:
        reasons.append(
            f"최대 낙폭 {metrics.max_drawdown:.1%} 가 한도 {MAX_OBJECTIVE_DRAWDOWN:.0%} 를 넘습니다"
        )
    # A winner picked from N tries has to beat what N tries of nothing would have
    # produced. Without this the floor passes on search width alone: six candidates
    # trading at random cleared a +16.2% best-of-six against a -3.7% average.
    # `candidates_evaluated` is 1 until the correction is applied, which leaves this
    # term at in_sample_sharpe and changes no single-candidate behaviour.
    if metrics.selection_adjusted_sharpe is None:
        reasons.append("탐색 폭 보정 Sharpe 를 계산하지 못했습니다")
    elif metrics.selection_adjusted_sharpe < MIN_SELECTION_ADJUSTED_SHARPE:
        reasons.append(
            f"탐색 폭 보정 Sharpe {metrics.selection_adjusted_sharpe:.2f} 가 "
            f"기준 {MIN_SELECTION_ADJUSTED_SHARPE:g} 에 미달합니다"
        )

    strategy = getattr(result, "strategy_a", None)
    if getattr(strategy, "selection_mode", "standard") != "automatic":
        return reasons
    payload = getattr(result, "backtest_payload", {}) or {}
    benchmark = payload.get("benchmark") if isinstance(payload, Mapping) else None
    primary = benchmark.get("primary") if isinstance(benchmark, Mapping) else None
    if not isinstance(primary, Mapping) or not primary.get("available"):
        reasons.append("공식 KOSPI/KOSDAQ TR 벤치마크를 확보하지 못했습니다")
        return reasons
    reasons.extend(
        _benchmark_objective_reasons(metrics, benchmark_return=primary.get("return"))
    )
    return reasons


def _passes_objective_floor(result: CandidateBacktestResult) -> bool:
    """Whether the floor lets this strategy through, given the current gate mode.

    In report-only mode the reasons are computed, logged, and published, but they do not
    withhold validation. See `ai_graph.validation_gates` for why the switch exists and
    what it deliberately does not cover.
    """

    reasons = objective_floor_reasons(result)
    if not reasons:
        return True
    if objective_floor_is_enforced():
        return False
    _logger.info(
        "acceptance floor not enforced; publishing as validated despite: %s",
        "; ".join(reasons),
    )
    return True



def _benchmark_objective_reasons(
    metrics: BacktestMetrics, *, benchmark_return: float | None = None
) -> list[str]:
    """Why an automatic strategy failed the benchmark-relative acceptance rule.

    The final lockbox checks preserve the hold-out acceptance contract. Aggregate
    walk-forward and official-primary checks are required as well; unavailable nullable
    values fail closed instead of being mistaken for neutral performance.
    """

    reasons: list[str] = []
    if metrics.benchmark_period_count is None:
        reasons.append("walk-forward benchmark aggregate is unavailable")
    elif metrics.benchmark_period_count <= 0:
        reasons.append(
            f"{BENCHMARK_EVALUATION_PERIOD_DAYS}거래일 벤치마크 비교 구간이 없습니다"
        )
    if metrics.out_sample_benchmark_period_count is None:
        reasons.append("walk-forward final lockbox benchmark aggregate is unavailable")
    elif metrics.out_sample_benchmark_period_count <= 0:
        reasons.append(
            f"최종 미사용 구간에 {BENCHMARK_EVALUATION_PERIOD_DAYS}거래일 벤치마크 비교 구간이 없습니다"
        )
    elif (
        metrics.out_sample_benchmark_period_loss_rate is not None
        and metrics.out_sample_benchmark_period_loss_rate >= MAX_AUTOMATIC_BENCHMARK_LOSS_RATE
    ):
        reasons.append(
            "최종 미사용 구간의 벤치마크 패배 비율 "
            f"{metrics.out_sample_benchmark_period_loss_rate:.1%} >= "
            f"{MAX_AUTOMATIC_BENCHMARK_LOSS_RATE:.0%}"
        )
    if metrics.out_sample_excess_return is None:
        reasons.append("walk-forward final lockbox excess return is unavailable")
    elif metrics.out_sample_excess_return <= 0.0:
        reasons.append(f"최종 미사용 구간 초과수익률 {metrics.out_sample_excess_return:.2%} <= 0%")
    parsed_benchmark = float(benchmark_return) if _is_numeric_metric(benchmark_return) else None
    if (
        parsed_benchmark is None
        and metrics.in_sample_benchmark_return is not None
        and metrics.out_sample_benchmark_return is not None
    ):
        parsed_benchmark = (1.0 + metrics.in_sample_benchmark_return) * (
            1.0 + metrics.out_sample_benchmark_return
        ) - 1.0
    if parsed_benchmark is None:
        reasons.append("official benchmark aggregate is unavailable")
    elif metrics.total_return <= parsed_benchmark:
        reasons.append(f"전체 수익률 {metrics.total_return:.2%} <= 벤치마크 {parsed_benchmark:.2%}")
    return reasons


def _selected_objective_score(result: CandidateBacktestResult) -> float:
    return result.objective_scores_by_candidate.get(
        result.selected_candidate.candidate_id, float("-inf")
    )


def _objective_score(
    metrics: BacktestMetrics,
    engine_summary: Mapping[str, Any],
    price_rows: Sequence[Mapping[str, Any]],
    *,
    benchmark_context: _BenchmarkContext | None = None,
) -> float:
    trade_count = _summary_float_default(engine_summary, "selection_buy_count", 0.0)
    selection_days = (
        benchmark_context.selection_days
        if benchmark_context is not None
        else max(
            1,
            int(len({str(row.get("date")) for row in price_rows}) * BACKTEST_SPLIT_FRACTION),
        )
    )
    annual_return = _annualized_return(metrics.in_sample_return, trading_days=selection_days)
    calmar = _calmar_ratio(annual_return, metrics.in_sample_max_drawdown)
    if benchmark_context is None:
        dates = sorted({str(row.get("date")) for row in price_rows})
        cutoff = dates[max(0, selection_days - 1)] if dates else ""
        selection_rows = [row for row in price_rows if str(row.get("date")) <= cutoff]
        _, benchmark_return = _equal_weight_benchmark_curve(selection_rows)
    else:
        benchmark_return = benchmark_context.selection_return
    annual_benchmark_return = _annualized_return(
        float(benchmark_return or 0.0),
        trading_days=selection_days,
    )
    annual_excess_return = annual_return - annual_benchmark_return
    benchmark_consistency = (
        float(metrics.in_sample_benchmark_period_win_rate or 0.0)
        - float(metrics.in_sample_benchmark_period_loss_rate or 0.0)
    )
    trading_days = selection_days
    annual_turnover = trade_count * 252.0 / trading_days
    turnover_penalty = _turnover_cost_penalty(annual_turnover, engine_summary)
    # The hold-out must not affect selection.  It is only used by the objective floor
    # after a candidate has been selected.
    score = (
        0.35 * metrics.in_sample_sharpe
        + 0.15 * calmar
        + 0.10 * annual_return
        + 1.00 * annual_excess_return
        + 0.20 * benchmark_consistency
        - 0.05 * turnover_penalty
    )
    if trade_count < MIN_OBJECTIVE_TRADES:
        score -= (MIN_OBJECTIVE_TRADES - trade_count) * 0.05
    if metrics.in_sample_max_drawdown < MAX_OBJECTIVE_DRAWDOWN:
        # Was 2x, which let a single deep drawdown swamp every other term and drove the
        # score negative for otherwise strong candidates.
        score -= abs(metrics.in_sample_max_drawdown - MAX_OBJECTIVE_DRAWDOWN)
    if metrics.in_sample_sharpe < MIN_OBJECTIVE_SHARPE:
        score -= (MIN_OBJECTIVE_SHARPE - metrics.in_sample_sharpe) * 0.25
    if annual_return <= 0.0:
        score -= 0.25 + abs(annual_return) * 0.5
    if annual_excess_return <= 0.0:
        score -= 0.35 + abs(annual_excess_return)
    if (
        metrics.in_sample_benchmark_period_count is not None
        and metrics.in_sample_benchmark_period_count > 0
        and metrics.in_sample_benchmark_period_loss_rate is not None
        and metrics.in_sample_benchmark_period_loss_rate >= MAX_AUTOMATIC_BENCHMARK_LOSS_RATE
    ):
        score -= 0.25 + metrics.in_sample_benchmark_period_loss_rate
    return round(score, METRIC_ROUND_DIGITS)


def _annual_turnover(
    engine_summary: Mapping[str, Any] | None, price_rows: Sequence[Mapping[str, Any]]
) -> float:
    """Trades a year over the selection window, which is what the cap and penalty read."""

    if not engine_summary:
        return 0.0
    selection_days = max(
        1,
        int(len({str(row.get("date")) for row in price_rows}) * BACKTEST_SPLIT_FRACTION),
    )
    trades = _summary_float_default(engine_summary, "selection_buy_count", 0.0)
    return trades * 252.0 / selection_days


def _within_turnover_cap(
    candidates: Sequence[CodeCandidate],
    engine_summaries: Mapping[str, Mapping[str, Any]],
    price_rows: Sequence[Mapping[str, Any]],
) -> list[CodeCandidate]:
    """Drop candidates that trade more than the cost model can pay for.

    Pricing turnover inside the score was not enough: measured over 72 held-out test
    years it moved the pick in 10 of them and the out-of-sample difference was noise
    (+0.29pp, p=0.45). Refusing to select a candidate above the ceiling did move it - in
    65 of 72 years, worth +2.38pp a year (t=2.80, p=0.007), and the effect held at nearly
    the same size on the six markets the rule was fixed before seeing (+2.29pp search,
    +2.48pp confirmation). It also cut the spread of what a user receives by 61%.

    The ceiling is the same 24 trades a year the old saturating penalty already used as
    its knee, so it is not a value tuned against these results.

    Nothing is dropped when every candidate is over the ceiling: a turnover-heavy
    recommendation the report can qualify beats no recommendation at all.
    """

    eligible = [
        candidate
        for candidate in candidates
        if _annual_turnover(engine_summaries.get(candidate.candidate_id), price_rows)
        <= MAX_SELECTABLE_ANNUAL_TURNOVER
    ]
    return eligible or list(candidates)


def _turnover_cost_penalty(
    annual_turnover: float, engine_summary: Mapping[str, Any]
) -> float:
    """What a year of this candidate's trading actually costs, as a fraction of equity.

    The penalty used to be `min(1, annual_turnover / 24)`, which saturates: above 24
    trades a year it is a constant, so the objective could not tell 24 trades from 100.
    Measured over 72 held-out test years that is exactly the range where the money goes
    - cost drag rises with turnover at r=+1.00 while cost-free alpha does not move
    (r=-0.12, p=0.77), so every trade past the first few is a pure subtraction. Pricing
    turnover at the cost model the engine already charges restores the gradient, and it
    is the model's own numbers rather than another tuned constant.
    """

    cost_model = engine_summary.get("cost_model")
    if isinstance(cost_model, Mapping):
        commission = _coerce_float(cost_model.get("commission_pct"), DEFAULT_COMMISSION_PCT)
        tax = _coerce_float(cost_model.get("tax_pct"), DEFAULT_TAX_PCT)
        slippage = _coerce_float(cost_model.get("slippage_pct"), DEFAULT_SLIPPAGE_PCT)
    else:
        commission, tax, slippage = (
            DEFAULT_COMMISSION_PCT,
            DEFAULT_TAX_PCT,
            DEFAULT_SLIPPAGE_PCT,
        )
    # Buy and sell each pay commission and slippage; the transfer tax is on the sell.
    round_trip = 2.0 * commission + tax + 2.0 * slippage
    sizing = engine_summary.get("position_sizing")
    positions = (
        _coerce_float(sizing.get("max_positions"), 0.0)
        if isinstance(sizing, Mapping)
        else 0.0
    )
    if positions <= 0:
        positions = float(DEFAULT_MAX_POSITIONS_FOR_COST)
    # Each round trip turns over one slot, so one slot is 1/positions of the book.
    return annual_turnover * round_trip / positions


def _coerce_float(value: Any, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) and result >= 0.0 else default


def _calmar_ratio(total_return: float, max_drawdown: float) -> float:
    drawdown = abs(max_drawdown)
    if drawdown == 0:
        return 0.0
    return total_return / drawdown


def _annualized_return(
    total_return: float,
    price_rows: Sequence[Mapping[str, Any]] | None = None,
    *,
    trading_days: int | None = None,
) -> float:
    effective_days = (
        trading_days
        if trading_days is not None
        else len({str(row.get("date")) for row in price_rows or ()})
    )
    if effective_days <= 0 or total_return <= -1.0:
        return total_return
    return (1.0 + total_return) ** (252.0 / effective_days) - 1.0


def _profit_factor(engine_summary: Mapping[str, Any]) -> float | None:
    """Return realized-trade profit factor, never a period-return substitute.

    The engine records gross profit and loss from closed-trade net PnL as
    ``trade_profit_factor``. Older summaries that only have the unrelated period-return
    metric fail closed rather than changing the meaning of the public field.
    """

    value = engine_summary.get("trade_profit_factor")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _equal_weight_benchmark_curve(
    price_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[BacktestEquityPoint], float | None]:
    if not price_rows:
        return [], None

    rows_by_ticker: dict[str, dict[str, float]] = defaultdict(dict)
    for row in price_rows:
        ticker = str(row.get("ticker") or DEFAULT_FIXTURE_TICKER).zfill(6)
        date = str(row.get("date"))
        close = _finite_float(row.get("close"), f"{ticker}_close")
        if close > 0:
            rows_by_ticker[ticker][date] = close

    if not rows_by_ticker:
        return [], None

    dates = sorted({str(row.get("date")) for row in price_rows})
    if not dates:
        return [], None

    first_date = dates[0]
    universe = tuple(
        sorted(ticker for ticker, rows in rows_by_ticker.items() if first_date in rows)
    )
    if not universe:
        return [], None
    universe = tuple(ticker for ticker in universe if rows_by_ticker[ticker][first_date] > 0.0)
    if not universe:
        return [], None

    initial_prices = {ticker: rows_by_ticker[ticker][first_date] for ticker in universe}
    latest_prices = dict(initial_prices)
    curve: list[BacktestEquityPoint] = [BacktestEquityPoint(date=first_date, cumulative_return=0.0)]
    for date in dates[1:]:
        values: list[float] = []
        for ticker in universe:
            current = rows_by_ticker[ticker].get(date, latest_prices[ticker])
            latest_prices[ticker] = current
            initial_price = initial_prices[ticker]
            if initial_price <= 0:
                continue
            values.append(current / initial_price)
        if not values:
            continue
        cumulative_return = sum(values) / len(universe)
        curve.append(
            BacktestEquityPoint(
                date=date,
                cumulative_return=round(cumulative_return - 1.0, METRIC_ROUND_DIGITS),
            )
        )

    if not curve:
        return [], None
    return curve, round(curve[-1].cumulative_return, METRIC_ROUND_DIGITS)


def _benchmark_return(price_rows: Sequence[Mapping[str, Any]]) -> float:
    _, total_return = _equal_weight_benchmark_curve(price_rows)
    if total_return is None:
        return 0.0
    return total_return


def _backtest_payload(
    strategy: AIStrategySpec,
    rows: Sequence[Mapping[str, Any]],
    *,
    benchmark_context: _BenchmarkContext,
) -> dict[str, Any]:
    tickers = sorted({str(row.get("ticker") or DEFAULT_FIXTURE_TICKER).zfill(6) for row in rows})
    walk_forward = _walk_forward_sample(rows)
    payload = {
        "strategy_id": strategy.strategy_id,
        "market": strategy.market,
        "tickers": tickers,
        "price_rows": len(rows),
        "first_date": str(rows[0].get("date")) if rows else None,
        "last_date": str(rows[-1].get("date")) if rows else None,
        "analysis_initial_capital_krw": CANONICAL_ANALYSIS_INITIAL_CAPITAL,
        "initial_capital_contract": "canonical_analysis_job_sealed_primary_contract",
        "benchmark": _benchmark_provenance(benchmark_context),
        "walk_forward_sample": _walk_forward_metadata(
            walk_forward, _walk_forward_split_policy(rows)
        ),
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


def _undefined_metric_availability(
    metric_warnings: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, None | str]]:
    unavailable: dict[str, dict[str, None | str]] = {}
    for warning in metric_warnings:
        metric = warning.get("metric")
        # The native selection implementation writes ``reason`` while QuantStats
        # writes ``warning``. Both mean that the advertised scalar is not measured.
        reason = warning.get("reason") or warning.get("warning")
        if isinstance(metric, str) and isinstance(reason, str):
            unavailable[metric] = {"value": None, "unavailable_reason": reason}
    return unavailable

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
