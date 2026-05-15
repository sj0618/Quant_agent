import {
  ambiguousStrategyOptions,
  conflictExplanation,
  exampleStrategies,
  infeasibleExplanation,
  mockBacktestMetrics,
  mockBacktestSeries,
  mockCandidates,
  mockMessages,
  mockReportPreview,
  mockRiskWarnings,
  mockSignalDecisions,
  mockStrategies,
  termDefinition,
} from "../data/mockQuantAgentData";
import type {
  ActionSummary,
  ChatMessage,
  ScenarioCode,
  ScenarioPayload,
  SignalAction,
  StrategySpec,
  WorkspacePayload,
} from "../types/quantagent";

const DEFAULT_STRATEGY_ID = "strategy_rsi_volume_rebound";

let activeStrategyId = DEFAULT_STRATEGY_ID;

const createId = (prefix: string) => `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;

const nowIso = () => new Date().toISOString();

const delay = async () => Promise.resolve();

const getStrategyById = (strategyId: string): StrategySpec =>
  mockStrategies.find((strategy) => strategy.strategy_id === strategyId) ?? mockStrategies[0];

export async function getInitialMessages(): Promise<ChatMessage[]> {
  await delay();
  return [...mockMessages];
}

export async function getExampleStrategies(): Promise<string[]> {
  await delay();
  return [...exampleStrategies];
}

export async function getActiveStrategy(): Promise<StrategySpec> {
  await delay();
  return getStrategyById(activeStrategyId);
}

export async function getCandidates() {
  await delay();
  return [...mockCandidates];
}

export async function getReportPreview() {
  await delay();
  return [...mockReportPreview];
}

export async function getBacktestResult() {
  await delay();
  return {
    metrics: [...mockBacktestMetrics],
    series: [...mockBacktestSeries],
  };
}

export async function getWorkspacePayload(): Promise<WorkspacePayload> {
  await delay();
  const strategy = getStrategyById(activeStrategyId);

  return {
    activeStrategy: strategy,
    candidates: [...mockCandidates],
    signalDecisions: mockSignalDecisions.map((decision) => ({
      ...decision,
      strategy_id: strategy.strategy_id,
    })),
    riskWarnings: [...mockRiskWarnings],
    reportPreview: [...mockReportPreview],
    backtestMetrics: [...mockBacktestMetrics],
    backtestSeries: [...mockBacktestSeries],
  };
}

export async function selectStrategy(strategyId: string): Promise<WorkspacePayload> {
  await delay();
  activeStrategyId = getStrategyById(strategyId).strategy_id;
  return getWorkspacePayload();
}

export async function parseStrategy(input: string, forcedScenario: ScenarioCode | "AUTO" = "AUTO"): Promise<ScenarioPayload> {
  await delay();
  const normalized = input.trim().toLowerCase();
  const scenario = forcedScenario === "AUTO" ? detectScenario(normalized) : forcedScenario;

  if (scenario === "C1_INPUT_AMBIGUOUS") {
    return {
      scenario,
      assistantMessage: "입력이 넓게 해석될 수 있어요. 먼저 의도에 가까운 전략 후보를 골라주세요.",
      options: ambiguousStrategyOptions,
    };
  }

  if (scenario === "C2_TERM_UNKNOWN") {
    return {
      scenario,
      assistantMessage: "입력한 용어를 L1/L2 우선 검색으로 매핑했습니다. 다음 의미가 맞는지 확인해주세요.",
      termDefinition,
    };
  }

  if (scenario === "C4_CONFLICTING") {
    return {
      scenario,
      assistantMessage: "전략 조건 사이에 논리 충돌이 있어 Query smooth가 필요합니다.",
      conflict: conflictExplanation,
    };
  }

  if (scenario === "C5_INFEASIBLE") {
    return {
      scenario,
      assistantMessage: "요청 범위가 현재 FE MVP 지원 범위를 벗어났습니다.",
      infeasible: infeasibleExplanation,
    };
  }

  activeStrategyId = normalized.includes("방어") ? "strategy_defensive_quality" : DEFAULT_STRATEGY_ID;

  return {
    scenario: "READY",
    assistantMessage:
      "StrategySpec으로 변환했습니다. CandidateSnapshot → Signal Judge → Risk Warning layer → Report Preview 순서로 결과를 표시합니다.",
    strategy_id: activeStrategyId,
  };
}

export function createChatMessage(role: ChatMessage["role"], content: string, scenario?: ScenarioCode): ChatMessage {
  return {
    id: createId(role),
    role,
    content,
    scenario,
    createdAt: nowIso(),
  };
}

export function summarizeActions(actions: SignalAction[]): ActionSummary[] {
  const order: SignalAction[] = ["BUY", "SELL", "HOLD", "WATCH", "FILTERED_OUT"];
  return order.map((action) => ({
    action,
    count: actions.filter((item) => item === action).length,
  }));
}

const detectScenario = (normalizedInput: string): ScenarioCode => {
  if (!normalizedInput || normalizedInput.includes("저평가주 사줘")) {
    return "C1_INPUT_AMBIGUOUS";
  }

  if (normalizedInput.includes("눌림목")) {
    return "C2_TERM_UNKNOWN";
  }

  if (normalizedInput.includes("변동성 낮") && normalizedInput.includes("급등")) {
    return "C4_CONFLICTING";
  }

  if (
    normalizedInput.includes("옵션") ||
    normalizedInput.includes("선물") ||
    normalizedInput.includes("레버리지") ||
    normalizedInput.includes("주문")
  ) {
    return "C5_INFEASIBLE";
  }

  return "READY";
};
