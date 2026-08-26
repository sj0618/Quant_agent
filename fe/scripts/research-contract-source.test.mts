import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("ResearchResultV1 renderer and adapter handle only safe states without replacing the core workspace", async () => {
  const [adapter, fixtures, renderer, appPage, clientSource, configSource, types] = await Promise.all([
    readFile(new URL("../src/features/research-contract/researchResultAdapter.ts", import.meta.url), "utf8"),
    readFile(new URL("../src/features/research-contract/researchResultFixtures.ts", import.meta.url), "utf8"),
    readFile(new URL("../src/features/research-contract/ResearchResultRenderer.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/AppPage.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/api/quantAgentClient.ts", import.meta.url), "utf8"),
    readFile(new URL("../src/config/appConfig.ts", import.meta.url), "utf8"),
    readFile(new URL("../src/types/researchContract.ts", import.meta.url), "utf8"),
  ]);

  for (const status of ["ready", "need_clarification", "no_match", "unavailable", "failed", "dev_preview"]) {
    assert.match(renderer, new RegExp(`case "${status}"`));
    assert.match(types, new RegExp(`status: "${status}"`));
    assert.match(fixtures, new RegExp(`status: "${status}"`));
  }
  assert.match(adapter, /source !== "postgres"/);
  assert.match(adapter, /freshness !== "eod_current"/);
  assert.doesNotMatch(adapter, /fetch\(|backendRequest|analysis-jobs|draft_token/);
  assert.match(renderer, /출처 PostgreSQL · 기준일/);
  assert.doesNotMatch(renderer, /매수|매도|보유|추천|BUY|SELL|HOLD|debug_ref|trace_id/);
  assert.match(appPage, /StrategyWorkspace/);
  assert.doesNotMatch(appPage, /ResearchWorkspace|ResearchResultRenderer/);
  assert.match(clientSource, /createAnalysisJob/);
  assert.match(clientSource, /AI_ENDPOINTS\.analysisJobs/);
  assert.match(configSource, /analysisJobs: "\/analysis-jobs"/);
  assert.doesNotMatch(clientSource, /createAnalysisRun/);
});
