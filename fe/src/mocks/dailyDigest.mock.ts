import type { DailyDigestReport } from "../types/quantagent";

export const dailyDigestReport: DailyDigestReport = {
  header: {
    reportDate: "2026년 6월 29일",
    userName: "00",
    strategyCount: 3,
  },
  overallSummary: [
    "총 3개 전략 중 **1개 전략에서 BUY 신호**가 발생했습니다.",
    "1개 전략은 HOLD, 1개 전략은 관망 상태입니다.",
    "최근 백테스트 기준 평균 수익률은 8.4%, 평균 MDD는 -5.2%입니다.",
    "변동성이 확대된 전략은 **리스크 관리가 필요**합니다.",
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
      aiInterpretation:
        "RSI는 주가가 최근 얼마나 과하게 떨어졌는지를 보는 지표입니다. 이 전략은 RSI가 30 아래로 내려가 " +
        "**과매도** 구간에 들어간 뒤 반등이 시작될 때 사는 방식인데, 오늘 삼성전자와 SK하이닉스가 그 조건을 " +
        "만족해 **BUY 신호**가 나왔습니다. 과거 성적을 보면 10번 중 약 6번 수익이 났고(승률 58.3%), " +
        "수익이 손실보다 얼마나 컸는지를 나타내는 Sharpe 1.21은 **양호한 편**입니다.",
      caution:
        "다만 지금은 변동성이 커진 구간이라 **한 번에 다 사지 말고 2~3회로 나눠 사는 분할 매수**를 권합니다. " +
        "과매도 반등은 실패하는 경우도 적지 않으니 **살 때 손절 가격을 미리 정해두고**, 반등에 거래량이 함께 " +
        "늘고 있는지 확인하세요.",
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
      aiInterpretation:
        "MACD는 단기 가격 흐름이 장기 흐름을 위로 뚫는 순간을 **추세 전환 신호**로 보는 지표입니다. 오늘 " +
        "현대차는 그 전환이 아직 확실하지 않아 **HOLD**, 즉 새로 사기보다 **이미 갖고 있다면 그대로 두는 " +
        "구간**입니다. 승률 52%로 이기고 지는 비율은 반반에 가깝지만, 이길 때 더 크게 버는 쪽에 가까운 " +
        "전략이라 이 수치 자체가 나쁜 신호는 아닙니다.",
      caution:
        "**추세가 확인되기 전 신규 매수는 보류**하세요. 방향이 정해지지 않은 구간에서 들어가면 작은 " +
        "등락에도 흔들리기 쉽습니다. MACD선이 신호선을 넘은 상태가 **2~3거래일 유지되는지** 확인한 뒤 " +
        "판단해도 늦지 않습니다.",
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
      aiInterpretation:
        "볼린저 밴드는 주가가 평소 움직이는 범위를 위아래 띠로 그려주는 지표이고, 이 전략은 주가가 위쪽 띠를 " +
        "뚫고 올라갈 때 따라 사는 방식입니다. 오늘 LG화학은 그 돌파가 나오지 않아 **신규 진입 신호가 " +
        "없습니다**. 승률 47%, Sharpe 0.71로 세 전략 중 **성적이 가장 약한 편**이라 비중을 크게 두기는 " +
        "어렵습니다.",
      caution:
        "**신호가 없을 때 억지로 사지 않는 것도 전략의 일부**입니다. 특히 주가가 아래쪽 띠를 이탈하면 추가 " +
        "하락으로 이어질 수 있으니, **밴드 상단 돌파가 확인될 때까지 기다리세요.**",
    },
  ],
  aiOverallComment:
    "오늘 실제로 움직일 만한 전략은 **RSI 하나**입니다. 단기 매수 신호가 나왔지만 변동성이 커진 상태라 " +
    "**한 번에 사지 말고 나눠서 진입**하는 편이 안전합니다. MACD는 추세가 확인되지 않아 **기존 보유만 유지**, " +
    "볼린저는 진입 신호 자체가 없어 **기다리는 구간**입니다. 정리하면 오늘은 새로 벌리기보다 " +
    "**RSI 한 종목에만 조심스럽게 접근**하는 날에 가깝습니다.",
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
