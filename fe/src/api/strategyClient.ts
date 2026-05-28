import { STRATEGY_ENDPOINTS, appConfig } from "../config/appConfig";
import { createAnalysisJob } from "./quantAgentClient";
import type { StrategySpec } from "../types/quantagent";

const STRATEGY_DRAFT_STORAGE_KEY = "quantagent.strategy-draft.v1";

export interface StrategyDraft extends StrategySpec {
  id: string;
  name: string;
  updatedAt: string;
}

function assertOk(response: Response) {
  if (!response.ok) {
    throw new Error(`전략 서버 응답 실패: ${response.status}`);
  }
}

export function saveStrategyDraft(draft: StrategyDraft) {
  window.localStorage.setItem(STRATEGY_DRAFT_STORAGE_KEY, JSON.stringify(draft));
  return draft;
}

export function getStrategyDraft(): StrategyDraft | null {
  const raw = window.localStorage.getItem(STRATEGY_DRAFT_STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as StrategyDraft;
  } catch {
    return null;
  }
}

export async function persistStrategy(id: string | null, draft: StrategyDraft) {
  if (!appConfig.strategyApiBaseUrl) {
    saveStrategyDraft(draft);
    throw new Error("VITE_STRATEGY_API_BASE_URL 설정이 필요합니다. 초안은 브라우저에 저장했습니다.");
  }

  const endpoint = id ? STRATEGY_ENDPOINTS.update(id) : STRATEGY_ENDPOINTS.create;
  const response = await fetch(`${appConfig.strategyApiBaseUrl}${endpoint}`, {
    method: id ? "PUT" : "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draft),
  });
  assertOk(response);
  saveStrategyDraft(draft);
}

export async function requestStrategyAnalysis(id: string, query: string) {
  if (appConfig.aiApiBaseUrl) {
    return createAnalysisJob(query);
  }

  if (!appConfig.strategyApiBaseUrl) {
    throw new Error("VITE_AI_API_BASE_URL 또는 VITE_STRATEGY_API_BASE_URL 설정이 필요합니다.");
  }

  const response = await fetch(`${appConfig.strategyApiBaseUrl}${STRATEGY_ENDPOINTS.run(id)}`, {
    method: "POST",
    credentials: "include",
  });
  assertOk(response);
}
