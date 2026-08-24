import assert from "node:assert/strict";
import test from "node:test";

import { DEFAULT_REPORT_FILTERS, applyReportFilters, type ReportFilters } from "../src/features/reports/reportFilters.ts";
import type { ArchivedReportSummary } from "../src/types/quantagent.ts";

function makeReport(index: number, overrides: Partial<ArchivedReportSummary> = {}): ArchivedReportSummary {
  const day = String(25 - index).padStart(2, "0");
  return {
    id: `6389fb5d-0850-5c3e-88fd-ac66687ff75${index}`,
    date: `2026.07.${day}`,
    weekday: "금요일",
    sentAt: `오전 8:${String(index).padStart(2, "0")} 발송`,
    createdAt: `2026-07-${day}T08:00:00Z`,
    status: "sent",
    ...overrides,
  };
}

function makeReports(overrides: Array<Partial<ArchivedReportSummary>> = []) {
  return Array.from({ length: 5 }, (_, index) => makeReport(index, overrides[index] ?? {}));
}

test("reports list keeps five read-only snapshots when the backend supplies UUID ids and dotted display dates", () => {
  const reports = makeReports();
  const filters: ReportFilters = { ...DEFAULT_REPORT_FILTERS, range: "all" };

  assert.equal(applyReportFilters(reports, DEFAULT_REPORT_FILTERS).length, 5);
  assert.equal(applyReportFilters(reports, filters).length, 5);
});

test("archive filtering uses only reader-safe lifecycle fields", () => {
  const reports = makeReports(Array.from({ length: 5 }, () => ({ status: "sent" })));
  const filters: ReportFilters = { ...DEFAULT_REPORT_FILTERS, range: "all" };

  assert.equal(applyReportFilters(reports, filters).length, 5);
});

test("archive filtering keeps an unknown record only in an unbounded archive view", () => {
  const unknownTimestamp = makeReport(1, {
    createdAt: undefined,
    date: "2026.08.24",
    sentAt: "2026-08-24T07:05:00Z",
    publishedAt: "2026-08-24T07:00:00Z",
    updatedAt: "2026-08-24T08:00:00Z",
  });

  assert.deepEqual(
    applyReportFilters([unknownTimestamp], { ...DEFAULT_REPORT_FILTERS, range: "all" }).map((report) => report.id),
    [unknownTimestamp.id],
  );
  assert.deepEqual(applyReportFilters([unknownTimestamp], DEFAULT_REPORT_FILTERS), []);
  assert.deepEqual(
    applyReportFilters([unknownTimestamp], { ...DEFAULT_REPORT_FILTERS, range: "all", startDate: "2026-08-01" }),
    [],
  );
});

test("archive filtering does not use legacy strategy labels", () => {
  const reports = makeReports();
  const filters: ReportFilters = { ...DEFAULT_REPORT_FILTERS, range: "all" };

  assert.equal(applyReportFilters(reports, filters).length, 5);
});
