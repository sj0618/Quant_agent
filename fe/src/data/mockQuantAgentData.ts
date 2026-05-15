import type {
  BacktestMetric,
  BacktestPoint,
  CandidateStock,
  ChatMessage,
  ConflictExplanation,
  InfeasibleExplanation,
  ReportSection,
  RiskWarning,
  SignalDecision,
  StrategyOption,
  StrategySpec,
  TermDefinition,
} from "../types/quantagent";

export const exampleStrategies = [
  "RSI가 낮고 거래량이 증가한 종목 찾아줘",
  "변동성 낮은 종목으로 단기 급등 후보 찾아줘",
  "최근 외국인 순매수와 실적 개선이 있는 종목",
  "KOSPI200 종목 중 방어적인 전략 추천해줘",
];

export const mockMessages: ChatMessage[] = [
  {
    id: "msg_welcome",
    role: "assistant",
    content:
      "안녕하세요. QuantAgent Workspace입니다. 자연어 전략을 입력하면 StrategySpec 후보, Signal Judge 결과, Risk Warning, Report Preview를 mock으로 확인할 수 있습니다.",
    scenario: "READY",
    createdAt: "2026-08-01T09:00:00+09:00",
  },
];

export const mockStrategies: StrategySpec[] = [
  {
    strategy_id: "strategy_rsi_volume_rebound",
    name: "RSI 반등 + 거래량 증가 전략",
    summary: "KOSPI200 현물 중 과매도 구간에서 거래량 회복이 동반되는 반등 후보를 선별합니다.",
    universe: "KOSPI200 현물",
    entry_logic: "ALL",
    exit_logic: "ANY",
    candidate_snapshot: {
      snapshot_id: "snap_001",
      tickers: ["005930", "000660", "005380", "035720"],
      effective_from: "2026-08-01",
    },
    entry_rules: [
      {
        id: "entry_rsi",
        label: "RSI 35 이하",
        metric: "rsi_14",
        operator: "<=",
        value: "35",
      },
      {
        id: "entry_volume",
        label: "20일 평균 대비 거래량 125% 이상",
        metric: "volume_ratio_20d",
        operator: ">=",
        value: "1.25",
        unit: "x",
      },
      {
        id: "entry_candidate_snapshot",
        label: "CandidateSnapshot 포함",
        metric: "candidate_snapshot_membership",
        operator: "=",
        value: "true",
      },
    ],
    exit_rules: [
      {
        id: "exit_rsi",
        label: "RSI 68 이상",
        metric: "rsi_14",
        operator: ">=",
        value: "68",
      },
      {
        id: "exit_foreign_flow",
        label: "외국인 5일 순매도 전환",
        metric: "foreign_net_buy_5d",
        operator: "<",
        value: "0",
      },
    ],
  },
  {
    strategy_id: "strategy_defensive_quality",
    name: "KOSPI200 방어적 퀄리티 전략",
    summary: "낮은 변동성, 안정적 이익 개선, 수급 방어력을 함께 확인하는 보수형 전략입니다.",
    universe: "KOSPI200 현물",
    entry_logic: "ALL",
    exit_logic: "ANY",
    candidate_snapshot: {
      snapshot_id: "snap_002",
      tickers: ["005930", "005380", "055550"],
      effective_from: "2026-08-01",
    },
    entry_rules: [
      {
        id: "entry_volatility",
        label: "20일 변동성 하위 35%",
        metric: "volatility_rank_20d",
        operator: "<=",
        value: "35",
        unit: "%",
      },
      {
        id: "entry_quality",
        label: "영업이익 전망 상향",
        metric: "earnings_revision_1m",
        operator: ">",
        value: "0",
      },
    ],
    exit_rules: [
      {
        id: "exit_revision",
        label: "실적 전망 하향 전환",
        metric: "earnings_revision_1m",
        operator: "<",
        value: "0",
      },
    ],
  },
  {
    strategy_id: "strategy_pullback_momentum",
    name: "눌림목 재상승 확인 전략",
    summary: "상승 추세 중 단기 조정을 거친 뒤 거래대금과 모멘텀이 회복되는 종목을 추적합니다.",
    universe: "KOSPI200 현물",
    entry_logic: "ALL",
    exit_logic: "ANY",
    candidate_snapshot: {
      snapshot_id: "snap_003",
      tickers: ["000660", "035420", "051910"],
      effective_from: "2026-08-01",
    },
    entry_rules: [
      {
        id: "entry_ma",
        label: "20일선 위에서 5일 조정",
        metric: "pullback_near_ma20",
        operator: "=",
        value: "true",
      },
      {
        id: "entry_momentum",
        label: "거래대금 재증가",
        metric: "turnover_acceleration",
        operator: "increasing",
        value: "true",
      },
    ],
    exit_rules: [
      {
        id: "exit_trend_break",
        label: "20일선 이탈",
        metric: "close_vs_ma20",
        operator: "<",
        value: "0",
      },
    ],
  },
  {
    strategy_id: "strategy_low_vol_breakout_watch",
    name: "저변동성 압축 후 추세 확인 전략",
    summary: "저변동성 조건은 유지하되 단기 급등 대신 추세 확인 후 WATCH/BUY로 분리합니다.",
    universe: "KOSPI200 현물",
    entry_logic: "ALL",
    exit_logic: "ANY",
    candidate_snapshot: {
      snapshot_id: "snap_004",
      tickers: ["005930", "055550", "086790"],
      effective_from: "2026-08-01",
    },
    entry_rules: [
      {
        id: "entry_compression",
        label: "변동성 압축",
        metric: "volatility_compression_20d",
        operator: "=",
        value: "true",
      },
      {
        id: "entry_breakout_confirm",
        label: "종가 기준 돌파 확인",
        metric: "close_breakout_confirmed",
        operator: "=",
        value: "true",
      },
    ],
    exit_rules: [
      {
        id: "exit_false_breakout",
        label: "돌파 실패 후 거래량 감소",
        metric: "false_breakout_risk",
        operator: "=",
        value: "true",
      },
    ],
  },
];

export const ambiguousStrategyOptions: StrategyOption[] = [
  {
    strategy_id: "strategy_rsi_volume_rebound",
    title: "과매도 반등형",
    description: "RSI·거래량으로 단기 반등 가능성이 있는 KOSPI200 종목을 찾습니다.",
    keyConditions: ["RSI 35 이하", "20일 평균 대비 거래량 증가", "CandidateSnapshot 포함"],
  },
  {
    strategy_id: "strategy_defensive_quality",
    title: "방어적 퀄리티형",
    description: "저변동성과 실적 개선을 우선하여 보수적인 후보를 선별합니다.",
    keyConditions: ["변동성 하위 35%", "실적 전망 상향", "수급 안정"],
  },
  {
    strategy_id: "strategy_pullback_momentum",
    title: "눌림목 재상승형",
    description: "상승 추세 중 조정 후 거래대금 회복이 나타난 종목을 관찰합니다.",
    keyConditions: ["20일선 지지", "거래대금 재증가", "모멘텀 회복"],
  },
];

export const termDefinition: TermDefinition = {
  term: "눌림목 전략",
  definition:
    "상승 추세가 유지되는 종목이 단기 조정을 받은 뒤 주요 이동평균선 부근에서 재상승 신호를 확인하는 전략으로 해석했습니다.",
  confidence: 0.78,
  matchedSources: ["L1 전략 사전: pullback", "L2 시장 용어 매핑: 눌림목"],
  requiresConfirmation: true,
  mappedStrategyId: "strategy_pullback_momentum",
};

export const conflictExplanation: ConflictExplanation = {
  title: "조건 간 목표가 충돌합니다",
  conflictPoints: [
    "“변동성 낮은 종목”은 가격 움직임이 안정적인 후보를 의미합니다.",
    "“단기 급등 후보”는 높은 변동성·거래대금 확대가 필요한 조건입니다.",
  ],
  alternatives: [
    {
      strategy_id: "strategy_low_vol_breakout_watch",
      title: "저변동성 압축 후 추세 확인",
      description: "급등을 즉시 요구하지 않고 돌파 확인 전까지 WATCH로 관리합니다.",
      keyConditions: ["변동성 압축", "종가 돌파 확인", "실패 시 경고"],
    },
    {
      strategy_id: "strategy_defensive_quality",
      title: "방어적 저변동성 전략",
      description: "단기 급등 대신 손실 방어와 안정적 리포트 근거를 우선합니다.",
      keyConditions: ["저변동성", "실적 개선", "수급 안정"],
    },
    {
      strategy_id: "strategy_rsi_volume_rebound",
      title: "거래량 반등 전략",
      description: "저변동성 조건을 낮추고 단기 반등 가능성을 더 명확히 추적합니다.",
      keyConditions: ["RSI 저점", "거래량 증가", "BUY/WATCH 분리"],
    },
  ],
};

export const infeasibleExplanation: InfeasibleExplanation = {
  title: "현재 MVP 지원 범위를 벗어난 요청입니다",
  reason: "옵션·선물·레버리지·실시간 주문 실행은 이번 FE MVP 범위가 아닙니다.",
  supportedScope: "현재 MVP에서는 KOSPI200 현물 기반 전략만 지원합니다.",
  examples: [
    "KOSPI200 종목 중 RSI가 낮고 거래량이 증가한 종목 찾아줘",
    "최근 외국인 순매수와 실적 개선이 있는 종목",
    "방어적인 KOSPI200 현물 전략 추천해줘",
  ],
};

export const mockCandidates: CandidateStock[] = [
  {
    ticker: "005930",
    name: "삼성전자",
    sector: "반도체",
    lastPrice: 83500,
    dayChangeRate: 1.28,
    hasPosition: false,
    inCandidateSnapshot: true,
    marketSnapshot: {
      ticker: "005930",
      timestamp: "2026-08-01T09:10:00+09:00",
      metrics: {
        rsi_14: 31.8,
        volume_ratio_20d: 1.42,
        foreign_net_buy_5d: 128.4,
      },
      previous_metrics: {
        rsi_14: 36.2,
        volume_ratio_20d: 0.98,
      },
    },
    evidenceChips: [
      { label: "RSI", value: "31.8", tone: "blue" },
      { label: "Volume", value: "1.42x", tone: "emerald" },
      { label: "Snapshot", value: "IN", tone: "slate" },
    ],
  },
  {
    ticker: "000660",
    name: "SK하이닉스",
    sector: "반도체",
    lastPrice: 192000,
    dayChangeRate: 0.42,
    hasPosition: false,
    inCandidateSnapshot: true,
    marketSnapshot: {
      ticker: "000660",
      timestamp: "2026-08-01T09:10:00+09:00",
      metrics: {
        rsi_14: 39.4,
        volume_ratio_20d: 1.18,
        foreign_net_buy_5d: 64.8,
      },
    },
    evidenceChips: [
      { label: "RSI", value: "39.4", tone: "amber" },
      { label: "Volume", value: "1.18x", tone: "slate" },
      { label: "Trend", value: "Watch", tone: "amber" },
    ],
  },
  {
    ticker: "005380",
    name: "현대차",
    sector: "자동차",
    lastPrice: 244500,
    dayChangeRate: -0.18,
    hasPosition: true,
    inCandidateSnapshot: true,
    marketSnapshot: {
      ticker: "005380",
      timestamp: "2026-08-01T09:10:00+09:00",
      metrics: {
        rsi_14: 53.2,
        volume_ratio_20d: 0.96,
        foreign_net_buy_5d: 14.2,
      },
    },
    evidenceChips: [
      { label: "Position", value: "보유", tone: "blue" },
      { label: "Exit", value: "미충족", tone: "slate" },
      { label: "Flow", value: "+14.2억", tone: "emerald" },
    ],
  },
  {
    ticker: "035720",
    name: "카카오",
    sector: "플랫폼",
    lastPrice: 48100,
    dayChangeRate: -2.84,
    hasPosition: true,
    inCandidateSnapshot: true,
    marketSnapshot: {
      ticker: "035720",
      timestamp: "2026-08-01T09:10:00+09:00",
      metrics: {
        rsi_14: 69.1,
        volume_ratio_20d: 1.36,
        foreign_net_buy_5d: -82.6,
      },
    },
    evidenceChips: [
      { label: "RSI", value: "69.1", tone: "rose" },
      { label: "외국인", value: "-82.6억", tone: "rose" },
      { label: "Exit", value: "ANY 충족", tone: "amber" },
    ],
  },
  {
    ticker: "035420",
    name: "NAVER",
    sector: "플랫폼",
    lastPrice: 218000,
    dayChangeRate: 0.08,
    hasPosition: false,
    inCandidateSnapshot: false,
    marketSnapshot: {
      ticker: "035420",
      timestamp: "2026-08-01T09:10:00+09:00",
      metrics: {
        rsi_14: 34.1,
        volume_ratio_20d: 1.08,
        foreign_net_buy_5d: -11.3,
      },
    },
    evidenceChips: [
      { label: "Snapshot", value: "OUT", tone: "slate" },
      { label: "RSI", value: "34.1", tone: "blue" },
      { label: "Filter", value: "제외", tone: "slate" },
    ],
  },
];

export const mockSignalDecisions: SignalDecision[] = [
  {
    strategy_id: "strategy_rsi_volume_rebound",
    ticker: "005930",
    action: "BUY",
    confidence: 0.84,
    generatedBy: "Signal Judge",
    reasons: [
      "CandidateSnapshot에 포함되어 있습니다.",
      "포지션이 없고 entry_rules가 ALL 조건으로 충족되었습니다.",
      "RSI 31.8과 거래량 1.42x가 반등 후보 조건에 부합합니다.",
    ],
  },
  {
    strategy_id: "strategy_rsi_volume_rebound",
    ticker: "000660",
    action: "WATCH",
    confidence: 0.62,
    generatedBy: "Signal Judge",
    reasons: [
      "CandidateSnapshot에는 포함되지만 entry_rules가 모두 충족되지는 않았습니다.",
      "포지션이 없으므로 BUY가 아니라 WATCH로 관찰합니다.",
    ],
  },
  {
    strategy_id: "strategy_rsi_volume_rebound",
    ticker: "005380",
    action: "HOLD",
    confidence: 0.71,
    generatedBy: "Signal Judge",
    reasons: [
      "현재 보유 중이며 exit_rules가 충족되지 않았습니다.",
      "외국인 순매수와 가격 흐름이 아직 방어적입니다.",
    ],
  },
  {
    strategy_id: "strategy_rsi_volume_rebound",
    ticker: "035720",
    action: "SELL",
    confidence: 0.76,
    generatedBy: "Signal Judge",
    reasons: [
      "현재 보유 중이며 exit_rules 중 RSI 과열과 외국인 순매도 조건이 충족되었습니다.",
      "exit_logic=ANY 기준으로 매도 후보입니다.",
    ],
  },
  {
    strategy_id: "strategy_rsi_volume_rebound",
    ticker: "035420",
    action: "FILTERED_OUT",
    confidence: 0.91,
    generatedBy: "Signal Judge",
    reasons: [
      "CandidateSnapshot에 포함되지 않았습니다.",
      "entry_rules 평가 전에 필터링되었습니다.",
    ],
  },
];

export const mockRiskWarnings: RiskWarning[] = [
  {
    id: "risk_005930_supply",
    ticker: "005930",
    severity: "MEDIUM",
    reason: "BUY action은 유지하지만 메모리 업황 둔화 리포트가 혼재되어 진입 크기 조절이 필요합니다.",
    source: "Risk Manager warning layer",
    evidence: ["영문 IB 리포트 검색: HBM 수요 집중 리스크", "최근 목표가 상향 폭 둔화"],
    report_note:
      "Risk Manager는 BUY를 HOLD/SELL로 바꾸지 않고, 업황 리스크를 보고서 주석으로 분리했습니다.",
  },
  {
    id: "risk_035720_sell_evidence",
    ticker: "035720",
    severity: "HIGH",
    reason: "SELL 판단의 결손을 보강하는 3축 evidence가 동시에 약화 방향입니다.",
    source: "Risk Manager evidence layer",
    evidence: [
      "한경컨센서스 매수의견 감소율: -18%",
      "KIS 외국인 순매도: 5거래일 -82.6억",
      "영문 IB 리포트 검색: 광고 성장률 둔화 caution",
    ],
    report_note:
      "이 evidence는 SELL을 강제 생성하거나 action을 뒤집는 용도가 아니라, Signal Judge의 SELL 설명을 보강하는 위험 주석입니다.",
  },
  {
    id: "risk_000660_watch",
    ticker: "000660",
    severity: "LOW",
    reason: "WATCH 상태에서 거래량 확인 전 추격 매수 위험이 있습니다.",
    source: "Risk Manager caution",
    evidence: ["거래량 20일 평균 대비 1.18x로 BUY 기준 1.25x 미달"],
    report_note: "BUY 전환 전 거래량 확인이 필요합니다.",
  },
];

export const mockReportPreview: ReportSection[] = [
  {
    id: "report_01",
    title: "1. 전략 의도",
    summary: "KOSPI200 현물에서 과매도·거래량 회복이 동시에 발생한 반등 후보를 찾습니다.",
  },
  {
    id: "report_02",
    title: "2. StrategySpec 요약",
    summary: "entry_logic=ALL, exit_logic=ANY로 분리하여 매수·매도 판단 기준을 명확히 유지합니다.",
  },
  {
    id: "report_03",
    title: "3. CandidateSnapshot",
    summary: "snap_001 기준 4개 후보를 우선 평가하고, 미포함 종목은 FILTERED_OUT으로 처리합니다.",
  },
  {
    id: "report_04",
    title: "4. Signal Judge 결과",
    summary: "BUY 1, SELL 1, HOLD 1, WATCH 1, FILTERED_OUT 1로 판단되었습니다.",
    signalJudgeNote: "Signal Judge가 action과 confidence를 산출합니다. Risk Manager는 action을 수정하지 않습니다.",
  },
  {
    id: "report_05",
    title: "5. Risk Manager Warning",
    summary: "BUY·SELL action과 별도로 caution/warning evidence를 보고서에 추가합니다.",
    riskManagerNote:
      "Risk Manager warning layer는 BUY/HOLD/SELL/WATCH/FILTERED_OUT을 변경하지 않고 위험 주석만 생성합니다.",
  },
  {
    id: "report_06",
    title: "6. Backtest Preview",
    summary: "mock 수익률 곡선과 Total Return, Sharpe, MDD, Win Rate 지표를 표시합니다.",
  },
  {
    id: "report_07",
    title: "7. 투자 유의사항",
    summary: "본 결과는 투자 참고용이며, 실제 매매 판단과 책임은 사용자에게 있습니다.",
  },
];

export const mockBacktestMetrics: BacktestMetric[] = [
  { label: "Total Return", value: "+38.4%", detail: "KOSPI200 대비 +14.2%p", tone: "positive" },
  { label: "Sharpe", value: "1.31", detail: "변동성 조정 수익 안정", tone: "positive" },
  { label: "MDD", value: "-11.8%", detail: "최근 18개월 mock 기준", tone: "warning" },
  { label: "Win Rate", value: "57.6%", detail: "월간 승률 mock preview", tone: "neutral" },
];

export const mockBacktestSeries: BacktestPoint[] = [
  { date: "2025-01", strategy: 100, benchmark: 100 },
  { date: "2025-02", strategy: 103.4, benchmark: 101.2 },
  { date: "2025-03", strategy: 101.8, benchmark: 99.8 },
  { date: "2025-04", strategy: 108.6, benchmark: 103.1 },
  { date: "2025-05", strategy: 113.2, benchmark: 106.4 },
  { date: "2025-06", strategy: 111.4, benchmark: 105.9 },
  { date: "2025-07", strategy: 118.9, benchmark: 109.2 },
  { date: "2025-08", strategy: 124.3, benchmark: 112.8 },
  { date: "2025-09", strategy: 121.7, benchmark: 111.5 },
  { date: "2025-10", strategy: 130.8, benchmark: 116.3 },
  { date: "2025-11", strategy: 135.2, benchmark: 119.1 },
  { date: "2025-12", strategy: 138.4, benchmark: 124.2 },
];
