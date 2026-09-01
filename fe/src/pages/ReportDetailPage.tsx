import { useState } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { AppLayout } from "../components/layout/AppLayout";
import { getAnalysisJob, getReportById } from "../api/quantAgentClient";
import { printCurrentView } from "../api/reportActionsClient";
import { ROUTES, parseAnalysisReportJobId } from "../config/routes";
import { AnalysisReportDetail } from "../features/reports/AnalysisReportDetail";
import { ReportDetail } from "../features/reports/ReportDetail";
import { useAsyncData } from "../hooks/useAsyncData";

interface ReportDetailPageProps {
  id: string;
}

export function ReportDetailPage({ id }: ReportDetailPageProps) {
  const analysisJobId = parseAnalysisReportJobId(id);
  if (analysisJobId) {
    return <GeneratedReportDetailPage jobId={analysisJobId} />;
  }
  return <ArchivedReportDetailPage id={id} />;
}

function GeneratedReportDetailPage({ jobId }: { jobId: string }) {
  const { data, loading, error } = useAsyncData(() => getAnalysisJob(jobId), [jobId]);
  const [actionStatus, setActionStatus] = useState<string | null>(null);

  if (loading || error || !data || data.result?.status !== "ready") {
    return (
      <AppLayout active="reports">
        {loading ? <AsyncState title="전략 리포트를 불러오는 중입니다" tone="loading" /> : null}
        {error ? <AsyncState title="전략 리포트를 불러오지 못했습니다" description={error.message} tone="error" /> : null}
        {!loading && !error ? <AsyncState title="완료된 전략 리포트를 찾을 수 없습니다" description="이 실행은 아직 완료되지 않았거나, 보고서로 표시할 terminal result가 없습니다." tone="empty" /> : null}
      </AppLayout>
    );
  }

  return (
    <AppLayout active="reports">
      <div className="report-subbar">
        <a href={ROUTES.reports}>← 전략 리포트 목록</a>
        <span>/</span>
        <strong>생성된 전략 리포트</strong>
        <div>
          <button onClick={() => { printCurrentView(); setActionStatus("브라우저 인쇄 대화상자에서 PDF로 저장할 수 있습니다."); }} type="button">PDF 저장</button>
        </div>
      </div>
      {actionStatus ? <div className="action-feedback action-feedback--subbar">{actionStatus}</div> : null}
      <AnalysisReportDetail job={data} />
    </AppLayout>
  );
}

function ArchivedReportDetailPage({ id }: { id: string }) {
  const { data, loading, error } = useAsyncData(() => getReportById(id), [id]);
  const [actionStatus, setActionStatus] = useState<string | null>(null);

  if (loading || error || !data) {
    return (
      <AppLayout active="reports">
        {loading ? (
          <AsyncState title="리포트 상세를 불러오는 중입니다" tone="loading" />
        ) : error ? (
          <AsyncState title="리포트 상세를 불러오지 못했습니다" description={error.message} tone="error" />
        ) : (
          <AsyncState title="리포트를 찾을 수 없습니다" description="요청한 리포트 ID에 해당하는 데이터가 없습니다." tone="empty" />
        )}
      </AppLayout>
    );
  }

  return (
    <AppLayout active="reports">
      <div className="report-subbar">
        <a href={ROUTES.reports}>← 리포트 목록</a>
        <span>/</span>
        <strong>읽기 전용 결과 스냅샷</strong>
        <div>
          <button onClick={() => { printCurrentView(); setActionStatus("브라우저 인쇄 대화상자에서 PDF로 저장할 수 있습니다."); }} type="button">PDF 저장</button>
        </div>
      </div>
      {actionStatus ? <div className="action-feedback action-feedback--subbar">{actionStatus}</div> : null}
      <ReportDetail report={data} />
    </AppLayout>
  );
}
