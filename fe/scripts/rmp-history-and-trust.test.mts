import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path: string) => readFile(new URL(path, import.meta.url), "utf8");

test("immutable archive list, detail, and export keep unsafe report fields out of the browser surface", async () => {
  const [list, detail, actions, client] = await Promise.all([
    source("../src/features/reports/ReportList.tsx"),
    source("../src/features/reports/ReportDetail.tsx"),
    source("../src/api/reportActionsClient.ts"),
    source("../src/api/quantAgentClient.ts"),
  ]);

  assert.match(list, /읽기 전용 결과 스냅샷/);
  assert.match(detail, /READER_EVIDENCE_SECTION_IDS/);
  assert.match(actions, /\["result_id", "archived_date", "created_at", "status"\]/);
  assert.doesNotMatch(`${list}\n${detail}\n${actions}\n${client}`, /raw prompt|내부 추론|debug_ref|trace_id/i);
  assert.doesNotMatch(`${list}\n${detail}\n${actions}\n${client}`, /report\.candidates|report\.signals|recommendationScore|report\.performance/);
});

test("each public research-result state includes the same research-only and result-bound trust handoff", async () => {
  const [renderer, trustLinks, routes] = await Promise.all([
    source("../src/features/research-contract/ResearchResultRenderer.tsx"),
    source("../src/components/common/ResultTrustLinks.tsx"),
    source("../src/config/routes.ts"),
  ]);

  for (const status of ["ready", "need_clarification", "no_match", "unavailable", "failed", "dev_preview"]) {
    const statusBody = renderer.match(new RegExp(`case "${status}":[\\s\\S]*?(?=case |$)`))?.[0] ?? "";
    assert.match(statusBody, /ResearchResultDisclosure/);
    assert.match(statusBody, /ResultTrustLinks/);
  }
  assert.match(renderer, /연구 전용 결과입니다/);
  assert.match(trustLinks, /trustFeedback\(resultId, version\)/);
  assert.match(routes, /result_id/);
  assert.match(routes, /version/);
});
