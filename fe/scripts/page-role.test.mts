import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function read(relativePath: string) {
  return readFile(new URL(relativePath, import.meta.url), "utf8");
}

test("/reports exposes a read-only archive and safe export controls", async () => {
  const [reportsPage, reportList, reportActions, clientSource] = await Promise.all([
    read("../src/pages/ReportsPage.tsx"),
    read("../src/features/reports/ReportList.tsx"),
    read("../src/api/reportActionsClient.ts"),
    read("../src/api/quantAgentClient.ts"),
  ]);

  assert.match(reportsPage, /getReports/);
  assert.match(reportsPage, /downloadReportsCsv/);
  assert.match(reportsPage, /printCurrentView/);
  assert.match(reportsPage, /ReportList/);
  assert.match(reportList, /읽기 전용 결과 스냅샷/);
  assert.doesNotMatch(reportList, /resendReportEmail|copyReportShareLink|recommendationScore|report\.signals/);
  assert.match(reportActions, /export async function resendReportEmail/);
  assert.match(clientSource, /export async function getReports/);
  assert.doesNotMatch(reportsPage, /getReportStrategies/);
  assert.doesNotMatch(reportList, /getDigestStrategySelection|getEmailDeliveryHistory|reportsHistory|reportStrategies/);
});

test("/me and /me/notifications stay on the profile and notification surface", async () => {
  const [profilePage, appSource] = await Promise.all([
    read("../src/pages/ProfilePage.tsx"),
    read("../src/App.tsx"),
  ]);

  assert.match(profilePage, /interface ProfilePageProps/);
  assert.match(profilePage, /initialTab: "profile" \| "notifications"/);
  assert.match(profilePage, /getNotificationSettings/);
  assert.match(profilePage, /saveNotificationSettings/);
  assert.match(profilePage, /signOut/);
  assert.match(profilePage, /Google 계정/);
  assert.doesNotMatch(profilePage, /reportsHistory/);
  assert.match(profilePage, /EmailHistoryTimeline/);
  assert.match(appSource, /return <ProfilePage initialTab="profile" \/>/);
  assert.match(appSource, /return <ProfilePage initialTab="notifications" \/>/);
  assert.doesNotMatch(appSource, /StrategyReportsPage|StrategyReportDetailPage|ReportsHistoryPage/);
});

test("/search stays archive-centric and forwards the submitted q to report search", async () => {
  const [searchPage, clientSource] = await Promise.all([
    read("../src/pages/SearchPage.tsx"),
    read("../src/api/quantAgentClient.ts"),
  ]);

  assert.match(searchPage, /getReports/);
  assert.match(searchPage, /getReports\(normalizedQuery\)/);
  assert.match(searchPage, /ROUTES\.reportDetail/);
  assert.match(searchPage, /placeholder="결과 ID 또는 보관 기준일"/);
  assert.match(searchPage, /Badge variant="info">report<\/Badge>/);
  assert.doesNotMatch(clientSource, /export async function searchInstruments/);
  assert.doesNotMatch(searchPage, /getWorkspaceTemplate/);
  assert.doesNotMatch(searchPage, /refreshLatestAnalysisJob/);
  assert.doesNotMatch(searchPage, /mergeAnalysisJobIntoOverview/);
  assert.doesNotMatch(searchPage, /kind: "strategy"/);
  assert.doesNotMatch(searchPage, /kind: "candidate"/);
  assert.doesNotMatch(searchPage, /ROUTES\.app/);
  assert.doesNotMatch(searchPage, /tab=trading/);
  assert.doesNotMatch(searchPage, /getAppOverview/);
  assert.doesNotMatch(searchPage, /searchInstruments/);
});

test("/reports/:id keeps read-only snapshot navigation and PDF export", async () => {
  const [detailPage, reportActions] = await Promise.all([
    read("../src/pages/ReportDetailPage.tsx"),
    read("../src/api/reportActionsClient.ts"),
  ]);

  assert.match(detailPage, /getReportById/);
  assert.match(detailPage, /printCurrentView/);
  assert.match(detailPage, /ROUTES\.reports/);
  assert.doesNotMatch(detailPage, /mock data/);
  assert.match(reportActions, /buildReportPrintTitle/);
});
