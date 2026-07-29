import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function read(relativePath: string) {
  return readFile(new URL(relativePath, import.meta.url), "utf8");
}

test("/reports restores generated report roles and export controls", async () => {
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
  assert.match(reportList, /resendReportEmail/);
  assert.match(reportList, /copyReportShareLink/);
  assert.match(reportList, /printCurrentView/);
  assert.match(reportList, /ROUTES\.notifications/);
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
  assert.doesNotMatch(profilePage, /EmailHistoryTimeline|getEmailDeliveryHistory|reportsHistory/);
  assert.match(appSource, /return <ProfilePage initialTab="profile" \/>/);
  assert.match(appSource, /return <ProfilePage initialTab="notifications" \/>/);
  assert.doesNotMatch(appSource, /StrategyReportsPage|StrategyReportDetailPage|ReportsHistoryPage/);
});

test("/search uses current live report and workspace sources", async () => {
  const [searchPage, clientSource] = await Promise.all([
    read("../src/pages/SearchPage.tsx"),
    read("../src/api/quantAgentClient.ts"),
  ]);

  assert.match(searchPage, /getReports/);
  assert.match(searchPage, /getWorkspaceTemplate/);
  assert.match(searchPage, /refreshLatestAnalysisJob/);
  assert.match(searchPage, /mergeAnalysisJobIntoOverview/);
  assert.match(searchPage, /kind: "strategy"/);
  assert.match(searchPage, /kind: "candidate"/);
  assert.match(searchPage, /kind: "report"/);
  assert.match(searchPage, /ROUTES\.app/);
  assert.match(searchPage, /tab=trading/);
  assert.match(searchPage, /ROUTES\.reportDetail/);
  assert.doesNotMatch(clientSource, /export async function searchInstruments/);
  assert.doesNotMatch(searchPage, /getAppOverview/);
  assert.doesNotMatch(searchPage, /searchInstruments/);
});

test("/reports/:id keeps generated report detail navigation and actions", async () => {
  const [detailPage, reportActions] = await Promise.all([
    read("../src/pages/ReportDetailPage.tsx"),
    read("../src/api/reportActionsClient.ts"),
  ]);

  assert.match(detailPage, /getReportById/);
  assert.match(detailPage, /copyReportShareLink/);
  assert.match(detailPage, /printCurrentView/);
  assert.match(detailPage, /resendReportEmail/);
  assert.match(detailPage, /ROUTES\.reports/);
  assert.match(reportActions, /export async function resendReportEmail/);
});
