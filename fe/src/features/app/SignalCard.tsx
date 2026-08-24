import { Badge } from "../../components/common/Badge";
import type { AITickerAction, TradingCandidate } from "../../types/quantagent";

interface SignalCardProps {
  candidate: TradingCandidate;
  compact?: boolean;
  /**
   * The backtest's verdict for this name, when the run produced one. WATCH rows carry the
   * reason the strategy is not acting on it - outside the tested universe, no free slot,
   * or no instruction on the last session - which is the only thing that distinguishes a
   * screened name from a dropped one on this card.
   */
  tickerAction?: AITickerAction;
}

export function SignalCard({ candidate, compact = false, tickerAction }: SignalCardProps) {
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
      {tickerAction ? (
        <p className="signal-card__verdict">
          <Badge variant="soft">{tickerAction.action}</Badge>
          <span>{tickerAction.reason}</span>
        </p>
      ) : null}
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
