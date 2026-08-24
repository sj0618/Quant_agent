import assert from "node:assert/strict";
import test from "node:test";
import { archiveTimestamp } from "../src/features/reports/reportArchive.ts";

test("archive disclosure uses only the explicit report record timestamp", () => {
  assert.equal(
    archiveTimestamp({
      createdAt: "2026-08-24T07:05:00Z",
    }),
    "2026-08-24T07:05:00Z",
  );
});

test("archive disclosure never substitutes a delivery or business date", () => {
  assert.equal(
    archiveTimestamp({
      createdAt: undefined,
    }),
    "보관 기록 시각 미확인",
  );
});
