import { backendRequest } from "./backendClient";
import type { ArchivedReportDetail, ArchivedReportSummary, PersistedReportSection } from "../types/quantagent";

interface LiveReportListResponse {
  items: ArchivedReportSummary[];
  meta?: {
    limit?: number;
    hasMore?: boolean;
    nextCursor?: string | null;
  };
}

function normalizeReportListResponse(response: LiveReportListResponse | ArchivedReportSummary[]): ArchivedReportSummary[] {
  const items = Array.isArray(response) ? response : response.items;
  return items.map(normalizeArchivedReportSummary);
}

function normalizeArchivedReportSummary(report: Partial<ArchivedReportSummary>): ArchivedReportSummary {
  return {
    id: report.id ?? "",
    runId: report.runId,
    createdAt: report.createdAt,
    updatedAt: report.updatedAt,
    publishedAt: report.publishedAt,
    date: report.date ?? "",
    weekday: report.weekday ?? "",
    sentAt: report.sentAt ?? "",
    status: report.status ?? "unknown",
  };
}

function normalizePersistedReportSection(value: PersistedReportSection): PersistedReportSection {
  return {
    id: value.id,
    title: value.title,
    note: value.note,
    body: value.body,
    entries: Array.isArray(value.entries) ? value.entries.map((entry) => ({
      label: entry.label,
      value: entry.value,
      depth: entry.depth,
      description: entry.description,
    })) : [],
  };
}

function normalizeReportDetail(report: ArchivedReportDetail | null): ArchivedReportDetail | null {
  if (!report) {
    return null;
  }
  return {
    ...normalizeArchivedReportSummary(report),
    contentSections: Array.isArray(report.contentSections)
      ? report.contentSections.map(normalizePersistedReportSection)
      : [],
  };
}

/** Read-only report archive. New analysis execution is intentionally not exposed to the browser. */
export async function getReports(q?: string): Promise<ArchivedReportSummary[]> {
  const normalizedQuery = q?.trim();
  const path = normalizedQuery ? `/reports?${new URLSearchParams({ q: normalizedQuery }).toString()}` : "/reports";
  const response = await backendRequest<LiveReportListResponse | ArchivedReportSummary[]>(path);
  return normalizeReportListResponse(response);
}

export async function getReportById(id: string): Promise<ArchivedReportDetail | null> {
  return normalizeReportDetail(await backendRequest<ArchivedReportDetail | null>(`/reports/${encodeURIComponent(id)}`));
}
