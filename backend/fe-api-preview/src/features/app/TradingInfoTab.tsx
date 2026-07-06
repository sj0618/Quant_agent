import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import { ROUTES } from "../../config/routes";
import type { TradingCandidate } from "../../types/quantagent";
import { SignalCard } from "./SignalCard";

interface TradingInfoTabProps {
  candidates: TradingCandidate[];
}

export function TradingInfoTab({ candidates }: TradingInfoTabProps) {
  const counts = candidates.reduce(
    (acc, candidate) => ({ ...acc, [candidate.signal]: acc[candidate.signal] + 1 }),
    { BUY: 0, HOLD: 0, DROP: 0 },
  );

  return (
    <div className="workspace-content">
      <Card className="list-head">
        <div>
          <h1>매매종목 정보 <Badge variant="soft">총 {candidates.length}건</Badge></h1>
          <p>오늘 08:00 분석 · 반도체 모멘텀 + 기관 매수 회귀 전략</p>
        </div>
        <div className="filter-row">
          <Badge variant="dark">ALL {candidates.length}</Badge>
          <Badge signal="BUY">BUY {counts.BUY}</Badge>
          <Badge signal="HOLD">HOLD {counts.HOLD}</Badge>
          <Badge signal="DROP">DROP {counts.DROP}</Badge>
          <Badge variant="soft">점수 높은 순 ▾</Badge>
        </div>
      </Card>

      <section className="signal-grid">
        {candidates.map((candidate) => (
          <SignalCard candidate={candidate} key={candidate.id} />
        ))}
      </section>

      <Card className="source-strip">
        <span>신호는 매일 08:00 자동 갱신됩니다</span>
        <span>·</span>
        <span>출처: KIS API · DART · 한경컨센서스 · 에이전틱 서치</span>
        <a href={ROUTES.reportDetail("2026-04-18")}>리포트로 보기 →</a>
      </Card>
    </div>
  );
}
