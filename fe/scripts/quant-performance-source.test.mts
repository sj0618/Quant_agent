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

test("user_payload.performance is unwrapped from its availability envelope before use", async () => {
  const adapter = await source("../src/api/quantAgentClient.ts");

  // `user_payload.performance` is `{availability: "available", performance: {...}}` or
  // `{availability: "unavailable", reason_code}` on the wire, never the flat metrics
  // object directly - every reader must go through the unwrap helper or a completed job
  // with a real backtest curve reads as if it had none.
  assert.match(adapter, /function unwrapAIPerformance/);
  assert.match(adapter, /unwrapAIPerformance\(job\.result\?\.user_payload\.performance\)/);
  assert.match(adapter, /availability !== "available"/);
  assert.doesNotMatch(adapter, /const aiPerformance = job\.result\?\.user_payload\.performance;/);
});

test("a missed objective floor still shows the real recommendation score, not a placeholder", async () => {
  const overview = await source("../src/features/app/OverviewTab.tsx");

  assert.doesNotMatch(overview, /산출 안 함/);
  assert.match(overview, /백테스트 목표 기준 미달/);
  assert.match(overview, /참고용/);
  assert.match(overview, /overview\.performance\.limitations/);
});

test("ticker actions from the backtest render as reference picks even when the gate fails", async () => {
  const adapter = await source("../src/api/quantAgentClient.ts");

  assert.match(adapter, /function buildTradingCandidatesFromTickerActions/);
  assert.match(adapter, /user_payload\.ticker_actions/);
  assert.match(adapter, /참고용/);
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

test("generated strategies stay visible as pre-backtest blueprints with derivations", async () => {
  const performance = await source("../src/features/app/PerformanceTab.tsx");

  assert.match(performance, /strategyExplanation\?\.generated_strategies/);
  assert.match(performance, /generatedStrategies\.map/);
  assert.match(performance, /blueprint\.formula/);
  assert.match(performance, /blueprint\.derivation/);
  assert.match(performance, /blueprint\.why_generated/);
  assert.match(performance, /indicator\.customization/);
});
