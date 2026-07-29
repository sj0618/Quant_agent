import { Badge } from "../../components/common/Badge";
import type { TradingCandidate } from "../../types/quantagent";

interface SignalCardProps {
  candidate: TradingCandidate;
  compact?: boolean;
}

export function SignalCard({ candidate, compact = false }: SignalCardProps) {
  return (
    <article className={["signal-card", compact ? "signal-card--compact" : ""].filter(Boolean).join(" ")}>
      <div className="signal-card__top">
        {candidate.signal ? <Badge signal={candidate.signal}>{candidate.signal}</Badge> : null}
        <div className="signal-card__name">
          <strong>{candidate.name}</strong>
          <span>{candidate.ticker}</span>
          <small>{candidate.sector}</small>
        </div>
        {candidate.confidence === undefined ? null : (
          <div className="signal-card__score">
            <strong>{Math.round(candidate.confidence * 100)}%</strong>
            <small>신뢰도</small>
          </div>
        )}
      </div>
      <p>{candidate.rationale}</p>
      <div className="signal-card__meta">
        <span>
          <strong>{candidate.price}</strong>
          {candidate.changePercent ? (
            <em className={candidate.changePercent.startsWith("-") ? "is-negative" : "is-positive"}>
              {candidate.changePercent}
            </em>
          ) : null}
        </span>
      </div>
    </article>
  );
}
