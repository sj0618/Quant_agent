import { AsyncState } from "../components/common/AsyncState";
import { AppLayout } from "../components/layout/AppLayout";
import { getEmailReportById } from "../api/quantAgentClient";
import { ROUTES } from "../config/routes";
import { ReportDetail } from "../features/reports/ReportDetail";
import { useAsyncData } from "../hooks/useAsyncData";

interface EmailReportDetailPageProps {
  id: string;
}

/** The email report is reachable only from the My Page delivery timeline. */
export function EmailReportDetailPage({ id }: EmailReportDetailPageProps) {
  const { data, loading, error } = useAsyncData(() => getEmailReportById(id), [id]);

  if (loading || error || !data) {
    return (
      <AppLayout active="profile">
        {loading ? (
          <AsyncState title="이메일 리포트를 불러오는 중입니다" tone="loading" />
        ) : error ? (
          <AsyncState title="이메일 리포트를 불러오지 못했습니다" description={error.message} tone="error" />
        ) : (
          <AsyncState title="이메일 리포트를 찾을 수 없습니다" description="발송 이력에서 다시 선택해 주세요." tone="empty" />
        )}
      </AppLayout>
    );
  }

  return (
    <AppLayout active="profile">
      <div className="report-subbar">
        <a href={ROUTES.me}>← 이메일 발송 타임라인</a>
        <span>/</span>
        <strong>{data.date}</strong>
      </div>
      <ReportDetail report={data} />
    </AppLayout>
  );
}
