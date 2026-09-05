import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { clearUserScopedStorage, USER_SCOPED_STORAGE_KEYS } from "../src/utils/userScopedStorage.ts";
import { publicAiResponseFailure } from "../src/api/aiResponseFailure.ts";

test("strategy parse failures retain a safe diagnosis without echoing strategy input", () => {
  const validation = publicAiResponseFailure(422, {
    detail: [{ type: "string_too_short", loc: ["body", "natural_language"], input: "secret strategy text" }],
  });
  assert.equal(validation.reasonCode, "request_validation_failed");
  assert.match(validation.message ?? "", /natural_language/);
  assert.doesNotMatch(validation.message ?? "", /secret strategy text/);

  const unsafeDetail = publicAiResponseFailure(503, {
    detail: "provider trace contains secret strategy text",
  });
  assert.doesNotMatch(unsafeDetail.message ?? "", /provider trace|secret strategy text/);
});

test("workspace reports use completed analysis jobs and keep email snapshots separate", async () => {
  const source = await readFile(new URL("../src/api/quantAgentClient.ts", import.meta.url), "utf8");

  assert.match(source, /backendRequest/);
  assert.match(source, /export async function getReports\(q\?: string\)/);
  assert.match(source, /await listAnalysisJobs\(\)/);
  assert.match(source, /buildReportSummaryFromAnalysisJob/);
  assert.match(source, /export async function getWorkspaceReportById/);
  assert.match(source, /export async function getEmailReportById/);
  assert.match(source, /`\/me\/email-reports\/\$\{encodeURIComponent\(id\)\}`/);
  assert.doesNotMatch(source, /export async function searchInstruments/);
  assert.match(source, /AI_REPORT_ID_PREFIX/);
  assert.doesNotMatch(source, /reportClient|reportAdapter/);
});

test("workspace restores the latest server analysis on a fresh browser", async () => {
  const source = await readFile(new URL("../src/pages/AppPage.tsx", import.meta.url), "utf8");

  assert.match(source, /refreshLatestAnalysisJob\(\)/);
  assert.match(source, /setAnalysisJobs\(\(jobs\) => \(jobs\.length \? jobs : \[latestJob\]\)\)/);
});

test("workspace progress follows server stages instead of elapsed client time", async () => {
  const source = await readFile(new URL("../src/pages/AppPage.tsx", import.meta.url), "utf8");

  assert.match(source, /const percent = progressPercentFromSteps\(steps\);/);
  assert.match(source, /status: index === 0 \? "running" : "queued"/);
  assert.doesNotMatch(
    source,
    /MAX_ANALYSIS_DURATION_MS|PROGRESS_TICK_INTERVAL_MS|progressPercentFromElapsed|clientStageStatus|client_timeout/,
  );
});

test("analysis results with a failure cause retain the server diagnosis in the workspace", async () => {
  const source = await readFile(new URL("../src/pages/AppPage.tsx", import.meta.url), "utf8");

  assert.match(source, /const terminalFailureJob = latestJob\?\.result\?\.status === "failed" \? latestJob : undefined;/);
  assert.match(source, /const progressJob = runningJob \?\? terminalFailureJob;/);
  assert.match(source, /job: progressJob,/);
  assert.match(source, /error: progressJob \? jobErrors\[progressJob\.job_id\] \?\? terminalJobFailure\(progressJob\) : undefined,/);
});

test("workspace directly queues a natural-language strategy job", async () => {
  const clientSource = await readFile(new URL("../src/api/quantAgentClient.ts", import.meta.url), "utf8");
  const createJob = clientSource.slice(
    clientSource.indexOf("export async function createAnalysisJob"),
    clientSource.indexOf("export async function cancelAnalysisJob"),
  );
  assert.match(createJob, /fetchAI\(AI_ENDPOINTS\.analysisJobs/);
  assert.match(createJob, /JSON\.stringify\(\{ query: trimmedQuery \}\)/);
  assert.doesNotMatch(createJob, /strategyParse/);
  assert.doesNotMatch(createJob, /parse_token:/);
});

test("workspace does not require an RSI-style condition confirmation before a job", async () => {
  const [clientSource, appSource] = await Promise.all([
    readFile(new URL("../src/api/quantAgentClient.ts", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/AppPage.tsx", import.meta.url), "utf8"),
  ]);

  assert.doesNotMatch(clientSource, /reviewStrategy|createConfirmedAnalysisJob|strategyParsePayload/);
  assert.doesNotMatch(appSource, /StrategyDraftConfirmation|pendingDraft|handleConfirmDraft/);
  assert.match(appSource, /const job = await createAnalysisJob\(query\)/);
});

test("workspace discards a running job lost during a server restart", async () => {
  const source = await readFile(new URL("../src/pages/AppPage.tsx", import.meta.url), "utf8");

  assert.match(source, /missingJobIds\.add\(job\.job_id\)/);
  assert.match(source, /\.filter\(\(job\) => !missingJobIds\.has\(job\.job_id\)\)/);
  assert.doesNotMatch(source, /분석 job을 서버에서 찾을 수 없습니다/);
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

test("canonical product surface separates workspace reports from My Page email reports", async () => {
  const [appSource, routesSource, profileSource, timelineSource, searchSource] = await Promise.all([
    readFile(new URL("../src/App.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/config/routes.ts", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/ProfilePage.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/features/reports/EmailHistoryTimeline.tsx", import.meta.url), "utf8"),
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
  assert.match(routesSource, /emailReportDetail/);
  assert.match(appSource, /EmailReportDetailPage/);
  assert.match(appSource, /WorkspaceReportDetailPage/);
  assert.match(timelineSource, /ROUTES\.emailReportDetail/);
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
