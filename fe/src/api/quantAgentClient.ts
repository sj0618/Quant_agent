import { backendRequest } from "./backendClient";
import { landingSample } from "../mocks/landing.mock";
import type { LandingSample, ReportDetail, ReportSummary, Tone } from "../types/quantagent";

interface LiveReportListResponse {
  items: ReportSummary[];
  meta?: {
    limit?: number;
    hasMore?: boolean;
    nextCursor?: string | null;
  };
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

function normalizeReportListResponse(response: LiveReportListResponse | ReportSummary[]): ReportSummary[] {
  const items = Array.isArray(response) ? response : response.items;
  return items.map(normalizeReportSummary);
}

function normalizeReportSummary(report: Partial<ReportSummary>): ReportSummary {
  return {
    id: report.id ?? "",
    runId: report.runId,
    strategyId: report.strategyId,
    instrumentId: report.instrumentId,
    instrumentName: report.instrumentName,
    ticker: report.ticker,
    createdAt: report.createdAt,
    updatedAt: report.updatedAt,
    publishedAt: report.publishedAt,
    date: report.date ?? "",
    weekday: report.weekday ?? "",
    sentAt: report.sentAt ?? "",
    title: report.title ?? "",
    summary: report.summary ?? "",
    status: report.status ?? "unknown",
    strategyName: report.strategyName ?? "",
    recommendationScore: report.recommendationScore ?? "—",
    signals: {
      BUY: report.signals?.BUY ?? 0,
      HOLD: report.signals?.HOLD ?? 0,
      DROP: report.signals?.DROP ?? 0,
    },
    marketSnapshot: normalizeMarketSnapshot(report.marketSnapshot),
  };
}

function normalizeNullableText(value: string | null | undefined): string | null {
  const text = value?.trim();
  return text ? text : null;
}

function normalizeText(value: string | null | undefined, fallback = ""): string {
  const text = value?.trim();
  return text ? text : fallback;
}

function normalizeReportDetail(report: ReportDetail | null): ReportDetail | null {
  if (!report) {
    return null;
  }
  return {
    ...normalizeReportSummary(report),
    recipient: normalizeNullableText(report.recipient),
    marketBrief: normalizeText(report.marketBrief, normalizeText(report.summary)),
    marketContext: normalizeNullableText(report.marketContext),
    contentSections: report.contentSections,
    news: Array.isArray(report.news) ? report.news : [],
    candidates: Array.isArray(report.candidates) ? report.candidates : [],
    signalAxes: Array.isArray(report.signalAxes) ? report.signalAxes : [],
    riskManagerOverride: normalizeText(report.riskManagerOverride),
    conclusion: normalizeText(report.conclusion, normalizeText(report.summary)),
    warningNote: normalizeNullableText(report.warningNote),
    performance: {
      metrics: Array.isArray(report.performance?.metrics) ? report.performance.metrics : [],
      disclaimer: normalizeText(report.performance?.disclaimer),
    },
    costNotes: Array.isArray(report.costNotes) ? report.costNotes.filter((note) => typeof note === "string" && note.trim()) : [],
  };
}

function normalizeMarketSnapshot(snapshot: ReportSummary["marketSnapshot"] | undefined): ReportSummary["marketSnapshot"] {
  if (!Array.isArray(snapshot)) {
    return [];
  }
  return snapshot
    .filter((item): item is { label: string; value: string; tone?: Tone } => Boolean(item && typeof item.label === "string" && typeof item.value === "string"))
    .map((item) => ({
      label: item.label,
      value: item.value,
      tone: item.tone,
    }));
}

/** Local-only presentation fixture; no factual performance or live-market claim. */
export function getLandingSample(): Promise<LandingSample> {
  return Promise.resolve(clone(landingSample));
}

/** Read-only report archive. New analysis execution is intentionally not exposed to the browser. */
export async function getReports(q?: string): Promise<ReportSummary[]> {
  const normalizedQuery = q?.trim();
  const path = normalizedQuery ? `/reports?${new URLSearchParams({ q: normalizedQuery }).toString()}` : "/reports";
  const response = await backendRequest<LiveReportListResponse | ReportSummary[]>(path);
  return normalizeReportListResponse(response);
}

export async function getReportById(id: string): Promise<ReportDetail | null> {
  return normalizeReportDetail(await backendRequest<ReportDetail | null>(`/reports/${encodeURIComponent(id)}`));
}
