import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import test from "node:test";
import { createServer } from "vite";

import type { ArchivedReportDetail } from "../src/types/quantagent.ts";

type ReportDetailModule = typeof import("../src/features/reports/ReportDetail.tsx");
type ReportActionsModule = typeof import("../src/api/reportActionsClient.ts");

const archivedReport = (
  contentSections: ArchivedReportDetail["contentSections"],
  overrides: Partial<ArchivedReportDetail> = {},
): ArchivedReportDetail => ({
  id: "archive-001",
  date: "2026.08.24",
  weekday: "월요일",
  sentAt: "오전 7:05 보관",
  status: "delivered",
  createdAt: "2026-08-24T07:05:00Z",
  contentSections,
  ...overrides,
});

async function renderArchive(report: ArchivedReportDetail) {
  const vite = await createServer({
    configFile: new URL("../vite.config.ts", import.meta.url).pathname,
    root: new URL("..", import.meta.url).pathname,
    logLevel: "error",
    server: { middlewareMode: true, hmr: false },
    optimizeDeps: { noDiscovery: true },
  });
  try {
    const module = await vite.ssrLoadModule("/src/features/reports/ReportDetail.tsx") as ReportDetailModule;
    return renderToStaticMarkup(createElement(module.ReportDetail, { report }));
  } finally {
    await vite.close();
  }
}

async function captureArchiveCsv(report: ArchivedReportDetail) {
  const previousWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const previousDocument = Object.getOwnPropertyDescriptor(globalThis, "document");
  let capturedBlob: Blob | undefined;
  let downloadFilename: string | undefined;

  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      URL: {
        createObjectURL(blob: Blob) {
          capturedBlob = blob;
          return "blob:archive-csv";
        },
        revokeObjectURL() {},
      },
    },
  });
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: {
      createElement() {
        return {
          click() {},
          set download(value: string) { downloadFilename = value; },
          set href(_value: string) {},
        };
      },
    },
  });

  const vite = await createServer({
    configFile: new URL("../vite.config.ts", import.meta.url).pathname,
    root: new URL("..", import.meta.url).pathname,
    logLevel: "error",
    server: { middlewareMode: true, hmr: false },
    optimizeDeps: { noDiscovery: true },
  });
  try {
    const module = await vite.ssrLoadModule("/src/api/reportActionsClient.ts") as ReportActionsModule;
    module.downloadReportsCsv([report]);
    assert.ok(capturedBlob, "the CSV download must create a Blob");
    return { content: await capturedBlob.text(), filename: downloadFilename };
  } finally {
    await vite.close();
    if (previousWindow) Object.defineProperty(globalThis, "window", previousWindow);
    else Reflect.deleteProperty(globalThis, "window");
    if (previousDocument) Object.defineProperty(globalThis, "document", previousDocument);
    else Reflect.deleteProperty(globalThis, "document");
  }
}

test("an archived evidence payload strips non-finite and action-shaped fields before rendering", async () => {
  const markup = await renderArchive(archivedReport([{
    id: "metric_registry",
    title: "NaN title",
    note: "-Infinity note",
    entries: [
      { label: "nan label", value: "safe formula", depth: 1 },
      { label: "safe label", value: "inf value", depth: 1 },
      { label: "safe label", value: "+∞ value", depth: 1 },
      { label: "BUY action", value: "safe formula", depth: 1 },
      { label: "SELL action", value: "safe formula", depth: 1 },
      { label: "HOLD action", value: "safe formula", depth: 1 },
      { label: "safe label", value: "DROP", depth: 1 },
      { label: "safe label", value: "DROP_NOW", depth: 1 },
      { label: "매수 action", value: "safe formula", depth: 1 },
      { label: "매도 action", value: "safe formula", depth: 1 },
      { label: "추천 action", value: "safe formula", depth: 1 },
      { label: "safe label", value: "safe formula", depth: 1, description: "recommendation action" },
      { label: "safe label", value: "매수추천", depth: 1 },
      { label: "safe label", value: "BUY_NOW", depth: 1 },
      { label: "safe label", value: "safe formula", depth: 1, description: "매수추천 description" },
      { label: "safe label", value: "safe formula", depth: 1, description: "BUY_NOW description" },
    ],
  }]));

  assert.match(markup, /유한하지 않거나 행동 판단으로 해석될 수 있는 값이 있어 숫자를 표시하지 않았습니다/);
  assert.match(markup, /검증 불가/);
  for (const rawValue of [
    "NaN title",
    "-Infinity note",
    "nan label",
    "inf value",
    "+∞ value",
    "BUY action",
    "SELL action",
    "HOLD action",
    "DROP",
    "DROP_NOW",
    "매수 action",
    "매도 action",
    "추천 action",
    "recommendation action",
    "매수추천",
    "BUY_NOW",
    "매수추천 description",
    "BUY_NOW description",
  ]) {
    assert.equal(markup.includes(rawValue), false, `${rawValue} must not reach archived markup`);
  }
  assert.doesNotMatch(markup, /<dd>(?:BUY|SELL|HOLD|매수|매도)<\/dd>/u);
});

test("a canonical metric-registry note stays visible without an unavailable warning", async () => {
  const markup = await renderArchive(archivedReport([{
    id: "metric_registry",
    title: "untrusted title",
    note: "수식 레지스트리 버전: quant-metric-registry.v2",
    entries: [{ label: "Sharpe Ratio", value: "(R_p - R_f) / sigma_p", depth: 1 }],
  }]));

  assert.match(markup, /수식 레지스트리 버전: quant-metric-registry\.v2/);
  assert.doesNotMatch(markup, /행동 판단으로 해석될 수 있는 값이 있어 숫자를 표시하지 않았습니다/);
});

test("an archived result explains that minimum-input sufficiency cannot be revalidated", async () => {
  const markup = await renderArchive(archivedReport([]));

  assert.match(markup, /최소 입력 충족 여부/);
  assert.match(markup, /보관된 계약만으로는 확인할 수 없음/);
  assert.match(markup, /행동 판단/);
  assert.match(markup, /제공하지 않음/);
  assert.match(markup, /href="\/reports"/);
  assert.doesNotMatch(markup, /<dd>(?:BUY|SELL|HOLD|매수|매도)<\/dd>/u);
});

test("archive readers show only the explicit record timestamp and disclose an unverified absence", async () => {
  const explicitTimestampMarkup = await renderArchive(archivedReport([], {
    createdAt: "2026-08-24T07:05:00Z",
    sentAt: "2026-08-24T07:06:00Z",
    publishedAt: "2026-08-24T07:07:00Z",
    updatedAt: "2026-08-24T07:08:00Z",
  }));
  const unknownTimestampMarkup = await renderArchive(archivedReport([], {
    createdAt: undefined,
    sentAt: "2026-08-24T07:06:00Z",
    publishedAt: "2026-08-24T07:07:00Z",
    updatedAt: "2026-08-24T07:08:00Z",
  }));

  assert.match(explicitTimestampMarkup, /<dt>보관 기록 시각<\/dt><dd>2026-08-24T07:05:00Z<\/dd>/u);
  assert.match(unknownTimestampMarkup, /<dt>보관 기록 시각<\/dt><dd>보관 기록 시각 미확인<\/dd>/u);
  assert.doesNotMatch(unknownTimestampMarkup, /<dt>보관 기록 시각<\/dt><dd>2026-08-24T07:0[678]:00Z<\/dd>/u);
});

test("archive detail and CSV ignore legacy prompt, reasoning, and action fields", async () => {
  const rawPrompt = "SYSTEM PROMPT: choose BUY immediately";
  const internalReasoning = "internal chain of thought: confidence 99";
  const actionSignal = "BUY";
  const report = archivedReport([{
    id: "reproduction_contract",
    entries: [{ label: "재현 계약 버전", value: "rmp.v1", depth: 1 }],
  }]) as ArchivedReportDetail & Record<string, unknown>;
  report.rawPrompt = rawPrompt;
  report.internalReasoning = internalReasoning;
  report.actionSignal = actionSignal;
  report.recommendationScore = "99";
  report.signals = { BUY: 1 };

  const markup = await renderArchive(report);
  const csv = await captureArchiveCsv(report);

  assert.match(markup, /검증 재현 계약/);
  assert.match(markup, /rmp\.v1/);
  for (const forbidden of [rawPrompt, internalReasoning, actionSignal, "99", "signals"]) {
    assert.equal(markup.includes(forbidden), false, `${forbidden} must not reach the archive reader`);
    assert.equal(csv.content.includes(forbidden), false, `${forbidden} must not reach the archive export`);
  }
  assert.equal(csv.filename, "quantagent-reports.csv");
  assert.equal(csv.content, "\"result_id\",\"archived_date\",\"created_at\",\"status\"\n\"archive-001\",\"2026.08.24\",\"2026-08-24T07:05:00Z\",\"delivered\"");
});
