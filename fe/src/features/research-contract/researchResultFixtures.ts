import type { ResearchResultV1 } from "@/types/researchContract";

/** Test-only examples for the dark renderer; they are never connected to a public route. */
export const researchResultFixtures: readonly ResearchResultV1[] = [
  {
    result_id: "fixture-ready",
    rule_version: "research-rule-draft.v1",
    authoring_method: "deterministic",
    status: "ready",
    provenance: {
      source: "postgres",
      as_of: "2026-08-20",
      retrieved_at: "2026-08-20T00:00:00Z",
      freshness: "eod_current",
      universe_count: 2,
      candidate_count: 1,
    },
    candidates: [
      {
        ticker: "000000",
        name: "검증용 항목",
        market: "KRX",
        as_of: "2026-08-20",
        matched_conditions: ["RSI 30 이하"],
      },
    ],
  },
  {
    result_id: "fixture-clarification",
    rule_version: "research-rule-draft.v1",
    authoring_method: "deterministic",
    status: "need_clarification",
    explanation: "조건을 더 구체적으로 입력해 주세요.",
    choices: [{ label: "진입 조건 추가", reason: "조건 일치 여부를 계산하려면 필요합니다." }],
  },
  {
    result_id: "fixture-no-match",
    rule_version: "research-rule-draft.v1",
    authoring_method: "deterministic",
    status: "no_match",
    provenance: {
      source: "postgres",
      as_of: "2026-08-20",
      retrieved_at: "2026-08-20T00:00:00Z",
      freshness: "eod_current",
      universe_count: 2,
      candidate_count: 0,
    },
    explanation: "현재 기준일에는 조건과 일치한 항목이 없습니다.",
  },
  {
    result_id: "fixture-unavailable",
    rule_version: "research-rule-draft.v1",
    authoring_method: "deterministic",
    status: "unavailable",
    reason_code: "operational_data_provenance_required",
    explanation: "운영 데이터 기준일과 출처가 확인되지 않았습니다.",
    retryable: true,
  },
  {
    result_id: "fixture-failed",
    rule_version: "research-rule-draft.v1",
    authoring_method: "deterministic",
    status: "failed",
    support_reference: "fixture-support-reference",
    explanation: "검증 중 처리 오류가 발생했습니다.",
    retryable: false,
  },
  {
    result_id: "fixture-dev-preview",
    rule_version: "research-rule-draft.v1",
    authoring_method: "deterministic",
    status: "dev_preview",
    reason_code: "development_fixture_only",
    explanation: "이 fixture는 renderer 검증 전용입니다.",
  },
];
