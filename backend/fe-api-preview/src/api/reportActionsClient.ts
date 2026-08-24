import { ROUTES } from "../config/routes";
import { buildReportsCsv } from "../features/reports/reportArchive";
import type { PerformanceSummary, ReportDetail, ReportSummary } from "../types/quantagent";
import { downloadTextFile, toCsvValue } from "../utils/download";
export { archiveTimestamp, buildReportsCsv } from "../features/reports/reportArchive";

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
