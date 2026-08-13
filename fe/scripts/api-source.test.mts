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

test("workspace discards a running job lost during a server restart", async () => {
  const source = await readFile(new URL("../src/pages/AppPage.tsx", import.meta.url), "utf8");

  assert.match(source, /missingJobIds\.add\(job\.job_id\)/);
  assert.match(source, /\.filter\(\(job\) => !missingJobIds\.has\(job\.job_id\)\)/);
  assert.doesNotMatch(source, /분석 job을 서버에서 찾을 수 없습니다/);
});

test("workspace does not present a non-strategy message as a candidate-selection error", async () => {
  const source = await readFile(new URL("../src/pages/AppPage.tsx", import.meta.url), "utf8");

  assert.match(source, /hasCandidateSelection/);
  assert.match(source, /candidate_cards\.length/);
  assert.match(source, /분석할 전략 조건을 입력해 주세요/);
  assert.match(source, /latestPayload\?\.options\?\.length/);
});

test("report completion sends only the durable AI job id", async () => {
  const source = await readFile(new URL("../src/api/quantAgentClient.ts", import.meta.url), "utf8");
  const completion = source.slice(
    source.indexOf("export async function completeAnalysisRun"),
    source.indexOf("export async function getReports"),
  );

  assert.match(completion, /JSON\.stringify\(\{ aiJobId: job\.job_id \}\)/);
  assert.doesNotMatch(completion, /recommendationGate|performance|strategySpec|sections/);
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
  // The retired *route* stays retired; the send-history timeline itself lives on /me now.
  // It was deleted along with that route in 6dadc69 while its backend endpoint stayed live,
  // so it is asserted present rather than absent.
  assert.doesNotMatch(profileSource, /reportsHistory/);
  assert.match(profileSource, /EmailHistoryTimeline/);
  assert.match(profileSource, /getEmailDeliveries/);
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
  assert.match(authSource, /finally \{\s+clearCurrentSession\(\)/);
  assert.match(appSource, /validateCurrentSession\(\)/);
  assert.match(aiSource, /\[401, 403\]\.includes\(error\.status\)/);
  assert.match(aiSource, /error\.status === 404/);
  assert.match(profileSource, /window\.location\.assign\(ROUTES\.home\)/);
  assert.doesNotMatch(authSource, /TEST_AUTH_SESSION/);
  assert.doesNotMatch(authSource, /saveTestSession/);
  assert.doesNotMatch(authSource, /provider:\s*"test"/);
  assert.doesNotMatch(authSource, /completeTestLogin/);
  assert.doesNotMatch(authSource, /AUTH_ENDPOINTS\.testLogin/);
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
