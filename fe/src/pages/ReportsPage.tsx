import { useState } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { AppLayout } from "../components/layout/AppLayout";
import { getReports } from "../api/quantAgentClient";
import { downloadReportsCsv, printCurrentView } from "../api/reportActionsClient";
import { ROUTES } from "../config/routes";
import { DailyDigestPreview } from "../features/reports/DailyDigestPreview";
import { ReportList } from "../features/reports/ReportList";
import {
  DEFAULT_REPORT_FILTERS,
  applyReportFilters,
  parseReportFilters,
  serializeReportFilters,
  type ReportFilters,
} from "../features/reports/reportFilters";
import { useAsyncData } from "../hooks/useAsyncData";
import { dailyDigestReport } from "../mocks/dailyDigest.mock";

export function ReportsPage() {
  const { data, loading, error } = useAsyncData(getReports, []);
  const [filters, setFilters] = useState<ReportFilters>(() => parseReportFilters(window.location.search));
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [showDigestPreview, setShowDigestPreview] = useState(false);

  const reports = data ?? [];
  const filteredReports = applyReportFilters(reports, filters);

  const handleApplyFilters = (nextFilters: ReportFilters) => {
    setFilters(nextFilters);
    const query = serializeReportFilters(nextFilters);
    window.history.replaceState({}, "", query ? `${ROUTES.reports}?${query}` : ROUTES.reports);
  };

  const handleResetFilters = () => {
    handleApplyFilters(DEFAULT_REPORT_FILTERS);
  };

  const handleDownloadCsv = () => {
    downloadReportsCsv(filteredReports);
    setActionStatus(`${filteredReports.length}건의 CSV를 내보냈습니다.`);
  };

  const handlePrintPdf = () => {
    printCurrentView();
    setActionStatus("브라우저 인쇄 대화상자에서 PDF로 저장할 수 있습니다.");
  };

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
            <button onClick={() => setShowDigestPreview(true)} type="button">이메일 다이제스트 미리보기</button>
            <button onClick={handlePrintPdf} type="button">전체 PDF 다운로드</button>
            <button onClick={handleDownloadCsv} type="button">↓ CSV 내보내기</button>
          </div>
        </div>
        {actionStatus ? <div className="action-feedback">{actionStatus}</div> : null}
        <ReportList
          allReports={reports}
          filters={filters}
          onApplyFilters={handleApplyFilters}
          onResetFilters={handleResetFilters}
          reports={filteredReports}
        />
        {showDigestPreview ? (
          <DailyDigestPreview digest={dailyDigestReport} onClose={() => setShowDigestPreview(false)} />
        ) : null}
      </main>
    </AppLayout>
  );
}
