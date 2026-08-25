import type { SignalType, TradingCandidate } from "../types/quantagent";

/** Per-signal totals across candidates that carry a signal of their own. */
export function countScoredSignals(
  candidates: TradingCandidate[],
): Record<SignalType, number> | null {
  const scored = candidates.filter(
    (candidate): candidate is TradingCandidate & { signal: SignalType } => candidate.signal !== undefined,
  );
  // Screening matches have no per-name signal, so a tally over them would report every name
  // as one verdict - the "HOLD 30" that made a strategy-level action look like 30 decisions.
  // Null tells the caller to leave the breakdown out rather than print zeros.
  if (!scored.length) {
    return null;
  }
  return scored.reduce(
    (counts, candidate) => ({ ...counts, [candidate.signal]: counts[candidate.signal] + 1 }),
    { BUY: 0, HOLD: 0, DROP: 0 },
  );
}
