import { useState } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { AppLayout } from "../components/layout/AppLayout";
import { getWorkspaceReportById } from "../api/quantAgentClient";
import { ROUTES } from "../config/routes";
import { WorkspaceResultPanel, type WorkspaceResultTab } from "../features/app/WorkspaceResultPanel";
import { useAsyncData } from "../hooks/useAsyncData";

interface WorkspaceReportDetailPageProps {
  id: string;
}

/**
 * Read-only view of a report made in the strategy workspace.
 *
 * It deliberately reuses the workspace result panels instead of the delivery-email
 * template.  The two sources have different meanings and must never share a route.
 */
export function WorkspaceReportDetailPage({ id }: WorkspaceReportDetailPageProps) {
  const { data, loading, error } = useAsyncData(() => getWorkspaceReportById(id), [id]);
  const [activeTab, setActiveTab] = useState<WorkspaceResultTab>("overview");

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

  return (
    <AppLayout active="reports">
      <div className="report-subbar">
        <a href={ROUTES.reports}>← 전략 분석 리포트</a>
        <span>/ 워크스페이스 결과</span>
      </div>
      <main className="workspace-main">
        <WorkspaceResultPanel
          activeTab={activeTab}
          baseReport={data.baseReport}
          jobId={data.jobId}
          onTabChange={setActiveTab}
          overview={data.overview}
          recommendationGate={data.recommendationGate}
        />
      </main>
    </AppLayout>
  );
}
