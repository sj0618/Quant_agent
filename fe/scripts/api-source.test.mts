import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { clearUserScopedStorage, USER_SCOPED_STORAGE_KEYS } from "../src/utils/userScopedStorage.ts";

test("product screens use analysis API data without product mock overlays", async () => {
  const source = await readFile(new URL("../src/api/quantAgentClient.ts", import.meta.url), "utf8");

  assert.doesNotMatch(source, /mocks\/(?:app|reports|reportStrategies)\.mock/);
  assert.match(source, /AI_ENDPOINTS\.analysisJobs/);
  assert.match(source, /listAnalysisJobs/);
  assert.match(source, /refreshLatestAnalysisJob/);
  assert.match(source, /listAnalysisJobs\(1\)/);
  assert.match(source, /error\.status === 404/);
  assert.match(source, /buildTradingCandidatesFromAnalysisJob/);
  assert.doesNotMatch(source, /candidates: result \? \[\] : base\.candidates/);
  assert.match(source, /AI_REQUEST_TIMEOUT_MS = 1_200_000/);
  assert.match(source, /id\.startsWith\(AI_REPORT_ID_PREFIX\)/);
});

test("workspace restores the latest server analysis on a fresh browser", async () => {
  const source = await readFile(new URL("../src/pages/AppPage.tsx", import.meta.url), "utf8");

  assert.match(source, /refreshLatestAnalysisJob\(\)/);
  assert.match(source, /setAnalysisJobs\(\(jobs\) => \(jobs\.length \? jobs : \[latestJob\]\)\)/);
});

test("product surfaces do not expose retired candidate-scope fields", async () => {
  const sources = await Promise.all(
    [
      "../src/features/app/OverviewTab.tsx",
      "../src/features/reports/StrategyReportList.tsx",
      "../src/features/reports/ReportDetail.tsx",
      "../src/types/quantagent.ts",
    ].map((path) => readFile(new URL(path, import.meta.url), "utf8")),
  );

  for (const source of sources) {
    assert.doesNotMatch(source, /universe|유니버스|strategyUniverse/i);
  }
});


test("deployment does not force the mock LLM profile", async () => {
  const source = await readFile(new URL("../../.github/workflows/deploy.yml", import.meta.url), "utf8");

  assert.doesNotMatch(source, /AI_LLM_PROVIDER=mock/);
  assert.match(source, /AI_LLM_PROVIDER.*aoai/);
  assert.match(source, /AUTH_ENABLED=.*AUTH_ENABLED:-0/);
  assert.match(source, /VITE_ENABLE_TEST_LOGIN=1/);
  assert.match(source, /REDIS_URL must be configured/);
  assert.match(source, /QUANT_DB_HOST\/PORT\/NAME\/USER\/PASSWORD/);
  assert.match(source, /client\.ping\(\)/);
  assert.match(source, /VITE_AUTH_API_BASE_URL%\/\}\/health/);
  assert.match(source, /npm run preview/);
  assert.doesNotMatch(source, /nohup npm run dev/);
});


test("authentication boundaries do not leak cached analysis between users", async () => {
  const authSource = await readFile(new URL("../src/api/authClient.ts", import.meta.url), "utf8");
  const aiSource = await readFile(new URL("../src/api/quantAgentClient.ts", import.meta.url), "utf8");
  const appSource = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
  const profileSource = await readFile(new URL("../src/pages/ProfilePage.tsx", import.meta.url), "utf8");

  assert.match(authSource, /!currentSession \|\| currentSession\.user\.id !== session\.user\.id/);
  assert.match(authSource, /AUTH_ENDPOINTS\.me/);
  assert.match(authSource, /finally \{\s+clearCurrentSession\(\)/);
  assert.match(appSource, /validateCurrentSession\(\)/);
  assert.match(aiSource, /\[401, 403\]\.includes\(error\.status\)/);
  assert.match(aiSource, /error\.status === 404/);
  assert.match(profileSource, /finally \{\s+window\.location\.assign\(ROUTES\.home\)/);
});


test("user-scoped cache clearing removes every registered key", () => {
  const removed: string[] = [];

  clearUserScopedStorage({ removeItem: (key) => removed.push(key) });

  assert.deepEqual(removed, [...USER_SCOPED_STORAGE_KEYS]);
  assert.ok(removed.includes("quantagent.auth.session.v1"));
  assert.ok(removed.includes("quantagent.latest-analysis-job.v1"));
  assert.ok(removed.includes("quantagent.chat-conversations.v1"));
});
