export type AIEnvelopeStatus = "ready" | "need_clarification" | "rejected" | "failed";

export type AnalysisStage =
  | "strategy_parse"
  | "data_collect"
  | "signal_judge"
  | "backtest"
  | "risk_review"
  | "report_ready";

export type StageStatus = "ready" | "running" | "done" | "blocked" | "failed";

export type SignalType = "BUY" | "HOLD" | "DROP";

export type Tone = "positive" | "warning" | "negative" | "neutral" | "info";

export interface AIEnvelope<TUserPayload = unknown, TStrategySpec = StrategySpec> {
  status: AIEnvelopeStatus;
  trace_id: string;
  schema_version: string;
  user_payload: TUserPayload;
  strategy_spec: TStrategySpec;
  debug_ref: string;
  retryable: boolean;
}

export interface StrategySpec {
  natural_language_strategy: string;
  universe: string;
  sector: string;
  buy_condition: string;
  hold_condition: string;
  drop_condition: string;
  rebalance: string;
  constraints: string[];
}

export interface AnalysisJobStatus {
  trace_id: string;
  status: AIEnvelopeStatus;
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

export interface ABComparisonRow {
  metric: string;
  original: string;
  improved: string;
  delta: string;
  tone: Tone;
}

export interface MacroEvent {
  date: string;
  label: string;
  impact: "+α" | "-α" | "≈";
  tone: Tone;
}

export interface PerformanceSummary {
  headline: string;
  period: string;
  metrics: BacktestMetric[];
  equityCurve: EquityPoint[];
  comparison: ABComparisonRow[];
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
  envelope: AIEnvelope<{ active_tab: "overview" }>;
  jobStatus: AnalysisJobStatus;
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

export interface ReportSummary {
  id: string;
  date: string;
  weekday: string;
  sentAt: string;
  title: string;
  summary: string;
  status: "sent" | "draft" | "failed";
  strategyName: string;
  recommendationScore: string;
  signals: Record<SignalType, number>;
  marketSnapshot: Array<{ label: string; value: string; tone?: Tone }>;
}

export interface ReportDetail extends ReportSummary {
  recipient: string;
  marketBrief: string;
  news: Array<{ rank: number; title: string; source: string; tone: Tone }>;
  candidates: TradingCandidate[];
  signalAxes: Array<{ label: string; weight: string; title: string; description: string }>;
  riskManagerOverride: string;
  conclusion: string;
  performance: Pick<PerformanceSummary, "metrics" | "disclaimer">;
  costNotes: string[];
}
