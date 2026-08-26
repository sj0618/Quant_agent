import { backendRequest } from "./backendClient";
import type { ArchivedReportDetail, ArchivedReportSummary, PersistedReportSection } from "../types/quantagent";
import { AI_ENDPOINTS, appConfig } from "../config/appConfig";
import type { AnalysisJob } from "../types/quantagent";

const ANALYSIS_REQUEST_TIMEOUT_MS = 30_000;

export class CoreAnalysisApiError extends Error {
  constructor(readonly status: number) {
    super(status === 503
      ? "실데이터 전략 분석 준비가 완료되지 않았습니다. 잠시 뒤 다시 시도해 주세요."
      : "전략 분석 요청을 처리할 수 없습니다. 잠시 뒤 다시 시도해 주세요.");
  }
}

async function requestCoreAnalysis(path: string, init: RequestInit = {}): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), ANALYSIS_REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${appConfig.aiApiBaseUrl}${path}`, {
      ...init,
      credentials: init.credentials ?? "include",
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new CoreAnalysisApiError(response.status);
    }
    return response;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("전략 분석 서버의 응답 시간이 초과되었습니다. 잠시 뒤 다시 시도해 주세요.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

/** Submit the primary natural-language strategy workflow. Browser state is never used as a result fallback. */
export async function createAnalysisJob(query: string): Promise<AnalysisJob> {
  const normalizedQuery = query.trim();
  if (!normalizedQuery) {
    throw new Error("분석할 자연어 전략을 입력하세요.");
  }
  const response = await requestCoreAnalysis(AI_ENDPOINTS.analysisJobs, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: normalizedQuery }),
  });
  return response.json() as Promise<AnalysisJob>;
}

export async function getAnalysisJob(jobId: string): Promise<AnalysisJob> {
  const response = await requestCoreAnalysis(AI_ENDPOINTS.analysisJob(jobId));
  return response.json() as Promise<AnalysisJob>;
}

export async function cancelAnalysisJob(jobId: string): Promise<AnalysisJob> {
  const response = await requestCoreAnalysis(AI_ENDPOINTS.analysisJobCancel(jobId), { method: "POST" });
  return response.json() as Promise<AnalysisJob>;
}

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
