import { AsyncState } from "../components/common/AsyncState";
import { AppLayout } from "../components/layout/AppLayout";
import { getEmailDigestHistory } from "../api/quantAgentClient";
import { ROUTES } from "../config/routes";
import { EmailHistoryTimeline } from "../features/reports/EmailHistoryTimeline";
import { useAsyncData } from "../hooks/useAsyncData";

export function ReportsHistoryPage() {
  const { data, loading, error } = useAsyncData(getEmailDigestHistory, []);

  if (loading) {
    return <AsyncState title="이메일 발송 이력을 불러오는 중입니다" tone="loading" />;
  }

  if (error) {
    return <AsyncState title="이메일 발송 이력을 불러오지 못했습니다" description={error.message} tone="error" />;
  }

  if (!data || data.length === 0) {
    return <AsyncState title="표시할 이메일 발송 이력이 없습니다" description="발송 로그가 쌓이면 이 화면에서 시간순 타임라인으로 확인할 수 있습니다." tone="empty" />;
  }

  return (
    <AppLayout active="reports">
      <main className="reports-page">
        <div className="reports-page__head">
          <div>
            <h1>이메일 발송 이력</h1>
            <p>전송 완료, 전송 실패, 재전송 이력을 날짜와 전략 기준으로 시간순 확인합니다.</p>
          </div>
          <a className="reports-page__link" href={ROUTES.me}>마이페이지 →</a>
        </div>
        <EmailHistoryTimeline entries={data} />
      </main>
    </AppLayout>
  );
}
