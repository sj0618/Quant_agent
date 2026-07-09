import type { LandingSample } from "../types/quantagent";

export const landingSample: LandingSample = {
  heroStats: [
    { value: "150+", label: "TA-Lib 지표" },
    { value: "10년", label: "백테스트 시계열" },
    { value: "8 노드", label: "LLM 멀티 에이전트" },
    { value: "08:00", label: "매일 자동 발송" },
  ],
  steps: [
    {
      label: "STEP 1",
      title: "자연어 입력",
      description: "원하는 전략을 그대로 적어주세요. 조건식·코드 불필요.",
      example: ['"반도체 섹터에서 RSI 30 이하로', '과매도된 종목 잡아줘"'],
    },
    {
      label: "STEP 2",
      title: "전략 정형화",
      description: "Research 에이전트가 정/반/합 토론으로 StrategySpec을 생성합니다.",
      example: ["universe: KOSPI200·반도체", "buy: RSI ≤ 30 AND vol > 200%"],
    },
    {
      label: "STEP 3",
      title: "후보 코드 백테스트",
      description: "10년 시계열로 후보 코드를 검증하고 objective score 기준으로 선택합니다.",
      example: ["선택 후보 Sharpe 1.42", "MDD -9.4% · Win Rate 58%"],
    },
    {
      label: "STEP 4",
      title: "리포트 발송",
      description: "매일 오전 8시 KOSPI200 추천 종목·근거를 이메일로 보내드립니다.",
      example: ["BUY 삼성전자 0.91", "DROP LG화학 0.41"],
    },
  ],
  reportPreview: {
    title: "반도체 모멘텀 강세 지속, 신규 BUY 2건 추가",
    date: "2026.04.18 · 08:00",
    score: "7.6",
    market: [
      { label: "KOSPI", value: "2,654.21", tone: "positive" },
      { label: "외국인", value: "+2,140억", tone: "positive" },
      { label: "USD/KRW", value: "1,378.20" },
      { label: "VKOSPI", value: "15.4" },
    ],
    signals: [
      { signal: "BUY", name: "삼성전자", ticker: "005930", score: "0.91" },
      { signal: "BUY", name: "SK하이닉스", ticker: "000660", score: "0.84" },
      { signal: "HOLD", name: "현대차", ticker: "005380", score: "0.62" },
      { signal: "DROP", name: "LG화학", ticker: "051910", score: "0.41" },
    ],
  },
  comparisonRows: [
    { item: "기술 지표", traditional: "부분 지원", terminal: "라이브러리 직접 구성", quantAgent: "TA-Lib 150개" },
    { item: "텍스트 뉴스", traditional: "수작업", terminal: "고가 단말", quantAgent: "LLM 자동 요약" },
    { item: "검증", traditional: "없음", terminal: "전문가 설정", quantAgent: "10년 백테스트" },
    { item: "비용", traditional: "수수료만", terminal: "월 수십만 원", quantAgent: "무료" },
    { item: "접근성", traditional: "전용 PC", terminal: "전용 단말기", quantAgent: "웹 브라우저" },
  ],
  principles: [
    {
      label: "DATA",
      title: "검증 가능한 데이터 소스",
      description: "KIS Open API · DART · 한경컨센서스 · 에이전틱 서치. 4-레이어 데이터로 매수·매도 모두 근거를 제시합니다.",
    },
    {
      label: "TRANSPARENCY",
      title: "투명한 거래비용 모델",
      description: "수수료 0.015% · 거래세 0.23% · 슬리피지 0.1%를 백테스트에 반영. walk-forward로 과적합도 방지합니다.",
    },
    {
      label: "COMPLIANCE",
      title: "PIPA 준수 · 면책 명시",
      description: '개인정보보호법 명시 동의 수집. 모든 리포트에 "투자 권유가 아닙니다" 면책 조항을 포함합니다.',
    },
  ],
  faqs: [
    {
      question: "투자 권유인가요?",
      answer:
        "아니요. QuantAgent는 과거 데이터 기반 분석 도구이며, 모든 신호와 리포트는 투자 의사결정을 돕는 참고 자료입니다. 실제 매매·손익은 사용자 본인의 책임입니다.",
    },
    { question: "왜 무료인가요?", answer: "초기 버전은 전략 입력, 백테스트, Daily 리포트 품질 검증을 위해 무료로 제공합니다." },
    { question: "내 자산 정보를 입력해야 하나요?", answer: "아니요. 현재 목업 범위는 전략 분석과 리포트 발송이며 자산 정보나 주문 권한을 요구하지 않습니다." },
    { question: "어떤 종목을 분석하나요?", answer: "현재 기준은 KOSPI200 현물이며, 전략 조건에 맞는 섹터와 종목 후보를 선별합니다." },
    { question: "리포트는 언제 받나요?", answer: "Daily 리포트는 매일 오전 8시에 생성되며, 마이페이지 알림 설정에서 이메일 수신 여부를 바꿀 수 있습니다." },
  ],
};
