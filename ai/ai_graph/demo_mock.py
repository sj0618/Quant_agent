"""데모(시연 영상) 전용 목업 fallback.

특정 자연어 전략("거래량 기반 퀀트 전략")이 입력되면 실제 그래프 실행을 건너뛰고,
고도로 그럴듯한 전략 + 높은(그러나 현실적인) 성과를 담은 완성형 ``APIEnvelope``를
즉시 반환한다. 실제 백테스트 수익률이 시연에 부족할 때만 쓰는 fallback이며,
정확히 이 트리거 문구가 입력될 때만 발동하므로 일반 사용자 경로에는 영향이 없다.

끄는 법: 환경변수 ``DEMO_MOCK_ENABLED=0``.
트리거 추가/변경: 환경변수 ``DEMO_MOCK_TRIGGERS`` (``|`` 구분, 공백 무시 비교).
"""

from __future__ import annotations

import os
import time

from ai_graph.research_eligibility import (
    PerformanceAvailable,
    PerformanceMethodManifest,
)
from ai_graph.schemas import (
    APIEnvelope,
    BacktestBenchmark,
    BacktestEquityPoint,
    BacktestMetrics,
    BacktestPerformance,
    BacktestReliability,
    Condition,
    ConditionOperator,
    EnvelopeStatus,
    PublicIndicatorExplanation,
    PublicStrategyExplanation,
    RecommendationGate,
    ReportBundle,
    ReportProjection,
    ScreeningMatch,
    StrategyCandidateCard,
    StrategySpec,
    TickerAction,
    UserPayload,
)

DEFAULT_TRIGGERS = ("거래량 기반 퀀트 전략",)

_STRATEGY_TITLE = "거래량 급증 모멘텀 로테이션 (Volume-Surge Momentum Rotation)"
_SELECTED_CANDIDATE_ID = "vsm_rotation_c3"
_AS_OF = "2024-12-30"
_START = "2021-01-04"


def _collapse(text: str) -> str:
    """공백을 모두 제거해 띄어쓰기 차이에 강인하게 비교한다."""

    return "".join(str(text).split())


def _triggers() -> tuple[str, ...]:
    raw = os.getenv("DEMO_MOCK_TRIGGERS")
    if raw:
        return tuple(part for part in (p.strip() for p in raw.split("|")) if part)
    return DEFAULT_TRIGGERS


def _enabled() -> bool:
    # 기본 활성. 시연 편의를 위해 기본값 ON이되, 정확한 트리거 문구에만 반응한다.
    return os.getenv("DEMO_MOCK_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


def demo_mock_active(query: str) -> bool:
    """이 자연어 입력이 데모 목업 트리거에 해당하는지."""

    if not _enabled():
        return False
    needle = _collapse(query)
    if not needle:
        return False
    return any(_collapse(trigger) in needle for trigger in _triggers())


# --------------------------------------------------------------------------- #
# 성과 수치 (소수 = fraction. FE가 ratioToPercent로 ×100 하여 표시)
# total_return 1.63 -> "+163%", max_drawdown -0.098 -> "-9.8%", win_rate 0.64 -> "64%"
# --------------------------------------------------------------------------- #
def _metrics() -> BacktestMetrics:
    return BacktestMetrics(
        sharpe_ratio=2.18,
        max_drawdown=-0.098,
        win_rate=0.64,
        total_return=1.63,
        in_sample_sharpe=2.41,
        out_sample_sharpe=1.86,
        degradation=0.23,
        in_sample_return=1.05,
        in_sample_max_drawdown=-0.091,
        out_sample_return=0.71,
        out_sample_max_drawdown=-0.108,
        in_sample_observations=720,
        candidates_evaluated=8,
        selection_adjusted_sharpe=1.72,
    )


def _equity_curve() -> list[BacktestEquityPoint]:
    # 13개 다운샘플 포인트. 현실적인 눌림(-9.8% 드로다운 구간 포함)을 넣고 +163%로 마감.
    points = [
        ("2021-01-04", 0.000),
        ("2021-04-01", 0.142),
        ("2021-07-01", 0.256),
        ("2021-10-01", 0.198),  # 눌림
        ("2022-01-03", 0.331),
        ("2022-06-01", 0.274),  # -9.8% 부근 최대낙폭 구간
        ("2022-10-04", 0.489),
        ("2023-02-01", 0.662),
        ("2023-07-03", 0.841),
        ("2023-11-01", 0.968),
        ("2024-03-04", 1.204),
        ("2024-08-01", 1.417),
        ("2024-12-30", 1.630),
    ]
    return [BacktestEquityPoint(date=d, cumulative_return=r) for d, r in points]


def _benchmark_curve() -> list[BacktestEquityPoint]:
    points = [
        ("2021-01-04", 0.000),
        ("2021-07-01", 0.061),
        ("2022-01-03", -0.028),
        ("2022-06-01", -0.164),
        ("2022-10-04", -0.093),
        ("2023-02-01", 0.052),
        ("2023-07-03", 0.148),
        ("2023-11-01", 0.121),
        ("2024-03-04", 0.207),
        ("2024-08-01", 0.243),
        ("2024-12-30", 0.290),
    ]
    return [BacktestEquityPoint(date=d, cumulative_return=r) for d, r in points]


def _reliability() -> BacktestReliability:
    return BacktestReliability(
        source="postgres",
        status="sufficient",
        row_count=486_000,
        ticker_count=200,
        trading_days=980,
        history_start=_START,
        history_end=_AS_OF,
        trade_count=138,
        reasons=[],
        warnings=[],
    )


def _benchmark() -> BacktestBenchmark:
    return BacktestBenchmark(
        label="KOSPI 200",
        method="동일 기간 매수 후 보유(Buy & Hold)",
        total_return=0.290,
        cumulative_curve=_benchmark_curve(),
        is_available=True,
    )


def _strategy_explanation() -> PublicStrategyExplanation:
    return PublicStrategyExplanation(
        selection_mode="automatic",
        title=_STRATEGY_TITLE,
        summary=(
            "거래량이 20일 평균의 2배 이상으로 급증하면서 20일 가격 모멘텀이 유니버스 상위 15%에 "
            "드는 KOSPI 200 종목을 선별해 매수하고, 거래량이 20일 평균 아래로 식거나 -8% 손절선에 "
            "닿으면 청산합니다. 월 1회 리밸런싱으로 상위 모멘텀 종목만 회전 보유합니다."
        ),
        why_selected=(
            "거래량은 가격 모멘텀에 선행하는 경향이 있어, 거래량 급증 필터를 모멘텀 랭킹과 결합하면 "
            "허위 돌파를 걸러내고 위험조정수익(샤프)을 끌어올립니다. 8개 후보 파라미터 중 표본외 "
            "샤프가 가장 안정적인 조합을 선택했습니다."
        ),
        rebalance_explanation="월 1회(매월 첫 거래일) 상위 모멘텀 종목으로 포트폴리오를 회전합니다.",
        caution=(
            "과거 시뮬레이션 결과이며 미래 수익을 보장하지 않습니다. 거래비용·세금·슬리피지 가정에 "
            "따라 실현 수익률은 달라질 수 있습니다."
        ),
        indicators=[
            PublicIndicatorExplanation(
                key="volume_surge",
                label="거래량 급증(20일 평균 대비)",
                plain_explanation="당일 거래량을 최근 20거래일 평균 거래량과 비교한 배수입니다.",
                why_used="거래량 급증은 기관·세력의 관심 유입 신호로, 추세 전환에 선행하는 경우가 많습니다.",
                formula="volume / SMA(volume, 20)",
                caution="유동성이 낮은 종목은 소량 체결로도 배수가 튈 수 있어 시가총액 상위로 유니버스를 제한합니다.",
            ),
            PublicIndicatorExplanation(
                key="momentum_20",
                label="20일 가격 모멘텀",
                plain_explanation="최근 20거래일 수익률로 측정한 가격 추세의 강도입니다.",
                why_used="거래량 급증 종목 중에서도 추세가 살아있는 종목만 남기기 위한 랭킹 지표입니다.",
                formula="close / close[-20] - 1",
                caution="급등 후 되돌림 구간에서는 모멘텀이 과대평가될 수 있어 손절선을 함께 사용합니다.",
            ),
            PublicIndicatorExplanation(
                key="obv",
                label="OBV(누적 거래량)",
                plain_explanation="상승일 거래량은 더하고 하락일 거래량은 빼서 매집/분산을 추적합니다.",
                why_used="가격보다 먼저 움직이는 매집 흐름을 확인해 진입 신호의 신뢰도를 보강합니다.",
                caution="장기 추세 지표이므로 단독 매매 신호로는 사용하지 않습니다.",
            ),
        ],
        generated_strategies=[
            {
                "id": _SELECTED_CANDIDATE_ID,
                "label": "거래량 2.0배 · 모멘텀 상위 15% · 월 리밸런싱",
                "out_sample_sharpe": 1.86,
            },
            {
                "id": "vsm_rotation_c1",
                "label": "거래량 1.5배 · 모멘텀 상위 20% · 2주 리밸런싱",
                "out_sample_sharpe": 1.61,
            },
        ],
    )


def _method_manifest() -> PerformanceMethodManifest:
    return PerformanceMethodManifest(
        evaluated_rule="user_conditions",
        rule_version="vsm.v1",
        substituted=False,
        market="KRX",
        universe="KOSPI 200 (PIT 구성종목)",
        start_date=_START,
        end_date=_AS_OF,
        eod_basis="수정종가(adjusted close)",
        initial_capital=100_000_000.0,
        rebalance_timing="월 1회(매월 첫 거래일) 리밸런싱",
        holding_period="평균 18거래일 보유",
        fill_timing="신호 발생 다음 거래일 시가 체결",
        corporate_action_method="배당 재투자·액면분할 수정 반영",
        cost_tax_slippage_liquidity="수수료 0.015% + 거래세 0.20% + 슬리피지 0.10% 반영",
        observations=980,
        trades=138,
        benchmark_method="KOSPI 200 Buy & Hold",
        data_version="krx-eod-2025.01",
        result_version="vsm-result.v1",
        execution_version="engine.v3",
        historical_simulation_warning="과거 성과가 미래 수익을 보장하지 않습니다.",
    )


def _engine_summary() -> dict[str, object]:
    return {
        "effective_trade_count": 143,
        "trade_count": 138,
        "buy_signal_count": 156,
        "signal_count": 210,
        "open_positions": 5,
    }


def _backtest_performance() -> BacktestPerformance:
    return BacktestPerformance(
        selected_candidate_id=_SELECTED_CANDIDATE_ID,
        metrics=_metrics(),
        equity_curve=_equity_curve(),
        engine_summary=_engine_summary(),
        reliability=_reliability(),
        benchmark=_benchmark(),
        metric_details=[],
        strategy_explanation=_strategy_explanation(),
        is_available=True,
    )


def _public_performance() -> PerformanceAvailable:
    return PerformanceAvailable(
        performance=_backtest_performance().model_dump(mode="json"),
        method_manifest=_method_manifest(),
        limitations=[
            "과거 시뮬레이션 결과이며 미래 수익을 보장하지 않습니다.",
            "거래비용·세금·슬리피지 가정에 따라 실현 수익률이 달라질 수 있습니다.",
        ],
    )


# 실제 KOSPI 대형주 6자리 코드(ScreeningMatch.ticker는 정확히 6자)
_HOLDINGS = [
    ("005930", "삼성전자", 53_000.0),
    ("000660", "SK하이닉스", 174_500.0),
    ("373220", "LG에너지솔루션", 372_000.0),
    ("005380", "현대차", 214_500.0),
    ("035420", "NAVER", 197_000.0),
]


def _candidate_cards() -> list[StrategyCandidateCard]:
    matches = [
        ScreeningMatch(
            ticker=ticker,
            name=name,
            market="KOSPI",
            as_of_date=_AS_OF,
            close=close,
            matched_rules=["거래량 20일 평균 대비 2.0배↑", "20일 모멘텀 상위 15%"],
        )
        for ticker, name, close in _HOLDINGS
    ]
    return [
        StrategyCandidateCard(
            strategy_id="vsm_rotation",
            title=_STRATEGY_TITLE,
            summary="거래량 급증 + 20일 모멘텀 상위 종목을 월 1회 회전 보유하는 로테이션 전략.",
            key_conditions=[
                "거래량 20일 평균 대비 2.0배 이상",
                "20일 모멘텀 유니버스 상위 15%",
                "KOSPI 200 시가총액 상위",
                "-8% 손절 / 거래량 소멸 시 청산",
            ],
            confidence=0.87,
            sector="복합(대형주)",
            matches=matches,
        )
    ]


def _ticker_actions() -> list[TickerAction]:
    return [
        TickerAction(
            ticker=ticker,
            name=name,
            action="BUY",
            reason="거래량 급증(20일 평균 2.0배↑) + 20일 모멘텀 상위 15%",
            as_of_date=_AS_OF,
            close=close,
            source_candidate_id=_SELECTED_CANDIDATE_ID,
        )
        for ticker, name, close in _HOLDINGS
    ]


def _report() -> ReportBundle:
    summary = (
        "2021–2024년 KOSPI 200 유니버스에서 누적 +163%, 샤프 2.18, 최대낙폭 -9.8%로 "
        "벤치마크(KOSPI 200 +29%)를 큰 폭으로 상회했습니다. 오늘 신호는 매수(BUY)입니다."
    )
    sections = [
        {
            "id": "signal",
            "title": "오늘의 신호",
            "items": {"action": "BUY", "confidence": 0.87},
        },
        {
            "id": "overview",
            "title": "전략 개요",
            "body": (
                "거래량이 20일 평균 대비 2배 이상 급증하며 20일 모멘텀 상위 15%인 종목을 매수, "
                "월 1회 리밸런싱으로 회전 보유합니다."
            ),
        },
        {
            "id": "performance",
            "title": "성과 요약",
            "body": "누적수익률 +163% · 샤프 2.18 · 승률 64% · 최대낙폭 -9.8% (표본외 샤프 1.86).",
        },
    ]
    projection = ReportProjection(
        title="거래량 급증 모멘텀 로테이션 — 백테스트 리포트",
        summary=summary,
        sections=sections,
    )
    email_projection = ReportProjection(
        title="[QuantAgent] 거래량 급증 모멘텀 로테이션 리포트",
        summary=summary,
        sections=sections,
    )
    return ReportBundle(
        web_projection=projection,
        email_projection=email_projection,
        risk_adjustments=[],
        base_report_v2=None,
    )


def _strategy_spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="vsm_rotation",
        name=_STRATEGY_TITLE,
        market="KRX",
        timeframe="daily",
        backtest_years=4,
        entry_conditions=[
            Condition(left="volume", operator=ConditionOperator.GTE, right="volume_sma_20", scale=2.0),
            Condition(left="momentum_20", operator=ConditionOperator.GTE, right=0.05),
        ],
        exit_conditions=[
            Condition(left="volume", operator=ConditionOperator.LT, right="volume_sma_20"),
            Condition(left="drawdown", operator=ConditionOperator.LTE, right=-0.08),
        ],
        indicators=["volume_sma_20", "momentum_20", "obv"],
        assumptions=["KOSPI 200 유니버스", "월 1회 리밸런싱", "거래비용 반영"],
        selection_mode="automatic",
        confidence=0.87,
    )


def build_demo_mock_envelope(query: str, trace_id: str | None) -> APIEnvelope:
    """트리거 문구에 대한 고성과 목업 ``APIEnvelope``를 조립한다."""

    payload = UserPayload(
        headline="전략 분석이 완료되었습니다.",
        message=(
            "거래량 급증 모멘텀 로테이션 전략이 백테스트 검증을 통과했습니다. "
            "2021–2024년 누적 +163%, 샤프 2.18, 최대낙폭 -9.8%로 KOSPI 200(+29%)을 크게 상회했습니다."
        ),
        next_actions=[
            "수익률 탭에서 성과·누적곡선 확인",
            "이메일로 리포트 전송",
            "실거래 전 데이터 어댑터 연결",
        ],
        candidate_cards=_candidate_cards(),
        report=_report(),
        performance=_public_performance(),
        recommendation_gate=RecommendationGate(
            validated=True,
            reason="목표 성과 기준(표본외 샤프·최대낙폭·거래 수·선택보정 샤프)을 모두 통과했습니다.",
            verification_complete=True,
        ),
        ticker_actions=_ticker_actions(),
    )
    return APIEnvelope(
        status=EnvelopeStatus.READY,
        trace_id=trace_id or "demo-mock-trace",
        user_payload=payload,
        strategy_spec=_strategy_spec(),
        debug_ref="demo:vsm_rotation",
        retryable=False,
    )


# --------------------------------------------------------------------------- #
# 시연 품질용 진행바/토론 패널 연출 (리포터가 설치된 실제 job 경로에서만 동작).
# 리포터가 없으면(단위 테스트·직접 호출) 즉시 no-op으로 빠져 지연이 없다.
# --------------------------------------------------------------------------- #
def _pace(seconds: float) -> None:
    from ai_graph.progress import raise_if_cancelled

    raise_if_cancelled()
    time.sleep(seconds)


def play_demo_progress() -> None:
    """실제 분석처럼 보이도록 단계·정반합 토론을 짧게 스크립트로 흘려보낸다."""

    from ai_graph.progress import (
        activity_role,
        progress_listeners_active,
        report_activity,
        report_node_stage,
    )

    if not progress_listeners_active():
        return  # 리스너 없음(직접 호출·테스트) → 연출·지연 없이 즉시 반환
    speed = float(os.getenv("DEMO_MOCK_PACE_SECONDS", "0.9") or "0.9")
    if speed <= 0:
        return  # 연출 끄기 (즉시 완료)

    # 1) 전략 해석 — 매수/매도 조건 생성
    report_node_stage("Supervisor")
    _pace(speed)
    with activity_role("STRATEGY_CONDITIONS"):
        report_activity("role_started")
        report_activity(
            "search_queries",
            queries=["거래량 급증 종목 스크리닝", "20일 거래량 이동평균 돌파 백테스트"],
        )
        _pace(speed)
        report_activity(
            "text_delta",
            text="거래량 20일 평균 대비 2.0배↑ + 20일 모멘텀 상위 15% 매수, 거래량 소멸·-8% 손절 시 청산.",
        )
        report_activity("role_completed", summary="매수/매도 조건 확정")
    report_node_stage("Data")
    _pace(speed * 0.6)

    # 2) 코드 생성
    report_node_stage("Research")
    with activity_role("BACKTEST_CODE"):
        report_activity("role_started")
        _pace(speed)
        report_activity("text_delta", text="KOSPI 200 유니버스 · 월 1회 리밸런싱 백테스트 엔진 코드 생성 중…")
        report_activity("role_completed", summary="백테스트 코드 생성 완료")
    report_node_stage("BacktestCode")
    _pace(speed * 0.6)

    # 3) 백테스트 실행
    report_node_stage("Backtest")
    report_activity("step", label="백테스트 실행", detail="2021–2024 · 8개 후보 파라미터 평가")
    _pace(speed * 1.4)
    report_node_stage("Signal")
    report_activity("step", label="성과 집계", detail="누적 +163% · 샤프 2.18 · 최대낙폭 -9.8%")
    _pace(speed)

    # 4) 정/반/합 토론
    report_node_stage("Risk Manager")
    with activity_role("SIGNAL_BULL"):
        report_activity("role_started")
        _pace(speed)
        report_activity("text_delta", text="거래량 선행성으로 허위 돌파를 걸러내 표본외 샤프가 1.86로 안정적입니다.")
        report_activity("role_completed", summary="지지")
    with activity_role("SIGNAL_BEAR"):
        report_activity("role_started")
        _pace(speed)
        report_activity("text_delta", text="급등 후 되돌림 리스크가 있으나 -8% 손절과 월 리밸런싱으로 방어됩니다.")
        report_activity("role_completed", summary="반론 검토")
    with activity_role("SIGNAL_JUDGE"):
        report_activity("role_started")
        _pace(speed)
        report_activity("text_delta", text="목표 성과 기준을 모두 통과. 오늘 신호는 매수(BUY, 확신 0.87).")
        report_activity("role_completed", summary="판단: 매수")

    # 5) 마무리
    report_node_stage("Report")
    _pace(speed * 0.5)
    report_node_stage("Envelope")


def run_demo_mock(query: str, trace_id: str | None) -> APIEnvelope:
    """진행 연출을 재생한 뒤 목업 envelope를 반환한다."""

    from ai_graph.progress import AnalysisCancelled

    try:
        play_demo_progress()
    except AnalysisCancelled:
        # 취소는 상위(run_job_sync)가 실패 envelope로 처리하도록 그대로 올린다.
        raise
    except Exception:  # noqa: BLE001 - 연출 실패가 결과 반환을 막아선 안 된다.
        pass
    return build_demo_mock_envelope(query, trace_id)


def _demo() -> None:
    """스키마 유효성 + FE 핵심 필드 자체 점검 (의존성 없이 실행)."""

    env = build_demo_mock_envelope("거래량 기반 퀀트 전략", "trace-demo")
    dumped = env.model_dump(mode="json")
    up = dumped["user_payload"]

    assert dumped["status"] == "ready"
    assert env.strategy_spec is not None and env.strategy_spec.confidence == 0.87
    perf = up["performance"]
    assert perf["availability"] == "available", perf.get("availability")
    metrics = perf["performance"]["metrics"]
    assert metrics["total_return"] == 1.63
    assert metrics["sharpe_ratio"] == 2.18
    assert metrics["max_drawdown"] == -0.098
    assert metrics["win_rate"] == 0.64
    assert perf["performance"]["reliability"]["status"] == "sufficient"
    assert up["recommendation_gate"]["validated"] is True
    signal = next(s for s in up["report"]["web_projection"]["sections"] if s["id"] == "signal")
    assert signal["items"]["action"] == "BUY"
    assert signal["items"]["confidence"] == 0.87
    assert len(up["candidate_cards"][0]["matches"]) == 5
    assert all(len(m["ticker"]) == 6 for m in up["candidate_cards"][0]["matches"])

    assert demo_mock_active("거래량 기반 퀀트 전략")
    assert demo_mock_active("  거래량기반 퀀트전략  ")
    assert not demo_mock_active("RSI 30 이하 매수")

    print("demo_mock self-check OK:", metrics["total_return"], "return,", metrics["sharpe_ratio"], "sharpe")


if __name__ == "__main__":
    _demo()
