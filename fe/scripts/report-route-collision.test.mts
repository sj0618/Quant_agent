import assert from "node:assert/strict";
import test from "node:test";
import { parseEmailReportDetailId, parseReportDetailId } from "../src/config/routes.ts";

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

test("email delivery report route is distinct from the workspace report route", () => {
  assert.equal(parseEmailReportDetailId("/me/email-reports/abc-123"), "abc-123");
  assert.equal(parseEmailReportDetailId("/reports/abc-123"), null);
  assert.equal(parseReportDetailId("/me/email-reports/abc-123"), null);
  assert.equal(parseEmailReportDetailId("/me/email-reports/abc-123/extra"), null);
});
