import type { BacktestMetric } from "../../types/quantagent";

export interface MetricDisplay {
  isUnavailable: boolean;
  value: string;
  reason: string | null;
  source: string;
  asOf: string;
}

const SOURCE_LABELS = {
  fixture: "예시 데이터",
  postgres: "PostgreSQL 실데이터",
  unknown: "출처 미확인",
} as const;

const NON_FINITE_VALUE = /^[+-]?\s*(?:nan|infinity|∞)\s*[%x×]?$/iu;

export function isFiniteMetricValue(value: string | undefined): boolean {
  const normalized = value?.trim() ?? "";
  return Boolean(normalized) && !NON_FINITE_VALUE.test(normalized);
}

/**
 * Keep the display decision in one place so a stale, fixture, or non-finite metric
 * cannot be relabelled as a usable number by a future card variant.
 */
export function metricDisplay(metric: BacktestMetric): MetricDisplay {
  const source = metric.source === "postgres"
    ? "postgres"
    : metric.source === "fixture"
      ? "fixture"
      : "unknown";
  const isNonFinite = !isFiniteMetricValue(metric.value);
  const hasCurrentFreshness = metric.freshness === "eod_current";
  const hasVerifiedAsOf = Boolean(metric.asOf?.trim());
  const isUnavailable = metric.availability === "unavailable"
    || source !== "postgres"
    || !hasCurrentFreshness
    || !hasVerifiedAsOf
    || isNonFinite;

  if (!isUnavailable) {
    return {
      isUnavailable: false,
      value: metric.value,
      reason: null,
      source: SOURCE_LABELS[source],
      asOf: metric.asOf ?? "기준일 미확인",
    };
  }

  return {
    isUnavailable: true,
    value: "검증 불가",
    reason: unavailableReason(metric, { isNonFinite, hasCurrentFreshness, hasVerifiedAsOf, source }),
    source: SOURCE_LABELS[source],
    asOf: metric.asOf ?? "기준일 미확인",
  };
}

function unavailableReason(
  metric: BacktestMetric,
  context: {
    isNonFinite: boolean;
    hasCurrentFreshness: boolean;
    hasVerifiedAsOf: boolean;
    source: keyof typeof SOURCE_LABELS;
  },
): string {
  if (metric.unavailableReason?.trim()) {
    return metric.unavailableReason;
  }
  if (context.isNonFinite) {
    return "유한한 수치가 아니라 표시하지 않습니다.";
  }
  if (!context.hasCurrentFreshness) {
    return "기준일이 최신 상태인지 확인할 수 없어 수치를 표시하지 않습니다.";
  }
  if (!context.hasVerifiedAsOf) {
    return "기준일이 없어 수치를 표시하지 않습니다.";
  }
  if (context.source === "fixture") {
    return "예시 데이터는 운영 성과 수치로 표시하지 않습니다.";
  }
  return "검증 가능한 출처가 없어 수치를 표시하지 않습니다.";
}
