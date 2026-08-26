import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import { ROUTES } from "../../config/routes";
import type { TradingCandidate } from "../../types/quantagent";
import { countScoredSignals } from "../../utils/signalCounts";
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
            <p>실데이터 검증을 통과한 종목별 전략 신호가 없습니다.</p>
          </div>
        </Card>
      </div>
    );
  }

  const counts = countScoredSignals(candidates);

  return (
    <div className="workspace-content">
      <Card className="list-head">
        <div>
            <h1>조건 일치 종목 <Badge variant="soft">총 {candidates.length}건</Badge></h1>
          <p>최신 분석 · 조건 일치 종목 전체</p>
        </div>
        <div className="filter-row">
          <Badge variant="dark">ALL {candidates.length}</Badge>
          {counts ? (
            <>
              <Badge signal="BUY">BUY {counts.BUY}</Badge>
              <Badge signal="HOLD">HOLD {counts.HOLD}</Badge>
              <Badge signal="DROP">DROP {counts.DROP}</Badge>
            </>
          ) : null}
          <Badge variant="soft">종목코드 순</Badge>
        </div>
      </Card>

      <section className="signal-grid">
        {candidates.map((candidate) => (
          <SignalCard candidate={candidate} key={candidate.id} />
        ))}
      </section>

      <Card className="source-strip">
        <span>신호는 해당 전략의 실데이터 분석 결과 기준입니다</span>
        <span>·</span>
        <span>주문 지시가 아니며, 출처와 한계는 분석 리포트에서 확인할 수 있습니다</span>
        <a href={ROUTES.reports}>리포트로 보기 →</a>
      </Card>
    </div>
  );
}
