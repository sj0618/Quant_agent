import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";
import { clearUserScopedStorage, USER_SCOPED_STORAGE_KEYS } from "../src/utils/userScopedStorage.ts";

test("browser exposes rule-reviewed research without reviving the legacy analysis client", async () => {
  const [clientSource, appSource, activitySource] = await Promise.all([
    readFile(new URL("../src/api/quantAgentClient.ts", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/AppPage.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/api/analysisActivity.ts", import.meta.url), "utf8"),
  ]);

  assert.match(clientSource, /backendRequest/);
  assert.match(clientSource, /export async function getReports\(q\?: string\)/);
  assert.match(clientSource, /new URLSearchParams\(\{ q: normalizedQuery \}\)/);
  assert.match(clientSource, /export async function getReportById/);
  assert.doesNotMatch(clientSource, /createAnalysisJob|cancelAnalysisJob|createAnalysisRun|completeAnalysisRun/);
  assert.doesNotMatch(clientSource, /analysis-jobs|strategyDescriptions|fetchAI/);
  assert.match(appSource, /ResearchWorkspace/);
  assert.doesNotMatch(appSource, /매수|매도|보유|추천|BUY|SELL|HOLD/);
  assert.doesNotMatch(appSource, /StrategyInputPanel|useAnalysisActivity|analysis-jobs/);
  assert.match(activitySource, /analysisJobEvents/);
});

test("retained legacy preview cannot create analysis jobs or runs", async () => {
  const [legacyClientSource, legacyAppSource, legacyConfigSource, legacyReportDetailSource] = await Promise.all([
    readFile(new URL("../../backend/fe-api-preview/src/api/quantAgentClient.ts", import.meta.url), "utf8"),
    readFile(new URL("../../backend/fe-api-preview/src/pages/AppPage.tsx", import.meta.url), "utf8"),
    readFile(new URL("../../backend/fe-api-preview/src/config/appConfig.ts", import.meta.url), "utf8"),
    readFile(new URL("../../backend/fe-api-preview/src/features/reports/ReportDetail.tsx", import.meta.url), "utf8"),
  ]);

  assert.doesNotMatch(legacyClientSource, /createAnalysisJob|cancelAnalysisJob|createAnalysisRun|completeAnalysisRun/);
  assert.doesNotMatch(legacyClientSource, /analysis-jobs|\/runs\b/);
  assert.doesNotMatch(legacyConfigSource, /analysis-jobs|analysis-runs|\/runs\b/);
  assert.doesNotMatch(legacyAppSource, /StrategyInputPanel|useAnalysisActivity|createAnalysisJob|analysis-jobs|progressbar/);
  assert.match(legacyAppSource, /ROUTES\.reports/);
  assert.doesNotMatch(legacyReportDetailSource, /워크스페이스에서 상세 보기|채팅으로 전략 수정|href=\{ROUTES\.app\}/);
  assert.match(legacyReportDetailSource, /ROUTES\.reports/);
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
  assert.doesNotMatch(profileSource, /reportsHistory/);
  assert.match(profileSource, /EmailHistoryTimeline/);
  assert.match(profileSource, /getEmailDeliveries/);
  assert.match(searchSource, /getReports/);
  assert.match(searchSource, /getReports\(normalizedQuery\)/);
  assert.match(searchSource, /ROUTES\.reportDetail/);
  assert.match(searchSource, /Badge variant="info">report<\/Badge>/);
  assert.match(searchSource, /placeholder="결과 ID 또는 보관 기준일"/);
  assert.doesNotMatch(searchSource, /getAppOverview/);
  assert.doesNotMatch(searchSource, /getWorkspaceTemplate/);
  assert.doesNotMatch(searchSource, /refreshLatestAnalysisJob/);
  assert.doesNotMatch(searchSource, /mergeAnalysisJobIntoOverview/);
  assert.doesNotMatch(searchSource, /searchInstruments/);
});

test("authentication boundaries do not leak cached analysis between users", async () => {
  const authSource = await readFile(new URL("../src/api/authClient.ts", import.meta.url), "utf8");
  const clientSource = await readFile(new URL("../src/api/quantAgentClient.ts", import.meta.url), "utf8");
  const appSource = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
  const profileSource = await readFile(new URL("../src/pages/ProfilePage.tsx", import.meta.url), "utf8");

  assert.match(authSource, /!currentSession \|\| currentSession\.user\.id !== session\.user\.id/);
  assert.match(authSource, /AUTH_ENDPOINTS\.me/);
  assert.match(authSource, /finally \{\s+clearCurrentSession\(\)/);
  assert.match(appSource, /validateCurrentSession\(\)/);
  assert.doesNotMatch(clientSource, /localStorage|analysis-jobs|fetchAI/);
  assert.match(profileSource, /window\.location\.assign\(ROUTES\.home\)/);
  assert.doesNotMatch(authSource, /TEST_AUTH_SESSION/);
  assert.doesNotMatch(authSource, /saveTestSession/);
  assert.doesNotMatch(authSource, /provider:\s*"test"/);
  assert.doesNotMatch(authSource, /completeTestLogin/);
  assert.doesNotMatch(authSource, /AUTH_ENDPOINTS\.testLogin/);
});

test("public navigation and bundle sources contain no development preview, fake sample report link, or internal 404 copy", async () => {
  const [appSource, routesSource, landingSource, globalStyles] = await Promise.all([
    readFile(new URL("../src/App.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/config/routes.ts", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/LandingPage.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/styles/global.css", import.meta.url), "utf8"),
  ]);

  assert.doesNotMatch(appSource, /EmailTemplatePreviewPage|Figma HI-FI/);
  assert.doesNotMatch(routesSource, /emailTemplatePreview|dev\/email-template/);
  assert.doesNotMatch(landingSource, /reportDetail\("2026-04-18"\)|KRX LIVE|Sharpe 1\.42/);
  assert.match(landingSource, /로그인 후 읽기 전용 리포트 보관함으로 이동합니다/);
  assert.match(landingSource, /새 분석은 지원하지 않습니다/);
  assert.doesNotMatch(landingSource, /매수|매도|보유|추천|BUY|SELL|HOLD/);
  assert.doesNotMatch(await readFile(new URL("../src/api/quantAgentClient.ts", import.meta.url), "utf8"), /landing\.mock|getLandingSample|LandingSample/);
  assert.doesNotMatch(landingSource, /RELEASE VALIDATION|VALIDATION PRINCIPLES|READ-ONLY ARCHIVE|CURRENT SCOPE/);
  assert.doesNotMatch(globalStyles, /email-template/);
  await assert.rejects(access(new URL("../src/pages/EmailTemplatePreviewPage.tsx", import.meta.url)));
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
