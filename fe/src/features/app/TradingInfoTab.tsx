import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import { ROUTES } from "../../config/routes";
import type { TradingCandidate } from "../../types/quantagent";
import { SignalCard } from "./SignalCard";

interface TradingInfoTabProps {
  candidates: TradingCandidate[];
}

export function TradingInfoTab({ candidates }: TradingInfoTabProps) {
  if (!candidates.length) {
    return (
      <div className="workspace-content">
        <Card className="list-head">
          <div>
            <h1>매매종목 정보 <Badge variant="soft">총 0건</Badge></h1>
            <p>현재 AI 응답에는 종목별 추천 데이터가 없습니다.</p>
          </div>
        </Card>
      </div>
    );
  }

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
        <span>신호는 AI 분석 API 응답 기준입니다</span>
        <span>·</span>
        <span>출처와 근거는 분석 리포트에서 확인할 수 있습니다</span>
        <a href={ROUTES.reports}>리포트로 보기 →</a>
      </Card>
    </div>
  );
}
