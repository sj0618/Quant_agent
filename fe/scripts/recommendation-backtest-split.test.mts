import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path: string) => readFile(new URL(path, import.meta.url), "utf8");

test("the validation-period caption comes from the payload, never from a fixed string", async () => {
  const overview = await source("../src/features/app/OverviewTab.tsx");

  assert.match(overview, /const evaluationBasis = overview\.performance\.evaluationBasis/);
  assert.match(overview, /caption: insufficient[\s\S]{0,200}evaluationBasis\?\.caption/);
  // A run the backend evaluated with the rolling policy is not a hold-out tail, so the
  // client must not print either period as a constant.
  assert.doesNotMatch(overview, /마지막 30%/);
  assert.doesNotMatch(overview, /Walk-forward/);
  assert.doesNotMatch(overview, /Sharpe \(홀드아웃\)/);
});

test("the screen and the backtest universe are explained where the candidates are listed", async () => {
  const overview = await source("../src/features/app/OverviewTab.tsx");

  assert.match(overview, /const universePolicy = overview\.performance\.universePolicy/);
  assert.match(overview, /universePolicy\.summary/);
  assert.match(overview, /universePolicy\.excluded_screening_candidate_count > 0/);
  assert.match(overview, /universePolicy\.excluded_notice/);
});

test("a WATCH row carries the reason the strategy is not acting on it", async () => {
  const [overview, signalCard] = await Promise.all([
    source("../src/features/app/OverviewTab.tsx"),
    source("../src/features/app/SignalCard.tsx"),
  ]);

  assert.match(overview, /tickerActionByTicker/);
  assert.match(overview, /tickerAction=\{tickerActionByTicker\.get\(candidate\.ticker\)\}/);
  assert.match(signalCard, /tickerAction\.action/);
  assert.match(signalCard, /tickerAction\.reason/);
});

test("an unfinished verification is not shown as a passed one", async () => {
  const overview = await source("../src/features/app/OverviewTab.tsx");

  assert.match(overview, /gate\?\.verification_complete === false/);
  assert.match(overview, /caption: gate\?\.reason/);
  assert.match(overview, /검증 미완료/);
  // "did not clear the objective floor" was printed for runs blocked on a benchmark
  // series that was never loaded. The reason now comes from the graph.
  assert.doesNotMatch(overview, /백테스트 목표 기준 미달/);
});

test("the demo fixture never claims a period or a benchmark the backend does not report", async () => {
  const mock = await source("../src/mocks/app.mock.ts");

  assert.match(mock, /evaluationBasis: AIBacktestEvaluationBasis/);
  assert.match(mock, /basis: "hold_out"/);
  assert.match(mock, /krx_pit_common_stock_5y_kst_settled_session_v2/);
  assert.match(mock, /universePolicy: AIBacktestUniversePolicy/);
  assert.match(mock, /verification_complete: false/);
  // Copy for validations this engine has never run, and a ten-year window the
  // five-year point-in-time policy cannot produce.
  assert.doesNotMatch(mock, /Walk-forward .* 윈도우 평균/);
  assert.doesNotMatch(mock, /10y|10년 누적/);
  assert.doesNotMatch(mock, /2016/);
});
