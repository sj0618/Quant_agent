export const SIGNAL_ACTIONS = ["BUY", "SELL", "HOLD", "WATCH", "FILTERED_OUT"] as const;

export type SignalAction = (typeof SIGNAL_ACTIONS)[number];

export type LogicMode = "ALL" | "ANY";

export type ScenarioCode =
  | "READY"
  | "C1_INPUT_AMBIGUOUS"
  | "C2_TERM_UNKNOWN"
  | "C4_CONFLICTING"
  | "C5_INFEASIBLE";

export type MessageRole = "assistant" | "user" | "system";

export type RiskSeverity = "LOW" | "MEDIUM" | "HIGH";

export interface Condition {
  id: string;
  label: string;
  metric: string;
  operator: "<" | "<=" | ">" | ">=" | "=" | "increasing" | "decreasing";
  value: string;
  unit?: string;
}

export interface CandidateSnapshot {
  snapshot_id: string;
  tickers: string[];
  effective_from: string;
}

export interface StrategySpec {
  strategy_id: string;
  name: string;
  summary: string;
  universe: string;
  entry_rules: Condition[];
  exit_rules: Condition[];
  entry_logic: LogicMode;
  exit_logic: LogicMode;
  candidate_snapshot: CandidateSnapshot;
}

export interface MarketSnapshot {
  ticker: string;
  timestamp: string;
  metrics: Record<string, number>;
  previous_metrics?: Record<string, number>;
}

export interface EvidenceChip {
  label: string;
  value: string;
  tone: "blue" | "emerald" | "amber" | "rose" | "slate";
}

export interface CandidateStock {
  ticker: string;
  name: string;
  sector: string;
  lastPrice: number;
  dayChangeRate: number;
  hasPosition: boolean;
  inCandidateSnapshot: boolean;
  marketSnapshot: MarketSnapshot;
  evidenceChips: EvidenceChip[];
}

export interface SignalDecision {
  strategy_id: string;
  ticker: string;
  action: SignalAction;
  confidence: number;
  reasons: string[];
  generatedBy: "Signal Judge";
}

export interface RiskWarning {
  id: string;
  ticker: string;
  severity: RiskSeverity;
  reason: string;
  source: string;
  evidence: string[];
  report_note: string;
}

export interface StrategyOption {
  strategy_id: string;
  title: string;
  description: string;
  keyConditions: string[];
}

export interface TermDefinition {
  term: string;
  definition: string;
  confidence: number;
  matchedSources: string[];
  requiresConfirmation: boolean;
  mappedStrategyId: string;
}

export interface ConflictExplanation {
  title: string;
  conflictPoints: string[];
  alternatives: StrategyOption[];
}

export interface InfeasibleExplanation {
  title: string;
  reason: string;
  supportedScope: string;
  examples: string[];
}

export type ScenarioPayload =
  | {
      scenario: "READY";
      assistantMessage: string;
      strategy_id: string;
    }
  | {
      scenario: "C1_INPUT_AMBIGUOUS";
      assistantMessage: string;
      options: StrategyOption[];
    }
  | {
      scenario: "C2_TERM_UNKNOWN";
      assistantMessage: string;
      termDefinition: TermDefinition;
    }
  | {
      scenario: "C4_CONFLICTING";
      assistantMessage: string;
      conflict: ConflictExplanation;
    }
  | {
      scenario: "C5_INFEASIBLE";
      assistantMessage: string;
      infeasible: InfeasibleExplanation;
    };

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  scenario?: ScenarioCode;
  createdAt: string;
}

export interface BacktestMetric {
  label: "Total Return" | "Sharpe" | "MDD" | "Win Rate";
  value: string;
  detail: string;
  tone: "positive" | "neutral" | "warning";
}

export interface BacktestPoint {
  date: string;
  strategy: number;
  benchmark: number;
}

export interface ReportSection {
  id: string;
  title: string;
  summary: string;
  signalJudgeNote?: string;
  riskManagerNote?: string;
}

export interface WorkspacePayload {
  activeStrategy: StrategySpec;
  candidates: CandidateStock[];
  signalDecisions: SignalDecision[];
  riskWarnings: RiskWarning[];
  reportPreview: ReportSection[];
  backtestMetrics: BacktestMetric[];
  backtestSeries: BacktestPoint[];
}

export interface ActionSummary {
  action: SignalAction;
  count: number;
}
