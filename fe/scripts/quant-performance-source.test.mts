import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path: string) => readFile(new URL(path, import.meta.url), "utf8");

test("completed AI jobs never reuse demo performance numbers", async () => {
  const adapter = await source("../src/api/quantAgentClient.ts");

  assert.match(adapter, /buildUnavailableAiPerformanceSummary/);
  assert.match(adapter, /metrics:\s*\[\]/);
  assert.match(adapter, /equityCurve:\s*\[\]/);
  assert.doesNotMatch(adapter, /BASELINE_RETURN_PERCENT/);
  assert.doesNotMatch(adapter, /\+92\.4/);
});

test("benchmark series requires an available real curve and never a zero placeholder", async () => {
  const [adapter, overview, performance] = await Promise.all([
    source("../src/api/quantAgentClient.ts"),
    source("../src/features/app/OverviewTab.tsx"),
    source("../src/features/app/PerformanceTab.tsx"),
  ]);

  assert.match(adapter, /benchmark\?\.is_available/);
  assert.match(adapter, /benchmarkByDate/);
  assert.doesNotMatch(adapter, /benchmark:\s*0/);
  assert.doesNotMatch(adapter, /original:\s*0/);
  assert.match(overview, /benchmark\?\.is_available === true/);
  assert.match(performance, /benchmark\?\.is_available === true/);
  assert.doesNotMatch(`${overview}\n${performance}`, /point\.benchmark !== 0/);
  assert.doesNotMatch(`${adapter}\n${overview}\n${performance}`, /\?\? "KOSPI200"/);
});

test("insufficient reliability hides numbers and explains sample limits", async () => {
  const [adapter, performance] = await Promise.all([
    source("../src/api/quantAgentClient.ts"),
    source("../src/features/app/PerformanceTab.tsx"),
  ]);

  assert.match(adapter, /reliability\?\.status === "insufficient"/);
  assert.match(adapter, /isInsufficient\s*\?\s*\[\]/);
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
