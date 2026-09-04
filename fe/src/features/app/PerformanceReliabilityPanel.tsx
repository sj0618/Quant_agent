import { Card } from "../../components/common/Card";
import type { AIBacktestReliability } from "../../types/quantagent";

interface PerformanceReliabilityPanelProps {
  reliability: AIBacktestReliability;
}

/**
 * The performance overview and the full performance tab describe the same evidence.
 * This intentionally keeps the compact Workspace status strip: the reliability record
 * is supporting context, not a second metric dashboard competing with the report cards.
 */
export function PerformanceReliabilityPanel({ reliability }: PerformanceReliabilityPanelProps) {
  const notes = [...reliability.reasons, ...reliability.warnings];

  return (
    <Card className={`reliability-strip reliability-strip--${reliability.status}`}>
      <div className="reliability-strip__summary">
        <div>
          <strong>성과 신뢰도: {reliabilityLabel(reliability.status)}</strong>
          <span>{reliability.trading_days}거래일 · {reliability.ticker_count}종목 · 거래 {reliability.trade_count}회</span>
        </div>
      </div>
      {notes.length || reliability.status !== "sufficient" ? (
        <p>{notes.join(" · ") || reliabilityMessage(reliability.status)}</p>
      ) : null}
    </Card>
  );
}

function reliabilityLabel(status: AIBacktestReliability["status"]) {
  return { sufficient: "충분", limited: "제한적", insufficient: "부족" }[status];
}

function reliabilityMessage(status: AIBacktestReliability["status"]) {
  return {
    sufficient: "기간·종목·거래 수가 공개 성과 기준을 충족했습니다.",
    limited: "수치는 계산됐지만 표본 한계가 있어 참고용으로 해석해야 합니다.",
    insufficient: "표본이 너무 작아 수익률·샤프·낙폭 같은 숫자는 참고용입니다. 아래 사유가 부족한 항목입니다.",
  }[status];
}
