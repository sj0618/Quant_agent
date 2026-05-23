import { appOverview, analysisJobStatus, performanceSummary, tradingCandidates } from "../mocks/app.mock";
import { landingSample } from "../mocks/landing.mock";
import { reportDetails, reportSummaries } from "../mocks/reports.mock";
import type {
  AnalysisJobStatus,
  AppOverview,
  LandingSample,
  PerformanceSummary,
  ReportDetail,
  ReportSummary,
  TradingCandidate,
} from "../types/quantagent";

const MOCK_LATENCY_MS = 120;

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

async function respond<T>(value: T): Promise<T> {
  await new Promise((resolve) => window.setTimeout(resolve, MOCK_LATENCY_MS));
  return clone(value);
}

export function getLandingSample(): Promise<LandingSample> {
  return respond(landingSample);
}

export function getAppOverview(): Promise<AppOverview> {
  return respond({ ...appOverview, recentReports: reportSummaries.slice(0, 4) });
}

export function getTradingCandidates(): Promise<TradingCandidate[]> {
  return respond(tradingCandidates);
}

export function getPerformanceSummary(): Promise<PerformanceSummary> {
  return respond(performanceSummary);
}

export function getReports(): Promise<ReportSummary[]> {
  return respond(reportSummaries);
}

export function getReportById(id: string): Promise<ReportDetail | null> {
  const directDetail = reportDetails.find((report) => report.id === id);
  if (directDetail) {
    return respond(directDetail);
  }

  const summary = reportSummaries.find((report) => report.id === id);
  if (!summary) {
    return respond(null);
  }

  return respond({ ...reportDetails[0], ...summary });
}

export function getAnalysisJobStatus(): Promise<AnalysisJobStatus> {
  return respond(analysisJobStatus);
}
