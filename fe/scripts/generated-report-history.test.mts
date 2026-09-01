import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

import { parseAnalysisReportJobId } from "../src/config/routes.ts";
import type { AIPublicPerformance, AnalysisJob } from "../src/types/quantagent.ts";

type GeneratedReportListModule = typeof import("../src/features/reports/GeneratedReportList.tsx");
type AnalysisReportDetailModule = typeof import("../src/features/reports/AnalysisReportDetail.tsx");

const basePerformance = {
  selected_candidate_id: "rsi-1",
  metrics: { sharpe_ratio: 1.1, max_drawdown: -0.12, win_rate: 0.55, total_return: 0.12, in_sample_sharpe: 1.2, out_sample_sharpe: 1.0, degradation: 0.2 },
  equity_curve: [{ date: "2026-01-02", cumulative_return: 0 }, { date: "2026-08-25", cumulative_return: 0.12 }],
  reliability: { source: "postgres" as const, status: "sufficient" as const, row_count: 300, ticker_count: 20, trading_days: 160, history_start: "2026-01-02", history_end: "2026-08-25", trade_count: 18, reasons: [], warnings: [] },
  metric_details: [{ key: "total_return", label: "누적 수익률", value: 0.12, unit: "percent", is_available: true, unavailable_reason: null, plain_explanation: "기간 누적 수익률", why_used: "전략 성과", caution: "과거 성과", source_refs: [] }],
};

function completedJob(performance: AIPublicPerformance): AnalysisJob {
  return {
    job_id: "job-rsi-report",
    trace_id: "trace-rsi-report",
    query: "KRX 일봉에서 RSI 30 이하 진입, 70 이상 청산",
    created_at: "2026-08-25T00:00:00Z",
    updated_at: "2026-08-25T00:01:00Z",
    stages: [],
    result: {
      status: "ready",
      trace_id: "trace-rsi-report",
      schema_version: "ai-mvp.v1",
      debug_ref: "debug:report-test",
      retryable: false,
      strategy_spec: {
        strategy_id: "rsi-1",
        name: "RSI 역추세 전략",
        market: "KRX",
        timeframe: "daily",
        entry_conditions: [{ left: "RSI", operator: "lte", right: 30 }],
        exit_conditions: [{ left: "RSI", operator: "gte", right: 70 }],
        indicators: ["RSI"],
        risk_constraints: {},
        assumptions: [],
        source_refs: [],
        confidence: 0.8,
      },
      user_payload: {
        headline: "RSI 전략 분석 완료",
        message: "검증 결과를 확인하세요.",
        next_actions: [],
        candidate_cards: [],
        report: {
          web_projection: { title: "RSI 전략 리포트", summary: "실데이터 기반 백테스트 결과입니다.", sections: [] },
          email_projection: { title: "RSI 전략 리포트", summary: "실데이터 기반 백테스트 결과입니다.", sections: [] },
          risk_adjustments: [],
        },
        performance,
      },
    },
  };
}

async function renderHistory(jobs: AnalysisJob[]) {
  const vite = await createServer({
    configFile: new URL("../vite.config.ts", import.meta.url).pathname,
    root: new URL("..", import.meta.url).pathname,
    logLevel: "error",
    server: { middlewareMode: true, hmr: false },
    optimizeDeps: { noDiscovery: true },
  });
  try {
    const module = await vite.ssrLoadModule("/src/features/reports/GeneratedReportList.tsx") as GeneratedReportListModule;
    return renderToStaticMarkup(createElement(module.GeneratedReportList, { jobs }));
  } finally {
    await vite.close();
  }
}

async function renderDetail(job: AnalysisJob) {
  const vite = await createServer({
    configFile: new URL("../vite.config.ts", import.meta.url).pathname,
    root: new URL("..", import.meta.url).pathname,
    logLevel: "error",
    server: { middlewareMode: true, hmr: false },
    optimizeDeps: { noDiscovery: true },
  });
  try {
    const module = await vite.ssrLoadModule("/src/features/reports/AnalysisReportDetail.tsx") as AnalysisReportDetailModule;
    return renderToStaticMarkup(createElement(module.AnalysisReportDetail, { job }));
  } finally {
    await vite.close();
  }
}

test("generated report history renders the durable PostgreSQL terminal result as a report", async () => {
  const markup = await renderHistory([completedJob({
    availability: "available",
    performance: basePerformance,
    method_manifest: { start_date: "2026-01-02", end_date: "2026-08-25", data_version: "postgres-eod-v1", result_version: "r1", execution_version: "e1", historical_simulation_warning: "과거 시뮬레이션" },
    limitations: [],
  })]);

  assert.match(markup, /생성된 전략 리포트/);
  assert.match(markup, /RSI 전략 리포트/);
  assert.match(markup, /PostgreSQL EOD/);
  assert.match(markup, /\+12\.00%/);
  assert.match(markup, /\/reports\/analysis%3Ajob-rsi-report/);
});

test("generated report history does not turn a fixture terminal result into a performance report", async () => {
  const fixtureJob = completedJob({
    availability: "available",
    performance: { ...basePerformance, reliability: { ...basePerformance.reliability, source: "fixture" } },
    method_manifest: { start_date: "2026-01-02", end_date: "2026-08-25", data_version: "fixture-v1", result_version: "r1", execution_version: "e1", historical_simulation_warning: "과거 시뮬레이션" },
    limitations: [],
  });
  const [listMarkup, detailMarkup] = await Promise.all([renderHistory([fixtureJob]), renderDetail(fixtureJob)]);

  for (const markup of [listMarkup, detailMarkup]) {
    assert.match(markup, /출처 확인 필요|검증 범위 확인이 필요한 전략 결과/);
    assert.doesNotMatch(markup, /\+12\.00%/);
    assert.doesNotMatch(markup, /실데이터 기반 백테스트 결과입니다/);
  }
});

test("generated-report route IDs are distinct from legacy archive IDs", () => {
  assert.equal(parseAnalysisReportJobId("analysis:job-rsi-report"), "job-rsi-report");
  assert.equal(parseAnalysisReportJobId("archive-001"), null);
  assert.equal(parseAnalysisReportJobId("analysis:bad/path"), null);
});
