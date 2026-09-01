import { useState } from "react";
import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import { Tabs, type TabItem } from "../../components/common/Tabs";
import type { AnalysisJob } from "../../types/quantagent";
import { OverviewTab } from "../app/OverviewTab";
import { PerformanceTab } from "../app/PerformanceTab";
import { TradingInfoTab } from "../app/TradingInfoTab";
import { workspaceOverviewFromJob } from "../app/strategyWorkspaceMapper";
import { ExplorationBaseReport } from "./ExplorationBaseReport";

type ReportTab = "overview" | "trading" | "performance";

const TAB_ITEMS: Array<TabItem<ReportTab>> = [
  { id: "overview", label: "전략 요약" },
  { id: "trading", label: "조건 일치 종목" },
  { id: "performance", label: "백테스트" },
];

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

/** Renders the terminal job result itself, never a browser fixture or archive fallback. */
export function AnalysisReportDetail({ job }: { job: AnalysisJob }) {
  const [activeTab, setActiveTab] = useState<ReportTab>("overview");
  const overview = workspaceOverviewFromJob(job);
  const result = job.result;
  const report = result?.user_payload.report?.web_projection;
  const explorationReport = result?.user_payload.report?.base_report_v2;
  const method = result?.user_payload.performance?.availability === "available"
    ? result.user_payload.performance.method_manifest
    : null;
  const reliability = overview.performance.reliability;
  const hasPostgresEvidence = reliability?.source === "postgres";
  const title = hasPostgresEvidence
    ? report?.title || result?.user_payload.headline || "전략 분석 결과"
    : "검증 범위 확인이 필요한 전략 결과";
  const summary = hasPostgresEvidence
    ? report?.summary || result?.user_payload.message || "완료된 자연어 전략 분석입니다."
    : "실데이터 출처와 표본이 확인되기 전에는 생성 리포트 본문과 성과 수치를 표시하지 않습니다.";

  return (
    <main className="analysis-report-page">
      <section className="analysis-report-hero">
        <div className="analysis-report-hero__meta">
          <span><Badge variant="dark">STRATEGY REPORT</Badge> terminal result</span>
          <span>{formatDateTime(job.updated_at)}</span>
        </div>
        <h1>{title}</h1>
        <p>{summary}</p>
        <dl className="analysis-report-hero__facts">
          <div><dt>입력 전략</dt><dd>{job.query}</dd></div>
          {explorationReport ? <div><dt>연구 유형</dt><dd>사전등록 후보군 과거 검증</dd></div> : <>
            <div><dt>진입 조건</dt><dd>{overview.strategy.buy_condition}</dd></div>
            <div><dt>청산 조건</dt><dd>{overview.strategy.drop_condition}</dd></div>
          </>}
          <div><dt>데이터 기준</dt><dd>{reliability?.source === "postgres" ? "PostgreSQL EOD" : "검증 범위 확인 필요"}</dd></div>
          {method ? <div><dt>검증 구간</dt><dd>{method.start_date} ~ {method.end_date}</dd></div> : null}
        </dl>
      </section>

      <section className="analysis-report-disclosure">
        <strong>이 리포트는 생성 당시의 immutable terminal result입니다.</strong>
        <span>현재 시장 상태나 주문 지시가 아니며, 성과 수치는 실데이터 출처·표본·방법이 확인된 경우에만 표시합니다.</span>
      </section>

      {explorationReport ? <ExplorationBaseReport jobId={job.job_id} report={explorationReport} /> : <>
      <Tabs
        activeId={activeTab}
        items={TAB_ITEMS.map((tab) => tab.id === "trading" ? { ...tab, count: overview.candidates.length } : tab)}
        onChange={setActiveTab}
        rightSlot={<span>{overview.latestRunLabel}</span>}
      />
      {activeTab === "overview" ? <OverviewTab overview={overview} validated={overview.recommendationGate?.validated === true} /> : null}
      {activeTab === "trading" ? <TradingInfoTab candidates={overview.candidates} /> : null}
      {activeTab === "performance" ? <PerformanceTab performance={overview.performance} /> : null}
      </>}

      <Card className="analysis-report-limitations">
        <strong>해석 한계</strong>
        <p>{overview.performance.disclaimer}</p>
      </Card>
    </main>
  );
}
