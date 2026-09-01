import { useState } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { Card } from "../components/common/Card";
import { Tabs, type TabItem } from "../components/common/Tabs";
import { AppLayout } from "../components/layout/AppLayout";
import { getWorkspaceReportById } from "../api/quantAgentClient";
import { ROUTES } from "../config/routes";
import { OverviewTab } from "../features/app/OverviewTab";
import { PerformanceTab } from "../features/app/PerformanceTab";
import { TradingInfoTab } from "../features/app/TradingInfoTab";
import { useAsyncData } from "../hooks/useAsyncData";

interface WorkspaceReportDetailPageProps {
  id: string;
}

type WorkspaceReportTab = "overview" | "trading" | "performance";

const TABS: Array<TabItem<WorkspaceReportTab>> = [
  { id: "overview", label: "전략 요약" },
  { id: "trading", label: "조건 일치 종목" },
  { id: "performance", label: "백테스트" },
];

/**
 * Read-only view of a report made in the strategy workspace.
 *
 * It deliberately reuses the workspace result panels instead of the delivery-email
 * template.  The two sources have different meanings and must never share a route.
 */
export function WorkspaceReportDetailPage({ id }: WorkspaceReportDetailPageProps) {
  const { data, loading, error } = useAsyncData(() => getWorkspaceReportById(id), [id]);
  const [activeTab, setActiveTab] = useState<WorkspaceReportTab>("overview");

  if (loading || error || !data) {
    return (
      <AppLayout active="reports">
        {loading ? (
          <AsyncState title="전략 분석 리포트를 불러오는 중입니다" tone="loading" />
        ) : error ? (
          <AsyncState title="전략 분석 리포트를 불러오지 못했습니다" description={error.message} tone="error" />
        ) : (
          <AsyncState
            title="전략 분석 리포트를 찾을 수 없습니다"
            description="완료된 워크스페이스 분석 결과만 리포트 목록에 표시됩니다."
            tone="empty"
          />
        )}
      </AppLayout>
    );
  }

  const { overview, report } = data;
  return (
    <AppLayout active="reports">
      <div className="report-subbar">
        <a href={ROUTES.reports}>← 전략 분석 리포트</a>
        <span>/</span>
        <strong>{report.date}</strong>
      </div>
      <main className="reports-page">
        <Card className="list-head">
          <div>
            <p className="eyebrow-row"><span>WORKSPACE REPORT</span></p>
            <h1>{report.title}</h1>
            <p>{data.query}</p>
          </div>
          <dl className="workspace-report-meta">
            <div><dt>생성 시각</dt><dd>{report.sentAt}</dd></div>
            <div><dt>전략</dt><dd>{report.strategyName}</dd></div>
          </dl>
        </Card>
        <Tabs activeId={activeTab} items={TABS} onChange={setActiveTab} />
        {activeTab === "overview" ? <OverviewTab overview={overview} validated={data.recommendationValidated} /> : null}
        {activeTab === "trading" ? <TradingInfoTab candidates={overview.candidates} /> : null}
        {activeTab === "performance" ? <PerformanceTab performance={overview.performance} /> : null}
      </main>
    </AppLayout>
  );
}
