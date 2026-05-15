import type { CandidateStock, RiskWarning, SignalDecision } from "../../types/quantagent";
import { RiskWarningBadge, RiskWarningToggle } from "./RiskWarningToggle";
import { SignalBadge } from "./SignalBadge";

export function CandidateCard({
  candidate,
  decision,
  warning,
}: {
  candidate: CandidateStock;
  decision: SignalDecision;
  warning?: RiskWarning;
}) {
  const confidencePercent = Math.round(decision.confidence * 100);

  return (
    <article className="candidate-card">
      <div className="candidate-card__top">
        <div>
          <div className="candidate-card__name-row">
            <h3>{candidate.name}</h3>
            <span>{candidate.ticker}</span>
          </div>
          <p>
            {candidate.sector} · {candidate.hasPosition ? "보유 중" : "미보유"} ·{" "}
            {candidate.inCandidateSnapshot ? "CandidateSnapshot IN" : "CandidateSnapshot OUT"}
          </p>
        </div>
        <RiskWarningBadge warning={warning} />
      </div>

      <div className="candidate-card__market">
        <div>
          <span>현재가</span>
          <strong>{candidate.lastPrice.toLocaleString("ko-KR")}원</strong>
        </div>
        <div className={candidate.dayChangeRate >= 0 ? "text-positive" : "text-negative"}>
          <span>등락률</span>
          <strong>
            {candidate.dayChangeRate >= 0 ? "+" : ""}
            {candidate.dayChangeRate.toFixed(2)}%
          </strong>
        </div>
      </div>

      <div className="candidate-card__signal-row">
        <SignalBadge action={decision.action} />
        <div className="confidence">
          <div className="confidence__label">
            <span>confidence</span>
            <strong>{confidencePercent}%</strong>
          </div>
          <div className="confidence__track">
            <span style={{ width: `${confidencePercent}%` }} />
          </div>
        </div>
      </div>

      <div className="evidence-chip-list" aria-label={`${candidate.name} evidence chips`}>
        {candidate.evidenceChips.map((chip) => (
          <span className={`evidence-chip evidence-chip--${chip.tone}`} key={`${candidate.ticker}-${chip.label}`}>
            {chip.label}: {chip.value}
          </span>
        ))}
      </div>

      <div className="candidate-card__reasons">
        <strong>Signal Judge reason</strong>
        <ul>
          {decision.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </div>

      <RiskWarningToggle warning={warning} />
    </article>
  );
}
