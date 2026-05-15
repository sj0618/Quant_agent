import type { WorkspacePayload } from "../../types/quantagent";
import { CandidateCard } from "./CandidateCard";

export function CandidatesTab({ payload }: { payload: WorkspacePayload }) {
  return (
    <div className="tab-stack">
      <section className="panel-card">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Candidates</span>
            <h2>매매종목 정보</h2>
          </div>
          <span className="pill pill--slate">{payload.candidates.length} mock candidates</span>
        </div>
        <p className="muted">
          각 카드의 action은 Signal Judge 결과입니다. Risk Warning은 별도 toggle로만 노출되며 action을 바꾸지 않습니다.
        </p>
      </section>

      <section className="candidate-grid">
        {payload.candidates.map((candidate) => {
          const decision = payload.signalDecisions.find((item) => item.ticker === candidate.ticker);
          const warning = payload.riskWarnings.find((item) => item.ticker === candidate.ticker);

          if (!decision) {
            return null;
          }

          return <CandidateCard key={candidate.ticker} candidate={candidate} decision={decision} warning={warning} />;
        })}
      </section>
    </div>
  );
}
