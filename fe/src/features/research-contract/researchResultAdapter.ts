import type {
  ResearchCandidateV1,
  ResearchDataProvenanceV1,
  ResearchResultV1,
} from "@/types/researchContract";

type UnknownRecord = Record<string, unknown>;

const RESULT_STATUSES = new Set<ResearchResultV1["status"]>([
  "ready",
  "need_clarification",
  "no_match",
  "unavailable",
  "failed",
  "dev_preview",
]);

/**
 * Narrow an untrusted result payload into the small public projection that the
 * non-public renderer accepts.  This is deliberately not an HTTP client: the archive
 * remains the only public product route until the release gate activates this flow.
 */
export function toResearchResultV1(payload: unknown): ResearchResultV1 | null {
  if (!isRecord(payload) || !isResultStatus(payload.status)) {
    return null;
  }
  const base = parseBase(payload);
  if (!base) {
    return null;
  }

  switch (payload.status) {
    case "ready": {
      const provenance = parseProvenance(payload.provenance);
      const candidates = Array.isArray(payload.candidates)
        ? payload.candidates.map(parseCandidate)
        : null;
      if (!provenance || !candidates || !allPresent(candidates) || candidates.length !== provenance.candidate_count) {
        return null;
      }
      return { ...base, status: "ready", provenance, candidates };
    }
    case "need_clarification": {
      const explanation = asText(payload.explanation);
      const choices = Array.isArray(payload.choices) ? payload.choices.map(parseChoice) : null;
      if (!explanation || !choices || !allPresent(choices) || choices.length === 0 || choices.length > 3) {
        return null;
      }
      return { ...base, status: "need_clarification", explanation, choices };
    }
    case "no_match": {
      const provenance = parseProvenance(payload.provenance);
      const explanation = asText(payload.explanation);
      if (!provenance || provenance.candidate_count !== 0 || !explanation) {
        return null;
      }
      return { ...base, status: "no_match", provenance, explanation };
    }
    case "unavailable": {
      const explanation = asText(payload.explanation);
      if (payload.reason_code !== "operational_data_provenance_required" || !explanation || typeof payload.retryable !== "boolean") {
        return null;
      }
      return {
        ...base,
        status: "unavailable",
        reason_code: "operational_data_provenance_required",
        explanation,
        retryable: payload.retryable,
      };
    }
    case "failed": {
      const explanation = asText(payload.explanation);
      const supportReference = asText(payload.support_reference);
      if (!explanation || !supportReference || typeof payload.retryable !== "boolean") {
        return null;
      }
      return {
        ...base,
        status: "failed",
        support_reference: supportReference,
        explanation,
        retryable: payload.retryable,
      };
    }
    case "dev_preview": {
      const explanation = asText(payload.explanation);
      if (payload.reason_code !== "development_fixture_only" || !explanation) {
        return null;
      }
      return {
        ...base,
        status: "dev_preview",
        reason_code: "development_fixture_only",
        explanation,
      };
    }
  }
}

function parseBase(payload: UnknownRecord) {
  const resultId = asText(payload.result_id);
  const ruleVersion = asText(payload.rule_version);
  if (!resultId || !ruleVersion || (payload.authoring_method !== "deterministic" && payload.authoring_method !== "llm")) {
    return null;
  }
  return {
    result_id: resultId,
    rule_version: ruleVersion,
    authoring_method: payload.authoring_method,
  } as const;
}

function parseProvenance(value: unknown): ResearchDataProvenanceV1 | null {
  if (!isRecord(value) || value.source !== "postgres" || value.freshness !== "eod_current") {
    return null;
  }
  const asOf = asText(value.as_of);
  const retrievedAt = asText(value.retrieved_at);
  const universeCount = asNonNegativeInteger(value.universe_count);
  const candidateCount = asNonNegativeInteger(value.candidate_count);
  if (!asOf || !retrievedAt || universeCount === null || candidateCount === null) {
    return null;
  }
  return {
    source: "postgres",
    as_of: asOf,
    retrieved_at: retrievedAt,
    freshness: "eod_current",
    universe_count: universeCount,
    candidate_count: candidateCount,
  };
}

function parseCandidate(value: unknown): ResearchCandidateV1 | null {
  if (!isRecord(value) || value.market !== "KRX" || !Array.isArray(value.matched_conditions)) {
    return null;
  }
  const ticker = asText(value.ticker);
  const name = asText(value.name);
  const asOf = asText(value.as_of);
  const matchedConditions = value.matched_conditions.map(asText);
  if (!ticker || !name || !asOf || matchedConditions.length === 0 || !allPresent(matchedConditions)) {
    return null;
  }
  return { ticker, name, market: "KRX", as_of: asOf, matched_conditions: matchedConditions };
}

function parseChoice(value: unknown) {
  if (!isRecord(value)) {
    return null;
  }
  const label = asText(value.label);
  const reason = asText(value.reason);
  return label && reason ? { label, reason } : null;
}

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isResultStatus(value: unknown): value is ResearchResultV1["status"] {
  return typeof value === "string" && RESULT_STATUSES.has(value as ResearchResultV1["status"]);
}

function asText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function asNonNegativeInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;
}

function allPresent<T>(values: (T | null)[]): values is T[] {
  return values.every((value): value is T => value !== null);
}
