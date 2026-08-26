import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";
import { clearUserScopedStorage, USER_SCOPED_STORAGE_KEYS } from "../src/utils/userScopedStorage.ts";

test("browser exposes the durable natural-language strategy workspace without browser result fallbacks", async () => {
  const [clientSource, appSource, configSource, workspaceSource, mapperSource] = await Promise.all([
    readFile(new URL("../src/api/quantAgentClient.ts", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/AppPage.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/config/appConfig.ts", import.meta.url), "utf8"),
    readFile(new URL("../src/features/app/StrategyWorkspace.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/features/app/strategyWorkspaceMapper.ts", import.meta.url), "utf8"),
  ]);

  assert.match(clientSource, /backendRequest/);
  assert.match(clientSource, /export async function getReports\(q\?: string\)/);
  assert.match(clientSource, /new URLSearchParams\(\{ q: normalizedQuery \}\)/);
  assert.match(clientSource, /export async function getReportById/);
  assert.match(clientSource, /export async function createAnalysisJob/);
  assert.match(clientSource, /export async function getAnalysisJob/);
  assert.match(clientSource, /export async function cancelAnalysisJob/);
  assert.doesNotMatch(clientSource, /createAnalysisRun|completeAnalysisRun|localStorage/);
  assert.match(appSource, /StrategyWorkspace/);
  assert.match(workspaceSource, /StrategyInputPanel/);
  assert.match(workspaceSource, /createAnalysisJob/);
  assert.match(workspaceSource, /getAnalysisJob/);
  assert.match(workspaceSource, /natural-language strategy/);
  assert.match(mapperSource, /reliability\?\.source === "postgres"/);
  assert.match(mapperSource, /fixture·출처 미확인·표본 부족 결과는 성과 수치와 차트로 대체하지 않습니다/);
  assert.match(configSource, /analysisJobs: "\/analysis-jobs"/);
  assert.match(configSource, /analysisJobCancel/);
  assert.doesNotMatch(configSource, /analysis-runs|\/runs\b/);
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
  assert.doesNotMatch(clientSource, /localStorage/);
  assert.match(profileSource, /window\.location\.assign\(ROUTES\.home\)/);
  assert.doesNotMatch(authSource, /TEST_AUTH_SESSION/);
  assert.doesNotMatch(authSource, /saveTestSession/);
  assert.doesNotMatch(authSource, /provider:\s*"test"/);
  assert.doesNotMatch(authSource, /completeTestLogin/);
  assert.doesNotMatch(authSource, /AUTH_ENDPOINTS\.testLogin/);
});

test("public navigation describes the core strategy workflow without fake performance or internal preview copy", async () => {
  const [appSource, routesSource, landingSource, globalStyles] = await Promise.all([
    readFile(new URL("../src/App.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/config/routes.ts", import.meta.url), "utf8"),
    readFile(new URL("../src/pages/LandingPage.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/styles/global.css", import.meta.url), "utf8"),
  ]);

  assert.doesNotMatch(appSource, /EmailTemplatePreviewPage|Figma HI-FI/);
  assert.doesNotMatch(routesSource, /emailTemplatePreview|dev\/email-template/);
  assert.doesNotMatch(landingSource, /reportDetail\("2026-04-18"\)|KRX LIVE|Sharpe 1\.42/);
  assert.match(landingSource, /자연어 전략 분석 시작/);
  assert.match(landingSource, /자연어 전략 → 실데이터 백테스트 → 자연어 리포트/);
  assert.match(landingSource, /개인 보유 종목·계좌·수량·위험성향/);
  assert.doesNotMatch(landingSource, /새 분석은 지원하지 않습니다|현재 제공하지 않는 기능/);
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
