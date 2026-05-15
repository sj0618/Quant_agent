import type { ScenarioPayload, WorkspacePayload } from "../../types/quantagent";
import { summarizeActions } from "../../services/mockQuantAgentApi";
import { ReportPreview } from "./ReportPreview";
import { RiskWarningBadge } from "./RiskWarningToggle";
import { SignalBadge } from "./SignalBadge";
import { StrategySummaryCard } from "./StrategySummaryCard";

const statusCopy: Record<string, { title: string; detail: string }> = {
  READY: {
    title: "READY · StrategySpec 변환 완료",
    detail: "CandidateSnapshot → Signal Judge → Risk Warning layer → Report Preview 흐름으로 표시 중입니다.",
  },
  C1_INPUT_AMBIGUOUS: {
    title: "C1 · INPUT_AMBIGUOUS",
    detail: "입력 자체가 모호하여 전략 후보 3개를 제안했습니다.",
  },
  C2_TERM_UNKNOWN: {
    title: "C2 · TERM_UNKNOWN",
    detail: "용어 정의를 우선 검색하고 사용자 확인을 기다립니다.",
  },
  C4_CONFLICTING: {
    title: "C4 · CONFLICTING",
    detail: "조건 충돌 지점을 표시하고 대안 전략 후보를 제공합니다.",
  },
  C5_INFEASIBLE: {
    title: "C5 · INFEASIBLE",
    detail: "지원 범위를 벗어난 요청은 거절하고 가능한 입력 예시를 제공합니다.",
  },
};

export function SummaryTab({ payload, scenario }: { payload: WorkspacePayload; scenario?: ScenarioPayload }) {
  const scenarioCode = scenario?.scenario ?? "READY";
  const status = statusCopy[scenarioCode];
  const actionSummary = summarizeActions(payload.signalDecisions.map((decision) => decision.action));
  const highestRisk = payload.riskWarnings.find((warning) => warning.severity === "HIGH") ?? payload.riskWarnings[0];

  return (
    <div className="tab-stack">
      <StrategySummaryCard strategy={payload.activeStrategy} />

      <section className="panel-card status-card">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Analysis State</span>
            <h2>{status.title}</h2>
          </div>
          <span className="status-indicator">
            <i />
            Mock mode
          </span>
        </div>
        <p>{status.detail}</p>
      </section>

      <section className="summary-bento">
        <article className="panel-card">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Signal Summary</span>
              <h2>Signal Judge 결과</h2>
            </div>
          </div>
          <div className="action-summary-grid">
            {actionSummary.map((item) => (
              <div key={item.action}>
                <SignalBadge action={item.action} compact />
                <strong>{item.count}</strong>
              </div>
            ))}
          </div>
        </article>

        <article className="panel-card">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Risk Warning Summary</span>
              <h2>Action override 없음</h2>
            </div>
            <RiskWarningBadge warning={highestRisk} />
          </div>
          <p className="muted">
            Risk Manager는 warning, caution, evidence, report_note만 생성합니다. SignalDecision.action은 변경하지 않습니다.
          </p>
        </article>
      </section>

      <ReportPreview sections={payload.reportPreview} compact />
    </div>
  );
}
