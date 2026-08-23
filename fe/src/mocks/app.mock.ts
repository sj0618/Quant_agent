import type {
  AIEnvelope,
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

export const performanceSummary: PerformanceSummary = {
  headline: "백테스트 결과",
  // The engine splits the history once, 70/30, and selects on the first part. It does
  // not roll windows: the spec carries a walk_forward config that nothing reads. This
  // copy described a validation the backtest has never performed.
  period: "단일 홀드아웃 · 선택 70% / 검증 30% · 2016.01 ~ 2026.03",
  metrics: [
    { key: "sharpe", label: "Sharpe Ratio", value: "1.42", delta: "기준선 1.11", tone: "positive", caption: "홀드아웃 구간 기준. 1.5 이상이 우수." },
    { key: "mdd", label: "Max Drawdown", value: "-9.4%", delta: "기준선 -12.1%", tone: "negative", caption: "감내 가능한 수준. 시장 평균 -15% 대비 양호." },
    { key: "winRate", label: "Win Rate", value: "58.2%", delta: "+3.4pp", tone: "positive", caption: "수익 거래 비율. 10년 누적 1,247 거래." },
    { key: "totalReturn", label: "Total Return (10y)", value: "+92.4%", delta: "CAGR 6.8%", tone: "positive", caption: "거래비용 반영. KOSPI200 동기간 +54.3%." },
  ],
  equityCurve: [
    { date: "2016", strategy: 0, original: 0, benchmark: 0 },
    { date: "2018", strategy: 18, original: 14, benchmark: 9 },
    { date: "2020", strategy: 35, original: 27, benchmark: 21 },
    { date: "2022", strategy: 52, original: 38, benchmark: 30 },
    { date: "2024", strategy: 68, original: 51, benchmark: 43 },
    { date: "2026", strategy: 92.4, original: 70.1, benchmark: 54.3 },
  ],
  comparison: [
    { metric: "Sharpe", value: "1.42", context: "리스크 대비 수익", assessment: "양호", tone: "positive" },
    { metric: "MDD", value: "-9.4%", context: "최대 낙폭", assessment: "방어 양호", tone: "positive" },
    { metric: "Win Rate", value: "58.2%", context: "수익 거래 비율", assessment: "양호", tone: "positive" },
    { metric: "Total Return", value: "+92.4%", context: "10년 누적", assessment: "초과수익", tone: "positive" },
    { metric: "Trades", value: "1,247회", context: "엔진 요약", assessment: "거래 충분", tone: "positive" },
  ],
  macroEvents: [
    { date: "20.03", label: "코로나19 패닉, KOSPI -33%", impact: "+α", tone: "positive" },
    { date: "22.02", label: "러시아 우크라이나 침공", impact: "-α", tone: "negative" },
    { date: "22.10", label: "美 연준 4연속 자이언트 스텝", impact: "-α", tone: "negative" },
    { date: "23.10", label: "이스라엘·하마스 무력 충돌", impact: "≈", tone: "warning" },
    { date: "24.08", label: "엔캐리 청산, 글로벌 변동성", impact: "+α", tone: "positive" },
    { date: "25.04", label: "美 상호관세 발표", impact: "-α", tone: "negative" },
  ],
  disclaimer:
    "단일 홀드아웃 구간(마지막 30%) 기준. 여러 후보 중 선택 구간 성과가 가장 좋은 하나를 고른 결과이므로 탐색 폭만큼 상향 편향이 있습니다. 미래 수익률을 보장하지 않으며, 거래비용은 수수료 0.015% · 거래세 0.23% · 슬리피지 0.1% 반영.",
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
  envelope: readyEnvelope,
  jobStatus: analysisJobStatus,
};
