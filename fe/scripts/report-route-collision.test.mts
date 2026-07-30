import assert from "node:assert/strict";
import test from "node:test";
import { parseReportDetailId } from "../src/config/routes.ts";

test("retired report route segments do not resolve to report detail ids", () => {
  assert.equal(parseReportDetailId("/reports/history"), null);
  assert.equal(parseReportDetailId("/reports/strategies"), null);
  assert.equal(parseReportDetailId("/reports/strategies/some-test-id"), null);
  assert.equal(parseReportDetailId("/reports/2026-04-18"), "2026-04-18");
  assert.equal(
    parseReportDetailId("/reports/123e4567-e89b-12d3-a456-426614174000"),
    "123e4567-e89b-12d3-a456-426614174000",
  );
});
