import { AI_ENDPOINTS, appConfig } from "../config/appConfig";
import { toResearchResultV1 } from "../features/research-contract/researchResultAdapter";
import type {
  CanonicalResearchRuleV1,
  ResearchJobAcceptedV1,
  ResearchResultV1,
  ResearchRuleReviewV1,
} from "../types/researchContract";

/** A bounded browser adapter for the research-only API; it never calls a data source or provider. */
export class ResearchApiError extends Error {
  constructor(readonly status: number) {
    super("연구 요청을 지금 처리할 수 없습니다.");
    this.name = "ResearchApiError";
  }
}

export async function reviewResearchRule(naturalLanguage: string): Promise<ResearchRuleReviewV1> {
  return requestJson<ResearchRuleReviewV1>(AI_ENDPOINTS.researchRuleReview, {
    method: "POST",
    body: JSON.stringify({ natural_language: naturalLanguage }),
  }, [200, 422]);
}

export async function confirmResearchJob(
  canonicalRule: CanonicalResearchRuleV1,
  draftToken: string,
): Promise<ResearchJobAcceptedV1> {
  return requestJson<ResearchJobAcceptedV1>(AI_ENDPOINTS.researchJobs, {
    method: "POST",
    body: JSON.stringify({ canonical_rule: canonicalRule, draft_token: draftToken }),
  }, [201]);
}

export async function getResearchJobResult(jobId: string): Promise<ResearchResultV1> {
  const payload = await requestJson<unknown>(AI_ENDPOINTS.researchJobResult(jobId), { method: "GET" }, [200]);
  const result = toResearchResultV1(payload);
  if (!result) {
    throw new ResearchApiError(502);
  }
  return result;
}

async function requestJson<T>(
  path: string,
  init: RequestInit,
  acceptedStatuses: readonly number[],
): Promise<T> {
  const response = await fetch(`${appConfig.aiApiBaseUrl}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
    credentials: "include",
  });
  if (!acceptedStatuses.includes(response.status)) {
    throw new ResearchApiError(response.status);
  }
  return (await response.json()) as T;
}
