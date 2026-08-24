import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function read(relativePath: string) {
  return readFile(new URL(relativePath, import.meta.url), "utf8");
}

test("reports page keeps the archive read-only while retaining local export actions", async () => {
  const [reportsPage, reportList, reportActions] = await Promise.all([
    read("../src/pages/ReportsPage.tsx"),
    read("../src/features/reports/ReportList.tsx"),
    read("../src/api/reportActionsClient.ts"),
  ]);

  assert.match(reportsPage, /getReports/);
  assert.match(reportsPage, /downloadReportsCsv/);
  assert.match(reportsPage, /printCurrentView/);
  assert.match(reportsPage, /ReportList/);
  assert.match(reportList, /copyReportShareLink/);
  assert.doesNotMatch(reportList, /resendReportEmail|재발송/);
  assert.doesNotMatch(reportActions, /resendReportEmail|\/resend/);
  assert.doesNotMatch(reportsPage, /getReportStrategies/);
  assert.doesNotMatch(reportList, /getDigestStrategySelection|getEmailDeliveryHistory|reportsHistory|reportStrategies/);
});

test("search is report-centric and sends q to the live report endpoint", async () => {
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

test("canonical routes exclude retired history and strategy pages", async () => {
  const [appSource, routesSource, profilePage] = await Promise.all([
    read("../src/App.tsx"),
    read("../src/config/routes.ts"),
    read("../src/pages/ProfilePage.tsx"),
  ]);

  assert.doesNotMatch(routesSource, /reportsHistory|reportStrategies|strategyReportDetail/);
  assert.doesNotMatch(appSource, /ReportsHistoryPage|StrategyReportsPage|StrategyReportDetailPage/);
  assert.doesNotMatch(profilePage, /reportsHistory/);
  assert.match(profilePage, /EmailHistoryTimeline/);
});

test("report detail keeps only local export/share actions", async () => {
  const [detailPage, reportDetail, reportActions, archivePolicy] = await Promise.all([
    read("../src/pages/ReportDetailPage.tsx"),
    read("../src/features/reports/ReportDetail.tsx"),
    read("../src/api/reportActionsClient.ts"),
    read("../src/features/reports/reportArchive.ts"),
  ]);

  assert.match(detailPage, /getReportById/);
  assert.match(detailPage, /copyReportShareLink/);
  assert.match(detailPage, /printCurrentView/);
  assert.doesNotMatch(detailPage, /resendReportEmail|이메일 재발송/);
  assert.doesNotMatch(reportActions, /resendReportEmail|\/resend/);
  assert.match(reportDetail, /보관 기록 시각/);
  assert.match(archivePolicy, /snapshot은 90일 보관/);
  assert.match(archivePolicy, /최소 권한 원칙/);
  assert.match(archivePolicy, /재발송·수정·새 분석 실행은 지원하지 않습니다/);
});
