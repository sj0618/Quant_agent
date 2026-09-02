import { AI_ENDPOINTS, appConfig } from "../config/appConfig";
import { backendRequest } from "./backendClient";
import { publicAiResponseFailure } from "./aiResponseFailure";
import { landingSample } from "../mocks/landing.mock";
import { formatScoreValue, SCORE_SCALE, selectRecommendationConfidence } from "../utils/score";
import { clearUserScopedStorage } from "../utils/userScopedStorage";
import type {
  AIBacktestBenchmark,
  AIBacktestEquityPoint,
  AIBacktestMetricDetail,
  AIBacktestMetrics,
  AIBacktestPerformance,
  AIBacktestReliability,
  AICondition,
  AIEnvelopeStatus,
  AIJobStage,
  AIJobStageStatus,
  AIReportBundle,
  AIRiskAdjustment,
  AIStrategySpec,
  AnalysisJob,
  AnalysisJobStatus,
  AnalysisStage,
  AppOverview,
  BacktestMetric,
  ChatMessage,
  EquityPoint,
  LandingSample,
  PerformanceSummary,
  PerformanceComparisonRow,
  ReportDetail,
  ReportSummary,
  SignalType,
  StageStatus,
  StrategyReportDetail,
  StrategyReportSummary,
  StrategySpec,
  Tone,
  TradingCandidate,
  WorkspaceReportDetail,
} from "../types/quantagent";

const APP_LOCALE = "ko-KR";
const RECENT_REPORT_LIMIT = 4;
const PERCENT_SCALE = 100;
const TRACE_PREVIEW_LENGTH = 8;
const PERCENT_DISPLAY_DIGITS = 2;
const DECIMAL_DISPLAY_DIGITS = 2;
const AI_REQUEST_TIMEOUT_MS = 1_200_000;
const STORAGE_KEY_LATEST_ANALYSIS_JOB = "quantagent.latest-analysis-job.v1";
const AI_REPORT_ID_PREFIX = "ai-job:";
const TIMEFRAME_LABELS: Record<string, string> = {
  daily: "매일 분석",
  weekly: "매주 분석",
  monthly: "매월 분석",
};
const STAGE_LABELS: Record<AIJobStage, string> = {
  interpreting: "전략 해석 중",
  code_generation: "코드 생성 중",
  backtest: "백테스트 실행 중",
  debate: "정반 토론 중",
  finalizing: "최종 결정 중",
};
const WORKSPACE_STAGE_BY_AI_STAGE: Record<AIJobStage, AnalysisStage> = {
  interpreting: "strategy_parse",
  code_generation: "data_collect",
  backtest: "backtest",
  debate: "risk_review",
  finalizing: "report_ready",
};
const WORKSPACE_STATUS_BY_AI_STATUS: Record<AIJobStageStatus, StageStatus> = {
  queued: "ready",
  running: "running",
  succeeded: "done",
  failed: "failed",
};
const EMPTY_PERFORMANCE: PerformanceSummary = {
  headline: "분석 결과 없음",
  period: "전략을 분석하면 실제 API 백테스트 결과가 표시됩니다.",
  metrics: [],
  equityCurve: [],
  comparison: [],
  macroEvents: [],
  disclaimer: "분석 전에는 성과 데이터를 표시하지 않습니다.",
};
const EMPTY_WORKSPACE: AppOverview = {
  strategy: {
    natural_language_strategy: "",
    sector: "",
    buy_condition: "",
    hold_condition: "",
    drop_condition: "",
    rebalance: "",
    constraints: [],
  },
  recommendationScore: "—",
  recommendationDelta: "분석 전",
  passCount: 0,
  buyCount: 0,
  holdCount: 0,
  dropCount: 0,
  nextRunLabel: "예약 없음",
  latestRunLabel: "분석 전",
  chatMessages: [],
  candidates: [],
  performance: EMPTY_PERFORMANCE,
  recentReports: [],
  envelope: null,
  jobStatus: null,
};

interface StrategyDescriptionApiInput {
  strategy_id: string;
  name: string;
  timeframe: string;
  entry_summary: string;
  exit_summary: string;
  risk_summary: string;
  tags: string[];
}

interface StrategyDescriptionApiResponse {
  items: Array<{
    strategy_id: string;
    description: string;
  }>;
}

class AIResponseError extends Error {
  constructor(
    readonly status: number,
    readonly reasonCode: string | null = null,
    message: string | null = null,
  ) {
    super(message ?? `AI 서버 응답 실패: ${status}`);
  }
}

/** HTTP status behind a failed AI call, or null if it never reached the server. */
export function aiResponseStatus(error: unknown): number | null {
  return error instanceof AIResponseError ? error.status : null;
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

function requireAiApiBaseUrl() {
  if (!appConfig.aiApiBaseUrl) {
    throw new Error("VITE_AI_API_BASE_URL 설정이 필요합니다.");
  }
  return appConfig.aiApiBaseUrl;
}

async function assertOk(response: Response) {
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      clearUserScopedStorage();
    }
    let payload: unknown = null;
    try {
      payload = await response.clone().json();
    } catch {
      // A non-JSON gateway error is still represented by its HTTP status.
    }
    const failure = publicAiResponseFailure(response.status, payload);
    console.warn("AI API request rejected", {
      status: response.status,
      reasonCode: failure.reasonCode,
    });
    throw new AIResponseError(response.status, failure.reasonCode, failure.message);
  }
}

async function fetchAI(path: string, init: RequestInit = {}) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), AI_REQUEST_TIMEOUT_MS);
  try {
    return await fetch(`${requireAiApiBaseUrl()}${path}`, {
      ...init,
      credentials: init.credentials ?? "include",
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("AI 분석 요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export interface ResearchAppendix {
  status: "pending" | "ready" | "unavailable";
  payload: {
    strategy_reading?: string;
    metrics?: Array<{ name: string; definition: string; formula: string; required_inputs: string[] }>;
    citations?: Array<{ title: string; url: string }>;
    reason?: string;
  };
}

export async function getResearchAppendix(jobId: string): Promise<ResearchAppendix> {
  const response = await fetchAI(AI_ENDPOINTS.analysisJobResearchAppendix(jobId));
  await assertOk(response);
  return response.json() as Promise<ResearchAppendix>;
}

function buildStrategyDescriptionInput(strategy: StrategyReportSummary): StrategyDescriptionApiInput {
  return {
    strategy_id: strategy.id,
    name: strategy.name,
    timeframe: strategy.timeframe,
    entry_summary: strategy.entrySummary,
    exit_summary: strategy.exitSummary,
    risk_summary: strategy.riskSummary,
    tags: strategy.tags,
  };
}

async function fetchStrategyDescriptionMap(strategies: StrategyReportSummary[]) {
  if (strategies.length === 0) {
    return {} as Record<string, string>;
  }

  try {
    const response = await fetchAI(AI_ENDPOINTS.strategyDescriptions, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        strategies: strategies.map(buildStrategyDescriptionInput),
      }),
    });
    await assertOk(response);

    const payload = (await response.json()) as StrategyDescriptionApiResponse;
    return payload.items.reduce<Record<string, string>>((current, item) => {
      if (item.description.trim()) {
        current[item.strategy_id] = item.description.trim();
      }
      return current;
    }, {});
  } catch (error) {
    console.warn("전략 설명 AI 보강에 실패해 seed 설명을 사용합니다.", error);
    return {};
  }
}

async function hydrateStrategyDescriptions(strategies: StrategyReportSummary[]) {
  const descriptionMap = await fetchStrategyDescriptionMap(strategies);
  return strategies.map((strategy) => ({
    ...strategy,
    description: descriptionMap[strategy.id] ?? strategy.description,
  }));
}

function normalizeEmailReportDetail(report: ReportDetail | null): ReportDetail | null {
  if (!report) {
    return null;
  }
  return {
    ...report,
    date: report.date ?? "",
    weekday: report.weekday ?? "",
    sentAt: report.sentAt ?? "",
    status: report.status ?? "unknown",
    title: report.title ?? "이메일 리포트",
    summary: report.summary ?? "",
    strategyName: report.strategyName ?? "전략 미상",
    recommendationScore: report.recommendationScore ?? "—",
    signals: {
      BUY: report.signals?.BUY ?? 0,
      HOLD: report.signals?.HOLD ?? 0,
      DROP: report.signals?.DROP ?? 0,
    },
    marketSnapshot: Array.isArray(report.marketSnapshot) ? report.marketSnapshot : [],
    recipient: report.recipient ?? null,
    marketBrief: report.marketBrief ?? report.summary ?? "",
    marketContext: report.marketContext ?? null,
    contentSections: Array.isArray(report.contentSections) ? report.contentSections : [],
    news: Array.isArray(report.news) ? report.news : [],
    candidates: Array.isArray(report.candidates) ? report.candidates : [],
    signalAxes: Array.isArray(report.signalAxes) ? report.signalAxes : [],
    riskManagerOverride: report.riskManagerOverride ?? "",
    conclusion: report.conclusion ?? report.summary ?? "",
    warningNote: report.warningNote ?? null,
    performance: {
      metrics: Array.isArray(report.performance?.metrics) ? report.performance.metrics : [],
      disclaimer: report.performance?.disclaimer ?? "",
    },
    costNotes: Array.isArray(report.costNotes) ? report.costNotes : [],
  };
}

function readLatestAnalysisJob(): AnalysisJob | null {
  const raw = window.localStorage.getItem(STORAGE_KEY_LATEST_ANALYSIS_JOB);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as AnalysisJob;
  } catch (error) {
    console.warn("저장된 AI 분석 job을 읽지 못했습니다.", error);
    window.localStorage.removeItem(STORAGE_KEY_LATEST_ANALYSIS_JOB);
    return null;
  }
}

export function saveLatestAnalysisJob(job: AnalysisJob) {
  window.localStorage.setItem(STORAGE_KEY_LATEST_ANALYSIS_JOB, JSON.stringify(job));
}

export function clearLatestAnalysisJob() {
  window.localStorage.removeItem(STORAGE_KEY_LATEST_ANALYSIS_JOB);
}

export function getLatestAnalysisJob(): AnalysisJob | null {
  return readLatestAnalysisJob();
}

export async function createAnalysisJob(query: string): Promise<AnalysisJob> {
  const trimmedQuery = query.trim();
  if (!trimmedQuery) {
    throw new Error("분석할 자연어 전략을 입력하세요.");
  }

  // The server performs parse → versioned spec/hash → durable job admission as one
  // request. This keeps opaque short-lived tokens out of browser state and prevents
  // a valid strategy from failing when a reload lands between two API calls.
  const response = await fetchAI(AI_ENDPOINTS.analysisJobs, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: trimmedQuery }),
  });
  await assertOk(response);

  const job = (await response.json()) as AnalysisJob;
  saveLatestAnalysisJob(job);
  return job;
}

export async function cancelAnalysisJob(jobId: string): Promise<AnalysisJob> {
  const response = await fetchAI(AI_ENDPOINTS.analysisJobCancel(jobId), { method: "POST" });
  await assertOk(response);

  const job = (await response.json()) as AnalysisJob;
  saveLatestAnalysisJob(job);
  return job;
}

async function requestAnalysisJob(jobId: string): Promise<AnalysisJob> {
  const response = await fetchAI(AI_ENDPOINTS.analysisJob(jobId));
  await assertOk(response);

  return (await response.json()) as AnalysisJob;
}

export async function getAnalysisJob(jobId: string): Promise<AnalysisJob> {
  const job = await requestAnalysisJob(jobId);
  saveLatestAnalysisJob(job);
  return job;
}

async function listAnalysisJobs(limit = 100): Promise<AnalysisJob[]> {
  const response = await fetchAI(`${AI_ENDPOINTS.analysisJobs}?limit=${limit}`);
  await assertOk(response);
  return (await response.json()) as AnalysisJob[];
}

export async function refreshLatestAnalysisJob(): Promise<AnalysisJob | null> {
  const storedJob = readLatestAnalysisJob();
  if (!appConfig.aiApiBaseUrl) {
    return storedJob;
  }

  try {
    if (storedJob) {
      return await getAnalysisJob(storedJob.job_id);
    }
    const [latestJob] = await listAnalysisJobs(1);
    if (latestJob) {
      saveLatestAnalysisJob(latestJob);
    }
    return latestJob ?? null;
  } catch (error) {
    if (error instanceof AIResponseError && [401, 403].includes(error.status)) {
      clearLatestAnalysisJob();
      throw error;
    }
    if (error instanceof AIResponseError && error.status === 404) {
      clearLatestAnalysisJob();
      const [latestJob] = await listAnalysisJobs(1);
      if (latestJob) {
        saveLatestAnalysisJob(latestJob);
      }
      return latestJob ?? null;
    }
    console.warn("최신 AI 분석 job 갱신에 실패해 저장된 결과를 사용합니다.", error);
    return storedJob;
  }
}

export function latestAnalysisReportId(jobId: string) {
  return `${AI_REPORT_ID_PREFIX}${jobId}`;
}

export function mergeAnalysisJobIntoOverview(base: AppOverview, job: AnalysisJob): AppOverview {
  const result = job.result;
  const strategy = result?.strategy_spec ? mapAIStrategySpec(result.strategy_spec, job.query) : { ...base.strategy, natural_language_strategy: job.query };
  const reportSummary = buildReportSummaryFromAnalysisJob(job);
  const recentReports = reportSummary
    ? [reportSummary, ...base.recentReports.filter((report) => report.id !== reportSummary.id)].slice(0, RECENT_REPORT_LIMIT)
    : base.recentReports;
  const performance = buildPerformanceSummaryFromAnalysisJob(job, base.performance);
  const signals = reportSummary?.signals ?? { BUY: 0, HOLD: 0, DROP: 0 };
  const finalSignal = result?.user_payload.report ? extractFinalSignal(result.user_payload.report) : null;
  const recommendationConfidence = result?.strategy_spec
    ? selectRecommendationConfidence(finalSignal?.confidence, result.strategy_spec.confidence)
    : null;

  return {
    ...base,
    strategy,
    recommendationScore: recommendationConfidence === null ? base.recommendationScore : formatScore(recommendationConfidence),
    recommendationDelta: result ? formatStatusDelta(result.status) : base.recommendationDelta,
    passCount: result ? signals.BUY + signals.HOLD + signals.DROP : base.passCount,
    buyCount: result ? signals.BUY : base.buyCount,
    holdCount: result ? signals.HOLD : base.holdCount,
    dropCount: result ? signals.DROP : base.dropCount,
    latestRunLabel: `최신 분석 · ${formatDateTime(job.updated_at)}`,
    nextRunLabel: result ? "예약 없음" : base.nextRunLabel,
    chatMessages: mergeChatMessages(base.chatMessages, buildAnalysisChatMessages(job)),
    candidates: result ? buildTradingCandidatesFromAnalysisJob(job) : base.candidates,
    performance,
    recentReports,
    envelope: result ?? base.envelope,
    jobStatus: buildWorkspaceJobStatus(job),
  };
}

export function getLandingSample(): Promise<LandingSample> {
  return Promise.resolve(clone(landingSample));
}

export async function getAppOverview(): Promise<AppOverview> {
  const overview = await backendRequest<AppOverview>("/app/overview");
  const latestJob = await refreshLatestAnalysisJob();
  return latestJob ? mergeAnalysisJobIntoOverview(overview, latestJob) : overview;
}

export function getWorkspaceTemplate(): Promise<AppOverview> {
  return Promise.resolve(clone(EMPTY_WORKSPACE));
}

/** Service-DB run bookkeeping.
 *
 * The workspace talks to the AI service directly, so nothing in that path touches the
 * service DB. Persisting the run is a second, independent call: without it `GET /reports`
 * has no rows to return and the 리포트 page is permanently empty. This pairing was lost in
 * `6dadc69` and is restored here.
 */
export interface AnalysisRunHandle {
  id: string;
  status: string;
  reportId: string | null;
}

export async function createAnalysisRun(job: AnalysisJob): Promise<AnalysisRunHandle> {
  return backendRequest<AnalysisRunHandle>("/runs", {
    method: "POST",
    body: JSON.stringify({
      query: job.query,
      aiJobId: job.job_id,
      requestPayload: { aiJobId: job.job_id, traceId: job.trace_id, query: job.query },
    }),
  });
}

export async function completeAnalysisRun(runId: string, job: AnalysisJob): Promise<AnalysisRunHandle> {
  return backendRequest<AnalysisRunHandle>(`/runs/${encodeURIComponent(runId)}/complete`, {
    method: "POST",
    body: JSON.stringify({ aiJobId: job.job_id }),
  });
}

/**
 * `/reports` is the user's workspace-analysis library, not the email outbox.
 *
 * The canonical source is the completed analysis job: it contains the strategy
 * specification, actual backtest payload, and generated web report as one unit.
 * Email delivery records deliberately stay under `/me`.
 */
export async function getReports(q?: string): Promise<ReportSummary[]> {
  const normalizedQuery = q?.trim().toLocaleLowerCase(APP_LOCALE);
  const reports = (await listAnalysisJobs())
    .map(buildReportSummaryFromAnalysisJob)
    .filter((report): report is ReportSummary => report !== null);

  if (!normalizedQuery) {
    return reports;
  }

  return reports.filter((report) =>
    [report.title, report.summary, report.strategyName, report.date]
      .join(" ")
      .toLocaleLowerCase(APP_LOCALE)
      .includes(normalizedQuery),
  );
}

function workspaceJobIdFromReportId(id: string) {
  if (!id.startsWith(AI_REPORT_ID_PREFIX)) {
    return null;
  }
  const jobId = id.slice(AI_REPORT_ID_PREFIX.length);
  return jobId || null;
}

export async function getWorkspaceReportById(id: string): Promise<WorkspaceReportDetail | null> {
  const jobId = workspaceJobIdFromReportId(id);
  if (!jobId) {
    return null;
  }
  const job = await requestAnalysisJob(jobId);
  return buildWorkspaceReportDetailFromAnalysisJob(job);
}

/** Email delivery history opens this separately from the workspace-report route. */
export async function getEmailReportById(id: string): Promise<ReportDetail | null> {
  return normalizeEmailReportDetail(
    await backendRequest<ReportDetail | null>(`/me/email-reports/${encodeURIComponent(id)}`),
  );
}

export async function getReportStrategies(): Promise<StrategyReportSummary[]> {
  const jobs = await listAnalysisJobs();
  const strategies = jobs
    .map(buildStrategyReportSummaryFromAnalysisJob)
    .filter((strategy): strategy is StrategyReportSummary => strategy !== null)
    .filter((strategy, index, all) => all.findIndex((candidate) => candidate.id === strategy.id) === index);
  return hydrateStrategyDescriptions(strategies);
}

export async function getStrategyReportById(id: string): Promise<StrategyReportDetail | null> {
  const jobs = (await listAnalysisJobs()).filter((job) => job.result?.strategy_spec?.strategy_id === id);
  const strategy = jobs.length ? buildStrategyReportSummaryFromAnalysisJob(jobs[0]) : null;
  if (!strategy) {
    return null;
  }
  const [hydratedStrategy] = await hydrateStrategyDescriptions([strategy]);
  const emailReports = jobs
    .map(buildReportDetailFromAnalysisJob)
    .filter((report): report is ReportDetail => report !== null);
  return { strategy: hydratedStrategy, emailReports };
}

export async function getStrategyWorkspaceOverview(id: string): Promise<AppOverview | null> {
  const latestJob = (await listAnalysisJobs()).find((job) => job.result?.strategy_spec?.strategy_id === id);
  if (!latestJob) {
    return null;
  }
  return mergeAnalysisJobIntoOverview(clone(EMPTY_WORKSPACE), latestJob);
}

function mapAIStrategySpec(strategy: AIStrategySpec, query: string): StrategySpec {
  const riskConstraints = Object.entries(strategy.risk_constraints).map(([key, value]) => `${key}: ${String(value)}`);
  return {
    name: strategy.name,
    natural_language_strategy: query,
    sector: strategy.indicators.length ? strategy.indicators.join(", ") : strategy.market,
    buy_condition: describeConditions(strategy.entry_conditions),
    hold_condition: strategy.timeframe,
    drop_condition: describeConditions(strategy.exit_conditions),
    rebalance: TIMEFRAME_LABELS[strategy.timeframe] ?? strategy.timeframe,
    constraints: [...riskConstraints, ...strategy.assumptions],
  };
}

function describeConditions(conditions: AICondition[]) {
  if (!conditions.length) {
    return "조건 없음";
  }
  return conditions.map((condition) => condition.description ?? describeCondition(condition)).join(" AND ");
}

function describeCondition(condition: AICondition) {
  return `${condition.left} ${condition.operator} ${formatConditionRight(condition.right)}`;
}

function formatConditionRight(value: AICondition["right"]) {
  return Array.isArray(value) ? value.join("~") : String(value);
}

function buildWorkspaceJobStatus(job: AnalysisJob): AnalysisJobStatus {
  return {
    trace_id: job.trace_id,
    status: job.result?.status ?? "running",
    stages: job.stages.map((stage) => ({
      stage: WORKSPACE_STAGE_BY_AI_STAGE[stage.stage],
      status: WORKSPACE_STATUS_BY_AI_STATUS[stage.status],
      label: STAGE_LABELS[stage.stage],
      updated_at: stage.updated_at,
    })),
  };
}

function buildAnalysisChatMessages(job: AnalysisJob): ChatMessage[] {
  const payload = job.result?.user_payload;
  const status = job.result?.status ?? "running";
  const statusLabel = formatEnvelopeStatus(status);
  const visibleCandidateCards = status === "need_clarification" ? payload?.candidate_cards : undefined;
  const candidateCount = visibleCandidateCards?.length ?? 0;
  const clarification =
    payload?.question && payload.options?.length
      ? {
          question: payload.question,
          options: payload.options,
          recommended: payload.recommended,
        }
      : undefined;

  return [
    {
      id: `${job.job_id}:system`,
      sender: "system",
      label: "SYSTEM",
      time: formatDateTime(job.created_at),
      body: `분석 job ${job.job_id}를 생성했습니다. Trace ${job.trace_id.slice(0, TRACE_PREVIEW_LENGTH)}로 추적합니다.`,
    },
    {
      id: `${job.job_id}:user`,
      sender: "user",
      label: "나",
      time: formatDateTime(job.created_at),
      body: job.query,
    },
    {
      id: `${job.job_id}:agent`,
      sender: "agent",
      label: "AGENT",
      time: `${formatDateTime(job.updated_at)} · ${statusLabel}`,
      body: payload?.message ?? "AI 분석이 진행 중입니다.",
      stats: [
        { label: "상태", value: statusLabel },
        { label: "후보", value: `${candidateCount}` },
        { label: "Trace", value: job.trace_id.slice(0, TRACE_PREVIEW_LENGTH) },
      ],
      candidateCards: visibleCandidateCards,
      clarification,
    },
  ];
}

function mergeChatMessages(base: ChatMessage[], next: ChatMessage[]) {
  const seen = new Set<string>();
  return [...base, ...next].filter((message) => {
    if (seen.has(message.id)) {
      return false;
    }
    seen.add(message.id);
    return true;
  });
}

function buildReportSummaryFromAnalysisJob(job: AnalysisJob): ReportSummary | null {
  const result = job.result;
  const report = result?.user_payload.report;
  if (!result || result.status !== "ready" || !report) {
    return null;
  }

  const signal = extractFinalSignal(report);
  const confidence = result.strategy_spec
    ? selectRecommendationConfidence(signal?.confidence, result.strategy_spec.confidence)
    : signal?.confidence;
  const date = new Date(job.updated_at);
  return {
    id: latestAnalysisReportId(job.job_id),
    strategyId: result.strategy_spec?.strategy_id,
    date: formatReportDate(date),
    weekday: formatWeekday(date),
    sentAt: formatDateTime(job.updated_at),
    title: report.web_projection.title,
    summary: report.web_projection.summary,
    status: "draft",
    strategyName: result.strategy_spec?.name ?? result.user_payload.headline,
    recommendationScore: confidence === null || confidence === undefined ? formatEnvelopeStatus(result.status) : formatScoreValue(confidence),
    signals: signalCounts(signal?.action ?? null),
    marketSnapshot: [
      { label: "AI 상태", value: formatEnvelopeStatus(result.status), tone: toneForStatus(result.status) },
      { label: "Trace", value: result.trace_id.slice(0, TRACE_PREVIEW_LENGTH), tone: "neutral" },
    ],
  };
}

function buildWorkspaceReportDetailFromAnalysisJob(job: AnalysisJob): WorkspaceReportDetail | null {
  const report = buildReportSummaryFromAnalysisJob(job);
  const result = job.result;
  if (!report || !result) {
    return null;
  }

  const overview = mergeAnalysisJobIntoOverview(clone(EMPTY_WORKSPACE), job);
  return {
    id: report.id,
    query: job.query,
    createdAt: job.created_at,
    updatedAt: job.updated_at,
    report,
    overview,
    recommendationValidated: result.user_payload.recommendation_gate?.validated ?? true,
  };
}

function buildStrategyReportSummaryFromAnalysisJob(job: AnalysisJob): StrategyReportSummary | null {
  const strategy = job.result?.strategy_spec;
  const report = buildReportSummaryFromAnalysisJob(job);
  if (!strategy || !report) {
    return null;
  }

  const riskSummary = Object.entries(strategy.risk_constraints)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(" · ");
  return {
    id: strategy.strategy_id,
    name: strategy.name,
    description: report.summary,
    timeframe: TIMEFRAME_LABELS[strategy.timeframe] ?? strategy.timeframe,
    entrySummary: describeConditions(strategy.entry_conditions),
    exitSummary: describeConditions(strategy.exit_conditions),
    riskSummary: riskSummary || "별도 리스크 제약 없음",
    latestSentAt: report.sentAt,
    latestReportDate: report.date,
    latestStatus: report.status,
    latestEmailReportId: report.id,
    recommendationScore: report.recommendationScore,
    signals: report.signals,
    summary: report.summary,
    tags: strategy.indicators,
  };
}

function buildReportDetailFromAnalysisJob(job: AnalysisJob): ReportDetail | null {
  const result = job.result;
  const report = result?.user_payload.report;
  const summary = buildReportSummaryFromAnalysisJob(job);
  if (!result || !report || !summary) {
    return null;
  }
  const performance = buildPerformanceSummaryFromAnalysisJob(job, EMPTY_PERFORMANCE);

  return {
    ...summary,
    recipient: null,
    marketBrief: result.user_payload.message,
    news: report.web_projection.sections.map((section, index) => ({
      rank: index + 1,
      title: stringFromRecord(section, "title") ?? "AI 분석 섹션",
      source: "QuantAgent AI",
      tone: toneForStatus(result.status),
    })),
    candidates: buildTradingCandidatesFromAnalysisJob(job),
    signalAxes: [],
    riskManagerOverride: report.risk_adjustments.length ? describeRiskAdjustments(report.risk_adjustments) : "Risk Manager 변경 없음",
    conclusion: report.web_projection.summary,
    performance: { metrics: performance.metrics, disclaimer: performance.disclaimer },
    costNotes: result.user_payload.next_actions,
  };
}

function buildTradingCandidatesFromAnalysisJob(job: AnalysisJob): TradingCandidate[] {
  const result = job.result;
  if (!result) {
    return [];
  }
  // These names came out of a DB screen, so what is known about each one is which rules it
  // matched. The strategy's single action and the candidate card's confidence describe the
  // strategy, not any one name, and stamping them onto each row read as a per-name verdict.
  // The strategy-level signal is still shown once, in the overview counters.
  const candidates = result.user_payload.candidate_cards.flatMap((card) =>
    (card.matches ?? []).map((match) => {
      const matchedRules = match.matched_rules ?? [];
      const rationale = matchedRules.length ? matchedRules.join(" · ") : card.reason ?? card.summary;
      return {
        id: match.ticker,
        ticker: match.ticker,
        name: match.name,
        sector: match.sector ?? card.sector ?? match.market,
        price: match.close == null ? "—" : `${new Intl.NumberFormat(APP_LOCALE).format(match.close)}원`,
        rationale,
        evidence: [
          {
            provider: "QuantAgent DB screening",
            title: card.title,
            date: match.as_of_date,
            summary: rationale,
          },
        ],
        riskReasons: [],
      } satisfies TradingCandidate;
    }),
  );
  return candidates.filter(
    (candidate, index, all) => all.findIndex((item) => item.ticker === candidate.ticker) === index,
  );
}

function buildPerformanceSummaryFromAnalysisJob(job: AnalysisJob, fallback: PerformanceSummary): PerformanceSummary {
  const aiPerformance = job.result?.user_payload.performance;
  const selectedMetrics = aiPerformance?.metrics ?? null;
  if (!aiPerformance || !selectedMetrics) {
    return job.result?.status === "ready"
      ? buildUnavailableAiPerformanceSummary(fallback, job.updated_at)
      : fallback;
  }

  const reliability = parseAIBacktestReliability(aiPerformance.reliability);
  const metricDetails = parseAIBacktestMetricDetails(aiPerformance.metric_details);
  const benchmark = parseAIBacktestBenchmark(aiPerformance.benchmark);
  const isInsufficient = reliability?.status === "insufficient";
  const benchmarkCurve = benchmark?.is_available ? benchmark.cumulative_curve : [];
  const equityCurve = isInsufficient
    ? []
    : buildAIEquityCurve(aiPerformance.equity_curve, benchmarkCurve);
  const metrics = isInsufficient
    ? []
    : metricDetails.length
      ? buildAIMetricCardsFromDetails(metricDetails)
      : buildAIMetricCards(selectedMetrics, aiPerformance.engine_summary);
  const comparison = isInsufficient
    ? []
    : buildAIComparisonRows(selectedMetrics, aiPerformance.engine_summary);

  return {
    ...fallback,
    headline: "AI 백테스트 결과",
    source: "ai",
    period: `후보 코드 백테스트 · ${aiPerformance.selected_candidate_id} 선택 · ${formatDateTime(job.updated_at)}`,
    benchmarkLabel: benchmark?.label || "벤치마크",
    metrics,
    equityCurve,
    comparison,
    reliability,
    dataQuality: parseStringList(aiPerformance.data_quality),
    benchmark: benchmark ?? undefined,
    metricDetails,
    strategyExplanation: aiPerformance.strategy_explanation ?? null,
    macroEvents: [],
    disclaimer: buildPerformanceDisclaimer(
      aiPerformance.selected_candidate_id,
      reliability,
      benchmark,
    ),
  };
}

function buildUnavailableAiPerformanceSummary(
  fallback: PerformanceSummary,
  completedAt: string,
): PerformanceSummary {
  return {
    ...fallback,
    source: "ai",
    headline: "AI 백테스트 결과 없음",
    period: `완료 시각 ${formatDateTime(completedAt)}`,
    benchmarkLabel: "벤치마크",
    metrics: [],
    equityCurve: [],
    comparison: [],
    reliability: null,
    dataQuality: [],
    benchmark: undefined,
    metricDetails: [],
    strategyExplanation: null,
    macroEvents: [],
    disclaimer: "완료된 AI 분석에 검증 가능한 성과 데이터가 포함되지 않았습니다.",
  };
}

function buildAIMetricCardsFromDetails(details: AIBacktestMetricDetail[]): BacktestMetric[] {
  return details
    .filter((detail) => detail.is_available && detail.value !== null && Number.isFinite(detail.value))
    .map((detail) => ({
      key: metricCardKey(detail.key),
      label: detail.label,
      value: detail.unit === "percent" ? formatPercent(detail.value as number) : formatDecimal(detail.value as number),
      tone: toneForPublicMetric(detail.key, detail.value as number),
      caption: detail.plain_explanation,
      plainExplanation: detail.plain_explanation,
      whyUsed: detail.why_used,
      caution: detail.caution,
      sourceRefs: detail.source_refs,
    }));
}

function buildAIMetricCards(selected: AIBacktestMetrics, engineSummary?: Record<string, unknown>): BacktestMetric[] {
  const tradeCount = numberFromRecord(engineSummary, "effective_trade_count") ?? numberFromRecord(engineSummary, "trade_count");
  const openPositions = numberFromRecord(engineSummary, "open_positions");
  return [
    {
      key: "sharpe",
      label: "Sharpe Ratio",
      value: formatDecimal(selected.sharpe_ratio),
      delta: tradeCount !== null ? `거래 ${formatDecimal(tradeCount, 0)}회` : undefined,
      tone: selected.sharpe_ratio >= 1 ? "positive" : selected.sharpe_ratio >= 0.5 ? "neutral" : "negative",
      caption: "AI 전략 검증에서 선택된 후보 기준입니다.",
    },
    {
      key: "mdd",
      label: "Max Drawdown",
      value: formatPercent(selected.max_drawdown),
      delta: openPositions !== null ? `오픈 포지션 ${formatDecimal(openPositions, 0)}` : undefined,
      tone: selected.max_drawdown >= -0.1 ? "positive" : selected.max_drawdown >= -0.2 ? "neutral" : "negative",
      caption: "누적 자산 곡선 기준 최대 낙폭입니다.",
    },
    {
      key: "winRate",
      label: "Win Rate",
      value: formatPercent(selected.win_rate),
      tone: selected.win_rate >= 0.5 ? "positive" : selected.win_rate >= 0.4 ? "neutral" : "negative",
      caption: "체결 거래 중 수익 거래 비율입니다.",
    },
    {
      key: "totalReturn",
      label: "Total Return",
      value: formatPercent(selected.total_return),
      delta: formatSignedPercentPoint(selected.total_return),
      tone: toneForMetricDelta(selected.total_return),
      caption: "거래비용 반영 후 검증 기간 누적 수익률입니다.",
    },
  ];
}

function buildAIComparisonRows(selected: AIBacktestMetrics, engineSummary?: Record<string, unknown>): PerformanceComparisonRow[] {
  const tradeCount = numberFromRecord(engineSummary, "effective_trade_count") ?? numberFromRecord(engineSummary, "trade_count");
  const closedTradeCount = numberFromRecord(engineSummary, "trade_count");
  const buySignalCount = numberFromRecord(engineSummary, "buy_signal_count");
  const signalCount = numberFromRecord(engineSummary, "signal_count");
  const openPositions = numberFromRecord(engineSummary, "open_positions");
  return [
    {
      metric: "Sharpe",
      value: formatDecimal(selected.sharpe_ratio),
      context: "리스크 대비 수익",
      assessment: selected.sharpe_ratio >= 1 ? "양호" : "개선 필요",
      tone: selected.sharpe_ratio >= 1 ? "positive" : selected.sharpe_ratio >= 0.5 ? "neutral" : "negative",
    },
    {
      metric: "MDD",
      value: formatPercent(selected.max_drawdown),
      context: "최대 낙폭",
      assessment: selected.max_drawdown >= -0.1 ? "방어 양호" : "리스크 확인",
      tone: selected.max_drawdown >= -0.1 ? "positive" : "negative",
    },
    {
      metric: "Entries",
      value: tradeCount !== null ? `${formatDecimal(tradeCount, 0)}회` : "-",
      context: [
        buySignalCount !== null ? `진입 ${formatDecimal(buySignalCount, 0)}건` : null,
        closedTradeCount !== null ? `청산 ${formatDecimal(closedTradeCount, 0)}건` : null,
        signalCount !== null ? `신호 ${formatDecimal(signalCount, 0)}건` : null,
      ].filter(Boolean).join(" · ") || "엔진 요약",
      assessment: tradeCount !== null && tradeCount > 0 ? "거래 발생" : "거래 부족",
      tone: tradeCount !== null && tradeCount > 0 ? "positive" : "neutral",
    },
    {
      metric: "Open Positions",
      value: openPositions !== null ? `${formatDecimal(openPositions, 0)}건` : "-",
      context: `누적 수익률 ${formatPercent(selected.total_return)}`,
      assessment: openPositions === 0 ? "청산 완료" : "보유 중",
      tone: toneForMetricDelta(selected.total_return),
    },
  ];
}

function buildAIEquityCurve(
  sourceCurve: AIBacktestEquityPoint[] = [],
  benchmarkCurve: AIBacktestEquityPoint[] = [],
): EquityPoint[] {
  if (!sourceCurve.length) {
    return [];
  }

  const benchmarkByDate = new Map(
    benchmarkCurve
      .filter((point) => Number.isFinite(point.cumulative_return))
      .map((point) => [point.date, ratioToPercent(point.cumulative_return)]),
  );
  return sourceCurve
    .filter((point) => Number.isFinite(point.cumulative_return))
    .map((point) => {
      const benchmarkValue = benchmarkByDate.get(point.date);
      return {
        date: formatEquityPointLabel(point.date),
        strategy: ratioToPercent(point.cumulative_return),
        ...(benchmarkValue === undefined ? {} : { benchmark: benchmarkValue }),
      };
    });
}

function parseAIBacktestReliability(
  reliability: AIBacktestPerformance["reliability"],
): AIBacktestReliability | null {
  if (!reliability) {
    return null;
  }
  return {
    ...reliability,
    reasons: parseStringList(reliability.reasons),
    warnings: parseStringList(reliability.warnings),
  };
}

function parseAIBacktestBenchmark(
  benchmark: AIBacktestPerformance["benchmark"],
): AIBacktestBenchmark | null {
  if (!benchmark) {
    return null;
  }
  const curve = benchmark.cumulative_curve.filter(
    (point) => typeof point.date === "string" && Number.isFinite(point.cumulative_return),
  );
  return {
    ...benchmark,
    total_return:
      benchmark.total_return !== null && Number.isFinite(benchmark.total_return)
        ? benchmark.total_return
        : null,
    cumulative_curve: curve,
    is_available: benchmark.is_available && curve.length > 0,
  };
}

function parseAIBacktestMetricDetails(
  details: AIBacktestPerformance["metric_details"],
): AIBacktestMetricDetail[] {
  if (!Array.isArray(details)) {
    return [];
  }
  return details
    .filter((detail) => typeof detail.key === "string" && detail.key.length > 0)
    .map((detail) => ({
      ...detail,
      value:
        detail.value !== null && Number.isFinite(detail.value)
          ? detail.value
          : null,
      source_refs: parseStringList(detail.source_refs),
    }));
}

function parseStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value
        .filter((item): item is string => typeof item === "string")
        .map((item) => item.trim())
        .filter(Boolean)
    : [];
}

function metricCardKey(key: string) {
  return {
    total_return: "totalReturn",
    sharpe_ratio: "sharpe",
    max_drawdown: "mdd",
    win_rate: "winRate",
  }[key] ?? key;
}

function toneForPublicMetric(key: string, value: number): Tone {
  if (key === "max_drawdown") {
    return value >= -0.1 ? "positive" : value >= -0.2 ? "neutral" : "negative";
  }
  if (key === "annualized_volatility" || key === "degradation") {
    return value <= 0.2 ? "positive" : value <= 0.35 ? "neutral" : "negative";
  }
  if (key === "win_rate") {
    return value >= 0.5 ? "positive" : value >= 0.4 ? "neutral" : "negative";
  }
  if (key.includes("sharpe") || key.includes("sortino") || key.includes("calmar")) {
    return value >= 1 ? "positive" : value >= 0.5 ? "neutral" : "negative";
  }
  return value > 0 ? "positive" : value < 0 ? "negative" : "neutral";
}

function buildPerformanceDisclaimer(
  candidateId: string,
  reliability: AIBacktestReliability | null,
  benchmark: AIBacktestBenchmark | null,
) {
  if (reliability?.status === "insufficient") {
    return `후보 ${candidateId}: 표본이 부족해 수익률과 지표를 공개하지 않습니다.`;
  }
  const reliabilityNote = reliability?.status === "limited"
    ? "제한된 표본이므로 결과를 참고용으로만 해석하세요."
    : "충분 조건을 충족한 표본입니다.";
  const benchmarkNote = benchmark?.is_available
    ? `벤치마크는 ${benchmark.method} 방식입니다.`
    : "사용 가능한 벤치마크 곡선이 없어 비교선을 표시하지 않습니다.";
  return `후보 ${candidateId}: ${reliabilityNote} ${benchmarkNote}`;
}

function extractFinalSignal(report: AIReportBundle) {
  const signalSection = report.web_projection.sections.find((section) => stringFromRecord(section, "id") === "signal");
  const items = signalSection?.items;
  if (isRecord(items) && isSignalType(items.action)) {
    return { action: items.action, confidence: numberFromRecord(items, "confidence") };
  }
  return null;
}

function signalCounts(signal: SignalType | null): Record<SignalType, number> {
  return {
    BUY: signal === "BUY" ? 1 : 0,
    HOLD: signal === "HOLD" ? 1 : 0,
    DROP: signal === "DROP" ? 1 : 0,
  };
}

function describeRiskAdjustments(adjustments: AIRiskAdjustment[]) {
  return adjustments.map((adjustment) => `${adjustment.before} → ${adjustment.after}: ${adjustment.reason}`).join("\n");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function stringFromRecord(record: Record<string, unknown>, key: string) {
  const value = record[key];
  return typeof value === "string" ? value : null;
}

function numberFromRecord(record: Record<string, unknown> | undefined, key: string) {
  if (!record) {
    return null;
  }
  const value = record[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function isSignalType(value: unknown): value is SignalType {
  return value === "BUY" || value === "HOLD" || value === "DROP";
}

function formatScore(confidence: number) {
  return `${formatScoreValue(confidence)} / ${SCORE_SCALE}`;
}

function ratioToPercent(value: number) {
  return Number((value * PERCENT_SCALE).toFixed(PERCENT_DISPLAY_DIGITS));
}

function formatPercent(value: number) {
  const percent = ratioToPercent(value);
  const prefix = percent > 0 ? "+" : "";
  return `${prefix}${percent.toFixed(PERCENT_DISPLAY_DIGITS)}%`;
}

function formatSignedPercentPoint(value: number) {
  const percent = ratioToPercent(value);
  const prefix = percent >= 0 ? "+" : "";
  return `${prefix}${percent.toFixed(PERCENT_DISPLAY_DIGITS)}%p`;
}

function formatDecimal(value: number, digits = DECIMAL_DISPLAY_DIGITS) {
  return value.toFixed(digits);
}

function formatSignedDecimal(value: number) {
  const prefix = value >= 0 ? "+" : "";
  return `${prefix}${value.toFixed(DECIMAL_DISPLAY_DIGITS)}`;
}

function toneForMetricDelta(value: number): Tone {
  if (value > 0) {
    return "positive";
  }
  if (value < 0) {
    return "negative";
  }
  return "neutral";
}

function formatEquityPointLabel(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  // Backtest windows routinely cross a year boundary, and a month/day label cannot say
  // whether 11.03 precedes or follows 07.24 - nor which year the run covered at all.
  return new Intl.DateTimeFormat(APP_LOCALE, {
    year: "2-digit",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function formatStatusDelta(status: AIEnvelopeStatus) {
  return status === "ready" ? "AI 완료" : formatEnvelopeStatus(status);
}

function formatEnvelopeStatus(status: AIEnvelopeStatus | "running") {
  const labels: Record<AIEnvelopeStatus | "running", string> = {
    ready: "완료",
    need_clarification: "추가 확인",
    rejected: "거절",
    failed: "실패",
    running: "진행 중",
  };
  return labels[status];
}

function toneForStatus(status: AIEnvelopeStatus): Tone {
  if (status === "ready") {
    return "positive";
  }
  if (status === "failed" || status === "rejected") {
    return "negative";
  }
  return "warning";
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(APP_LOCALE, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatReportDate(date: Date) {
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}.${month}.${day}`;
}

function formatWeekday(date: Date) {
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat(APP_LOCALE, { weekday: "short" }).format(date);
}

export function confidenceToPercent(confidence: number) {
  return `${Math.round(confidence * PERCENT_SCALE)}%`;
}
