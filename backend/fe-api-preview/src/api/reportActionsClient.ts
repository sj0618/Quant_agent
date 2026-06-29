import { REPORT_ACTION_ENDPOINTS, appConfig } from "../config/appConfig";
import { ROUTES } from "../config/routes";
import type { PerformanceSummary, ReportDetail, ReportSummary } from "../types/quantagent";
import { recordDataSource } from "./dataSourceClient";
import { downloadTextFile, toCsvValue } from "../utils/download";

function assertOk(response: Response) {
  if (!response.ok) {
    throw new Error(`리포트 액션 서버 응답 실패: ${response.status}`);
  }
}

export function downloadReportsCsv(reports: ReportSummary[]) {
  const header = ["id", "date", "strategy", "score", "buy", "hold", "drop", "summary"];
  const rows = reports.map((report) => [
    report.id,
    report.date,
    report.strategyName,
    report.recommendationScore,
    report.signals.BUY,
    report.signals.HOLD,
    report.signals.DROP,
    report.summary,
  ]);
  const csv = [header, ...rows].map((row) => row.map(toCsvValue).join(",")).join("\n");
  downloadTextFile("quantagent-reports.csv", csv, "text/csv;charset=utf-8");
}

export function downloadPerformanceCsv(performance: PerformanceSummary) {
  const header = ["date", "selected_candidate", "baseline", "benchmark"];
  const rows = performance.equityCurve.map((point) => [point.date, point.strategy, point.original, point.benchmark]);
  const csv = [header, ...rows].map((row) => row.map(toCsvValue).join(",")).join("\n");
  downloadTextFile("quantagent-performance.csv", csv, "text/csv;charset=utf-8");
}

export function printCurrentView() {
  window.print();
}

export async function copyReportShareLink(reportId: string) {
  const url = `${window.location.origin}${ROUTES.reportDetail(reportId)}`;
  await window.navigator.clipboard.writeText(url);
  return url;
}

export async function resendReportEmail(reportId: string) {
  if (!appConfig.reportActionApiBaseUrl) {
    throw new Error("VITE_REPORT_ACTION_API_BASE_URL 설정이 필요합니다.");
  }

  const response = await fetch(`${appConfig.reportActionApiBaseUrl}${REPORT_ACTION_ENDPOINTS.resend(reportId)}`, {
    method: "POST",
    credentials: "include",
  });
  assertOk(response);
  recordDataSource({ key: "reportResend", path: REPORT_ACTION_ENDPOINTS.resend(reportId), source: "server", status: response.status });
}

export function buildReportPrintTitle(report: ReportDetail | ReportSummary) {
  return `${report.date} ${report.title}`;
}
