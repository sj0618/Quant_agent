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

interface StrategyExecutionSpecV1 {
  market: "KRX";
  timeframe: "daily";
  entry_conditions: Array<{ metric: "rsi"; comparator: "lte" | "gte"; value: number; role: "entry" }>;
  exit_conditions: Array<{ metric: "rsi"; comparator: "lte" | "gte"; value: number; role: "exit" }>;
}

interface RuleDraftOutcome {
  kind: "rule_draft";
  editable_summary: string;
  clarifications: Array<{ label: string; reason: string }>;
  is_executable: boolean;
  strategy_execution_spec?: StrategyExecutionSpecV1;
  spec_version?: "strategy-execution-spec.v1";
  spec_hash?: string;
  parse_token?: string;
}

type ParseOutcome = RuleDraftOutcome | { kind: "scope_refusal" | "unsupported_scope"; explanation: string };

export class StrategyClarificationRequiredError extends Error {
  constructor(outcome: RuleDraftOutcome) {
    const choices = outcome.clarifications.map((item) => `- ${item.label}: ${item.reason}`).join("\n");
    super([outcome.editable_summary, choices].filter(Boolean).join("\n"));
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
  const parseResponse = await requestCoreAnalysis(AI_ENDPOINTS.researchRuleReview, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ natural_language: normalizedQuery }),
  });
  const parsed = await parseResponse.json() as ParseOutcome;
  if (parsed.kind !== "rule_draft") {
    throw new Error(parsed.explanation);
  }
  if (
    !parsed.is_executable
    || !parsed.strategy_execution_spec
    || !parsed.spec_version
    || !parsed.spec_hash
    || !parsed.parse_token
  ) {
    throw new StrategyClarificationRequiredError(parsed);
  }

  const response = await requestCoreAnalysis(AI_ENDPOINTS.analysisJobs, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      parse_token: parsed.parse_token,
      client_idempotency_key: crypto.randomUUID(),
      spec_version: parsed.spec_version,
      spec_hash: parsed.spec_hash,
      strategy_execution_spec: parsed.strategy_execution_spec,
    }),
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
