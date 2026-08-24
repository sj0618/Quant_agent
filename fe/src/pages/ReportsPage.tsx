import { useState } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { AppLayout } from "../components/layout/AppLayout";
import { getReports } from "../api/quantAgentClient";
import { downloadReportsCsv, printCurrentView } from "../api/reportActionsClient";
import { ROUTES } from "../config/routes";
import { ReportList } from "../features/reports/ReportList";
import {
  DEFAULT_REPORT_FILTERS,
  applyReportFilters,
  parseReportFilters,
  serializeReportFilters,
  type ReportFilters,
} from "../features/reports/reportFilters";
import { useAsyncData } from "../hooks/useAsyncData";

export function ReportsPage() {
  const { data, loading, error } = useAsyncData(getReports, []);
  const [filters, setFilters] = useState<ReportFilters>(() => parseReportFilters(window.location.search));
  const [actionStatus, setActionStatus] = useState<string | null>(null);

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

  // Loading/empty/error used to return before AppLayout, so every non-happy path silently
  // dropped the top bar and left the user with no way to navigate out.
  if (loading || error || !data || data.length === 0) {
    return (
      <AppLayout active="reports">
        {loading ? (
          <AsyncState title="리포트 목록을 불러오는 중입니다" tone="loading" />
        ) : error ? (
          <AsyncState title="리포트 목록을 불러오지 못했습니다" description={error.message} tone="error" />
        ) : (
          <AsyncState title="보관된 리포트가 없습니다" description="공개 조건을 통과한 기록만 이 보관함에 표시됩니다." tone="empty" />
        )}
      </AppLayout>
    );
  }

  return (
    <AppLayout active="reports">
      <main className="reports-page">
        <div className="reports-page__head">
          <div>
            <h1>리포트</h1>
            <p>검증 범위와 보관 조건이 함께 기록된 읽기 전용 리포트를 확인할 수 있습니다.</p>
          </div>
          <div>
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
      </main>
    </AppLayout>
  );
}
