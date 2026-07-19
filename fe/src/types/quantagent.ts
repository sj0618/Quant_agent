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
  confidence: number;
}

export interface StrategyCandidateCard {
  strategy_id: string;
  title: string;
  summary: string;
  key_conditions: string[];
  confidence: number;
  reason?: string | null;
  sector?: string | null;
  matches: Array<{
    ticker: string;
    name: string;
    market: string;
    sector?: string | null;
    score: number;
    as_of_date: string;
    close?: number | null;
    matched_rules: string[];
  }>;
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

export interface AIBacktestPerformance {
  selected_candidate_id: string;
  metrics: AIBacktestMetrics;
  equity_curve: AIBacktestEquityPoint[];
  engine_summary?: Record<string, unknown>;
}

export interface AIUserPayload {
  headline: string;
  message: string;
  next_actions: string[];
  candidate_cards: StrategyCandidateCard[];
  report: AIReportBundle | null;
  performance?: AIBacktestPerformance | null;
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
  signal: SignalType;
  confidence: number;
  score: number;
  price: string;
  changePercent: string;
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
}

export interface EquityPoint {
  date: string;
  strategy: number;
  original: number;
  benchmark: number;
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
  envelope: AIEnvelope<{ active_tab: "overview" } | AIUserPayload, StrategySpec | AIStrategySpec | null> | null;
  jobStatus: AnalysisJobStatus | null;
}

export interface LandingSample {
  heroStats: Array<{ value: string; label: string }>;
  steps: Array<{ label: string; title: string; description: string; example: string[] }>;
  reportPreview: {
    title: string;
    date: string;
    score: string;
    market: Array<{ label: string; value: string; tone?: Tone }>;
    signals: Array<{ signal: SignalType; name: string; ticker: string; score: string }>;
  };
  comparisonRows: Array<{ item: string; traditional: string; terminal: string; quantAgent: string }>;
  principles: Array<{ label: string; title: string; description: string }>;
  faqs: Array<{ question: string; answer?: string }>;
}

export type ReportDeliveryStatus = "sent" | "draft" | "failed" | "resent";

export interface ReportSummary {
  id: string;
  strategyId?: string;
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
  reportId: string;
  strategyId: string;
  strategyName: string;
  reportDate: string;
  sentAt: string;
  status: ReportDeliveryStatus;
  title: string;
}

export interface ReportDetail extends ReportSummary {
  recipient: string;
  marketBrief: string;
  marketContext?: string;
  news: Array<{ rank: number; title: string; source: string; tone: Tone }>;
  candidates: TradingCandidate[];
  signalAxes: Array<{ label: string; weight: string; title: string; description: string }>;
  riskManagerOverride: string;
  conclusion: string;
  warningNote?: string;
  performance: Pick<PerformanceSummary, "metrics" | "disclaimer">;
  costNotes: string[];
}
