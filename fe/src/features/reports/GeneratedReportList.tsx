import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import { ROUTES } from "../../config/routes";
import type { AnalysisJob } from "../../types/quantagent";
import { workspaceOverviewFromJob } from "../app/strategyWorkspaceMapper";

interface GeneratedReportListProps {
  jobs: AnalysisJob[];
}

function completedReportJobs(jobs: AnalysisJob[]) {
  return jobs.filter((job) => job.result?.status === "ready");
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

/**
 * A strategy report is a terminal result in the durable analysis-job ledger.  It is
 * intentionally separate from the legacy report archive: archive records can lack the
 * original body, whereas this view reads the immutable terminal result that produced it.
 */
export function GeneratedReportList({ jobs }: GeneratedReportListProps) {
  const reports = completedReportJobs(jobs);

  return (
    <section className="generated-report-list" aria-labelledby="generated-report-list-title">
      <div className="report-list-head">
        <div>
          <strong id="generated-report-list-title">최근 생성된 전략 리포트</strong>
          <p>서버가 반환한 완료된 자연어 전략 분석의 terminal report입니다.</p>
        </div>
        <Badge variant="dark">{reports.length}건</Badge>
      </div>

      {reports.length === 0 ? (
        <Card className="generated-report-empty">
          <strong>아직 완료된 전략 리포트가 없습니다</strong>
          <p>전략 분석이 완료되면, 결과·데이터 출처·표본·한계를 이곳에서 다시 열 수 있습니다.</p>
        </Card>
      ) : (
        <div className="generated-report-grid">
          {reports.map((job) => <GeneratedReportCard job={job} key={job.job_id} />)}
        </div>
      )}
    </section>
  );
}

function GeneratedReportCard({ job }: { job: AnalysisJob }) {
  const overview = workspaceOverviewFromJob(job);
  const report = job.result?.user_payload.report?.web_projection;
  const performance = overview.performance;
  const reliability = performance.reliability;
  const metrics = performance.metrics.slice(0, 3);
  const hasPostgresEvidence = reliability?.source === "postgres";
  // A terminal envelope can be structurally ready even while its performance payload
  // is fixture-originated or lacks provenance.  Keep that execution discoverable, but
  // do not elevate its generated narrative into a strategy report.
  const title = hasPostgresEvidence
    ? report?.title || job.result?.user_payload.headline || "전략 분석 결과"
    : "검증 범위 확인이 필요한 전략 결과";
  const summary = hasPostgresEvidence
    ? report?.summary || job.result?.user_payload.message || "완료된 분석 결과를 확인하세요."
    : "실데이터 출처와 표본이 확인되기 전에는 성과 수치나 생성 리포트 본문을 표시하지 않습니다.";

  return (
    <Card className="generated-report-card">
      <div className="generated-report-card__top">
        <div>
          <Badge variant={hasPostgresEvidence ? "positive" : "warning"}>
            {hasPostgresEvidence ? "실데이터 검증" : "검증 범위 확인 필요"}
          </Badge>
          <span>{formatDateTime(job.updated_at)}</span>
        </div>
        <span className="generated-report-card__status">완료</span>
      </div>
      <h2>{title}</h2>
      <p>{summary}</p>

      <dl className="generated-report-card__facts">
        <div>
          <dt>전략</dt>
          <dd>{overview.strategy.name || "자연어 전략"}</dd>
        </div>
        <div>
          <dt>데이터</dt>
          <dd>{hasPostgresEvidence ? "PostgreSQL EOD" : "출처 확인 필요"}</dd>
        </div>
        <div>
          <dt>표본</dt>
          <dd>{reliability ? `${reliability.row_count.toLocaleString("ko-KR")}행 · ${reliability.ticker_count}종목` : "확인 필요"}</dd>
        </div>
      </dl>

      {metrics.length ? (
        <div className="generated-report-card__metrics" aria-label="백테스트 핵심 지표">
          {metrics.map((metric) => (
            <span key={metric.key}>
              <small>{metric.label}</small>
              <strong>{metric.value}</strong>
            </span>
          ))}
        </div>
      ) : null}

      <div className="generated-report-card__footer">
        <small>입력: {job.query}</small>
        <a href={ROUTES.analysisReportDetail(job.job_id)}>리포트 열기 →</a>
      </div>
    </Card>
  );
}
