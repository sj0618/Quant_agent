import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";

import { REQUIRED_READINESS_CHECKS, validateReadinessPayload } from "./readiness-semantic-gate.mjs";

function buildReadyPayload() {
  return {
    status: "ready",
    checks: REQUIRED_READINESS_CHECKS.map((name) => ({
      name,
      ready: true,
      reason: null,
    })),
  };
}

test("readiness semantic gate accepts the exact ready contract", () => {
  const payload = buildReadyPayload();

  assert.deepEqual(validateReadinessPayload(payload), {
    status: "ready",
    checks: REQUIRED_READINESS_CHECKS.map((name) => ({
      name,
      ready: true,
      reason: null,
    })),
  });
});

test("readiness semantic gate rejects an unavailable response or missing dependency", () => {
  assert.throws(
    () =>
      validateReadinessPayload({
        ...buildReadyPayload(),
        status: "unavailable",
      }),
    /status must be ready/u,
  );

  assert.throws(
    () =>
      validateReadinessPayload({
        status: "ready",
        checks: [
          { name: "auth_runtime", ready: true, reason: null },
          { name: "main_db", ready: true, reason: null },
          { name: "redis", ready: true, reason: null },
        ],
      }),
    /missing required checks: trading_data_db/u,
  );

  assert.throws(
    () =>
      validateReadinessPayload({
        status: "ready",
        checks: REQUIRED_READINESS_CHECKS.map((name) =>
          name === "redis" ? { name, ready: false, reason: "redis_unavailable" } : { name, ready: true, reason: null },
        ),
      }),
    /is not ready: redis/u,
  );
});

test("readiness semantic gate CLI reads stdin and emits a summary", () => {
  const result = spawnSync(
    process.execPath,
    ["scripts/readiness-semantic-gate.mjs", "--label", "pre-deploy"],
    {
      encoding: "utf8",
      input: `${JSON.stringify(buildReadyPayload())}\n`,
    },
  );

  assert.equal(result.status, 0);
  assert.match(result.stdout, /"label": "pre-deploy"/u);
  assert.match(result.stdout, /"status": "ready"/u);
  assert.match(result.stdout, /"auth_runtime"/u);
});
