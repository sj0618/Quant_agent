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

test("search page uses the shared optional candidate formatter and avoids unconditional confidence dereference", async () => {
  const searchPage = await read("../src/pages/SearchPage.tsx");

  assert.match(searchPage, /formatTradingCandidateMeta/);
  assert.doesNotMatch(searchPage, /candidate\.confidence\.toFixed/);
  assert.doesNotMatch(searchPage, /candidate\.confidence!/);
  assert.doesNotMatch(searchPage, /candidate\.confidence as number/);
  assert.doesNotMatch(searchPage, /candidate\.confidence \?\? 0/);
});
