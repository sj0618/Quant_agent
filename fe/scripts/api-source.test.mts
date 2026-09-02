import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { clearUserScopedStorage, USER_SCOPED_STORAGE_KEYS } from "../src/utils/userScopedStorage.ts";
import { publicAiResponseFailure } from "../src/api/aiResponseFailure.ts";
import { createStrategyParsePayload } from "../src/api/strategyParsePayload.ts";

test("strategy review payload remains compatible across an FE/AI rolling deployment", () => {
  const query = "KRX 일봉에서 RSI 30 이하 진입, 70 이상 청산";

  assert.deepEqual(createStrategyParsePayload(query), {
    natural_language: query,
    query,
  });
});

test("strategy parse failures retain a safe diagnosis without echoing strategy input", () => {
  const validation = publicAiResponseFailure(422, {
    detail: [{ type: "string_too_short", loc: ["body", "natural_language"], input: "secret strategy text" }],
  });
  assert.equal(validation.reasonCode, "request_validation_failed");
  assert.match(validation.message ?? "", /natural_language/);
  assert.doesNotMatch(validation.message ?? "", /secret strategy text/);

  const scope = publicAiResponseFailure(422, {
    reason_code: "unsupported_scope",
    explanation: "원문 전략을 포함한 미등록 상세 오류",
  });
  assert.deepEqual(scope, {
    reasonCode: "unsupported_scope",
    message: "이 전략은 현재 전략 검증 범위에서 지원하지 않습니다.",
  });

  const personalized = publicAiResponseFailure(422, {
    detail: { reason_code: "personalized_investment_request", message: "unsafe upstream text" },
  });
  assert.equal(personalized.reasonCode, "personalized_investment_request");
  assert.match(personalized.message ?? "", /개인 보유·계좌·주문/);
  assert.doesNotMatch(personalized.message ?? "", /unsafe upstream text/);

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

test("workspace delegates parse-bound admission to the server in one request", async () => {
  const clientSource = await readFile(new URL("../src/api/quantAgentClient.ts", import.meta.url), "utf8");
  const createJob = clientSource.slice(
    clientSource.indexOf("export async function createAnalysisJob"),
    clientSource.indexOf("export async function cancelAnalysisJob"),
  );
  assert.match(createJob, /fetchAI\(AI_ENDPOINTS\.analysisJobs/);
  assert.match(createJob, /JSON\.stringify\(\{ query: trimmedQuery \}\)/);
  assert.doesNotMatch(createJob, /fetchAI\(AI_ENDPOINTS\.strategyParse/);
  assert.doesNotMatch(createJob, /parse_token:/);
});

test("review confirmation keeps the original natural-language context without changing the sealed rule", async () => {
  const clientSource = await readFile(new URL("../src/api/quantAgentClient.ts", import.meta.url), "utf8");
  const review = clientSource.slice(
    clientSource.indexOf("export async function reviewStrategy"),
    clientSource.indexOf("export interface ResearchAppendix"),
  );
  const confirmation = clientSource.slice(
    clientSource.indexOf("export async function createConfirmedAnalysisJob"),
    clientSource.indexOf("export interface ResearchAppendix"),
  );

  assert.match(review, /\{ \.\.\.parsed, original_query: normalizedQuery \}/);
  assert.match(confirmation, /strategy_execution_spec: parsed\.strategy_execution_spec,/);
  assert.match(confirmation, /query: parsed\.original_query,/);
  assert.match(review, /createStrategyParsePayload\(normalizedQuery\)/);
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
