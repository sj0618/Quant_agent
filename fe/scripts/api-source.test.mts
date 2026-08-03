import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { clearUserScopedStorage, USER_SCOPED_STORAGE_KEYS } from "../src/utils/userScopedStorage.ts";

test("report surfaces keep the restored live report source", async () => {
  const source = await readFile(new URL("../src/api/quantAgentClient.ts", import.meta.url), "utf8");

  assert.match(source, /mocks\/(?:app|reports)\.mock/);
  assert.match(source, /backendRequest/);
  assert.match(source, /export async function getReports\(q\?: string\)/);
  assert.match(source, /new URLSearchParams\(\{ q: normalizedQuery \}\)/);
  assert.match(source, /export async function getReportById/);
  assert.doesNotMatch(source, /export async function searchInstruments/);
  assert.match(source, /AI_REPORT_ID_PREFIX/);
  assert.doesNotMatch(source, /reportClient|reportAdapter/);
});

test("workspace restores the latest server analysis on a fresh browser", async () => {
  const source = await readFile(new URL("../src/pages/AppPage.tsx", import.meta.url), "utf8");

  assert.match(source, /refreshLatestAnalysisJob\(\)/);
  assert.match(source, /setAnalysisJobs\(\(jobs\) => \(jobs\.length \? jobs : \[latestJob\]\)\)/);
});

test("canonical product surface excludes retired history and strategy routes", async () => {
  const [appSource, routesSource, profileSource, searchSource] = await Promise.all([
    readFile(new URL("../src/App.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/config/routes.ts", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/ProfilePage.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/SearchPage.tsx", import.meta.url), "utf8"),
  ]);

  assert.doesNotMatch(routesSource, /reportsHistory|reportStrategies|strategyReportDetail/);
  assert.doesNotMatch(appSource, /ReportsHistoryPage|StrategyReportsPage|StrategyReportDetailPage/);
  assert.doesNotMatch(profileSource, /EmailHistoryTimeline|getEmailDeliveryHistory|reportsHistory/);
  assert.match(searchSource, /getReports/);
  assert.match(searchSource, /getReports\(normalizedQuery\)/);
  assert.match(searchSource, /ROUTES\.reportDetail/);
  assert.match(searchSource, /Badge variant="info">report<\/Badge>/);
  assert.match(searchSource, /placeholder="리포트 제목, 전략명, 후보명, 티커"/);
  assert.doesNotMatch(searchSource, /getAppOverview/);
  assert.doesNotMatch(searchSource, /getWorkspaceTemplate/);
  assert.doesNotMatch(searchSource, /refreshLatestAnalysisJob/);
  assert.doesNotMatch(searchSource, /mergeAnalysisJobIntoOverview/);
  assert.doesNotMatch(searchSource, /searchInstruments/);
});

test("authentication boundaries do not leak cached analysis between users", async () => {
  const authSource = await readFile(new URL("../src/api/authClient.ts", import.meta.url), "utf8");
  const aiSource = await readFile(new URL("../src/api/quantAgentClient.ts", import.meta.url), "utf8");
  const appSource = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
  const profileSource = await readFile(new URL("../src/pages/ProfilePage.tsx", import.meta.url), "utf8");

  assert.match(authSource, /!currentSession \|\| currentSession\.user\.id !== session\.user\.id/);
  assert.match(authSource, /AUTH_ENDPOINTS\.me/);
  assert.match(authSource, /AUTH_ENDPOINTS\.testLogin/);
  assert.match(authSource, /completeTestLogin/);
  assert.match(authSource, /finally \{\s+clearCurrentSession\(\)/);
  assert.match(appSource, /validateCurrentSession\(\)/);
  assert.match(aiSource, /\[401, 403\]\.includes\(error\.status\)/);
  assert.match(aiSource, /error\.status === 404/);
  assert.match(profileSource, /window\.location\.assign\(ROUTES\.home\)/);
  assert.doesNotMatch(authSource, /TEST_AUTH_SESSION/);
  assert.doesNotMatch(authSource, /saveTestSession/);
  assert.doesNotMatch(authSource, /provider:\s*"test"/);
});

test("Google callback reuses its one-time exchange under React StrictMode", async () => {
  const source = await readFile(new URL("../src/pages/AuthCallbackPage.tsx", import.meta.url), "utf8");

  assert.match(source, /useRef<ReturnType<typeof completeGoogleSignIn> \| null>\(null\)/);
  assert.match(source, /callbackRequestRef\.current \?\?=/);
});

test("user-scoped cache clearing removes every registered key", () => {
  const removed: string[] = [];

  clearUserScopedStorage({ removeItem: (key) => removed.push(key) });

  assert.deepEqual(removed, [...USER_SCOPED_STORAGE_KEYS]);
  assert.ok(removed.includes("quantagent.auth.session.v1"));
  assert.ok(removed.includes("quantagent.latest-analysis-job.v1"));
  assert.ok(removed.includes("quantagent.chat-conversations.v1"));
});
