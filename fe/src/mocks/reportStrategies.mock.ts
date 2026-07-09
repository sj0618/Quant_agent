import { tradingCandidates } from "./app.mock";
import { reportDetails } from "./reports.mock";
import type {
  EmailDigestHistoryEntry,
  ReportDeliveryStatus,
  ReportDetail,
  StrategyReportDetail,
} from "../types/quantagent";

type EmailReportSeed = Pick<
  ReportDetail,
  | "id"
  | "strategyId"
  | "strategyName"
  | "strategyUniverse"
  | "date"
  | "weekday"
  | "sentAt"
  | "title"
  | "summary"
  | "status"
  | "recommendationScore"
  | "signals"
  | "marketSnapshot"
  | "marketBrief"
  | "marketContext"
  | "conclusion"
  | "warningNote"
  | "riskManagerOverride"
> & {
  recipient: string;
  news: ReportDetail["news"];
  candidateTickers: string[];
};

type StrategySeed = {
  id: string;
  name: string;
  description: string;
  universe: string;
  timeframe: string;
  entrySummary: string;
  exitSummary: string;
  riskSummary: string;
  tags: string[];
  emailReports: EmailReportSeed[];
};

const baseReport = reportDetails[0];

function createEmailReport(seed: EmailReportSeed): ReportDetail {
  const { candidateTickers, news, ...reportSeed } = seed;

  return {
    ...baseReport,
    ...reportSeed,
    news,
    candidates: tradingCandidates.filter((candidate) => candidateTickers.includes(candidate.ticker)),
  };
}

function normalizeDate(value: string) {
  return value.replace(/\./g, "-");
}

function statusPriority(status: ReportDeliveryStatus) {
  if (status === "resent") return 2;
  if (status === "failed") return 1;
  return 0;
}

const strategySeeds: StrategySeed[] = [
  {
    id: "semiconductor-momentum",
    name: "반도체 모멘텀 + 기관 매수",
    description: "반도체 업종 내 상대강도와 외국인 순매수 흐름이 동시에 강화되는 종목에 집중하는 모멘텀 전략입니다.",
    universe: "KOSPI200 · 반도체",
    timeframe: "daily",
    entrySummary: "20일 상대강도 상위권이면서 외국인 순매수가 동반된 종목만 진입 후보로 올립니다.",
    exitSummary: "상대강도 둔화 또는 외국인 수급 반전이 확인되면 비중을 축소합니다.",
    riskSummary: "실적 발표와 환율 급등 구간에서는 신규 비중 확대를 늦춥니다.",
    tags: ["모멘텀", "외국인 수급", "섹터 강도"],
    emailReports: [
      {
        id: "semiconductor-momentum-2026-04-18",
        strategyId: "semiconductor-momentum",
        strategyName: "반도체 모멘텀 + 기관 매수",
        strategyUniverse: "KOSPI200 · 반도체",
        date: "2026.04.18",
        weekday: "목요일",
        sentAt: "오전 8:00 전송",
        title: "반도체 모멘텀 강세 지속, 신규 BUY 2건 추가",
        summary: "메모리 업황 회복 기대와 외국인 순매수가 겹치며 핵심 반도체 종목의 모멘텀이 유지됐습니다.",
        status: "sent",
        recommendationScore: "7.6",
        signals: { BUY: 2, HOLD: 1, DROP: 1 },
        marketSnapshot: [
          { label: "KOSPI", value: "2,654.21 (+0.84%)", tone: "positive" },
          { label: "외국인", value: "+2,140억", tone: "positive" },
          { label: "USD/KRW", value: "1,378.20" },
        ],
        recipient: "홍길동 님께",
        marketBrief: "HBM 수요 기대와 외국인 수급 개선으로 반도체 대형주 중심 강세가 이어졌습니다.",
        marketContext: "외국인 순매수와 메모리 업황 기대가 동시에 강화되며 반도체 대형주가 시장 주도권을 유지했습니다.",
        news: [
          { rank: 1, title: "HBM 공급 확대 기대에 반도체 장비주 동반 상승", source: "연합뉴스", tone: "positive" },
          { rank: 2, title: "외국인 KOSPI 5거래일 연속 순매수", source: "한국경제", tone: "positive" },
          { rank: 3, title: "원화 환율 안정세에 수출주 선호 유지", source: "Reuters", tone: "neutral" },
          { rank: 4, title: "메모리 가격 반등 속도는 종목별 차별화", source: "한경컨센서스", tone: "warning" },
          { rank: 5, title: "실적 시즌 앞두고 반도체 대형주 변동성 확대 가능성", source: "DART", tone: "warning" },
        ],
        candidateTickers: ["005930", "000660", "005380", "051910"],
        conclusion: "주도 업종 내 강한 종목을 유지하는 구간이며 신규 진입은 분할 매수 관점이 적절합니다.",
        warningNote: "실적 발표 직전 구간에서는 일시적 변동성이 커질 수 있어 비중 확대 속도를 조절하세요.",
        riskManagerOverride: "환율 급등이 동반되지 않는 한 모멘텀 우위 신호를 유지합니다.",
      },
      {
        id: "semiconductor-momentum-2026-04-17",
        strategyId: "semiconductor-momentum",
        strategyName: "반도체 모멘텀 + 기관 매수",
        strategyUniverse: "KOSPI200 · 반도체",
        date: "2026.04.17",
        weekday: "수요일",
        sentAt: "오전 8:07 재전송",
        title: "전일 후보 조정, SK하이닉스 BUY 유지",
        summary: "외국인 4일 연속 순매수 흐름 속에서 핵심 반도체 종목의 BUY 의견을 재확인했습니다.",
        status: "resent",
        recommendationScore: "7.4",
        signals: { BUY: 2, HOLD: 1, DROP: 1 },
        marketSnapshot: [
          { label: "KOSPI", value: "+0.42%", tone: "positive" },
          { label: "외국인", value: "+1,820억", tone: "positive" },
        ],
        recipient: "홍길동 님께",
        marketBrief: "실적 시즌 진입과 함께 반도체 중심 순환매가 강화됐습니다.",
        marketContext: "섹터 내 선도 종목으로 자금이 다시 모이며 상대강도 상위권 종목의 우위가 이어졌습니다.",
        news: [
          { rank: 1, title: "메모리 재고 정상화 기대감 부각", source: "연합뉴스", tone: "positive" },
          { rank: 2, title: "AI 서버 수요가 반도체 업황 회복 기대 자극", source: "한국경제", tone: "positive" },
          { rank: 3, title: "반도체 대형주 위주 순환매 재개", source: "Reuters", tone: "neutral" },
          { rank: 4, title: "실적 시즌 변동성 확대 가능성", source: "DART", tone: "warning" },
          { rank: 5, title: "원화 강세 둔화 시 수출주 수급 약화 가능성", source: "한경컨센서스", tone: "warning" },
        ],
        candidateTickers: ["005930", "000660", "051910"],
        conclusion: "주도 섹터 집중이 유효하나 실적 발표 전후 변동성은 주의가 필요합니다.",
        warningNote: "재전송 이력이 있었던 날이라 장중 급등 추격보다 종가 기준 확인이 더 안전합니다.",
        riskManagerOverride: "시장 변동성 확대 전까진 signal judge 결과를 유지합니다.",
      },
      {
        id: "semiconductor-momentum-2026-04-16",
        strategyId: "semiconductor-momentum",
        strategyName: "반도체 모멘텀 + 기관 매수",
        strategyUniverse: "KOSPI200 · 반도체",
        date: "2026.04.16",
        weekday: "화요일",
        sentAt: "오전 8:00 전송",
        title: "실적 시즌 본격화, 반도체 대형주 중심 선별 매수",
        summary: "실적 기대감이 반영되며 BUY와 HOLD가 혼합된 선별 매수 구간이 형성됐습니다.",
        status: "sent",
        recommendationScore: "7.1",
        signals: { BUY: 2, HOLD: 2, DROP: 0 },
        marketSnapshot: [{ label: "KOSPI", value: "+0.42%", tone: "positive" }],
        recipient: "홍길동 님께",
        marketBrief: "실적 시즌 초입에서 반도체와 자동차 중심 차별화가 나타났습니다.",
        marketContext: "업종 대표주 중심 강도는 유지됐지만 후보 종목 간 편차가 커져 선별 기준이 중요해졌습니다.",
        news: [
          { rank: 1, title: "실적 시즌 앞두고 반도체 기대감 확대", source: "연합뉴스", tone: "positive" },
          { rank: 2, title: "기관 수급은 선택적 순매수 전환", source: "한국경제", tone: "neutral" },
          { rank: 3, title: "장비주보다 대형주 선호가 두드러짐", source: "Reuters", tone: "neutral" },
          { rank: 4, title: "일부 소재주는 컨센서스 하향", source: "한경컨센서스", tone: "warning" },
          { rank: 5, title: "환율 반등 시 변동성 재확대 가능성", source: "DART", tone: "warning" },
        ],
        candidateTickers: ["005930", "000660", "005380"],
        conclusion: "섹터 강도는 유지되지만 후보 종목 간 편차가 커져 선별 접근이 필요합니다.",
        warningNote: "대표 종목 위주로 비중을 유지하고 후발주는 거래대금 확인 이후 접근하세요.",
        riskManagerOverride: "급격한 환율 움직임이 없을 때만 공격적 비중 확대를 고려하세요.",
      },
    ],
  },
  {
    id: "rsi-rebound",
    name: "RSI 과매도 반등 전략",
    description: "단기 과매도 종목 중 RSI 저점 이탈 이후 거래대금이 회복되는 구간만 선별하는 반등 전략입니다.",
    universe: "KOSPI200 · 단기 반등 후보",
    timeframe: "daily",
    entrySummary: "RSI 30 이하 이탈 이후 거래량이 회복되고 종가가 전일 고점을 되찾은 종목만 진입합니다.",
    exitSummary: "RSI가 중립권으로 복귀하거나 반등 거래대금이 꺾이면 빠르게 정리합니다.",
    riskSummary: "낙폭과대 반등은 실패 확률이 높아 손절 규칙을 우선 적용합니다.",
    tags: ["RSI", "과매도", "단기 반등"],
    emailReports: [
      {
        id: "rsi-rebound-2026-04-18",
        strategyId: "rsi-rebound",
        strategyName: "RSI 과매도 반등 전략",
        strategyUniverse: "KOSPI200 · 단기 반등 후보",
        date: "2026.04.18",
        weekday: "목요일",
        sentAt: "오전 8:00 전송",
        title: "RSI 반등 후보 부상, 분할 진입 권고",
        summary: "과매도 해소 초기 구간에서 단기 BUY 후보가 재등장했습니다.",
        status: "sent",
        recommendationScore: "6.8",
        signals: { BUY: 1, HOLD: 2, DROP: 0 },
        marketSnapshot: [
          { label: "KOSPI", value: "+0.84%", tone: "positive" },
          { label: "VKOSPI", value: "15.4" },
        ],
        recipient: "홍길동 님께",
        marketBrief: "낙폭 과대 종목에 저가 매수 수요가 유입되며 반등 후보가 늘었습니다.",
        marketContext: "거래대금이 회복된 낙폭과대 종목 위주로 단기 반등 시도가 확인됐습니다.",
        news: [
          { rank: 1, title: "플랫폼·2차전지 낙폭 과대주 저가 매수 유입", source: "연합뉴스", tone: "positive" },
          { rank: 2, title: "단기 변동성 완화로 반등 전략 선호 회복", source: "한국경제", tone: "positive" },
          { rank: 3, title: "거래대금 회복 없는 반등은 제한적", source: "Reuters", tone: "warning" },
          { rank: 4, title: "테마주 급반등 후 변동성 재확대 주의", source: "한경컨센서스", tone: "warning" },
          { rank: 5, title: "장중 변동성 확대 시 손절 규칙 중요", source: "DART", tone: "warning" },
        ],
        candidateTickers: ["035420", "035720", "051910", "003670"],
        conclusion: "분할 진입과 손절 기준을 함께 쓰는 조건부 BUY가 적절합니다.",
        warningNote: "반등 확인 이전 추격 진입은 피하고 거래량 회복 여부를 먼저 확인하세요.",
        riskManagerOverride: "변동성 확대로 추격 매수는 피하고 거래량 동반 여부를 확인하세요.",
      },
      {
        id: "rsi-rebound-2026-04-17",
        strategyId: "rsi-rebound",
        strategyName: "RSI 과매도 반등 전략",
        strategyUniverse: "KOSPI200 · 단기 반등 후보",
        date: "2026.04.17",
        weekday: "수요일",
        sentAt: "오전 8:02 전송 실패",
        title: "반등 후보 유지, 신규 진입은 보수적으로",
        summary: "RSI 저점 탈출 시도는 이어졌지만 확인 신호가 부족해 HOLD 우세로 정리됐습니다.",
        status: "failed",
        recommendationScore: "6.3",
        signals: { BUY: 1, HOLD: 2, DROP: 1 },
        marketSnapshot: [{ label: "KOSPI", value: "+0.42%", tone: "positive" }],
        recipient: "홍길동 님께",
        marketBrief: "반등 시도는 유효하나 거래대금 집중은 아직 제한적입니다.",
        marketContext: "낙폭 과대 종목의 가격 반등은 있었지만 거래대금이 따라오지 않아 추세 전환 확신은 부족했습니다.",
        news: [
          { rank: 1, title: "낙폭 과대 성장주 반등 시도", source: "연합뉴스", tone: "neutral" },
          { rank: 2, title: "거래대금 약한 반등은 지속성 제한", source: "한국경제", tone: "warning" },
          { rank: 3, title: "플랫폼주 기술적 반등 신호 혼조", source: "Reuters", tone: "neutral" },
          { rank: 4, title: "단기 트레이더 매수세는 유입", source: "한경컨센서스", tone: "positive" },
          { rank: 5, title: "실적 공백 구간 변동성 유의", source: "DART", tone: "warning" },
        ],
        candidateTickers: ["035420", "035720", "003670"],
        conclusion: "기존 관찰 종목 유지가 우선이며 신규 진입은 장중 확인 후가 적절합니다.",
        warningNote: "전송 실패 이력이 남은 날이라 보고서 확인 전 자동 집행처럼 해석하지 마세요.",
        riskManagerOverride: "과매도 반등은 실패 확률도 높아 손절 규칙을 반드시 함께 적용하세요.",
      },
      {
        id: "rsi-rebound-2026-04-16",
        strategyId: "rsi-rebound",
        strategyName: "RSI 과매도 반등 전략",
        strategyUniverse: "KOSPI200 · 단기 반등 후보",
        date: "2026.04.16",
        weekday: "화요일",
        sentAt: "오전 8:00 전송",
        title: "저가매수 대기, 관찰 리스트 유지",
        summary: "아직 본격 반등으로 보기 어려워 HOLD 비중이 높은 관찰 단계였습니다.",
        status: "sent",
        recommendationScore: "5.9",
        signals: { BUY: 0, HOLD: 3, DROP: 1 },
        marketSnapshot: [{ label: "VKOSPI", value: "16.8", tone: "warning" }],
        recipient: "홍길동 님께",
        marketBrief: "낙폭은 컸지만 추세 전환 신호가 약한 종목이 많았습니다.",
        marketContext: "과매도 진입 종목 수는 많았지만 거래량이 붙지 않아 관찰 리스트 유지가 우선이었습니다.",
        news: [
          { rank: 1, title: "낙폭 과대주 저점 탐색 구간 진입", source: "연합뉴스", tone: "neutral" },
          { rank: 2, title: "단기 반등 전략은 거래량 확인이 관건", source: "한국경제", tone: "warning" },
          { rank: 3, title: "VKOSPI 재상승으로 추세 전환 확인 지연", source: "Reuters", tone: "warning" },
          { rank: 4, title: "플랫폼·2차전지 약세 지속", source: "한경컨센서스", tone: "negative" },
          { rank: 5, title: "장중 변동성 확대 대비 필요", source: "DART", tone: "warning" },
        ],
        candidateTickers: ["035420", "035720", "051910"],
        conclusion: "당일 강세보다 다음 확인 신호를 대기하는 전략이 적절합니다.",
        warningNote: "낙폭과대라는 이유만으로 진입하지 말고 반등 거래량과 종가 회복을 함께 보세요.",
        riskManagerOverride: "거래량 없이 RSI만 반등하는 종목은 후보에서 제외하세요.",
      },
    ],
  },
  {
    id: "dividend-defense",
    name: "배당 방어주 로테이션",
    description: "현금흐름 안정성과 배당 지속성이 높은 대형주로 방어 비중을 옮기는 로테이션 전략입니다.",
    universe: "KOSPI 고배당 · 방어주",
    timeframe: "daily",
    entrySummary: "배당 안정성과 이익 추정치 방어력이 유지되는 종목만 편입 후보로 삼습니다.",
    exitSummary: "금리 민감도가 급격히 높아지거나 배당 매력이 약해지면 비중을 줄입니다.",
    riskSummary: "강한 위험선호 장세에서는 상대수익률이 둔화될 수 있습니다.",
    tags: ["배당", "방어주", "로테이션"],
    emailReports: [
      {
        id: "dividend-defense-2026-04-18",
        strategyId: "dividend-defense",
        strategyName: "배당 방어주 로테이션",
        strategyUniverse: "KOSPI 고배당 · 방어주",
        date: "2026.04.18",
        weekday: "목요일",
        sentAt: "오전 8:03 전송 실패",
        title: "방어주 상대강도 회복, HOLD 우세",
        summary: "금리 경계감 속 방어주 선호가 회복됐지만 공격적 비중 확대까지는 확인되지 않았습니다.",
        status: "failed",
        recommendationScore: "6.5",
        signals: { BUY: 1, HOLD: 2, DROP: 0 },
        marketSnapshot: [
          { label: "KOSPI", value: "+0.84%", tone: "positive" },
          { label: "10Y 금리", value: "3.42%", tone: "warning" },
        ],
        recipient: "홍길동 님께",
        marketBrief: "고배당·현금흐름 안정 업종의 하방 방어력이 재확인됐습니다.",
        marketContext: "강한 위험선호 장세는 아니었지만 금리 경계감이 남아 있어 방어주 수급이 꾸준히 이어졌습니다.",
        news: [
          { rank: 1, title: "고배당 대형주에 방어 자금 유입", source: "연합뉴스", tone: "positive" },
          { rank: 2, title: "금리 불확실성에 배당주 재평가", source: "한국경제", tone: "positive" },
          { rank: 3, title: "위험선호 회복 시 방어주 수익률 둔화 가능성", source: "Reuters", tone: "warning" },
          { rank: 4, title: "자동차·대형주 배당 매력 재부각", source: "한경컨센서스", tone: "neutral" },
          { rank: 5, title: "금리 재상승 구간 밸류 재조정 유의", source: "DART", tone: "warning" },
        ],
        candidateTickers: ["005380", "000270", "005930"],
        conclusion: "공격적 매수보다 비중 유지와 대기자금 분배에 적합한 구간입니다.",
        warningNote: "전송 실패가 있었더라도 전략 신호 자체는 유지 관점이며, 확인 전 자동 비중 확대는 피하세요.",
        riskManagerOverride: "금리 재상승 시 배당주의 상대 메리트가 약화될 수 있습니다.",
      },
      {
        id: "dividend-defense-2026-04-17",
        strategyId: "dividend-defense",
        strategyName: "배당 방어주 로테이션",
        strategyUniverse: "KOSPI 고배당 · 방어주",
        date: "2026.04.17",
        weekday: "수요일",
        sentAt: "오전 8:06 재전송",
        title: "배당주 비중 유지, 신규 매수는 제한적",
        summary: "시장 변동성이 완화되며 방어주 메리트는 유지됐지만 신규 BUY는 제한적이었습니다.",
        status: "resent",
        recommendationScore: "6.1",
        signals: { BUY: 0, HOLD: 3, DROP: 1 },
        marketSnapshot: [{ label: "KOSPI", value: "+0.42%", tone: "positive" }],
        recipient: "홍길동 님께",
        marketBrief: "방어주 수급은 안정적이나 상승 탄력은 둔화됐습니다.",
        marketContext: "배당 안정성이 높은 종목이 시장 대비 덜 흔들렸지만, 공격적 매수로 이어질 강도는 부족했습니다.",
        news: [
          { rank: 1, title: "고배당 대형주 상대 강도 유지", source: "연합뉴스", tone: "neutral" },
          { rank: 2, title: "방어주 ETF 자금 유입 지속", source: "한국경제", tone: "positive" },
          { rank: 3, title: "성장주 반등 시 상대수익률 둔화 가능성", source: "Reuters", tone: "warning" },
          { rank: 4, title: "배당락 시즌 전 점검 필요", source: "한경컨센서스", tone: "warning" },
          { rank: 5, title: "현금흐름 안정 기업 선별 중요", source: "DART", tone: "neutral" },
        ],
        candidateTickers: ["005380", "000270", "051910"],
        conclusion: "현금흐름 안정성 중심 종목 유지가 여전히 유효합니다.",
        warningNote: "재전송된 리포트라면 최종 문안 기준으로만 대응하고 이전 초안 판단은 버리세요.",
        riskManagerOverride: "배당락 전후 이벤트 구간에서는 과도한 비중 확대를 피하세요.",
      },
      {
        id: "dividend-defense-2026-04-16",
        strategyId: "dividend-defense",
        strategyName: "배당 방어주 로테이션",
        strategyUniverse: "KOSPI 고배당 · 방어주",
        date: "2026.04.16",
        weekday: "화요일",
        sentAt: "오전 8:00 전송",
        title: "유틸리티·통신 방어 강도 유지",
        summary: "방어 업종이 상대적 우위를 보였지만 BUY까지는 제한적이었습니다.",
        status: "sent",
        recommendationScore: "5.7",
        signals: { BUY: 0, HOLD: 2, DROP: 1 },
        marketSnapshot: [{ label: "배당지수", value: "+0.18%", tone: "positive" }],
        recipient: "홍길동 님께",
        marketBrief: "시장 주도주는 아니지만 포트폴리오 방어 목적으론 의미 있는 흐름이 유지됐습니다.",
        marketContext: "위험자산 선호가 약한 날에는 방어주가 상대적 우위를 보였고, 대형 배당주 중심으로 하방 경직성이 확인됐습니다.",
        news: [
          { rank: 1, title: "배당지수 완만한 강세 유지", source: "연합뉴스", tone: "positive" },
          { rank: 2, title: "방어주 로테이션은 수익보다 방어 목적", source: "한국경제", tone: "neutral" },
          { rank: 3, title: "장기 금리 반등 시 배당주 할인율 부담", source: "Reuters", tone: "warning" },
          { rank: 4, title: "대형 가치주 선호 유지", source: "한경컨센서스", tone: "neutral" },
          { rank: 5, title: "배당 안정성 재검토 필요", source: "DART", tone: "warning" },
        ],
        candidateTickers: ["005380", "000270", "005930"],
        conclusion: "방어주 로테이션은 유지하되 수익 기대보다 변동성 완화 목적이 적절합니다.",
        warningNote: "시장 강세가 본격화되면 방어주 비중이 상대적으로 뒤처질 수 있습니다.",
        riskManagerOverride: "시장 강세 전환 시 상대 수익률 저하 가능성을 감안해야 합니다.",
      },
    ],
  },
];

export const strategyReportDetails: StrategyReportDetail[] = strategySeeds.map((seed) => {
  const emailReports = seed.emailReports.map(createEmailReport);
  const latestReport = emailReports[0];

  return {
    strategy: {
      id: seed.id,
      name: seed.name,
      description: seed.description,
      universe: seed.universe,
      timeframe: seed.timeframe,
      entrySummary: seed.entrySummary,
      exitSummary: seed.exitSummary,
      riskSummary: seed.riskSummary,
      latestSentAt: latestReport.sentAt,
      latestReportDate: latestReport.date,
      latestStatus: latestReport.status,
      latestEmailReportId: latestReport.id,
      recommendationScore: latestReport.recommendationScore,
      signals: latestReport.signals,
      summary: latestReport.summary,
      tags: seed.tags,
    },
    emailReports,
  };
});

export const emailDigestHistoryEntries: EmailDigestHistoryEntry[] = strategyReportDetails
  .flatMap((detail) =>
    detail.emailReports.map((report) => ({
      id: `history:${report.id}`,
      reportId: report.id,
      strategyId: detail.strategy.id,
      strategyName: detail.strategy.name,
      reportDate: report.date,
      sentAt: report.sentAt,
      status: report.status,
      title: report.title,
    })),
  )
  .sort((left, right) => {
    const dateCompare = normalizeDate(right.reportDate).localeCompare(normalizeDate(left.reportDate));
    if (dateCompare !== 0) return dateCompare;
    return statusPriority(right.status) - statusPriority(left.status);
  });
