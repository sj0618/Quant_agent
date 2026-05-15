import type { WorkspacePayload } from "../../types/quantagent";
import { BacktestLineChart } from "./BacktestLineChart";
import { BacktestMetricCards } from "./BacktestMetricCards";
import { ReportPreview } from "./ReportPreview";
import { SignalBadge } from "./SignalBadge";

export function ReportTab({ payload }: { payload: WorkspacePayload }) {
  return (
    <div className="tab-stack">
      <BacktestMetricCards metrics={payload.backtestMetrics} />
      <BacktestLineChart series={payload.backtestSeries} />

      <section className="judge-risk-split">
        <article className="panel-card">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Signal Judge</span>
              <h2>Action 결과</h2>
            </div>
          </div>
          <div className="decision-list">
            {payload.signalDecisions.map((decision) => (
              <div key={`${decision.ticker}-${decision.action}`}>
                <span>{decision.ticker}</span>
                <SignalBadge action={decision.action} compact />
                <strong>{Math.round(decision.confidence * 100)}%</strong>
              </div>
            ))}
          </div>
        </article>

        <article className="panel-card">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Risk Manager Warning</span>
              <h2>분리된 위험 설명</h2>
            </div>
          </div>
          <div className="risk-report-list">
            {payload.riskWarnings.map((warning) => (
              <div key={warning.id}>
                <strong>
                  {warning.ticker} · {warning.severity}
                </strong>
                <p>{warning.report_note}</p>
              </div>
            ))}
          </div>
        </article>
      </section>

      <ReportPreview sections={payload.reportPreview} />
    </div>
  );
}
