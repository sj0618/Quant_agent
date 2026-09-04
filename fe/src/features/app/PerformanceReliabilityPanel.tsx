import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import type { AIBacktestReliability } from "../../types/quantagent";

interface PerformanceReliabilityPanelProps {
  reliability: AIBacktestReliability;
}

/**
 * The performance overview and the full performance tab describe the same evidence.
 * Keep their visual hierarchy and labels in one component so saved reports cannot
 * degrade into a second, compact interpretation of the same reliability record.
 */
export function PerformanceReliabilityPanel({ reliability }: PerformanceReliabilityPanelProps) {
  return (
    <Card className={`reliability-panel reliability-panel--${reliability.status}`}>
      <div className="reliability-panel__head">
        <div>
          <strong>성과 수치 신뢰도</strong>
          <p>{reliabilityMessage(reliability.status)}</p>
        </div>
        <Badge variant={reliabilityTone(reliability.status)}>
          {reliabilityLabel(reliability.status)}
        </Badge>
      </div>
      <dl className="reliability-panel__samples">
        <div><dt>데이터</dt><dd>{sourceLabel(reliability.source)}</dd></div>
        <div><dt>기간</dt><dd>{formatHistoryPeriod(reliability.history_start, reliability.history_end)}</dd></div>
        <div><dt>표본</dt><dd>{reliability.row_count.toLocaleString("ko-KR")}행 · {reliability.ticker_count}종목</dd></div>
        <div><dt>검증량</dt><dd>{reliability.trading_days}거래일 · 거래 {reliability.trade_count}회</dd></div>
      </dl>
      {[...reliability.reasons, ...reliability.warnings].length ? (
        <ul className="reliability-panel__reasons">
          {[...reliability.reasons, ...reliability.warnings].map((reason) => <li key={reason}>{reason}</li>)}
        </ul>
      ) : null}
    </Card>
  );
}

function reliabilityLabel(status: AIBacktestReliability["status"]) {
  return { sufficient: "충분", limited: "제한적", insufficient: "부족" }[status];
}

function reliabilityTone(status: AIBacktestReliability["status"]): "positive" | "warning" | "negative" {
  if (status === "sufficient") {
    return "positive";
  }
  return status === "limited" ? "warning" : "negative";
}

function reliabilityMessage(status: AIBacktestReliability["status"]) {
  return {
    sufficient: "기간·종목·거래 수가 공개 성과 기준을 충족했습니다.",
    limited: "수치는 계산됐지만 표본 한계가 있어 참고용으로 해석해야 합니다.",
    insufficient: "표본이 너무 작아 수익률·샤프·낙폭 같은 숫자는 참고용입니다. 아래 사유가 부족한 항목입니다.",
  }[status];
}

function sourceLabel(source: AIBacktestReliability["source"]) {
  return { fixture: "예시 데이터", postgres: "PostgreSQL 실데이터", unknown: "출처 미확인" }[source];
}

function formatHistoryPeriod(start: string | null, end: string | null) {
  if (!start && !end) {
    return "기간 없음";
  }
  return `${start || "?"} ~ ${end || "?"}`;
}
