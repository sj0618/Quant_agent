import assert from "node:assert/strict";
import test from "node:test";

import { DEFAULT_REPORT_FILTERS, applyReportFilters, getReportStrategyNames, type ReportFilters } from "../src/features/reports/reportFilters.ts";
import type { ReportSummary } from "../src/types/quantagent.ts";

function makeReport(index: number, overrides: Partial<ReportSummary> = {}): ReportSummary {
  const day = String(25 - index).padStart(2, "0");
  return {
    id: `6389fb5d-0850-5c3e-88fd-ac66687ff75${index}`,
    date: `2026.07.${day}`,
    weekday: "금요일",
    sentAt: `오전 8:${String(index).padStart(2, "0")} 발송`,
    title: "RSI 과매도 반등 분석 결과",
    summary: `요약 ${index}`,
    status: "sent",
    strategyName: "",
    recommendationScore: "7.4",
    signals: { BUY: 2, HOLD: 1, DROP: 1 },
    marketSnapshot: [{ label: "KOSPI", value: "2,654.21 (+0.84%)" }],
    ...overrides,
  };
}

function makeReports(overrides: Array<Partial<ReportSummary>> = []) {
  return Array.from({ length: 5 }, (_, index) => makeReport(index, overrides[index] ?? {}));
}

test("reports list keeps five live rows when the backend supplies UUID ids and dotted display dates", () => {
  const reports = makeReports();
  const filters: ReportFilters = { ...DEFAULT_REPORT_FILTERS, range: "all", strategyName: "all" };

  assert.equal(applyReportFilters(reports, DEFAULT_REPORT_FILTERS).length, 5);
  assert.equal(applyReportFilters(reports, filters).length, 5);
});

test("reports with zero signal counts remain visible by default", () => {
  const reports = makeReports(Array.from({ length: 5 }, () => ({ signals: { BUY: 0, HOLD: 0, DROP: 0 } })));
  const filters: ReportFilters = { ...DEFAULT_REPORT_FILTERS, range: "all", strategyName: "all" };

  assert.equal(applyReportFilters(reports, filters).length, 5);
});

test("missing strategy labels are neutralized instead of rendering prompt labels", () => {
  const reports = makeReports();
  const invalidStrategyFilters: ReportFilters = {
    ...DEFAULT_REPORT_FILTERS,
    range: "all",
    strategyName: "Run a new live analysis for Samsung Electronics (005930) using live data.",
  };

  assert.deepEqual(getReportStrategyNames(reports), []);
  assert.equal(applyReportFilters(reports, invalidStrategyFilters).length, 5);
});

test("meaningful strategy labels remain deduplicated when present", () => {
  const reports = makeReports([
    { strategyName: "반도체 모멘텀 + 기관 매수" },
    { strategyName: "반도체 모멘텀 + 기관 매수" },
    { strategyName: "배당 방어주 로테이션" },
  ]);

  assert.deepEqual(getReportStrategyNames(reports), ["반도체 모멘텀 + 기관 매수", "배당 방어주 로테이션"]);
});
