import { ROUTES } from "../config/routes";
import type { PerformanceSummary, ReportDetail, ReportSummary } from "../types/quantagent";
import { downloadTextFile, toCsvValue } from "../utils/download";

export const ARCHIVE_TIMESTAMP_UNKNOWN = "보관 기록 시각 미확인";

/**
 * This retained preview may show only the explicit record timestamp as the
 * archive timestamp. Delivery, business, publication, and update times are
 * not substitutes for an absent archive record.
 */
export function archiveTimestamp(report: Pick<ReportSummary, "createdAt">) {
  return report.createdAt ?? ARCHIVE_TIMESTAMP_UNKNOWN;
}

export function buildReportsCsv(reports: ReportSummary[]) {
  const header = ["result_id", "archived_date", "created_at", "status"];
  const rows = reports.map((report) => [
    report.id,
    report.date,
    archiveTimestamp(report),
    report.status,
  ]);
  return [header, ...rows].map((row) => row.map(toCsvValue).join(",")).join("\n");
}

export function downloadReportsCsv(reports: ReportSummary[]) {
  downloadTextFile("quantagent-reports.csv", buildReportsCsv(reports), "text/csv;charset=utf-8");
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

export function buildReportPrintTitle(report: ReportDetail | ReportSummary) {
  return `${report.date} ${report.title}`;
}
