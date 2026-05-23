import { AsyncState } from "../components/common/AsyncState";
import { AppLayout } from "../components/layout/AppLayout";
import { getReports } from "../api/quantAgentClient";
import { ReportList } from "../features/reports/ReportList";
import { useAsyncData } from "../hooks/useAsyncData";

export function ReportsPage() {
  const { data, loading, error } = useAsyncData(getReports, []);

  if (loading) {
    return <AsyncState title="리포트 목록을 불러오는 중입니다" tone="loading" />;
  }

  if (error) {
    return <AsyncState title="리포트 목록을 불러오지 못했습니다" description={error.message} tone="error" />;
  }

  if (!data || data.length === 0) {
    return <AsyncState title="아직 생성된 리포트가 없습니다" description="전략 활성화 다음 날부터 일일 리포트가 자동 생성됩니다." tone="empty" />;
  }

  return (
    <AppLayout active="reports">
      <main className="reports-page">
        <div className="reports-page__head">
          <div>
            <h1>리포트</h1>
            <p>매일 오전 8시 발송된 일일 분석 리포트를 모두 확인할 수 있습니다.</p>
          </div>
          <div>
            <button type="button">전체 PDF 다운로드</button>
            <button type="button">↓ CSV 내보내기</button>
          </div>
        </div>
        <ReportList reports={data} />
      </main>
    </AppLayout>
  );
}
