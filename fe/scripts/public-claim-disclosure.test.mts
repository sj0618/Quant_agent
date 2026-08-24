import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path: string) => readFile(new URL(path, import.meta.url), "utf8");

test("public copy has a claim identifier and declares that it does not show sample or live performance", async () => {
  const [ledger, landing, disclosure] = await Promise.all([
    source("../src/content/publicClaimLedger.ts"),
    source("../src/pages/LandingPage.tsx"),
    source("../src/components/common/PublicClaimDisclosure.tsx"),
  ]);

  assert.match(ledger, /CLAIM-UI-ARCHIVE-001/);
  assert.match(ledger, /sample·live 성과 수치를 표시하지 않음/);
  assert.match(landing, /PublicClaimDisclosure claimKey="landingArchiveScope"/);
  assert.match(disclosure, /공개 문구 ID/);
  assert.match(disclosure, /근거 범위/);
  assert.match(disclosure, /기준 시점/);
});

test("archived reports declare stale-state limits before rendering allow-listed evidence", async () => {
  const detail = await source("../src/features/reports/ReportDetail.tsx");

  assert.match(detail, /현재 검증할 수 없음/);
  assert.match(detail, /보관 기준일/);
  assert.match(detail, /보관 리포트 목록으로 돌아가기/);
  assert.match(detail, /PublicClaimDisclosure claimKey="archivedSnapshot"/);
  assert.match(detail, /READER_EVIDENCE_SECTION_IDS/);
  assert.doesNotMatch(detail, /report\.performance|recommendationScore|report\.signals|report\.candidates/);
});
