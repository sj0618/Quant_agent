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

test("a recommendation score never shows a numeric grade for a run the gate rejected", async () => {
  const adapter = await source("../src/api/quantAgentClient.ts");

  // One shared label, used at both places that turn a confidence into a recommendation
  // score, so "10.0 / 10" can never be printed for a strategy the gate marked unvalidated -
  // and the fallback is a conclusion ("보류"), never a blank string or "산출 안 함".
  assert.match(adapter, /const RECOMMENDATION_SCORE_HOLD_LABEL = "보류";/);
  assert.doesNotMatch(adapter, /산출 안 함/);
  const holdLabelUses = adapter.match(/RECOMMENDATION_SCORE_HOLD_LABEL/g) ?? [];
  assert.ok(holdLabelUses.length >= 3, "expected the shared label declared once and used at both score builders");
  assert.match(adapter, /gateValidated\s*=\s*result\?\.user_payload\.recommendation_gate\?\.validated\s*\?\?\s*true/);
  assert.match(adapter, /gateValidated\s*=\s*result\.user_payload\.recommendation_gate\?\.validated\s*\?\?\s*true/);
});

test("overview total return and Sharpe tiles read the same out-of-sample figures as the chart", async () => {
  const overview = await source("../src/features/app/OverviewTab.tsx");

  assert.match(overview, /검증 구간\(OOS\) 누적 수익률/);
  assert.match(overview, /Sharpe \(Walk-forward OOS\)/);
  // The total-return tile must prefer the chart's own `strategyReturn` (the out-of-sample
  // equity curve) over the whole-period metric card - that priority inversion is what let
  // the tile disagree with the chart in the first place.
  assert.match(overview, /strategyReturn !== undefined\s*\n?\s*\?\s*formatPercentValue\(strategyReturn\)\s*\n?\s*:\s*totalReturnMetric\?\.value/);
  assert.match(overview, /metricByKey\(overview, "out_sample_sharpe"\)/);
  assert.match(overview, /overview\.performance\.outOfSampleMaxDrawdown/);
});

test("overview chart renders the full out-of-sample curve, not just the last 5 points", async () => {
  const overview = await source("../src/features/app/OverviewTab.tsx");

  const capMatch = overview.match(/CHART_POINT_LIMIT\s*=\s*(\d+)/);
  assert.ok(capMatch, "expected a named point cap for the overview equity curve");
  const cap = Number(capMatch![1]);
  // An 81-point out-of-sample curve (a typical walk-forward window) must not be truncated
  // down to the 5-point stub the tile used to draw.
  assert.ok(cap > 81, `cap (${cap}) must exceed a typical 81-point OOS curve so it isn't truncated`);
  assert.match(overview, /equityCurve\.slice\(-CHART_POINT_LIMIT\)/);
  assert.doesNotMatch(overview, /equityCurve\.slice\(-5\)/);
});

test("win rate never carries a +/- sign and a zero degradation card is hidden", async () => {
  const adapter = await source("../src/api/quantAgentClient.ts");

  assert.match(adapter, /formatPercent\(detail\.value as number, detail\.key !== "win_rate"\)/);
  assert.match(adapter, /formatPercent\(selected\.win_rate, false\)/);
  assert.match(adapter, /detail\.key === "degradation" && detail\.value === 0/);
  assert.match(adapter, /function formatPercent\(value: number, signed = true\)/);
});

test("the performance tab's metric cards are captioned as whole-period, selected-candidate numbers", async () => {
  const performance = await source("../src/features/app/PerformanceTab.tsx");

  assert.match(performance, /선택 후보 전체 구간 기준/);
});
