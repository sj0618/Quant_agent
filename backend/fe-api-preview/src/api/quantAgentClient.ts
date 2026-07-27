import { AI_ENDPOINTS, appConfig } from "../config/appConfig";
import { fetchServerJson, recordDataSource } from "./dataSourceClient";
import { performanceSummary } from "../mocks/app.mock";
import { reportDetails } from "../mocks/reports.mock";
import type {
  AIBacktestMetrics,
  AIBacktestPerformance,
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
  StrategySpec,
  Tone,
  TradingCandidate,
} from "../types/quantagent";

const APP_LOCALE = "ko-KR";
const RECENT_REPORT_LIMIT = 4;
const SCORE_SCALE = 10;
const PERCENT_SCALE = 100;
const TRACE_PREVIEW_LENGTH = 8;
const PERCENT_DISPLAY_DIGITS = 2;
const DECIMAL_DISPLAY_DIGITS = 2;
const BASELINE_RETURN_PERCENT = 0;
const AI_REQUEST_TIMEOUT_MS = 45_000;
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

async function fetchAI(path: string, init: RequestInit = {}) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), AI_REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${requireAiApiBaseUrl()}${path}`, {
      ...init,
      credentials: init.credentials ?? "include",
      signal: controller.signal,
    });
    recordDataSource({ key: "analysisJob", path, source: "server", status: response.status });
    return response;
  } catch (error) {
    recordDataSource({
      key: "analysisJob",
      path,
      source: "server",
      message: error instanceof Error ? error.message : "AI server fetch failed",
    });
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("AI 분석 요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
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

  const response = await fetchAI(AI_ENDPOINTS.analysisJobs, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: trimmedQuery }),
  });
  assertOk(response);

  const job = (await response.json()) as AnalysisJob;
  saveLatestAnalysisJob(job);
  return job;
}

export async function getAnalysisJob(jobId: string): Promise<AnalysisJob> {
  const response = await fetchAI(AI_ENDPOINTS.analysisJob(jobId));
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
  return getAnalysisJob(storedJob.job_id);
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

  return {
    ...base,
    strategy,
    recommendationScore: result?.strategy_spec ? formatScore(result.strategy_spec.confidence) : base.recommendationScore,
    recommendationDelta: result ? formatStatusDelta(result.status) : base.recommendationDelta,
    latestRunLabel: `최신 분석 · ${formatDateTime(job.updated_at)}`,
    chatMessages: mergeChatMessages(base.chatMessages, buildAnalysisChatMessages(job)),
    performance,
    recentReports,
    envelope: result ?? base.envelope,
    jobStatus: buildWorkspaceJobStatus(job),
  };
}

export function getLandingSample(): Promise<LandingSample> {
  return fetchServerJson<LandingSample>({
    key: "landingSample",
    path: "/landing-sample",
  });
}

export async function getAppOverview(): Promise<AppOverview> {
  const overview = await fetchServerJson<AppOverview>({
    key: "appOverview",
    path: "/app/overview",
  });
  const latestJob = await refreshLatestAnalysisJob();
  return latestJob ? mergeAnalysisJobIntoOverview(overview, latestJob) : overview;
}

export function getWorkspaceTemplate(): Promise<AppOverview> {
  return fetchServerJson<AppOverview>({
    key: "workspaceTemplate",
    path: "/workspace/template",
  });
}

export function getTradingCandidates(): Promise<TradingCandidate[]> {
  return fetchServerJson<TradingCandidate[]>({
    key: "tradingCandidates",
    path: "/trading-candidates",
  });
}

export function getPerformanceSummary(): Promise<PerformanceSummary> {
  return fetchServerJson<PerformanceSummary>({
    key: "performanceSummary",
    path: "/performance/summary",
  });
}

export async function getReports(): Promise<ReportSummary[]> {
  const reports = await fetchServerJson<ReportSummary[]>({
    key: "reportSummaries",
    path: "/reports",
  });
  const latestJob = await refreshLatestAnalysisJob();
  const latestReport = latestJob ? buildReportSummaryFromAnalysisJob(latestJob) : null;
  return latestReport ? [latestReport, ...reports.filter((report) => report.id !== latestReport.id)] : reports;
}

export async function getReportById(id: string): Promise<ReportDetail | null> {
  const latestJob = await refreshLatestAnalysisJob();
  if (latestJob && id === latestAnalysisReportId(latestJob.job_id)) {
    return buildReportDetailFromAnalysisJob(latestJob);
  }

  return fetchServerJson<ReportDetail | null>({
    key: "reportDetail",
    path: `/reports/${encodeURIComponent(id)}`,
  });
}

export async function getAnalysisJobStatus(): Promise<AnalysisJobStatus> {
  const latestJob = await refreshLatestAnalysisJob();
  return latestJob
    ? buildWorkspaceJobStatus(latestJob)
    : fetchServerJson<AnalysisJobStatus>({
        key: "analysisJobStatus",
        path: "/analysis-jobs/latest/status",
      });
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
  const baselineReport = reportDetails[0];
  if (!result || !report || !summary || !baselineReport) {
    return null;
  }
  const performance = buildPerformanceSummaryFromAnalysisJob(job, performanceSummary);

  return {
    ...summary,
    recipient: baselineReport.recipient,
    marketBrief: result.user_payload.message,
    news: report.web_projection.sections.map((section, index) => ({
      rank: index + 1,
      title: stringFromRecord(section, "title") ?? "AI 분석 섹션",
      source: "QuantAgent AI",
      tone: toneForStatus(result.status),
    })),
    candidates: baselineReport.candidates,
    signalAxes: baselineReport.signalAxes,
    riskManagerOverride: report.risk_adjustments.length ? describeRiskAdjustments(report.risk_adjustments) : "Risk Manager 변경 없음",
    conclusion: report.web_projection.summary,
    performance: { metrics: performance.metrics, disclaimer: performance.disclaimer },
    costNotes: result.user_payload.next_actions,
  };
}

function buildPerformanceSummaryFromAnalysisJob(job: AnalysisJob, baseline: PerformanceSummary): PerformanceSummary {
  const aiPerformance = job.result?.user_payload.performance;
  const selectedMetrics = aiPerformance?.metrics ?? null;
  if (!aiPerformance || !selectedMetrics) {
    return baseline;
  }

  const equityCurve = buildAIEquityCurve(aiPerformance);
  const comparison = buildAIComparisonRows(selectedMetrics, aiPerformance.engine_summary);

  return {
    ...baseline,
    headline: "AI 전략 검증 결과",
    period: `후보 코드 백테스트 · ${aiPerformance.selected_candidate_id} 선택 · ${formatDateTime(job.updated_at)}`,
    benchmarkLabel: "검증 기준선",
    metrics: buildAIMetricCards(selectedMetrics, aiPerformance.engine_summary),
    equityCurve: equityCurve.length ? equityCurve : baseline.equityCurve,
    comparison: comparison.length ? comparison : baseline.comparison,
    disclaimer:
      `AI 백테스트 엔진이 후보 코드 중 ${aiPerformance.selected_candidate_id}를 선택했습니다. ` +
      "벤치마크 데이터가 없는 검증 응답은 0% 기준선과 함께 표시합니다.",
  };
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

function buildAIEquityCurve(performance: AIBacktestPerformance): EquityPoint[] {
  const sourceCurve = performance.equity_curve ?? [];
  if (!sourceCurve.length) {
    return [];
  }

  return sourceCurve.map((point) => ({
    date: formatEquityPointLabel(point.date),
    strategy: ratioToPercent(point.cumulative_return),
    original: BASELINE_RETURN_PERCENT,
    benchmark: BASELINE_RETURN_PERCENT,
  }));
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
  const normalized = Math.round(confidence * SCORE_SCALE * SCORE_SCALE) / SCORE_SCALE;
  return `${normalized.toFixed(1)} / ${SCORE_SCALE}`;
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
