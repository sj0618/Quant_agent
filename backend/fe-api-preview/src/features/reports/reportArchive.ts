import type { ReportSummary } from "../../types/quantagent";

export const ARCHIVE_TIMESTAMP_UNKNOWN = "보관 기록 시각 미확인";

/**
 * This retained preview may show only the explicit record timestamp as the
 * archive timestamp. Delivery, business, publication, and update times are
 * not substitutes for an absent archive record.
 */
export function archiveTimestamp(report: Pick<ReportSummary, "createdAt">) {
  return report.createdAt ?? ARCHIVE_TIMESTAMP_UNKNOWN;
}

function toCsvValue(value: string | number | undefined) {
  const text = String(value ?? "");
  return `"${text.replace(/"/g, '""')}"`;
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
