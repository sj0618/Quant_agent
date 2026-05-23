import { AsyncState } from "../components/common/AsyncState";
import { AppLayout } from "../components/layout/AppLayout";
import { getReportById } from "../api/quantAgentClient";
import { ReportDetail } from "../features/reports/ReportDetail";
import { useAsyncData } from "../hooks/useAsyncData";

interface ReportDetailPageProps {
  id: string;
}

export function ReportDetailPage({ id }: ReportDetailPageProps) {
  const { data, loading, error } = useAsyncData(() => getReportById(id), [id]);

  if (loading) {
    return <AsyncState title="리포트 상세를 불러오는 중입니다" tone="loading" />;
  }

  if (error) {
    return <AsyncState title="리포트 상세를 불러오지 못했습니다" description={error.message} tone="error" />;
  }

  if (!data) {
    return <AsyncState title="리포트를 찾을 수 없습니다" description="요청한 리포트 ID에 해당하는 mock data가 없습니다." tone="empty" />;
  }

  return (
    <AppLayout active="reports">
      <div className="report-subbar">
        <a href="/reports">← 리포트 목록</a>
        <span>/</span>
        <strong>{data.date}</strong>
        <div>
          <button type="button">이메일 재발송</button>
          <button type="button">PDF 저장</button>
          <button type="button">공유 링크</button>
        </div>
      </div>
      <ReportDetail report={data} />
    </AppLayout>
  );
}
