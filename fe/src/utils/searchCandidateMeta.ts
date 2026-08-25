import type { TradingCandidate } from "../types/quantagent";

export function formatTradingCandidateMeta(candidate: Pick<TradingCandidate, "signal" | "confidence" | "price">) {
  const parts = [
    candidate.signal,
    typeof candidate.confidence === "number" ? candidate.confidence.toFixed(1) : undefined,
    candidate.price,
  ];

  return parts.filter((part): part is string => part !== undefined && part !== "").join(" · ");
}
