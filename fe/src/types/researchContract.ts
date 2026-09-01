export interface ResearchClarificationChoiceV1 {
  label: string;
  reason: string;
}

export interface ResearchRuleConditionV1 {
  metric: string;
  comparator: "lt" | "lte" | "gt" | "gte" | "eq" | "ne";
  value: number;
  lookback: number;
  role: "entry" | "exit";
}

export interface ResearchUnsupportedConditionV1 {
  condition: string;
  reason: string;
}

export interface ResearchIndicatorSelectionV1 {
  metric: string;
  reason: string;
}

export interface CanonicalResearchRuleV1 {
  market: "KRX";
  timeframe: "daily";
  entry_conditions: ResearchRuleConditionV1[];
  exit_conditions: ResearchRuleConditionV1[];
}

export interface ResearchRuleDraftV1 {
  kind: "rule_draft";
  market: "KRX";
  timeframe: "daily";
  entry_conditions: ResearchRuleConditionV1[];
  exit_conditions: ResearchRuleConditionV1[];
  unsupported_conditions: ResearchUnsupportedConditionV1[];
  clarification_required: boolean;
  explanation: string;
  indicator_selections: ResearchIndicatorSelectionV1[];
  canonical_rule: CanonicalResearchRuleV1 | null;
  editable_summary: string;
  clarifications: ResearchClarificationChoiceV1[];
  is_executable: boolean;
  authoring_method: "deterministic" | "llm";
  schema_version: string;
  policy_hash: string;
  expires_at: string;
  draft_token: string;
}

export interface ResearchScopeRefusalV1 {
  kind: "scope_refusal" | "unsupported_scope";
  reason_code: "personalized_investment_request" | "unsupported_asset_family";
  explanation: string;
  general_example: string;
  guidance: string;
}

export type ResearchRuleReviewV1 = ResearchRuleDraftV1 | ResearchScopeRefusalV1;

export interface ResearchJobAcceptedV1 {
  kind: "research_job_accepted";
  job_id: string;
  status: "queued";
}

export interface ResearchDataProvenanceV1 {
  source: "postgres";
  as_of: string;
  retrieved_at: string;
  freshness: "eod_current";
  universe_count: number;
  candidate_count: number;
}

export interface ResearchCandidateV1 {
  ticker: string;
  name: string;
  market: "KRX";
  as_of: string;
  matched_conditions: string[];
}

interface ResearchResultBaseV1 {
  result_id: string;
  rule_version: string;
  authoring_method: "deterministic" | "llm";
}

export interface ResearchReadyV1 extends ResearchResultBaseV1 {
  status: "ready";
  provenance: ResearchDataProvenanceV1;
  candidates: ResearchCandidateV1[];
}

export interface ResearchNeedClarificationV1 extends ResearchResultBaseV1 {
  status: "need_clarification";
  explanation: string;
  choices: ResearchClarificationChoiceV1[];
}

export interface ResearchNoMatchV1 extends ResearchResultBaseV1 {
  status: "no_match";
  provenance: ResearchDataProvenanceV1;
  explanation: string;
}

export interface ResearchUnavailableV1 extends ResearchResultBaseV1 {
  status: "unavailable";
  reason_code: "operational_data_provenance_required";
  explanation: string;
  retryable: boolean;
}

export interface ResearchFailedV1 extends ResearchResultBaseV1 {
  status: "failed";
  support_reference: string;
  explanation: string;
  retryable: boolean;
}

export interface ResearchDevPreviewV1 extends ResearchResultBaseV1 {
  status: "dev_preview";
  reason_code: "development_fixture_only";
  explanation: string;
}

export type ResearchResultV1 =
  | ResearchReadyV1
  | ResearchNeedClarificationV1
  | ResearchNoMatchV1
  | ResearchUnavailableV1
  | ResearchFailedV1
  | ResearchDevPreviewV1;
