import { AI_ENDPOINTS, appConfig } from "../config/appConfig";
import { appOverview, analysisJobStatus, performanceSummary, tradingCandidates } from "../mocks/app.mock";
import { landingSample } from "../mocks/landing.mock";
import { reportDetails, reportSummaries } from "../mocks/reports.mock";
import type {
  ABComparisonRow,
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
const PERCENT_DISPLAY_DIGITS = 2;
const DECIMAL_DISPLAY_DIGITS = 2;
const BASELINE_RETURN_PERCENT = 0;
const STORAGE_KEY_LATEST_ANALYSIS_JOB = "quantagent.latest-analysis-job.v1";
const AI_REPORT_ID_PREFIX = "ai-job:";
const VARIANT_LABELS: Record<"A" | "B", string> = {
  A: "원본 전략",
  B: "AI 개선본",
};
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
  return respond(landingSample);
}

export async function getAppOverview(): Promise<AppOverview> {
  const overview = await respond({ ...appOverview, recentReports: reportSummaries.slice(0, RECENT_REPORT_LIMIT) });
  const latestJob = await refreshLatestAnalysisJob();
  return latestJob ? mergeAnalysisJobIntoOverview(overview, latestJob) : overview;
}

export function getWorkspaceTemplate(): Promise<AppOverview> {
  return respond({
    ...appOverview,
    chatMessages: [],
    recentReports: [],
  });
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
  const fallback = reportDetails[0];
  if (!result || !report || !summary || !fallback) {
    return null;
  }
  const performance = buildPerformanceSummaryFromAnalysisJob(job, performanceSummary);

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
    performance: { metrics: performance.metrics, disclaimer: performance.disclaimer },
    costNotes: result.user_payload.next_actions,
  };
}

function buildPerformanceSummaryFromAnalysisJob(job: AnalysisJob, fallback: PerformanceSummary): PerformanceSummary {
  const aiPerformance = job.result?.user_payload.performance;
  const selectedMetrics = aiPerformance ? metricsForSelectedVariant(aiPerformance) : null;
  if (!aiPerformance || !selectedMetrics) {
    return fallback;
  }

  const selectedLabel = VARIANT_LABELS[aiPerformance.selected_variant];
  const equityCurve = buildAIEquityCurve(aiPerformance);
  const comparison = buildAIComparisonRows(aiPerformance.metrics_by_variant.A, aiPerformance.metrics_by_variant.B);

  return {
    ...fallback,
    headline: "AI 전략 검증 결과",
    period: `BacktestCode Loop3 · ${selectedLabel} 선택 · ${formatDateTime(job.updated_at)}`,
    benchmarkLabel: "검증 기준선",
    metrics: buildAIMetricCards(selectedMetrics, aiPerformance),
    equityCurve: equityCurve.length ? equityCurve : fallback.equityCurve,
    comparison: comparison.length ? comparison : fallback.comparison,
    disclaimer:
      `내 전략/원본 전략은 AI 백테스트 엔진 산출값입니다. 선택 후보 ${aiPerformance.selected_candidate_id}, ` +
      "벤치마크 데이터가 없는 검증 응답은 0% 기준선과 함께 표시합니다.",
  };
}

function metricsForSelectedVariant(performance: AIBacktestPerformance): AIBacktestMetrics | null {
  return performance.metrics_by_variant[performance.selected_variant] ?? null;
}

function buildAIMetricCards(selected: AIBacktestMetrics, performance: AIBacktestPerformance): BacktestMetric[] {
  const counterpartVariant = performance.selected_variant === "A" ? "B" : "A";
  const counterpart = performance.metrics_by_variant[counterpartVariant];
  const counterpartLabel = VARIANT_LABELS[counterpartVariant];

  return [
    {
      key: "sharpe",
      label: "Sharpe Ratio",
      value: formatDecimal(selected.sharpe_ratio),
      delta: counterpart ? `${counterpartLabel} ${formatDecimal(counterpart.sharpe_ratio)}` : undefined,
      tone: counterpart ? toneForMetricDelta(selected.sharpe_ratio - counterpart.sharpe_ratio) : "neutral",
      caption: "AI 전략 검증에서 선택된 후보 기준입니다.",
    },
    {
      key: "mdd",
      label: "Max Drawdown",
      value: formatPercent(selected.max_drawdown),
      delta: counterpart ? `${counterpartLabel} ${formatPercent(counterpart.max_drawdown)}` : undefined,
      tone: counterpart ? toneForMetricDelta(selected.max_drawdown - counterpart.max_drawdown) : "neutral",
      caption: "누적 자산 곡선 기준 최대 낙폭입니다.",
    },
    {
      key: "winRate",
      label: "Win Rate",
      value: formatPercent(selected.win_rate),
      delta: counterpart ? formatSignedPercentPoint(selected.win_rate - counterpart.win_rate) : undefined,
      tone: counterpart ? toneForMetricDelta(selected.win_rate - counterpart.win_rate) : "neutral",
      caption: "체결 거래 중 수익 거래 비율입니다.",
    },
    {
      key: "totalReturn",
      label: "Total Return",
      value: formatPercent(selected.total_return),
      delta: counterpart ? formatSignedPercentPoint(selected.total_return - counterpart.total_return) : undefined,
      tone: counterpart ? toneForMetricDelta(selected.total_return - counterpart.total_return) : "neutral",
      caption: "거래비용 반영 후 검증 기간 누적 수익률입니다.",
    },
  ];
}

function buildAIComparisonRows(original: AIBacktestMetrics | undefined, improved: AIBacktestMetrics | undefined): ABComparisonRow[] {
  if (!original || !improved) {
    return [];
  }

  return [
    {
      metric: "Sharpe",
      original: formatDecimal(original.sharpe_ratio),
      improved: formatDecimal(improved.sharpe_ratio),
      delta: formatSignedDecimal(improved.sharpe_ratio - original.sharpe_ratio),
      tone: toneForMetricDelta(improved.sharpe_ratio - original.sharpe_ratio),
    },
    {
      metric: "MDD",
      original: formatPercent(original.max_drawdown),
      improved: formatPercent(improved.max_drawdown),
      delta: formatSignedPercentPoint(improved.max_drawdown - original.max_drawdown),
      tone: toneForMetricDelta(improved.max_drawdown - original.max_drawdown),
    },
    {
      metric: "Win Rate",
      original: formatPercent(original.win_rate),
      improved: formatPercent(improved.win_rate),
      delta: formatSignedPercentPoint(improved.win_rate - original.win_rate),
      tone: toneForMetricDelta(improved.win_rate - original.win_rate),
    },
    {
      metric: "Total Return",
      original: formatPercent(original.total_return),
      improved: formatPercent(improved.total_return),
      delta: formatSignedPercentPoint(improved.total_return - original.total_return),
      tone: toneForMetricDelta(improved.total_return - original.total_return),
    },
  ];
}

function buildAIEquityCurve(performance: AIBacktestPerformance): EquityPoint[] {
  const selectedCurve = performance.equity_curve_by_variant[performance.selected_variant] ?? [];
  const originalCurve = performance.equity_curve_by_variant.A ?? [];
  const sourceCurve = selectedCurve.length ? selectedCurve : originalCurve;
  if (!sourceCurve.length) {
    return [];
  }

  const originalByDate = new Map(originalCurve.map((point) => [point.date, point]));
  return sourceCurve.map((point, index) => {
    const originalPoint = originalByDate.get(point.date) ?? originalCurve[index] ?? point;
    return {
      date: formatEquityPointLabel(point.date),
      strategy: ratioToPercent(point.cumulative_return),
      original: ratioToPercent(originalPoint.cumulative_return),
      benchmark: BASELINE_RETURN_PERCENT,
    };
  });
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

function formatDecimal(value: number) {
  return value.toFixed(DECIMAL_DISPLAY_DIGITS);
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
  return new Intl.DateTimeFormat(APP_LOCALE, {
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
