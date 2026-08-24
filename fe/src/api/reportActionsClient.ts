import { ROUTES } from "../config/routes";
import { backendRequest } from "./backendClient";
import type { ArchivedReportDetail, ArchivedReportSummary, PerformanceSummary } from "../types/quantagent";
import { downloadTextFile, toCsvValue } from "../utils/download";

export function downloadReportsCsv(reports: ArchivedReportSummary[]) {
  const header = ["result_id", "archived_date", "created_at", "status"];
  const rows = reports.map((report) => [
    report.id,
    report.date,
    report.createdAt ?? report.publishedAt ?? report.sentAt,
    report.status,
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
  await backendRequest<void>(`/reports/${encodeURIComponent(reportId)}/resend`, {
    method: "POST",
  });
}

export function buildReportPrintTitle(report: ArchivedReportDetail | ArchivedReportSummary) {
  return `QuantAgent 결과 스냅샷 ${report.id}`;
}
