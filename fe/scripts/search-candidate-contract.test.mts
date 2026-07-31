import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { formatTradingCandidateMeta } from "../src/utils/searchCandidateMeta.ts";

async function read(relativePath: string) {
  return readFile(new URL(relativePath, import.meta.url), "utf8");
}

test("trading candidate meta keeps confidence when present and omits it when absent", () => {
  assert.equal(formatTradingCandidateMeta({ signal: "BUY", confidence: 0.84, price: "₩100,000" }), "BUY · 0.8 · ₩100,000");
  assert.equal(formatTradingCandidateMeta({ price: "₩100,000" }), "₩100,000");
});

test("search page is report-centric and forwards q to the report list endpoint", async () => {
  const searchPage = await read("../src/pages/SearchPage.tsx");

  assert.match(searchPage, /getReports\(normalizedQuery\)/);
  assert.match(searchPage, /ROUTES\.reportDetail/);
  assert.match(searchPage, /placeholder="리포트 제목, 전략명, 후보명, 티커"/);
  assert.match(searchPage, /Badge variant="info">report<\/Badge>/);
  assert.doesNotMatch(searchPage, /formatTradingCandidateMeta/);
  assert.doesNotMatch(searchPage, /kind: "strategy"/);
  assert.doesNotMatch(searchPage, /kind: "candidate"/);
  assert.doesNotMatch(searchPage, /ROUTES\.app/);
  assert.doesNotMatch(searchPage, /tab=trading/);
});
