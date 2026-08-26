import assert from "node:assert/strict";
import test from "node:test";

import { workspaceOverviewFromJob } from "../src/features/app/strategyWorkspaceMapper.ts";
import type { AIPublicPerformance, AnalysisJob } from "../src/types/quantagent.ts";

function jobWithPerformance(performance: AIPublicPerformance): AnalysisJob {
  return {
    job_id: "job-core-test",
    trace_id: "trace-core-test",
    query: "RSI 30 이하 진입, 70 이상 청산 전략을 검증해줘",
    created_at: "2026-08-26T00:00:00Z",
    updated_at: "2026-08-26T00:01:00Z",
    stages: [],
    result: {
      status: "ready",
      trace_id: "trace-core-test",
      schema_version: "ai-mvp.v1",
      debug_ref: "debug:core-test",
      retryable: false,
      strategy_spec: null,
      user_payload: {
        headline: "전략 분석 완료",
        message: "검증 결과를 확인하세요.",
        next_actions: [],
        candidate_cards: [{
          strategy_id: "strategy-1",
          title: "RSI 전략",
          summary: "RSI 조건을 검증했습니다.",
          key_conditions: ["RSI 30/70"],
          confidence: 0.8,
          matches: [{ ticker: "005930", name: "테스트 종목", market: "KRX", as_of_date: "2026-08-25", close: 70_000, matched_rules: [] }],
        }],
        report: null,
        performance,
        ticker_actions: [{ ticker: "005930", name: "테스트 종목", action: "BUY", reason: "전략 조건 충족", as_of_date: "2026-08-25", close: 70_000 }],
      },
    },
  };
}

const basePerformance = {
  selected_candidate_id: "strategy-1",
  metrics: { sharpe_ratio: 1.1, max_drawdown: -0.12, win_rate: 0.55, total_return: 0.12, in_sample_sharpe: 1.2, out_sample_sharpe: 1.0, degradation: 0.2 },
  equity_curve: [{ date: "2026-01-02", cumulative_return: 0 }, { date: "2026-08-25", cumulative_return: 0.12 }],
  reliability: { source: "postgres" as const, status: "sufficient" as const, row_count: 300, ticker_count: 20, trading_days: 160, history_start: "2026-01-02", history_end: "2026-08-25", trade_count: 18, reasons: [], warnings: [] },
  metric_details: [{ key: "total_return", label: "누적 수익률", value: 0.12, unit: "percent", is_available: true, unavailable_reason: null, plain_explanation: "기간 누적 수익률", why_used: "전략 성과", caution: "과거 성과", source_refs: [] }],
};

test("fixture-originated payload never becomes a workspace performance or action result", () => {
  const overview = workspaceOverviewFromJob(jobWithPerformance({
    availability: "available",
    performance: { ...basePerformance, reliability: { ...basePerformance.reliability, source: "fixture" } },
    method_manifest: { start_date: "2026-01-02", end_date: "2026-08-25", data_version: "fixture-v1", result_version: "r1", execution_version: "e1", historical_simulation_warning: "과거 시뮬레이션" },
    limitations: [],
  }));

  assert.equal(overview.performance.metrics.length, 0);
  assert.equal(overview.candidates.length, 0);
  assert.equal(overview.tickerActions?.length, 0);
  assert.match(overview.performance.disclaimer, /fixture/);
});

test("verified PostgreSQL public performance supplies the workspace result", () => {
  const overview = workspaceOverviewFromJob(jobWithPerformance({
    availability: "available",
    performance: basePerformance,
    method_manifest: { start_date: "2026-01-02", end_date: "2026-08-25", data_version: "postgres-eod-v1", result_version: "r1", execution_version: "e1", historical_simulation_warning: "과거 시뮬레이션" },
    limitations: ["표본 해석에 주의하세요."],
  }));

  assert.equal(overview.performance.metrics[0]?.value, "+12.00%");
  assert.equal(overview.candidates.length, 1);
  assert.equal(overview.candidates[0]?.signal, "BUY");
  assert.equal(overview.tickerActions?.[0]?.action, "BUY");
});
