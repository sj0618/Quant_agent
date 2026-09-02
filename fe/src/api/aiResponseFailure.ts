type JsonObject = Record<string, unknown>;

export interface PublicAiResponseFailure {
  message: string | null;
  reasonCode: string | null;
}

const PUBLIC_REASON_MESSAGES: Readonly<Record<string, string>> = {
  analysis_execution_unavailable: "실데이터 전략 분석 실행 준비가 완료되지 않았습니다. 잠시 후 다시 시도해 주세요.",
  exploration_policy_unavailable: "전략 탐색 정책을 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.",
  personalized_investment_request: "개인 보유·계좌·주문을 전제로 한 요청은 처리할 수 없습니다. 일반적인 전략 조건으로 다시 입력해 주세요.",
  request_validation_failed: "전략 입력 형식을 서버가 읽지 못했습니다. 화면을 새로고침한 뒤 다시 시도해 주세요.",
  strategy_research_unavailable: "전략 의미를 해석하는 AI 리서치가 준비되지 않았습니다. 잠시 후 다시 시도해 주세요.",
  unsupported_asset_family: "이 자산군은 현재 전략 검증 범위에서 지원하지 않습니다.",
  unsupported_scope: "이 전략은 현재 전략 검증 범위에서 지원하지 않습니다.",
};

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function validationField(detail: unknown): string | null {
  if (!Array.isArray(detail)) return null;
  const location = detail
    .map((item) => (isObject(item) && Array.isArray(item.loc) ? item.loc : []))
    .flat()
    .filter((item): item is string => typeof item === "string");
  return location.find((item) => item !== "body") ?? null;
}

function reasonCodeFrom(payload: JsonObject): string | null {
  const detail = isObject(payload.detail) ? payload.detail : null;
  const candidate =
    nonEmptyString(payload.reason_code) ??
    nonEmptyString(payload.code) ??
    (detail ? nonEmptyString(detail.reason_code) ?? nonEmptyString(detail.code) : null);
  return candidate && Object.hasOwn(PUBLIC_REASON_MESSAGES, candidate) ? candidate : null;
}

function genericMessage(status: number): string {
  if (status === 401) return "로그인 상태를 확인한 뒤 전략 검증을 다시 시도해 주세요.";
  if (status === 403) return "이 전략 검증 요청에 대한 권한이 없습니다.";
  if (status === 409) return "전략 초안이 변경되었거나 만료되었습니다. 다시 해석해 주세요.";
  if (status === 422) return "전략 입력 형식을 서버가 읽지 못했습니다. 화면을 새로고침한 뒤 다시 시도해 주세요.";
  if (status >= 500) return "AI 전략 검증 서버가 일시적으로 응답하지 않습니다. 잠시 후 다시 시도해 주세요.";
  return "전략 검증 요청을 처리하지 못했습니다. 다시 시도해 주세요.";
}

/**
 * Turn a public FastAPI failure body into a message that is useful to a user
 * without echoing their strategy text, a token, or a provider/DB error.  The
 * matching reason code remains available for safe browser diagnostics.
 */
export function publicAiResponseFailure(status: number, payload: unknown): PublicAiResponseFailure {
  if (!isObject(payload)) return { message: genericMessage(status), reasonCode: null };

  const reasonCode = reasonCodeFrom(payload);
  if (reasonCode) return { message: PUBLIC_REASON_MESSAGES[reasonCode], reasonCode };

  const detail = payload.detail;
  if (status === 422 && Array.isArray(detail)) {
    const field = validationField(detail);
    return {
      message: field
        ? `전략 입력의 ${field} 항목을 서버가 읽지 못했습니다. 화면을 새로고침한 뒤 다시 시도해 주세요.`
        : genericMessage(status),
      reasonCode: "request_validation_failed",
    };
  }

  // Never render upstream explanations/detail strings.  Audit DBs retain raw
  // diagnostics under controlled access; the browser receives only this
  // allow-listed, strategy-text-free projection.
  return { message: genericMessage(status), reasonCode: null };
}
