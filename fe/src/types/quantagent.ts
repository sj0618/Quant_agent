export type AIEnvelopeStatus = "ready" | "need_clarification" | "rejected" | "failed";

export type AISourceType = "internal_db" | "krx" | "dart" | "aoai_web_search" | "analyst_evidence" | "none";
export type AIFreshnessStatus = "fresh" | "stale" | "unknown" | "not_time_sensitive";

export interface AISemanticSlots {
  indicator: string[];
  threshold: string[];
  lookback: string[];
  horizon: string[];
  price_basis: string[];
  event: string[];
  action: string[];
  slot_evidence_refs: string[];
  missing_slots: string[];
  contradictions: string[];
  confidence: number;
  parse_status: "ready" | "needs_clarification" | "failed";
  extraction_method: "deterministic_rules" | "json_schema_llm";
  schema_validation_status: "valid" | "invalid";
}

export interface AIDataRequirement {
  family: string;
  required: boolean;
  availability: "available" | "derivable" | "partial" | "unavailable" | "outside_owner" | "not_required";
  owner: "ai_graph" | "data_source_config" | "product_data_gap" | "outside_owner" | "unknown";
  preferred_source: AISourceType;
  fallback_sources: AISourceType[];
  freshness_requirement: string;
  source_confidence_floor: number;
  proxy_allowed: boolean;
  proxy_used: boolean;
  proxy_disclosure?: Record<string, string> | null;
  evidence_ref: string;
}

export interface AISourceUsage {
  source_type: AISourceType;
  query: string;
  retrieved_at: string;
  source_refs: string[];
  freshness_status: AIFreshnessStatus;
  confidence: number;
  fallback_used: boolean;
  evidence_refs: string[];
}

export interface AIFailureDiagnostic {
  category: string;
  subcause: string;
  failure_stage: string;
  owner: "ai_graph" | "data_source_config" | "fe_state" | "outside_owner" | "product_data_gap" | "unknown";
  retryable: boolean;
  safe_message: string;
  evidence_refs: string[];
}

export interface AIEvidenceRef {
  ref_id: string;
  source_type: AISourceType;
  stage: string;
  retrieved_at: string;
  sanitized_summary: string;
  confidence: number;
}

export type AIJobStage = "interpreting" | "code_generation" | "backtest" | "debate" | "finalizing";

export type AIJobStageStatus = "queued" | "running" | "succeeded" | "failed";

export type AnalysisStage =
  | "strategy_parse"
  | "data_collect"
  | "signal_judge"
  | "backtest"
  | "risk_review"
  | "report_ready";

export type StageStatus = "ready" | "running" | "done" | "blocked" | "failed";

export type WorkspaceAnalysisStatus = AIEnvelopeStatus | "running";

export type SignalType = "BUY" | "HOLD" | "DROP";

export type Tone = "positive" | "warning" | "negative" | "neutral" | "info";

export interface AIEnvelope<TUserPayload = unknown, TStrategySpec = StrategySpec | null> {
  status: AIEnvelopeStatus;
  trace_id: string;
  schema_version: string;
  user_payload: TUserPayload;
  strategy_spec: TStrategySpec;
  debug_ref: string;
  retryable: boolean;
  semantic_slots?: AISemanticSlots | null;
  data_requirements?: AIDataRequirement[];
  source_usage?: AISourceUsage[];
  freshness_status?: AIFreshnessStatus | null;
  proxy_disclosure?: Record<string, string> | null;
  failure_cause?: AIFailureDiagnostic | null;
  evidence_refs?: AIEvidenceRef[];
}

export interface StrategySpec {
  name?: string;
  natural_language_strategy: string;
  sector: string;
  buy_condition: string;
  hold_condition: string;
  drop_condition: string;
  rebalance: string;
  constraints: string[];
}

export interface AICondition {
  left: string;
  operator: "lt" | "lte" | "gt" | "gte" | "eq" | "ne" | "between" | "cross_above" | "cross_below";
  right: number | string | number[];
  description?: string | null;
}

export interface AIStrategySpec {
  strategy_id: string;
  name: string;
  market: string;
  timeframe: string;
  entry_conditions: AICondition[];
  exit_conditions: AICondition[];
  indicators: string[];
  risk_constraints: Record<string, number | string | boolean>;
  assumptions: string[];
  source_refs: string[];
  selection_mode?: "standard" | "automatic" | "user_defined";
  confidence: number;
}

export interface AIScreeningMatch {
  ticker: string;
  name: string;
  market: string;
  sector?: string | null;
  as_of_date: string;
  close?: number | null;
  matched_rules: string[];
}

export interface StrategyCandidateCard {
  strategy_id: string;
  title: string;
  summary: string;
  key_conditions: string[];
  confidence: number;
  reason?: string | null;
  sector?: string | null;
  matches: AIScreeningMatch[];
}

export interface AIClarificationOption {
  label: string;
  reason: string;
}

export interface AIReportProjection {
  title: string;
  summary: string;
  sections: Array<Record<string, unknown>>;
}

export interface AIRiskAdjustment {
  before: SignalType;
  after: SignalType;
  rule: string;
  reason: string;
}

export interface AIReportBundle {
  web_projection: AIReportProjection;
  email_projection: AIReportProjection;
  risk_adjustments: AIRiskAdjustment[];
}

export interface AIBacktestMetrics {
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  total_return: number;
  in_sample_sharpe: number;
  out_sample_sharpe: number;
  degradation: number;
}

export interface AIBacktestEquityPoint {
  date: string;
  cumulative_return: number;
}

export interface AIBacktestReliability {
  source: "fixture" | "postgres" | "unknown";
  status: "sufficient" | "limited" | "insufficient";
  row_count: number;
  ticker_count: number;
  trading_days: number;
  history_start: string | null;
  history_end: string | null;
  trade_count: number;
  reasons: string[];
  warnings: string[];
}

export interface AIBacktestBenchmark {
  label: string;
  method: string;
  warning: string | null;
  total_return: number | null;
  cumulative_curve: AIBacktestEquityPoint[];
  is_available: boolean;
  unavailable_reason: string | null;
}

export interface AIBacktestMetricDetail {
  key: string;
  label: string;
  value: number | null;
  unit: "percent" | "ratio" | string;
  is_available: boolean;
  unavailable_reason: string | null;
  plain_explanation: string;
  why_used: string;
  caution: string;
  source_refs: string[];
}

export interface AIIndicatorExplanation {
  key: string;
  label: string;
  plain_explanation: string;
  why_used: string;
  formula?: string | null;
  derivation?: string | null;
  customization?: string | null;
  caution: string;
  source_refs: string[];
}

export interface AIGeneratedStrategyBlueprint {
  blueprint_id: string;
  profile: string;
  title: string;
  formula: string;
  derivation: string;
  why_generated: string;
  lookback: number;
  max_positions: number;
  rebalance_interval_days: number;
  stop_loss_pct: number;
  trailing_stop_pct: number;
  source_refs: string[];
}

export interface AIStrategyExplanation {
  selection_mode: "standard" | "automatic" | "user_defined";
  title: string;
  summary: string;
  why_selected: string;
  rebalance_explanation: string | null;
  caution: string;
  indicators: AIIndicatorExplanation[];
  generated_strategies?: AIGeneratedStrategyBlueprint[];
  source_refs: string[];
}

/**
 * Which slice of the history the public numbers were measured on. The backend decides
 * this per run - a single hold-out tail, or the rolling policy's evaluation sessions -
 * so a caption written in the client would be wrong whenever the run takes the other
 * path. Render `caption`; the structured fields are there for anything that needs to
 * reason about the basis rather than print it.
 */
export interface AIBacktestEvaluationBasis {
  basis: "hold_out" | "walk_forward_policy";
  caption: string;
  hold_out_fraction?: number | null;
  window_start?: string | null;
  window_end?: string | null;
  window_policy_id?: string | null;
  evaluation_session_count?: number | null;
  fold_count?: number | null;
  cost_model_applied?: boolean;
}

/** Why a name recommended today can be missing from the backtest that was run. */
export interface AIBacktestUniversePolicy {
  summary: string;
  policy_id?: string | null;
  window_start?: string | null;
  window_end?: string | null;
  traded_ticker_count?: number | null;
  excluded_screening_candidate_count: number;
  excluded_notice?: string | null;
}

export interface AIBacktestPerformance {
  selected_candidate_id: string;
  metrics: AIBacktestMetrics;
  equity_curve: AIBacktestEquityPoint[];
  engine_summary?: Record<string, unknown>;
  reliability?: AIBacktestReliability | null;
  data_quality?: string[];
  benchmark?: AIBacktestBenchmark | null;
  metric_details?: AIBacktestMetricDetail[];
  strategy_explanation?: AIStrategyExplanation | null;
  evaluation_basis?: AIBacktestEvaluationBasis | null;
  universe_policy?: AIBacktestUniversePolicy | null;
}

export interface AIRecommendationGate {
  validated: boolean;
  reason: string;
  /**
   * False when the acceptance rule could not be evaluated at all - a missing input, not a
   * measured shortfall. A gate can be `validated` on the metrics it did measure and still
   * be incomplete, so both flags have to be read.
   */
  verification_complete?: boolean;
  unmet_objective_criteria?: string[];
  unmet_data_requirements?: string[];
}

export type AITickerActionType = 'BUY' | 'SELL' | 'HOLD' | 'WATCH';

/** Today's verdict for one stock, produced by the same backtest run as `performance`. */
export interface AITickerAction {
  ticker: string;
  name: string;
  action: AITickerActionType;
  reason: string;
  as_of_date: string;
  close?: number | null;
  source_candidate_id?: string | null;
}

export interface AIUserPayload {
  headline: string;
  message: string;
  next_actions: string[];
  candidate_cards: StrategyCandidateCard[];
  report: AIReportBundle | null;
  performance?: AIBacktestPerformance | null;
  recommendation_gate?: AIRecommendationGate | null;
  ticker_actions?: AITickerAction[];
  question?: string | null;
  options?: AIClarificationOption[];
  recommended?: number | null;
}

export interface AIStageProgress {
  stage: AIJobStage;
  status: AIJobStageStatus;
  updated_at: string;
  message?: string | null;
}

export interface AnalysisJob {
  job_id: string;
  trace_id: string;
  query: string;
  created_at: string;
  updated_at: string;
  stages: AIStageProgress[];
  result: AIEnvelope<AIUserPayload, AIStrategySpec | null> | null;
}

export interface AnalysisJobStatus {
  trace_id: string;
  status: WorkspaceAnalysisStatus;
  stages: Array<{
    stage: AnalysisStage;
    status: StageStatus;
    label: string;
    updated_at: string;
  }>;
}

export interface EvidenceSource {
  provider: string;
  title: string;
  date: string;
  summary: string;
}

export interface TradingCandidate {
  id: string;
  ticker: string;
  name: string;
  sector: string;
  // A screening match is not a per-ticker verdict. The graph decides one action and one
  // confidence for the whole strategy, so copying them onto every matched name invented a
  // per-name judgement that nothing computed - 30 names all reading "HOLD 86%". These stay
  // optional and are only set by sources that really do score a single name.
  signal?: SignalType;
  confidence?: number;
  price: string;
  changePercent?: string;
  rationale: string;
  evidence: EvidenceSource[];
  riskReasons: string[];
  risk_manager_override?: string;
  web_projection?: string;
}

export interface BacktestMetric {
  key: string;
  label: string;
  value: string;
  delta?: string;
  tone: Tone;
  caption: string;
  plainExplanation?: string;
  whyUsed?: string;
  caution?: string;
  sourceRefs?: string[];
}

export interface EquityPoint {
  date: string;
  strategy: number;
  original?: number;
  benchmark?: number;
}

export interface PerformanceComparisonRow {
  metric: string;
  value: string;
  context: string;
  assessment: string;
  tone: Tone;
}

export interface MacroEvent {
  date: string;
  label: string;
  impact: "+α" | "-α" | "≈";
  tone: Tone;
}

export interface PerformanceSummary {
  source?: "ai";
  headline: string;
  period: string;
  benchmarkLabel?: string;
  metrics: BacktestMetric[];
  equityCurve: EquityPoint[];
  comparison: PerformanceComparisonRow[];
  macroEvents: MacroEvent[];
  reliability?: AIBacktestReliability | null;
  dataQuality?: string[];
  benchmark?: AIBacktestBenchmark;
  metricDetails?: AIBacktestMetricDetail[];
  strategyExplanation?: AIStrategyExplanation | null;
  evaluationBasis?: AIBacktestEvaluationBasis | null;
  universePolicy?: AIBacktestUniversePolicy | null;
  disclaimer: string;
}

export interface ChatMessage {
  id: string;
  sender: "system" | "user" | "agent";
  label: string;
  time: string;
  body: string;
  stats?: Array<{ label: string; value: string }>;
  candidateCards?: StrategyCandidateCard[];
  clarification?: {
    question: string;
    options: AIClarificationOption[];
    recommended?: number | null;
  };
}

export interface ChatConversationPreview {
  id: string;
  title: string;
  updatedAt: string;
  status: WorkspaceAnalysisStatus;
  messages: ChatMessage[];
}

export interface AppOverview {
  strategy: StrategySpec;
  recommendationScore: string;
  recommendationDelta: string;
  passCount: number;
  buyCount: number;
  holdCount: number;
  dropCount: number;
  nextRunLabel: string;
  latestRunLabel: string;
  chatMessages: ChatMessage[];
  candidates: TradingCandidate[];
  performance: PerformanceSummary;
  recentReports: ReportSummary[];
  // The graph's own verdict per stock, and why the picks are (or are not) validated.
  // Both are decided in the backtest run behind `performance`, so the overview reads
  // them rather than deriving a second opinion from the candidate rows.
  tickerActions?: AITickerAction[];
  recommendationGate?: AIRecommendationGate | null;
  envelope: AIEnvelope<{ active_tab: "overview" } | AIUserPayload, StrategySpec | AIStrategySpec | null> | null;
  jobStatus: AnalysisJobStatus | null;
}

export type ReportDeliveryStatus = "sent" | "draft" | "failed" | "resent" | "submitted" | "processing" | "delivered" | "cancelled" | "unknown";

export interface ReportSummary {
  id: string;
  runId?: string;
  strategyId?: string;
  instrumentId?: string;
  instrumentName?: string;
  ticker?: string;
  createdAt?: string;
  updatedAt?: string;
  publishedAt?: string;
  date: string;
  weekday: string;
  sentAt: string;
  title: string;
  summary: string;
  status: ReportDeliveryStatus;
  strategyName: string;
  recommendationScore: string;
  signals: Record<SignalType, number>;
  marketSnapshot: Array<{ label: string; value: string; tone?: Tone }>;
}

export interface PersistedReportSection {
  id?: string;
  title?: string;
  note?: string;
  body?: string;
  entries?: PersistedReportEntry[];
}

export interface PersistedReportEntry {
  label?: string;
  value: string;
  depth: number;
  description?: string;
}

export interface DailyDigestHeader {
  reportDate: string;
  userName: string;
  strategyCount: number;
}

export interface DailyDigestComparisonRow {
  strategyId: string;
  name: string;
  todaySignal: SignalType;
  totalReturn: number;
  maxDrawdown: number;
  sharpeRatio: number;
  status: "주목" | "유지" | "관망";
}

export interface DailyDigestStrategyCard {
  strategyId: string;
  title: string;
  todaySignal: SignalType;
  targets: string[];
  totalReturn: number;
  maxDrawdown: number;
  sharpeRatio: number;
  winRate: number;
  tradeCount: number;
  aiInterpretation: string;
  caution: string;
}

export interface DailyDigestMarketBriefItem {
  title: string;
  source: string;
  url?: string;
  publishedAt?: string;
  tone: Tone;
  summary: string;
}

export interface DailyDigestMarketBrief {
  headline: string;
  items: DailyDigestMarketBriefItem[];
}

export interface DailyDigestReport {
  header: DailyDigestHeader;
  overallSummary: string[];
  comparisonRows: DailyDigestComparisonRow[];
  strategyCards: DailyDigestStrategyCard[];
  aiOverallComment: string;
  marketBrief: DailyDigestMarketBrief;
  footer: string[];
}

export interface StrategyReportSummary {
  id: string;
  name: string;
  description: string;
  timeframe: string;
  entrySummary: string;
  exitSummary: string;
  riskSummary: string;
  latestSentAt: string;
  latestReportDate: string;
  latestStatus: ReportDeliveryStatus;
  latestEmailReportId: string;
  recommendationScore: string;
  signals: Record<SignalType, number>;
  summary: string;
  tags: string[];
}

export interface StrategyReportDetail {
  strategy: StrategyReportSummary;
  emailReports: ReportDetail[];
}

export interface EmailDigestHistoryEntry {
  id: string;
  reportId?: string;
  strategyId?: string;
  strategyName: string;
  reportDate: string;
  sentAt: string;
  status: ReportDeliveryStatus;
  title: string;
}

export interface ReportDetail extends ReportSummary {
  recipient: string | null;
  marketBrief: string;
  marketContext?: string | null;
  contentSections?: PersistedReportSection[];
  news: Array<{ rank: number; title: string; source: string; tone: Tone }>;
  candidates: TradingCandidate[];
  signalAxes: Array<{ label: string; weight: string; title: string; description: string }>;
  riskManagerOverride: string;
  conclusion: string;
  warningNote?: string | null;
  performance: Pick<PerformanceSummary, "metrics" | "disclaimer">;
  costNotes: string[];
}

export type EmailDeliveryStatus = "sent" | "resent" | "failed" | "draft";

/** One row of `GET /api/v1/me/email-deliveries`, trimmed to what the timeline renders. */
export interface EmailDeliveryEntry {
  deliveryId: string;
  reportId: string | null;
  reportTitle: string | null;
  strategyName: string | null;
  status: EmailDeliveryStatus;
  reportDate: string | null;
  sentAt: string | null;
  createdAt: string | null;
  failedAt: string | null;
}
