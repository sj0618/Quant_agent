import type {
  AIBacktestEvaluationBasis,
  AIBacktestUniversePolicy,
  AIEnvelope,
  AIRecommendationGate,
  AITickerAction,
  AnalysisJobStatus,
  AppOverview,
  PerformanceSummary,
  StrategySpec,
  TradingCandidate,
} from "../types/quantagent";

export const activeStrategySpec: StrategySpec = {
  name: "반도체 모멘텀 + 기관 매수 회귀",
  natural_language_strategy: "반도체 섹터에서 RSI 30 이하로 과매도된 종목 잡아줘",
  sector: "반도체",
  buy_condition: "RSI ≤ 30 AND 거래량 > 200%",
  hold_condition: "RSI 31~70 또는 주요 이벤트 대기",
  drop_condition: "RSI ≥ 70 OR 보유 30일",
  rebalance: "매일 08:00 분석 후 신호 갱신",
  constraints: ["KRX 상장 보통주 지원", "거래비용 0.015% / 0.23% / 0.1% 반영"],
};

export const readyEnvelope: AIEnvelope<{ active_tab: "overview" }> = {
  status: "ready",
  trace_id: "qa-trace-20260418-0800",
  schema_version: "qa.ai_envelope.v1",
  user_payload: { active_tab: "overview" },
  strategy_spec: activeStrategySpec,
  debug_ref: "dbg_20260418_0800_semiconductor",
  retryable: true,
};

export const analysisJobStatus: AnalysisJobStatus = {
  trace_id: readyEnvelope.trace_id,
  status: "ready",
  stages: [
    { stage: "strategy_parse", status: "done", label: "전략 정형화", updated_at: "2026-04-18T07:12:00+09:00" },
    { stage: "data_collect", status: "done", label: "KIS·DART·뉴스 수집", updated_at: "2026-04-18T07:29:00+09:00" },
    { stage: "signal_judge", status: "done", label: "신호 판정", updated_at: "2026-04-18T07:44:00+09:00" },
    { stage: "backtest", status: "done", label: "홀드아웃 백테스트", updated_at: "2026-04-18T07:52:00+09:00" },
    { stage: "risk_review", status: "done", label: "Risk Manager 검토", updated_at: "2026-04-18T07:57:00+09:00" },
    { stage: "report_ready", status: "done", label: "리포트 준비 완료", updated_at: "2026-04-18T08:00:00+09:00" },
  ],
};

export const tradingCandidates: TradingCandidate[] = [
  {
    id: "005930",
    ticker: "005930",
    name: "삼성전자",
    sector: "반도체",
    signal: "BUY",
    confidence: 0.91,
    price: "82,400원",
    changePercent: "+1.7%",
    rationale: "메모리 사이클 회복 + 외국인 5일 연속 순매수. 컨센서스 9.2만원 상향.",
    evidence: [
      {
        provider: "미래에셋증권",
        title: "HBM 공급 개선과 서버 DRAM 회복",
        date: "04.17",
        summary: "메모리 가격 반등과 외국인 순매수가 동시에 확인됨.",
      },
    ],
    riskReasons: ["단기 환율 변동성", "실적 발표 전 변동성 확대 가능"],
    web_projection: "AI 서버 수요 회복 가정 시 2분기 마진 개선 가능성이 높음",
  },
  {
    id: "000660",
    ticker: "000660",
    name: "SK하이닉스",
    sector: "반도체",
    signal: "BUY",
    confidence: 0.84,
    price: "201,500원",
    changePercent: "+2.4%",
    rationale: "HBM3E 12단 양산 본격화. NVIDIA 공급 확대 모멘텀, 분기 영업이익 컨센 상향.",
    evidence: [
      {
        provider: "삼성증권",
        title: "HBM 실적 민감도 상향",
        date: "04.17",
        summary: "HBM 매출 비중 확대와 기관 매수 전환 확인.",
      },
    ],
    riskReasons: ["고밸류 부담", "고객사 발주 지연 가능성"],
  },
  {
    id: "035420",
    ticker: "035420",
    name: "NAVER",
    sector: "플랫폼",
    signal: "BUY",
    confidence: 0.78,
    price: "187,000원",
    changePercent: "+0.9%",
    rationale: "커머스 사업 회복 + AI 검색 베타 호조. 외국인 3일 연속 순매수 전환.",
    evidence: [
      {
        provider: "한국투자증권",
        title: "커머스·AI 검색 회복",
        date: "04.16",
        summary: "광고 단가와 커머스 거래액 반등이 확인됨.",
      },
    ],
    riskReasons: ["광고 경기 둔화", "AI 서비스 비용 증가"],
  },
  {
    id: "035720",
    ticker: "035720",
    name: "카카오",
    sector: "플랫폼",
    signal: "BUY",
    confidence: 0.72,
    price: "54,200원",
    changePercent: "+1.3%",
    rationale: "광고·결제 사업부 흑자 전환. AI 모델 카카오브레인 적용 발표 호재.",
    evidence: [
      {
        provider: "NH투자증권",
        title: "비용 통제와 AI 적용",
        date: "04.17",
        summary: "비용 효율화와 신사업 모멘텀이 동시에 반영됨.",
      },
    ],
    riskReasons: ["규제 리스크", "플랫폼 성장률 둔화"],
  },
  {
    id: "005380",
    ticker: "005380",
    name: "현대차",
    sector: "자동차",
    signal: "HOLD",
    confidence: 0.62,
    price: "247,000원",
    changePercent: "+0.2%",
    rationale: "1Q 실적 양호하나 미국 IRA 관련 불확실성 잔존. 보유 유지 권고.",
    evidence: [
      {
        provider: "KB증권",
        title: "북미 판매 견조",
        date: "04.16",
        summary: "판매는 견조하지만 정책 변수 확인이 필요함.",
      },
    ],
    riskReasons: ["IRA 보조금 정책 변경", "원화 강세 시 마진 둔화"],
  },
  {
    id: "000270",
    ticker: "000270",
    name: "기아",
    sector: "자동차",
    signal: "HOLD",
    confidence: 0.58,
    price: "128,500원",
    changePercent: "+0.1%",
    rationale: "북미 판매 견조하나 환율 변동성 확대. 추가 매수보다 보유 중심.",
    evidence: [
      {
        provider: "하나증권",
        title: "판매 믹스 양호",
        date: "04.16",
        summary: "실적 안정성은 유지되나 신규 매수 점수는 낮음.",
      },
    ],
    riskReasons: ["환율 변동성", "원가 상승 압력"],
  },
  {
    id: "051910",
    ticker: "051910",
    name: "LG화학",
    sector: "화학",
    signal: "DROP",
    confidence: 0.41,
    price: "342,500원",
    changePercent: "-1.8%",
    rationale: "외국인 5일 연속 순매도 + 한경컨센서스 매수 의견 3주 누적 하향. 양극재 분할설 부담.",
    evidence: [
      {
        provider: "한경컨센서스",
        title: "매수 의견 하향",
        date: "04.17",
        summary: "컨센서스 하향과 수급 약세가 동시에 관측됨.",
      },
    ],
    riskReasons: ["양극재 ASP 하락", "사업부 분할 이슈"],
    risk_manager_override: "override 없음: Rule-based macro guard 안전 구간",
  },
  {
    id: "003670",
    ticker: "003670",
    name: "포스코퓨처엠",
    sector: "2차전지소재",
    signal: "DROP",
    confidence: 0.38,
    price: "289,000원",
    changePercent: "-2.4%",
    rationale: "양극재 ASP 하락 압력. 외국인 4일 연속 순매도, 기술적 200일선 이탈.",
    evidence: [
      {
        provider: "신한투자증권",
        title: "소재 업황 둔화",
        date: "04.16",
        summary: "업황 회복 신호가 약하고 기술적 지지선 이탈.",
      },
    ],
    riskReasons: ["ASP 하락", "외국인 순매도"],
  },
];

// Shaped exactly like `BacktestPerformance.evaluation_basis`, so the demo cannot describe
// a period the backend would never report. The fixed five-year window matches the loader's
// krx_pit_common_stock_5y_kst_session_v1 policy.
export const evaluationBasis: AIBacktestEvaluationBasis = {
  basis: "hold_out",
  caption: "2021-08-23~2026-08-21 구간 중 마지막 30% 검증 구간 누적 · 거래비용 반영",
  hold_out_fraction: 0.3,
  window_start: "2021-08-23",
  window_end: "2026-08-21",
  window_policy_id: "krx_pit_common_stock_5y_kst_session_v1",
  cost_model_applied: true,
};

export const universePolicy: AIBacktestUniversePolicy = {
  summary:
    "백테스트는 과거 시점(PIT) 기준으로 그 시점에 상장돼 있던 종목만 거래해 규칙 자체를 검증하고, 오늘의 추천 종목은 같은 규칙을 오늘 데이터에 적용한 결과입니다. 두 목록이 서로 다른 것은 정상입니다.",
  policy_id: "krx_pit_common_stock_5y_kst_session_v1",
  window_start: "2021-08-23",
  window_end: "2026-08-21",
  traded_ticker_count: 812,
  excluded_screening_candidate_count: 2,
  excluded_notice:
    "오늘 스크리닝 후보 중 2종목은 백테스트 구간의 과거 시점 유니버스에 없어 백테스트 거래 대상에서 제외됐습니다.",
};

export const performanceSummary: PerformanceSummary = {
  headline: "백테스트 결과",
  // Both evaluation paths the backend can take are named here rather than one of them
  // being asserted: this fixture is a hold-out run, and it says so, with the same window
  // the basis object carries.
  period: "단일 홀드아웃 · 선택 70% / 검증 30% · 2021.08 ~ 2026.08",
  metrics: [
    { key: "sharpe", label: "Sharpe Ratio", value: "1.42", delta: "기준선 1.11", tone: "positive", caption: "검증 구간(마지막 30%) 기준. 1.5 이상이 우수." },
    { key: "mdd", label: "Max Drawdown", value: "-9.4%", delta: "기준선 -12.1%", tone: "negative", caption: "감내 가능한 수준. 시장 평균 -15% 대비 양호." },
    { key: "winRate", label: "Win Rate", value: "58.2%", delta: "+3.4pp", tone: "positive", caption: "수익 거래 비율. 5년 누적 612 거래." },
    { key: "totalReturn", label: "Total Return (검증 구간)", value: "+31.6%", delta: "CAGR 6.8%", tone: "positive", caption: evaluationBasis.caption },
  ],
  equityCurve: [
    { date: "2021", strategy: 0, original: 0, benchmark: 0 },
    { date: "2022", strategy: 9, original: 7, benchmark: 4 },
    { date: "2023", strategy: 21, original: 16, benchmark: 12 },
    { date: "2024", strategy: 34, original: 25, benchmark: 21 },
    { date: "2025", strategy: 48, original: 36, benchmark: 30 },
    { date: "2026", strategy: 61.2, original: 45.3, benchmark: 38.7 },
  ],
  comparison: [
    { metric: "Sharpe", value: "1.42", context: "리스크 대비 수익", assessment: "양호", tone: "positive" },
    { metric: "MDD", value: "-9.4%", context: "최대 낙폭", assessment: "방어 양호", tone: "positive" },
    { metric: "Win Rate", value: "58.2%", context: "수익 거래 비율", assessment: "양호", tone: "positive" },
    { metric: "Total Return", value: "+61.2%", context: "선택 구간 포함 5년 누적", assessment: "초과수익", tone: "positive" },
    { metric: "Trades", value: "612회", context: "엔진 요약", assessment: "거래 충분", tone: "positive" },
  ],
  macroEvents: [
    { date: "22.02", label: "러시아 우크라이나 침공", impact: "-α", tone: "negative" },
    { date: "22.10", label: "美 연준 4연속 자이언트 스텝", impact: "-α", tone: "negative" },
    { date: "23.10", label: "이스라엘·하마스 무력 충돌", impact: "≈", tone: "warning" },
    { date: "24.08", label: "엔캐리 청산, 글로벌 변동성", impact: "+α", tone: "positive" },
    { date: "25.04", label: "美 상호관세 발표", impact: "-α", tone: "negative" },
  ],
  evaluationBasis,
  universePolicy,
  disclaimer:
    "단일 홀드아웃 구간(마지막 30%) 기준. 여러 후보 중 선택 구간 성과가 가장 좋은 하나를 고른 결과이므로 탐색 폭만큼 상향 편향이 있습니다. 미래 수익률을 보장하지 않으며, 거래비용은 수수료 0.015% · 거래세 0.23% · 슬리피지 0.1% 반영.",
};

export const tickerActions: AITickerAction[] = [
  {
    ticker: "005930",
    name: "삼성전자",
    action: "BUY",
    reason: "진입 조건 충족 - 신규 매수",
    as_of_date: "2026-08-21",
    close: 82400,
    source_candidate_id: "A2",
  },
  {
    ticker: "000660",
    name: "SK하이닉스",
    action: "HOLD",
    reason: "청산 조건 미충족 - 보유 유지",
    as_of_date: "2026-08-21",
    close: 201500,
    source_candidate_id: "A2",
  },
  {
    ticker: "035420",
    name: "NAVER",
    action: "WATCH",
    reason: "백테스트 마지막 거래일에 전략 보유 슬롯 5/5이 모두 차 있어 신규 진입이 제한된 상태였습니다.",
    as_of_date: "2026-08-21",
    close: 187000,
  },
  {
    ticker: "035720",
    name: "카카오",
    action: "WATCH",
    reason:
      "백테스트가 거래한 과거 시점(PIT) 유니버스에 없는 종목이라 백테스트가 판정한 적이 없습니다. 오늘 스크리닝 조건에는 부합합니다.",
    as_of_date: "2026-08-21",
    close: 54200,
  },
];

export const recommendationGate: AIRecommendationGate = {
  validated: true,
  reason:
    "측정된 objective 지표는 모두 통과했지만, 검증에 필요한 데이터가 없어 검증을 끝내지 못했습니다: 공식 KOSPI/KOSDAQ TR 벤치마크 시계열이 아직 적재되지 않아 벤치마크 대비 검증을 완료하지 못했습니다 (official KOSPI/KOSDAQ TR rows are not loaded for the backtest window)",
  verification_complete: false,
  unmet_objective_criteria: [],
  unmet_data_requirements: [
    "공식 KOSPI/KOSDAQ TR 벤치마크 시계열이 아직 적재되지 않아 벤치마크 대비 검증을 완료하지 못했습니다 (official KOSPI/KOSDAQ TR rows are not loaded for the backtest window)",
  ],
};

export const appOverview: AppOverview = {
  strategy: activeStrategySpec,
  recommendationScore: "7.6 / 10",
  recommendationDelta: "+0.4",
  passCount: 4,
  buyCount: 4,
  holdCount: 4,
  dropCount: 2,
  latestRunLabel: "최신 분석 · 오늘 08:00",
  nextRunLabel: "내일 08:00",
  chatMessages: [
    {
      id: "m1",
      sender: "system",
      label: "SYSTEM",
      time: "오늘 08:00",
      body: "오늘의 분석이 완료되었습니다. 추천 종목 4건 (BUY 2, HOLD 1, DROP 1), 권장도 7.6 / 10. 우측 대시보드에서 상세 결과를 확인하세요.",
    },
    {
      id: "m2",
      sender: "user",
      label: "나",
      time: "오늘 09:14",
      body: activeStrategySpec.natural_language_strategy,
    },
    {
      id: "m3",
      sender: "agent",
      label: "AGENT",
      time: "방금 전 · 분석 완료",
      body: "반도체 섹터 8개 종목에서 RSI ≤ 30 + 거래량 200% 이상 조건으로 스크리닝했습니다.",
      stats: [
        { label: "통과 종목", value: "3" },
        { label: "BUY 신호", value: "2" },
        { label: "권장도", value: "7.8" },
      ],
    },
  ],
  candidates: tradingCandidates,
  performance: performanceSummary,
  recentReports: [],
  tickerActions,
  recommendationGate,
  envelope: readyEnvelope,
  jobStatus: analysisJobStatus,
};
