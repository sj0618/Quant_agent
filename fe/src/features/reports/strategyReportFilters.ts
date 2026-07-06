import type { SignalType, StrategyReportSummary } from "../../types/quantagent";

export type StrategyReportRange = "1" | "7" | "30" | "90" | "all";

export interface StrategyReportFilters {
  range: StrategyReportRange;
  signals: Record<SignalType, boolean>;
  minScore: number;
}

export const DEFAULT_STRATEGY_REPORT_FILTERS: StrategyReportFilters = {
  range: "7",
  signals: { BUY: true, HOLD: true, DROP: true },
  minScore: 0,
};

const SIGNALS: SignalType[] = ["BUY", "HOLD", "DROP"];

function parseDate(value: string) {
  const normalized = value.replace(/\./g, "-").trim();
  const time = Date.parse(normalized);
  return Number.isNaN(time) ? null : new Date(time);
}

function latestStrategyDate(strategy: StrategyReportSummary) {
  return parseDate(strategy.latestReportDate);
}

function diffDays(from: Date, to: Date) {
  const millisecondsPerDay = 24 * 60 * 60 * 1000;
  return Math.floor((to.getTime() - from.getTime()) / millisecondsPerDay);
}

export function parseStrategyReportFilters(search: string): StrategyReportFilters {
  const params = new URLSearchParams(search);
  const range = params.get("range");
  const signals = params.get("signals")?.split(",").filter(Boolean) as SignalType[] | undefined;
  const minScore = Number(params.get("minScore") ?? DEFAULT_STRATEGY_REPORT_FILTERS.minScore);

  return {
    range:
      range === "1" || range === "7" || range === "30" || range === "90" || range === "all"
        ? range
        : DEFAULT_STRATEGY_REPORT_FILTERS.range,
    signals: {
      BUY: signals ? signals.includes("BUY") : DEFAULT_STRATEGY_REPORT_FILTERS.signals.BUY,
      HOLD: signals ? signals.includes("HOLD") : DEFAULT_STRATEGY_REPORT_FILTERS.signals.HOLD,
      DROP: signals ? signals.includes("DROP") : DEFAULT_STRATEGY_REPORT_FILTERS.signals.DROP,
    },
    minScore: Number.isFinite(minScore) ? minScore : DEFAULT_STRATEGY_REPORT_FILTERS.minScore,
  };
}

export function serializeStrategyReportFilters(filters: StrategyReportFilters) {
  const params = new URLSearchParams();
  if (filters.range !== DEFAULT_STRATEGY_REPORT_FILTERS.range) params.set("range", filters.range);

  const selectedSignals = SIGNALS.filter((signal) => filters.signals[signal]);
  if (selectedSignals.length !== SIGNALS.length) params.set("signals", selectedSignals.join(","));
  if (filters.minScore > DEFAULT_STRATEGY_REPORT_FILTERS.minScore) params.set("minScore", String(filters.minScore));
  return params.toString();
}

export function applyStrategyReportFilters(strategies: StrategyReportSummary[], filters: StrategyReportFilters) {
  const latestDate = strategies
    .map(latestStrategyDate)
    .filter((value): value is Date => value instanceof Date)
    .sort((left, right) => right.getTime() - left.getTime())[0];

  return strategies.filter((strategy) => {
    const strategyDate = latestStrategyDate(strategy);
    if (!strategyDate) return false;
    if (latestDate && filters.range !== "all" && diffDays(strategyDate, latestDate) >= Number(filters.range)) return false;
    if (Number(strategy.recommendationScore) < filters.minScore) return false;
    if (!SIGNALS.some((signal) => filters.signals[signal] && strategy.signals[signal] > 0)) return false;
    return true;
  });
}
