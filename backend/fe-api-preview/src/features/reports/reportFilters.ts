import type { ReportSummary, SignalType } from "../../types/quantagent";

export type ReportRange = "1" | "7" | "30" | "90" | "all";

export interface ReportFilters {
  range: ReportRange;
  strategyName: string;
  signals: Record<SignalType, boolean>;
  startDate: string;
  endDate: string;
  minScore: number;
}

export const DEFAULT_REPORT_FILTERS: ReportFilters = {
  range: "7",
  strategyName: "all",
  signals: { BUY: true, HOLD: true, DROP: true },
  startDate: "",
  endDate: "",
  minScore: 0,
};

const SIGNALS: SignalType[] = ["BUY", "HOLD", "DROP"];

function parseDate(value: string) {
  const time = Date.parse(value);
  return Number.isNaN(time) ? null : new Date(time);
}

function getReportDate(report: ReportSummary) {
  return parseDate(report.createdAt ?? "");
}

function diffDays(from: Date, to: Date) {
  const millisecondsPerDay = 24 * 60 * 60 * 1000;
  return Math.floor((to.getTime() - from.getTime()) / millisecondsPerDay);
}

export function parseReportFilters(search: string): ReportFilters {
  const params = new URLSearchParams(search);
  const range = params.get("range");
  const signals = params.get("signals")?.split(",").filter(Boolean) as SignalType[] | undefined;
  const minScore = Number(params.get("minScore") ?? DEFAULT_REPORT_FILTERS.minScore);

  return {
    range: range === "1" || range === "7" || range === "30" || range === "90" || range === "all" ? range : DEFAULT_REPORT_FILTERS.range,
    strategyName: params.get("strategy") ?? DEFAULT_REPORT_FILTERS.strategyName,
    signals: {
      BUY: signals ? signals.includes("BUY") : DEFAULT_REPORT_FILTERS.signals.BUY,
      HOLD: signals ? signals.includes("HOLD") : DEFAULT_REPORT_FILTERS.signals.HOLD,
      DROP: signals ? signals.includes("DROP") : DEFAULT_REPORT_FILTERS.signals.DROP,
    },
    startDate: params.get("start") ?? DEFAULT_REPORT_FILTERS.startDate,
    endDate: params.get("end") ?? DEFAULT_REPORT_FILTERS.endDate,
    minScore: Number.isFinite(minScore) ? minScore : DEFAULT_REPORT_FILTERS.minScore,
  };
}

export function serializeReportFilters(filters: ReportFilters) {
  const params = new URLSearchParams();
  if (filters.range !== DEFAULT_REPORT_FILTERS.range) params.set("range", filters.range);
  if (filters.strategyName !== DEFAULT_REPORT_FILTERS.strategyName) params.set("strategy", filters.strategyName);

  const selectedSignals = SIGNALS.filter((signal) => filters.signals[signal]);
  if (selectedSignals.length !== SIGNALS.length) params.set("signals", selectedSignals.join(","));
  if (filters.startDate) params.set("start", filters.startDate);
  if (filters.endDate) params.set("end", filters.endDate);
  if (filters.minScore > DEFAULT_REPORT_FILTERS.minScore) params.set("minScore", String(filters.minScore));
  return params.toString();
}

export function applyReportFilters(reports: ReportSummary[], filters: ReportFilters) {
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
    if (filters.strategyName !== "all" && report.strategyName !== filters.strategyName) return false;
    if (Number(report.recommendationScore) < filters.minScore) return false;
    if (!SIGNALS.some((signal) => filters.signals[signal] && report.signals[signal] > 0)) return false;
    return true;
  });
}
