import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";

import {
  REQUIRED_AI_READINESS_CHECKS,
  REQUIRED_READINESS_CHECKS,
  validateReadinessPayload,
} from "./readiness-semantic-gate.mjs";

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

function buildAiReadyPayload() {
  return {
    status: "ready",
    checks: REQUIRED_AI_READINESS_CHECKS.map((name) => ({ name, ready: true, reason: null })),
  };
}

test("the backend profile rejects the AI API's own dependency set", () => {
  // This is the exact pair of errors that blocked every deploy gating on
  // /ai-api/readiness: the AI names are neither expected nor present.
  assert.throws(
    () => validateReadinessPayload(buildAiReadyPayload()),
    /missing required checks: auth_runtime, main_db, trading_data_db, redis/u,
  );
});

test("the ai profile accepts the AI readiness contract and still fails closed", () => {
  const payload = buildAiReadyPayload();

  assert.deepEqual(
    validateReadinessPayload(payload, { requiredChecks: REQUIRED_AI_READINESS_CHECKS }),
    payload,
  );
  assert.throws(
    () =>
      validateReadinessPayload(
        {
          status: "ready",
          checks: REQUIRED_AI_READINESS_CHECKS.map((name) =>
            name === "rule_draft_signer"
              ? { name, ready: false, reason: "rule_draft_signer_required" }
              : { name, ready: true, reason: null },
          ),
        },
        { requiredChecks: REQUIRED_AI_READINESS_CHECKS },
      ),
    /is not ready: rule_draft_signer/u,
  );
  assert.throws(
    () => validateReadinessPayload(buildReadyPayload(), { requiredChecks: REQUIRED_AI_READINESS_CHECKS }),
    /missing required checks: durable_job_store/u,
  );
});

test("the CLI selects a check list by profile and refuses an unknown one", () => {
  const accepted = spawnSync(
    process.execPath,
    ["scripts/readiness-semantic-gate.mjs", "--label", "deployed-ai-api-readiness", "--profile", "ai"],
    { encoding: "utf8", input: `${JSON.stringify(buildAiReadyPayload())}\n` },
  );
  assert.equal(accepted.status, 0);
  assert.match(accepted.stdout, /"durable_job_store"/u);

  const rejected = spawnSync(
    process.execPath,
    ["scripts/readiness-semantic-gate.mjs", "--label", "deployed-ai-api-readiness"],
    { encoding: "utf8", input: `${JSON.stringify(buildAiReadyPayload())}\n` },
  );
  assert.equal(rejected.status, 1);

  const unknown = spawnSync(
    process.execPath,
    ["scripts/readiness-semantic-gate.mjs", "--label", "x", "--profile", "frontend"],
    { encoding: "utf8", input: `${JSON.stringify(buildAiReadyPayload())}\n` },
  );
  assert.equal(unknown.status, 1);
  assert.match(unknown.stderr, /unknown readiness profile: frontend/u);
});
