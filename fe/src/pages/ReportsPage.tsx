import { useState } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { AppLayout } from "../components/layout/AppLayout";
import { getAnalysisJobs, getReports } from "../api/quantAgentClient";
import { downloadReportsCsv, printCurrentView } from "../api/reportActionsClient";
import { ROUTES } from "../config/routes";
import { ReportList } from "../features/reports/ReportList";
import { GeneratedReportList } from "../features/reports/GeneratedReportList";
import {
  DEFAULT_REPORT_FILTERS,
  applyReportFilters,
  parseReportFilters,
  serializeReportFilters,
  type ReportFilters,
} from "../features/reports/reportFilters";
import { useAsyncData } from "../hooks/useAsyncData";

export function ReportsPage() {
  const { data, loading, error } = useAsyncData(async () => {
    const [jobsResult, archiveResult] = await Promise.allSettled([getAnalysisJobs(), getReports()]);
    return {
      jobs: jobsResult.status === "fulfilled" ? jobsResult.value : [],
      archive: archiveResult.status === "fulfilled" ? archiveResult.value : [],
      jobsError: jobsResult.status === "rejected" ? jobsResult.reason : null,
      archiveError: archiveResult.status === "rejected" ? archiveResult.reason : null,
    };
  }, []);
  const [filters, setFilters] = useState<ReportFilters>(() => parseReportFilters(window.location.search));
  const [actionStatus, setActionStatus] = useState<string | null>(null);

  const reports = data?.archive ?? [];
  const jobs = data?.jobs ?? [];
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
  if (loading || error || !data) {
    return (
      <AppLayout active="reports">
        {loading ? (
          <AsyncState title="리포트 목록을 불러오는 중입니다" tone="loading" />
        ) : error ? (
          <AsyncState title="리포트 목록을 불러오지 못했습니다" description={error.message} tone="error" />
        ) : (
          <AsyncState title="리포트 목록을 준비할 수 없습니다" tone="error" />
        )}
      </AppLayout>
    );
  }

  return (
    <AppLayout active="reports">
      <main className="reports-page">
        <div className="reports-page__head">
          <div>
            <h1>전략 리포트</h1>
            <p>완료된 자연어 분석의 결과·근거·한계를 다시 확인할 수 있습니다.</p>
          </div>
          <div>
            <button onClick={handlePrintPdf} type="button">전체 PDF 다운로드</button>
            <button onClick={handleDownloadCsv} type="button">↓ CSV 내보내기</button>
          </div>
        </div>
        {actionStatus ? <div className="action-feedback">{actionStatus}</div> : null}
        {data.jobsError ? <div className="action-feedback action-feedback--error">생성된 전략 리포트 목록을 불러오지 못했습니다. 과거 보관 기록은 아래에서 계속 확인할 수 있습니다.</div> : null}
        <GeneratedReportList jobs={jobs} />
        {data.archiveError ? <div className="action-feedback action-feedback--error">과거 보관 기록을 불러오지 못했습니다.</div> : null}
        {filteredReports.length ? (
          <section className="legacy-archive-section" aria-labelledby="legacy-archive-title">
            <div className="report-list-head">
              <div>
                <strong id="legacy-archive-title">이전 보관 기록</strong>
                <p>본문이 보존되지 않은 과거 기록입니다. 생성된 전략 리포트를 대신하지 않습니다.</p>
              </div>
              <span>{filteredReports.length}건</span>
            </div>
            <ReportList
              filters={filters}
              onApplyFilters={handleApplyFilters}
              onResetFilters={handleResetFilters}
              reports={filteredReports}
            />
          </section>
        ) : null}
      </main>
    </AppLayout>
  );
}
