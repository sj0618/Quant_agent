import { AI_ENDPOINTS, appConfig } from "../config/appConfig";
import { appOverview, analysisJobStatus, performanceSummary, tradingCandidates } from "../mocks/app.mock";
import { landingSample } from "../mocks/landing.mock";
import { reportDetails, reportSummaries } from "../mocks/reports.mock";
import type {
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
  ChatMessage,
  LandingSample,
  PerformanceSummary,
  ReportDetail,
  ReportSummary,
  SignalType,
  StageStatus,
  StrategySpec,
  Tone,
  TradingCandidate,
} from "../types/quantagent";

const APP_LOCALE = "ko-KR";
const MOCK_LATENCY_MS = 120;
const RECENT_REPORT_LIMIT = 4;
const SCORE_SCALE = 10;
const PERCENT_SCALE = 100;
const TRACE_PREVIEW_LENGTH = 8;
const STORAGE_KEY_LATEST_ANALYSIS_JOB = "quantagent.latest-analysis-job.v1";
const AI_REPORT_ID_PREFIX = "ai-job:";
const TIMEFRAME_LABELS: Record<string, string> = {
  daily: "매일 분석",
  weekly: "매주 분석",
  monthly: "매월 분석",
};
const STAGE_LABELS: Record<AIJobStage, string> = {
  interpreting: "전략 해석",
  code_generation: "코드 후보 생성",
  backtest: "백테스트",
  debate: "신호·리스크 검토",
  finalizing: "리포트 생성",
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

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

async function respond<T>(value: T): Promise<T> {
  await new Promise((resolve) => window.setTimeout(resolve, MOCK_LATENCY_MS));
  return clone(value);
}

function requireAiApiBaseUrl() {
  if (!appConfig.aiApiBaseUrl) {
    throw new Error("VITE_AI_API_BASE_URL 설정이 필요합니다.");
  }
  return appConfig.aiApiBaseUrl;
}

function assertOk(response: Response) {
  if (!response.ok) {
    throw new Error(`AI 서버 응답 실패: ${response.status}`);
  }
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

export function getLatestAnalysisJob(): AnalysisJob | null {
  return readLatestAnalysisJob();
}

export async function createAnalysisJob(query: string): Promise<AnalysisJob> {
  const trimmedQuery = query.trim();
  if (!trimmedQuery) {
    throw new Error("분석할 자연어 전략을 입력하세요.");
  }

  const response = await fetch(`${requireAiApiBaseUrl()}${AI_ENDPOINTS.analysisJobs}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: trimmedQuery }),
  });
  assertOk(response);

  const job = (await response.json()) as AnalysisJob;
  saveLatestAnalysisJob(job);
  return job;
}

export async function getAnalysisJob(jobId: string): Promise<AnalysisJob> {
  const response = await fetch(`${requireAiApiBaseUrl()}${AI_ENDPOINTS.analysisJob(jobId)}`, {
    credentials: "include",
  });
  assertOk(response);

  const job = (await response.json()) as AnalysisJob;
  saveLatestAnalysisJob(job);
  return job;
}

export async function refreshLatestAnalysisJob(): Promise<AnalysisJob | null> {
  const storedJob = readLatestAnalysisJob();
  if (!storedJob) {
    return null;
  }
  if (!appConfig.aiApiBaseUrl) {
    return storedJob;
  }

  try {
    return await getAnalysisJob(storedJob.job_id);
  } catch (error) {
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

  return {
    ...base,
    strategy,
    recommendationScore: result?.strategy_spec ? formatScore(result.strategy_spec.confidence) : base.recommendationScore,
    recommendationDelta: result ? formatStatusDelta(result.status) : base.recommendationDelta,
    latestRunLabel: `최신 분석 · ${formatDateTime(job.updated_at)}`,
    chatMessages: buildAnalysisChatMessages(job),
    recentReports,
    envelope: result ?? base.envelope,
    jobStatus: buildWorkspaceJobStatus(job),
  };
}

export function getLandingSample(): Promise<LandingSample> {
  return respond(landingSample);
}

export async function getAppOverview(): Promise<AppOverview> {
  const overview = await respond({ ...appOverview, recentReports: reportSummaries.slice(0, RECENT_REPORT_LIMIT) });
  const latestJob = await refreshLatestAnalysisJob();
  return latestJob ? mergeAnalysisJobIntoOverview(overview, latestJob) : overview;
}

export function getTradingCandidates(): Promise<TradingCandidate[]> {
  return respond(tradingCandidates);
}

export function getPerformanceSummary(): Promise<PerformanceSummary> {
  return respond(performanceSummary);
}

export async function getReports(): Promise<ReportSummary[]> {
  const reports = await respond(reportSummaries);
  const latestJob = await refreshLatestAnalysisJob();
  const latestReport = latestJob ? buildReportSummaryFromAnalysisJob(latestJob) : null;
  return latestReport ? [latestReport, ...reports.filter((report) => report.id !== latestReport.id)] : reports;
}

export async function getReportById(id: string): Promise<ReportDetail | null> {
  const latestJob = await refreshLatestAnalysisJob();
  if (latestJob && id === latestAnalysisReportId(latestJob.job_id)) {
    return buildReportDetailFromAnalysisJob(latestJob);
  }

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

export async function getAnalysisJobStatus(): Promise<AnalysisJobStatus> {
  const latestJob = await refreshLatestAnalysisJob();
  return latestJob ? buildWorkspaceJobStatus(latestJob) : respond(analysisJobStatus);
}

function mapAIStrategySpec(strategy: AIStrategySpec, query: string): StrategySpec {
  const riskConstraints = Object.entries(strategy.risk_constraints).map(([key, value]) => `${key}: ${String(value)}`);
  return {
    name: strategy.name,
    natural_language_strategy: query,
    universe: formatUniverse(strategy),
    sector: strategy.indicators.length ? strategy.indicators.join(", ") : strategy.market,
    buy_condition: describeConditions(strategy.entry_conditions),
    hold_condition: strategy.timeframe,
    drop_condition: describeConditions(strategy.exit_conditions),
    rebalance: TIMEFRAME_LABELS[strategy.timeframe] ?? strategy.timeframe,
    constraints: [...riskConstraints, ...strategy.assumptions],
  };
}

function formatUniverse(strategy: AIStrategySpec) {
  return strategy.market ? `${strategy.market} · ${strategy.universe}` : strategy.universe;
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
  const candidateCount = payload?.candidate_cards.length ?? 0;

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
    },
  ];
}

function buildReportSummaryFromAnalysisJob(job: AnalysisJob): ReportSummary | null {
  const result = job.result;
  const report = result?.user_payload.report;
  if (!result || !report) {
    return null;
  }

  const action = extractSignalAction(report);
  const date = new Date(job.updated_at);
  return {
    id: latestAnalysisReportId(job.job_id),
    date: formatReportDate(date),
    weekday: formatWeekday(date),
    sentAt: formatDateTime(job.updated_at),
    title: report.web_projection.title,
    summary: report.web_projection.summary,
    status: result.status === "failed" ? "failed" : "draft",
    strategyName: result.strategy_spec?.name ?? result.user_payload.headline,
    recommendationScore: result.strategy_spec ? formatScore(result.strategy_spec.confidence) : formatEnvelopeStatus(result.status),
    signals: signalCounts(action),
    marketSnapshot: [
      { label: "AI 상태", value: formatEnvelopeStatus(result.status), tone: toneForStatus(result.status) },
      { label: "Trace", value: result.trace_id.slice(0, TRACE_PREVIEW_LENGTH), tone: "neutral" },
    ],
  };
}

function buildReportDetailFromAnalysisJob(job: AnalysisJob): ReportDetail | null {
  const result = job.result;
  const report = result?.user_payload.report;
  const summary = buildReportSummaryFromAnalysisJob(job);
  const fallback = reportDetails[0];
  if (!result || !report || !summary || !fallback) {
    return null;
  }

  return {
    ...summary,
    recipient: fallback.recipient,
    marketBrief: result.user_payload.message,
    news: report.web_projection.sections.map((section, index) => ({
      rank: index + 1,
      title: stringFromRecord(section, "title") ?? "AI 분석 섹션",
      source: "QuantAgent AI",
      tone: toneForStatus(result.status),
    })),
    candidates: fallback.candidates,
    signalAxes: fallback.signalAxes,
    riskManagerOverride: report.risk_adjustments.length ? describeRiskAdjustments(report.risk_adjustments) : "Risk Manager 변경 없음",
    conclusion: report.web_projection.summary,
    performance: fallback.performance,
    costNotes: result.user_payload.next_actions,
  };
}

function extractSignalAction(report: AIReportBundle): SignalType | null {
  const signalSection = report.web_projection.sections.find((section) => stringFromRecord(section, "id") === "signal");
  const items = signalSection?.items;
  if (isRecord(items) && isSignalType(items.action)) {
    return items.action;
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

function isSignalType(value: unknown): value is SignalType {
  return value === "BUY" || value === "HOLD" || value === "DROP";
}

function formatScore(confidence: number) {
  const normalized = Math.round(confidence * SCORE_SCALE * SCORE_SCALE) / SCORE_SCALE;
  return `${normalized.toFixed(1)} / ${SCORE_SCALE}`;
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
