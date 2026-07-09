import type { DailyDigestReport } from "../types/quantagent";

export const dailyDigestReport: DailyDigestReport = {
  header: {
    reportDate: "2026년 6월 29일",
    userName: "00",
    strategyCount: 3,
  },
  overallSummary: [
    "총 3개 전략 중 1개 전략에서 BUY 신호가 발생했습니다.",
    "1개 전략은 HOLD, 1개 전략은 관망 상태입니다.",
    "최근 백테스트 기준 평균 수익률은 8.4%, 평균 MDD는 -5.2%입니다.",
    "변동성이 확대된 전략은 리스크 관리가 필요합니다.",
  ],
  comparisonRows: [
    { strategyId: "rsi", name: "RSI 전략", todaySignal: "BUY", totalReturn: 0.124, maxDrawdown: -0.068, sharpeRatio: 1.21, status: "주목" },
    { strategyId: "macd", name: "MACD 전략", todaySignal: "HOLD", totalReturn: 0.071, maxDrawdown: -0.042, sharpeRatio: 0.94, status: "유지" },
    { strategyId: "boll", name: "볼린저 전략", todaySignal: "DROP", totalReturn: 0.035, maxDrawdown: -0.029, sharpeRatio: 0.71, status: "관망" },
  ],
  strategyCards: [
    {
      strategyId: "rsi",
      title: "RSI 과매도 반등 전략",
      todaySignal: "BUY",
      targets: ["삼성전자", "SK하이닉스"],
      totalReturn: 0.124,
      maxDrawdown: -0.068,
      sharpeRatio: 1.21,
      winRate: 0.583,
      tradeCount: 24,
      aiInterpretation: "최근 하락 이후 RSI 과매도 구간에서 반등 신호가 발생했습니다. 다만 변동성이 확대되어 진입 비중을 낮추는 것이 적절합니다.",
      caution: "손절 기준을 명확히 설정해야 하며, 거래량 확인이 필요합니다.",
    },
    {
      strategyId: "macd",
      title: "MACD 골든크로스 전략",
      todaySignal: "HOLD",
      targets: ["현대차"],
      totalReturn: 0.071,
      maxDrawdown: -0.042,
      sharpeRatio: 0.94,
      winRate: 0.52,
      tradeCount: 18,
      aiInterpretation: "추세 확인이 부족해 신규 진입보다는 기존 포지션 유지가 적절한 구간입니다.",
      caution: "추세 전환 신호가 나올 때까지 신규 매수는 보류하세요.",
    },
    {
      strategyId: "boll",
      title: "볼린저 밴드 돌파 전략",
      todaySignal: "DROP",
      targets: ["LG화학"],
      totalReturn: 0.035,
      maxDrawdown: -0.029,
      sharpeRatio: 0.71,
      winRate: 0.47,
      tradeCount: 12,
      aiInterpretation: "아직 명확한 진입 신호가 없어 관망이 필요한 구간입니다.",
      caution: "밴드 하단 이탈 시 추가 하락 가능성을 염두에 두세요.",
    },
  ],
  aiOverallComment:
    "현재 선택된 3개 전략 중 RSI 전략은 단기 매수 신호가 발생했으나, 최근 변동성이 커진 상태이므로 분할 진입이 적절합니다. " +
    "MACD 전략은 추세 확인이 부족해 유지 관점이 적절하며, 볼린저 밴드 전략은 아직 명확한 진입 신호가 없어 관망이 필요합니다.",
  marketBrief: {
    headline: "美 연준 금리 동결 시사에 위험자산 선호 회복, KOSPI 반도체 중심 강세",
    items: [
      {
        title: "반도체 업황 저점 통과, HBM 수요 확대 전망",
        source: "연합뉴스",
        publishedAt: "2026-06-29",
        tone: "positive",
        summary: "메모리 사이클 회복 기대감에 외국인 순매수가 이어지고 있습니다.",
      },
      {
        title: "美 연준 6월 금리 동결 시사, 위험자산 선호 회복",
        source: "Reuters",
        publishedAt: "2026-06-29",
        tone: "positive",
        summary: "연준의 매파적 발언 완화로 글로벌 증시 위험자산 선호가 회복되는 분위기입니다.",
      },
      {
        title: "원/달러 환율 변동성 확대, 수출주 영향 주시",
        source: "한국경제",
        publishedAt: "2026-06-29",
        tone: "warning",
        summary: "환율 변동성이 커지며 수출 비중이 높은 종목의 단기 변동성 확대가 예상됩니다.",
      },
    ],
  },
  footer: [
    "본 리포트는 투자 참고용 정보이며, 투자 판단과 책임은 사용자 본인에게 있습니다.",
    "QuantAgent는 알고리즘 기반 분석 결과를 제공하며 수익을 보장하지 않습니다.",
    "이 메일은 사용자가 선택한 전략을 기준으로 매일 오전 8시에 자동 발송됩니다.",
  ],
};
