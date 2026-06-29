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
        <Badge signal={candidate.signal}>{candidate.signal}</Badge>
        <div className="signal-card__name">
          <strong>{candidate.name}</strong>
          <span>{candidate.ticker}</span>
          <small>{candidate.sector}</small>
        </div>
        <div className="signal-card__score">
          <strong>{candidate.score.toFixed(2)}</strong>
          <small>score</small>
        </div>
      </div>
      <p>{candidate.rationale}</p>
      <div className="signal-card__meta">
        <span>
          <b>근거</b> {candidate.evidence[0]?.provider} · {candidate.evidence[0]?.date}
        </span>
        <span>
          <strong>{candidate.price}</strong>
          <em className={candidate.changePercent.startsWith("-") ? "is-negative" : "is-positive"}>
            {candidate.changePercent}
          </em>
        </span>
      </div>
      {!compact && candidate.riskReasons.length > 0 ? (
        <div className="signal-card__risks">
          {candidate.riskReasons.map((risk) => (
            <span key={risk}>{risk}</span>
          ))}
        </div>
      ) : null}
    </article>
  );
}
