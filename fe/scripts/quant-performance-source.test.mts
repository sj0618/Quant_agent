import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path: string) => readFile(new URL(path, import.meta.url), "utf8");

test("read-only reports never fall back to demo numbers or expose legacy performance fields", async () => {
  const [adapter, reportDetail] = await Promise.all([
    source("../src/api/quantAgentClient.ts"),
    source("../src/features/reports/ReportDetail.tsx"),
  ]);

  assert.match(adapter, /backendRequest/);
  assert.match(reportDetail, /READER_EVIDENCE_SECTION_TITLES/);
  assert.doesNotMatch(adapter, /BASELINE_RETURN_PERCENT/);
  assert.doesNotMatch(adapter, /\+92\.4/);
  assert.doesNotMatch(reportDetail, /\+92\.4|Sharpe 1\.42/);
  assert.doesNotMatch(reportDetail, /report\.performance|recommendationScore|report\.signals|report\.candidates/);
});

test("benchmark series requires an available real curve and never a zero placeholder", async () => {
  const [overview, performance] = await Promise.all([
    source("../src/features/app/OverviewTab.tsx"),
    source("../src/features/app/PerformanceTab.tsx"),
  ]);

  assert.match(performance, /hasBenchmarkSeries/);
  assert.match(overview, /benchmark\?\.is_available === true/);
  assert.match(performance, /benchmark\?\.is_available === true/);
  assert.doesNotMatch(`${overview}\n${performance}`, /point\.benchmark !== 0/);
  assert.doesNotMatch(`${overview}\n${performance}`, /\?\? "KOSPI200"/);
});

test("insufficient reliability hides numbers and explains sample limits", async () => {
  const performance = await source("../src/features/app/PerformanceTab.tsx");

  assert.match(performance, /표본이 너무 작아 수익률·샤프·낙폭 같은 숫자를 숨겼습니다/);
  assert.match(performance, /row_count/);
  assert.match(performance, /ticker_count/);
  assert.match(performance, /trading_days/);
  assert.match(performance, /trade_count/);
  assert.match(performance, /reliability\.reasons/);
});

test("metric and strategy explanations expose cautions and source links", async () => {
  const [metricCard, performance] = await Promise.all([
    source("../src/features/app/MetricCard.tsx"),
    source("../src/features/app/PerformanceTab.tsx"),
  ]);

  assert.match(metricCard, /왜 이 지표를 보나요/);
  assert.match(metricCard, /metric\.whyUsed/);
  assert.match(metricCard, /metric\.caution/);
  assert.match(metricCard, /target="_blank"/);
  assert.match(performance, /왜 이 전략인가요/);
  assert.match(performance, /strategyExplanation\.indicators/);
  assert.match(performance, /indicator\.source_refs/);
});

test("archived reports render only the reader-safe metric and replay evidence contract", async () => {
  const reportDetail = await source("../src/features/reports/ReportDetail.tsx");

  assert.match(reportDetail, /readerEvidenceSections/);
  assert.match(reportDetail, /reproduction_contract/);
  assert.match(reportDetail, /metric_registry/);
  assert.match(reportDetail, /검증 재현 계약/);
  assert.match(reportDetail, /section\.entries/);
  assert.doesNotMatch(reportDetail, /implementation_source|implementation_path|price_rows|raw_rows/);
});

test("generated strategies stay visible as pre-backtest blueprints with derivations", async () => {
  const performance = await source("../src/features/app/PerformanceTab.tsx");

  assert.match(performance, /strategyExplanation\?\.generated_strategies/);
  assert.match(performance, /generatedStrategies\.map/);
  assert.match(performance, /blueprint\.formula/);
  assert.match(performance, /blueprint\.derivation/);
  assert.match(performance, /blueprint\.why_generated/);
  assert.match(performance, /indicator\.customization/);
});
