import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function read(relativePath: string) {
  return readFile(new URL(relativePath, import.meta.url), "utf8");
}

test("/reports lists workspace-generated strategy reports, not email deliveries", async () => {
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
  assert.match(reportList, /copyReportShareLink/);
  assert.match(reportList, /printCurrentView/);
  assert.match(reportList, /ROUTES\.app/);
  assert.match(reportActions, /export async function resendReportEmail/);
  assert.match(clientSource, /await listAnalysisJobs\(\)/);
  assert.match(clientSource, /getWorkspaceReportById/);
  assert.match(clientSource, /getEmailReportById/);
  assert.doesNotMatch(reportList, /resendReportEmail/);
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

test("/search stays report-centric and forwards the submitted q to report search", async () => {
  const [searchPage, clientSource] = await Promise.all([
    read("../src/pages/SearchPage.tsx"),
    read("../src/api/quantAgentClient.ts"),
  ]);

  assert.match(searchPage, /getReports/);
  assert.match(searchPage, /getReports\(normalizedQuery\)/);
  assert.match(searchPage, /ROUTES\.reportDetail/);
  assert.match(searchPage, /placeholder="리포트 제목, 전략명, 후보명, 티커"/);
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

test("workspace and email report details have distinct routes and views", async () => {
  const [appPage, workspaceDetail, workspaceResult, emailDetail, timeline, routesSource] = await Promise.all([
    read("../src/pages/AppPage.tsx"),
    read("../src/pages/WorkspaceReportDetailPage.tsx"),
    read("../src/features/app/WorkspaceResultPanel.tsx"),
    read("../src/pages/EmailReportDetailPage.tsx"),
    read("../src/features/reports/EmailHistoryTimeline.tsx"),
    read("../src/config/routes.ts"),
  ]);

  assert.match(workspaceDetail, /getWorkspaceReportById/);
  assert.match(workspaceDetail, /WorkspaceResultPanel/);
  assert.match(appPage, /WorkspaceResultPanel/);
  assert.match(workspaceResult, /OverviewTab/);
  assert.match(workspaceResult, /TradingInfoTab/);
  assert.match(workspaceResult, /PerformanceTab/);
  assert.match(workspaceResult, /ExplorationBaseReport/);
  assert.match(emailDetail, /getEmailReportById/);
  assert.match(emailDetail, /ReportDetail/);
  assert.match(timeline, /ROUTES\.emailReportDetail/);
  assert.match(routesSource, /emailReportDetail/);
  assert.doesNotMatch(workspaceDetail, /features\/reports\/ReportDetail/);
  assert.doesNotMatch(workspaceDetail, /이메일 재발송/);
});
