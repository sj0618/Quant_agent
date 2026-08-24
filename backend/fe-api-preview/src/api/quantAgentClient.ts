import { fetchServerJson } from "./dataSourceClient";
import type { AppOverview, LandingSample, ReportDetail, ReportSummary } from "../types/quantagent";

/**
 * Read-only API client for the retained local preview. New analysis, runs, and
 * their progress state are deliberately unavailable in this bundle.
 */
export function getLandingSample(): Promise<LandingSample> {
  return fetchServerJson<LandingSample>({
    key: "landingSample",
    path: "/landing-sample",
  });
}

export function getAppOverview(): Promise<AppOverview> {
  return fetchServerJson<AppOverview>({
    key: "appOverview",
    path: "/app/overview",
  });
}

export function getReports(): Promise<ReportSummary[]> {
  return fetchServerJson<ReportSummary[]>({
    key: "reportSummaries",
    path: "/reports",
  });
}

export function getReportById(id: string): Promise<ReportDetail | null> {
  return fetchServerJson<ReportDetail | null>({
    key: "reportDetail",
    path: `/reports/${encodeURIComponent(id)}`,
  });
}

export function confidenceToPercent(confidence: number) {
  return `${Math.round(confidence * 100)}%`;
}
