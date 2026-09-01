import type {
  AICondition,
  AIEnvelopeStatus,
  AIJobStage,
  AIJobStageStatus,
  AIUserPayload,
  AnalysisJob,
  AnalysisStage,
  AppOverview,
  BacktestMetric,
  ChatMessage,
  PerformanceSummary,
  SignalType,
  StageStatus,
  StrategySpec,
  Tone,
  TradingCandidate,
} from "../../types/quantagent";

const STAGE_LABELS: Record<AIJobStage, string> = {
  interpreting: "전략 해석 중",
  code_generation: "전략 규칙을 준비하는 중",
  backtest: "실데이터 백테스트 실행 중",
  debate: "결과와 한계를 검토하는 중",
  finalizing: "자연어 리포트를 정리하는 중",
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
  period: "자연어 전략을 입력하면 실데이터 준비 상태를 확인한 뒤 백테스트를 시작합니다.",
  metrics: [],
  equityCurve: [],
  comparison: [],
  macroEvents: [],
  disclaimer: "분석 전에는 성과 수치나 종목 신호를 표시하지 않습니다.",
};

export const EMPTY_WORKSPACE: AppOverview = {
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
  nextRunLabel: "실행 요청 후 상태를 확인합니다",
  latestRunLabel: "분석 전",
  chatMessages: [],
  candidates: [],
  performance: EMPTY_PERFORMANCE,
  recentReports: [],
  envelope: null,
  jobStatus: null,
};

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
}

function describeConditions(conditions: AICondition[]): string {
  if (!conditions.length) {
    return "조건이 명시되지 않았습니다";
  }
  return conditions.map((condition) => condition.description ?? `${condition.left} ${condition.operator} ${String(condition.right)}`).join(" · ");
}

function strategyFromJob(job: AnalysisJob): StrategySpec {
  const strategy = job.result?.strategy_spec;
  if (!strategy) {
    return { ...EMPTY_WORKSPACE.strategy, natural_language_strategy: job.query };
  }
  return {
    name: strategy.name,
    natural_language_strategy: job.query,
    sector: strategy.indicators.join(", ") || strategy.market,
    buy_condition: describeConditions(strategy.entry_conditions),
    hold_condition: strategy.timeframe,
    drop_condition: describeConditions(strategy.exit_conditions),
    rebalance: strategy.timeframe,
    constraints: [...strategy.assumptions, ...Object.entries(strategy.risk_constraints).map(([key, value]) => `${key}: ${String(value)}`)],
  };
}

function resultStatusLabel(status: AIEnvelopeStatus | "running"): string {
  return {
    ready: "완료",
    need_clarification: "추가 확인 필요",
    rejected: "실행 불가",
    failed: "실패",
    running: "진행 중",
  }[status];
}

function messagesFromJob(job: AnalysisJob): ChatMessage[] {
  const payload = job.result?.user_payload;
  const status = job.result?.status ?? "running";
  return [
    {
      id: `${job.job_id}:user`,
      sender: "user",
      label: "나",
      time: formatDateTime(job.created_at),
      body: job.query,
    },
    {
      id: `${job.job_id}:system`,
      sender: "system",
      label: "ANALYSIS",
      time: formatDateTime(job.updated_at),
      body: payload?.message ?? "서버가 전략 분석을 진행하고 있습니다.",
      stats: [{ label: "상태", value: resultStatusLabel(status) }],
      clarification: payload?.question && payload.options?.length
        ? { question: payload.question, options: payload.options, recommended: payload.recommended }
        : undefined,
      candidateCards: status === "need_clarification" ? payload?.candidate_cards : undefined,
    },
  ];
}

function metricTone(key: string, value: number): Tone {
  if (key === "max_drawdown") return value >= -0.1 ? "positive" : value >= -0.2 ? "warning" : "negative";
  if (key.includes("sharpe") || key.includes("sortino")) return value >= 1 ? "positive" : value >= 0.5 ? "warning" : "negative";
  return value > 0 ? "positive" : value < 0 ? "negative" : "neutral";
}

function formatMetric(value: number, unit: string): string {
  if (unit === "percent") {
    return `${value > 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
  }
  return value.toFixed(2);
}

function publicPerformanceSummary(payload: AIUserPayload): PerformanceSummary {
  const publicPerformance = payload.performance;
  if (!publicPerformance || publicPerformance.availability === "unavailable") {
    const reason = publicPerformance?.reason_code ?? "performance_not_available";
    return {
      ...EMPTY_PERFORMANCE,
      headline: "백테스트 결과를 표시할 수 없습니다",
      period: "현재 실행은 검증 가능한 성과 조건을 충족하지 못했습니다.",
      disclaimer: `성과 수치와 차트는 표시하지 않습니다. 사유: ${reason}`,
    };
  }

  const performance = publicPerformance.performance;
  const reliability = performance.reliability ?? null;
  const isRealData = reliability?.source === "postgres";
  if (!isRealData || reliability?.status === "insufficient") {
    return {
      ...EMPTY_PERFORMANCE,
      headline: "백테스트 결과를 표시할 수 없습니다",
      period: "실데이터 출처 또는 최소 표본 요건을 확인하지 못했습니다.",
      reliability,
      disclaimer: "fixture·출처 미확인·표본 부족 결과는 성과 수치와 차트로 대체하지 않습니다.",
    };
  }

  const metrics: BacktestMetric[] = (performance.metric_details ?? [])
    .filter((detail) => detail.is_available && detail.value !== null && Number.isFinite(detail.value))
    .map((detail) => ({
      key: detail.key === "total_return" ? "totalReturn" : detail.key === "sharpe_ratio" ? "sharpe" : detail.key === "max_drawdown" ? "mdd" : detail.key,
      label: detail.label,
      value: formatMetric(detail.value as number, detail.unit),
      tone: metricTone(detail.key, detail.value as number),
      caption: detail.plain_explanation,
      plainExplanation: detail.plain_explanation,
      whyUsed: detail.why_used,
      caution: detail.caution,
      sourceRefs: detail.source_refs,
      source: "postgres",
      availability: "available",
    }));
  const benchmark = performance.benchmark ?? undefined;
  const benchmarkByDate = new Map((benchmark?.cumulative_curve ?? []).map((point) => [point.date, point.cumulative_return * 100]));
  return {
    headline: "실데이터 백테스트 결과",
    source: "ai",
    period: `${formatDate(publicPerformance.method_manifest.start_date)} ~ ${formatDate(publicPerformance.method_manifest.end_date)} · ${publicPerformance.method_manifest.data_version}`,
    benchmarkLabel: benchmark?.label,
    metrics,
    equityCurve: performance.equity_curve
      .filter((point) => Number.isFinite(point.cumulative_return))
      .map((point) => ({ date: point.date, strategy: point.cumulative_return * 100, benchmark: benchmarkByDate.get(point.date) })),
    comparison: [],
    macroEvents: [],
    reliability,
    dataQuality: performance.data_quality ?? [],
    benchmark,
    metricDetails: performance.metric_details ?? [],
    strategyExplanation: performance.strategy_explanation ?? null,
    evaluationBasis: performance.evaluation_basis ?? null,
    universePolicy: performance.universe_policy ?? null,
    disclaimer: [publicPerformance.method_manifest.historical_simulation_warning, ...publicPerformance.limitations].filter(Boolean).join(" "),
  };
}

function actionSignal(action: "BUY" | "SELL" | "HOLD" | "WATCH"): SignalType | undefined {
  return action === "BUY" ? "BUY" : action === "SELL" ? "DROP" : action === "HOLD" ? "HOLD" : undefined;
}

function candidatesFromJob(job: AnalysisJob, performance: PerformanceSummary): TradingCandidate[] {
  const payload = job.result?.user_payload;
  if (!payload || performance.metrics.length === 0) {
    return [];
  }
  const actions = new Map((payload.ticker_actions ?? []).map((action) => [action.ticker, action]));
  return payload.candidate_cards.flatMap((card) => card.matches.map((match) => {
    const action = actions.get(match.ticker);
    const rationale = action?.reason ?? card.reason ?? card.summary;
    return {
      id: match.ticker,
      ticker: match.ticker,
      name: match.name,
      sector: match.sector ?? match.market,
      signal: action ? actionSignal(action.action) : undefined,
      price: match.close === null || match.close === undefined ? "—" : `${match.close.toLocaleString("ko-KR")}원`,
      rationale,
      evidence: [{ provider: "PostgreSQL EOD", title: card.title, date: match.as_of_date, summary: rationale }],
      riskReasons: [],
    } satisfies TradingCandidate;
  }));
}

export function workspaceOverviewFromJob(job: AnalysisJob): AppOverview {
  const result = job.result;
  const payload = result?.user_payload;
  const performance = payload ? publicPerformanceSummary(payload) : EMPTY_PERFORMANCE;
  const candidates = candidatesFromJob(job, performance);
  const actions = performance.metrics.length ? payload?.ticker_actions ?? [] : [];
  const signalCounts = { BUY: 0, HOLD: 0, DROP: 0 };
  for (const action of actions) {
    const signal = actionSignal(action.action);
    if (signal) signalCounts[signal] += 1;
  }
  const report = payload?.report;
  const exploration = report?.base_report_v2;
  return {
    ...EMPTY_WORKSPACE,
    strategy: strategyFromJob(job),
    recommendationScore: exploration ? "연구" : result?.strategy_spec ? `${Math.round(result.strategy_spec.confidence * 100)}%` : "—",
    recommendationDelta: result ? resultStatusLabel(result.status) : "진행 중",
    passCount: signalCounts.BUY + signalCounts.HOLD + signalCounts.DROP,
    buyCount: signalCounts.BUY,
    holdCount: signalCounts.HOLD,
    dropCount: signalCounts.DROP,
    latestRunLabel: `최신 분석 · ${formatDateTime(job.updated_at)}`,
    chatMessages: messagesFromJob(job),
    candidates,
    performance,
    tickerActions: actions,
    recommendationGate: payload?.recommendation_gate ?? null,
    recentReports: report ? [{
      id: `ai-job:${job.job_id}`,
      date: formatDate(job.updated_at),
      weekday: "결과",
      sentAt: formatDateTime(job.updated_at),
      title: report.web_projection.title,
      summary: report.web_projection.summary,
      status: result?.status === "failed" ? "failed" : "draft",
      strategyName: result?.strategy_spec?.name ?? payload?.headline ?? "전략 분석",
      recommendationScore: exploration ? "연구" : result?.strategy_spec ? `${Math.round(result.strategy_spec.confidence * 100)}%` : "—",
      signals: signalCounts,
      marketSnapshot: [],
    }] : [],
    envelope: result ?? null,
    jobStatus: {
      trace_id: job.trace_id,
      status: result?.status ?? "running",
      stages: job.stages.map((stage) => ({
        stage: WORKSPACE_STAGE_BY_AI_STAGE[stage.stage],
        status: WORKSPACE_STATUS_BY_AI_STATUS[stage.status],
        label: STAGE_LABELS[stage.stage],
        updated_at: stage.updated_at,
      })),
    },
  };
}

export function stageLabel(stage: AIJobStage): string {
  return STAGE_LABELS[stage];
}
