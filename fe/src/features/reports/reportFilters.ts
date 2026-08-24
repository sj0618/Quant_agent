import type { ArchivedReportSummary } from "../../types/quantagent";

export type ReportRange = "1" | "7" | "30" | "90" | "all";

export interface ReportFilters {
  range: ReportRange;
  startDate: string;
  endDate: string;
}

export const DEFAULT_REPORT_FILTERS: ReportFilters = {
  range: "7",
  startDate: "",
  endDate: "",
};

function parseDate(value: string) {
  const normalized = value.trim();
  if (!normalized) return null;

  const dottedDate = normalized.match(/^(\d{4})\.(\d{2})\.(\d{2})$/);
  if (dottedDate) {
    return new Date(Date.UTC(Number(dottedDate[1]), Number(dottedDate[2]) - 1, Number(dottedDate[3])));
  }

  const isoDate = normalized.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (isoDate) {
    return new Date(Date.UTC(Number(isoDate[1]), Number(isoDate[2]) - 1, Number(isoDate[3])));
  }

  const time = Date.parse(normalized);
  return Number.isNaN(time) ? null : new Date(time);
}

function getReportDate(report: ArchivedReportSummary) {
  return parseDate(report.createdAt ?? "");
}

function diffDays(from: Date, to: Date) {
  return Math.floor((to.getTime() - from.getTime()) / (24 * 60 * 60 * 1000));
}

export function parseReportFilters(search: string): ReportFilters {
  const params = new URLSearchParams(search);
  const range = params.get("range");
  return {
    range: range === "1" || range === "7" || range === "30" || range === "90" || range === "all" ? range : DEFAULT_REPORT_FILTERS.range,
    startDate: params.get("start") ?? DEFAULT_REPORT_FILTERS.startDate,
    endDate: params.get("end") ?? DEFAULT_REPORT_FILTERS.endDate,
  };
}

export function serializeReportFilters(filters: ReportFilters) {
  const params = new URLSearchParams();
  if (filters.range !== DEFAULT_REPORT_FILTERS.range) params.set("range", filters.range);
  if (filters.startDate) params.set("start", filters.startDate);
  if (filters.endDate) params.set("end", filters.endDate);
  return params.toString();
}

export function applyReportFilters(reports: ArchivedReportSummary[], filters: ReportFilters) {
  const latestDate = reports.map(getReportDate).find(Boolean);
  const startDate = parseDate(filters.startDate);
  const endDate = parseDate(filters.endDate);

  return reports.filter((report) => {
    const reportDate = getReportDate(report);
    const hasDateConstraint = filters.range !== "all" || startDate !== null || endDate !== null;
    if (!reportDate && hasDateConstraint) return false;
    if (reportDate) {
      if (latestDate && filters.range !== "all" && diffDays(reportDate, latestDate) >= Number(filters.range)) return false;
      if (startDate && reportDate < startDate) return false;
      if (endDate && reportDate > endDate) return false;
    }
    return true;
  });
}
