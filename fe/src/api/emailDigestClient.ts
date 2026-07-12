const DIGEST_STRATEGY_STORAGE_KEY = "quantagent.email-digest-strategies.v1";

export const MAX_EMAIL_DIGEST_STRATEGIES = 3;

export class EmailDigestSelectionLimitError extends Error {
  constructor() {
    super(`이메일 다이제스트 구독 전략은 최대 ${MAX_EMAIL_DIGEST_STRATEGIES}개까지 선택할 수 있습니다.`);
    this.name = "EmailDigestSelectionLimitError";
  }
}

function readSelection(): string[] {
  const raw = window.localStorage.getItem(DIGEST_STRATEGY_STORAGE_KEY);
  if (!raw) {
    return [];
  }

  try {
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === "string") : [];
  } catch {
    return [];
  }
}

export function getDigestStrategySelection(): string[] {
  return readSelection();
}

export function saveDigestStrategySelection(strategyIds: string[]): string[] {
  const unique = Array.from(new Set(strategyIds));
  if (unique.length > MAX_EMAIL_DIGEST_STRATEGIES) {
    throw new EmailDigestSelectionLimitError();
  }
  window.localStorage.setItem(DIGEST_STRATEGY_STORAGE_KEY, JSON.stringify(unique));
  return unique;
}

export function toggleDigestStrategySelection(strategyId: string, checked: boolean): string[] {
  const current = readSelection();
  const next = checked ? [...current, strategyId] : current.filter((name) => name !== strategyId);
  return saveDigestStrategySelection(next);
}
