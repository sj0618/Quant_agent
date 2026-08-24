import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createServer } from "vite";

const previewSource = (relativePath: string) => readFile(new URL(`../../backend/fe-api-preview/${relativePath}`, import.meta.url), "utf8");
const previewRoot = new URL("../../backend/fe-api-preview/", import.meta.url);

interface PreviewReportSummary {
  id: string;
  createdAt?: string;
  date: string;
  weekday: string;
  sentAt: string;
  title: string;
  summary: string;
  status: "sent" | "draft" | "failed";
  strategyName: string;
  recommendationScore: string;
  signals: { BUY: number; HOLD: number; DROP: number };
  marketSnapshot: never[];
}

async function loadPreviewArchiveModules() {
  const vite = await createServer({
    configFile: new URL("vite.config.ts", previewRoot).pathname,
    root: previewRoot.pathname,
    logLevel: "error",
    server: { middlewareMode: true, hmr: false },
    optimizeDeps: { noDiscovery: true },
  });
  try {
    const [actions, filters] = await Promise.all([
      vite.ssrLoadModule("/src/api/reportActionsClient.ts"),
      vite.ssrLoadModule("/src/features/reports/reportFilters.ts"),
    ]);
    return { actions, filters };
  } finally {
    await vite.close();
  }
}

function previewReport(overrides: Partial<PreviewReportSummary> = {}): PreviewReportSummary {
  return {
    id: "archive-001",
    createdAt: "2026-08-24T07:05:00Z",
    date: "2026.08.24",
    weekday: "월요일",
    sentAt: "2026-08-24T07:06:00Z",
    title: "legacy preview record",
    summary: "must not be exported",
    status: "sent",
    strategyName: "must not be exported",
    recommendationScore: "9.9",
    signals: { BUY: 3, HOLD: 2, DROP: 1 },
    marketSnapshot: [],
    ...overrides,
  };
}

test("retained legacy preview archive has no resend write path or obsolete config and uses explicit createdAt only", async () => {
  const [actions, config, list, detail, detailPage, types, canonicalConfig, canonicalEnv, previewEnv, readme] = await Promise.all([
    previewSource("src/api/reportActionsClient.ts"),
    previewSource("src/config/appConfig.ts"),
    previewSource("src/features/reports/ReportList.tsx"),
    previewSource("src/features/reports/ReportDetail.tsx"),
    previewSource("src/pages/ReportDetailPage.tsx"),
    previewSource("src/types/quantagent.ts"),
    readFile(new URL("../src/config/appConfig.ts", import.meta.url), "utf8"),
    readFile(new URL("../src/vite-env.d.ts", import.meta.url), "utf8"),
    previewSource("src/vite-env.d.ts"),
    readFile(new URL("../README.md", import.meta.url), "utf8"),
  ]);
  const archiveSurface = `${actions}\n${config}\n${list}\n${detail}\n${detailPage}`;

  assert.match(types, /createdAt\?: string/);
  assert.match(actions, /archiveTimestamp\(report: Pick<ReportSummary, "createdAt">\)/);
  assert.match(list, /archiveTimestamp\(report\)/);
  assert.match(detail, /archiveTimestamp\(report\)/);
  assert.match(archiveSurface, /보관 기록 시각/);
  assert.doesNotMatch(archiveSurface, /resendReportEmail|\/resend|재발송/);
  assert.doesNotMatch(actions, /fetch\(|recordDataSource|backendRequest/);
  assert.doesNotMatch(config, /REPORT_ACTION_ENDPOINTS|reportActionApiBaseUrl/);
  for (const source of [canonicalConfig, canonicalEnv, previewEnv, readme]) {
    assert.doesNotMatch(source, /VITE_REPORT_ACTION_API_BASE_URL|reportActionApiBaseUrl/);
  }
  assert.match(actions, /window\.print/);
  assert.match(actions, /navigator\.clipboard\.writeText/);
  assert.match(actions, /downloadTextFile/);
});

test("legacy preview filters and CSV fail closed to createdAt without hiding unknown records from all", async () => {
  const { actions, filters } = await loadPreviewArchiveModules();
  const knownTimestamp = previewReport();
  const unknownTimestamp = previewReport({
    id: "archive-unknown",
    createdAt: undefined,
    date: "2026.08.24",
    sentAt: "2026-08-24T07:06:00Z",
  });
  const reports = [knownTimestamp, unknownTimestamp];

  assert.deepEqual(
    filters.applyReportFilters(reports, { ...filters.DEFAULT_REPORT_FILTERS, range: "all" }).map((report: PreviewReportSummary) => report.id),
    [knownTimestamp.id, unknownTimestamp.id],
  );
  assert.deepEqual(
    filters.applyReportFilters(reports, { ...filters.DEFAULT_REPORT_FILTERS, range: "7" }).map((report: PreviewReportSummary) => report.id),
    [knownTimestamp.id],
  );
  assert.deepEqual(
    filters.applyReportFilters(reports, { ...filters.DEFAULT_REPORT_FILTERS, range: "all", startDate: "2026-08-01" }).map((report: PreviewReportSummary) => report.id),
    [knownTimestamp.id],
  );

  assert.equal(
    actions.buildReportsCsv(reports),
    [
      '"result_id","archived_date","created_at","status"',
      '"archive-001","2026.08.24","2026-08-24T07:05:00Z","sent"',
      '"archive-unknown","2026.08.24","보관 기록 시각 미확인","sent"',
    ].join("\n"),
  );
});
