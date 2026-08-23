import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path: string) => readFile(new URL(path, import.meta.url), "utf8");

test("archived report readers expose only immutable identifiers and allow-listed evidence", async () => {
  const [list, detail, actions, client, searchCommand] = await Promise.all([
    source("../src/features/reports/ReportList.tsx"),
    source("../src/features/reports/ReportDetail.tsx"),
    source("../src/api/reportActionsClient.ts"),
    source("../src/api/quantAgentClient.ts"),
    source("../src/components/layout/SearchCommand.tsx"),
  ]);

  assert.match(list, /읽기 전용 결과 스냅샷/);
  assert.match(list, /결과 ID \{report\.id\}/);
  assert.doesNotMatch(list, /recommendationScore|report\.signals|resendReportEmail|copyReportShareLink/);
  assert.match(detail, /READER_EVIDENCE_SECTION_IDS/);
  assert.match(detail, /reproduction_contract/);
  assert.match(detail, /metric_registry/);
  assert.match(detail, /ResultTrustLinks/);
  assert.doesNotMatch(detail, /report\.title|report\.summary|report\.candidates|report\.signals|recommendationScore/);
  assert.match(actions, /result_id/);
  assert.doesNotMatch(actions, /recommendationScore|report\.signals|report\.summary/);
  assert.match(client, /ArchivedReportSummary/);
  assert.match(client, /ArchivedReportDetail/);
  assert.doesNotMatch(client, /recommendationScore|marketSnapshot|report\.signals|report\.candidates|report\.performance/);
  assert.match(searchCommand, /읽기 전용 결과 스냅샷/);
  assert.doesNotMatch(searchCommand, /report\.title|report\.summary|recommendationScore/);
});

test("every public research result and archived result links to a result-bound trust record", async () => {
  const [renderer, trustLinks, routes, app, legal] = await Promise.all([
    source("../src/features/research-contract/ResearchResultRenderer.tsx"),
    source("../src/components/common/ResultTrustLinks.tsx"),
    source("../src/config/routes.ts"),
    source("../src/App.tsx"),
    source("../src/pages/LegalPage.tsx"),
  ]);

  assert.match(renderer, /ResultTrustLinks resultId=\{result\.result_id\} version=\{result\.rule_version\}/);
  assert.match(trustLinks, /trustFeedback\(resultId, version\)/);
  assert.match(routes, /trust: "\/trust"/);
  assert.match(routes, /result_id/);
  assert.match(app, /ROUTES\.trust/);
  assert.match(legal, /결과 문제 기록/);
  assert.match(legal, /feedbackResultId/);

  for (const status of ["ready", "need_clarification", "no_match", "unavailable", "failed", "dev_preview"]) {
    const statusBody = renderer.match(new RegExp(`case "${status}":[\\s\\S]*?(?=case |$)`))?.[0] ?? "";
    assert.match(statusBody, /ResearchResultDisclosure/);
    assert.match(statusBody, /ResultTrustLinks/);
  }
  assert.match(renderer, /연구 전용 결과입니다/);
  assert.match(renderer, /AI가 만든 설명은 운영 데이터의 출처·기준일·검증 계약을 대신하지 않으며/);
});
