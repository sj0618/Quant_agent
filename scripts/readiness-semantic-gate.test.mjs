import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";

import { REQUIRED_READINESS_CHECKS, validateReadinessPayload } from "./readiness-semantic-gate.mjs";

const AI_REQUIRED_CHECKS = [
  "durable_job_store",
  "migration_revision",
  "live_provider_configuration",
  "ai_contract_version",
  "rule_draft_signer",
];

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

function buildAiReadyPayload() {
  return {
    status: "ready",
    ai_contract_version: "ai-mvp.v1",
    migration_revision: "024_parse_bound_analysis_job_admission",
    checks: AI_REQUIRED_CHECKS.map((name) => ({
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

test("readiness semantic gate accepts a custom AI-ready contract when required checks are supplied", () => {
  const payload = buildAiReadyPayload();

  assert.deepEqual(validateReadinessPayload(payload, { requiredChecks: AI_REQUIRED_CHECKS }), {
    status: "ready",
    checks: AI_REQUIRED_CHECKS.map((name) => ({
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

test("readiness semantic gate CLI accepts custom required checks for AI readiness", () => {
  const result = spawnSync(
    process.execPath,
    [
      "scripts/readiness-semantic-gate.mjs",
      "--label",
      "public-ai-readiness",
      "--checks",
      AI_REQUIRED_CHECKS.join(","),
    ],
    {
      encoding: "utf8",
      input: `${JSON.stringify(buildAiReadyPayload())}\n`,
    },
  );

  assert.equal(result.status, 0);
  assert.match(result.stdout, /"label": "public-ai-readiness"/u);
  assert.match(result.stdout, /"status": "ready"/u);
  assert.match(result.stdout, /"durable_job_store"/u);
});
