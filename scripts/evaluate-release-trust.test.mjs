import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  buildReleaseTrustChecks,
  createOfflineTestEnvironment,
  exitCodeFromResult,
  runReleaseTrust,
} from "./evaluate-release-trust.mjs";

const SAMPLE_CHECKS = [
  { name: "first", command: "first-command", args: ["--first"], cwd: "/repo" },
  { name: "second", command: "second-command", args: ["--second"], cwd: "/repo" },
];

test("offline environment removes live settings and forces local test modes", () => {
  const environment = createOfflineTestEnvironment({
    AI_AOAI_API_KEY: "must-not-propagate",
    AI_DATABASE_DSN: "postgresql://must-not-propagate",
    AI_LLM_DIGEST_API_KEY: "role-secret-must-not-propagate",
    AUTH_ENABLED: "1",
    AI_LLM_PROVIDER: "aoai",
    KEEP_ME: "yes",
  });

  assert.equal(environment.AI_AOAI_API_KEY, undefined);
  assert.equal(environment.AI_DATABASE_DSN, undefined);
  assert.equal(environment.AI_LLM_DIGEST_API_KEY, undefined);
  assert.equal(environment.AUTH_ENABLED, "0");
  assert.equal(environment.AI_LLM_PROVIDER, "mock");
  assert.equal(environment.KEEP_ME, "yes");
});

test("release trust executes fixed checks with shell disabled and sanitized settings", () => {
  const calls = [];
  const environment = createOfflineTestEnvironment({ AI_AOAI_API_KEY: "do-not-pass" });
  const exitCode = runReleaseTrust({
    checks: SAMPLE_CHECKS,
    environment,
    run(command, args, options) {
      calls.push({ command, args, options });
      return { status: 0 };
    },
  });

  assert.equal(exitCode, 0);
  assert.deepEqual(calls.map(({ command }) => command), ["first-command", "second-command"]);
  assert.equal(calls[0].options.shell, false);
  assert.equal(calls[0].options.env.AI_AOAI_API_KEY, undefined);
  assert.equal(calls[0].options.stdio, "inherit");
});

test("release trust preserves the first failing child exit code", () => {
  const calls = [];
  const exitCode = runReleaseTrust({
    checks: SAMPLE_CHECKS,
    run(command) {
      calls.push(command);
      return { status: 17 };
    },
  });

  assert.equal(exitCode, 17);
  assert.deepEqual(calls, ["first-command"]);
});

test("release trust maps a missing executable and a signal to nonzero exits", () => {
  assert.equal(exitCodeFromResult({ error: { code: "ENOENT" } }), 127);
  assert.equal(exitCodeFromResult({ status: null, signal: "SIGTERM" }), 143);
});

test("release trust includes API, screen, metric, and backend contract gates", () => {
  const checks = buildReleaseTrustChecks({ repositoryRoot: "/repo", exists: () => false });

  assert.deepEqual(checks.map(({ name }) => name), [
    "ai-api-and-research-contracts",
    "backtest-metric-contracts",
    "backend-auth-report-and-deploy-contracts",
    "frontend-production-build-and-contracts",
  ]);
  assert.ok(checks[0].args.includes("ai/tests/test_research_request_preflight.py"));
  assert.ok(checks[1].args.includes("backtest_module/tests/test_backtest.py"));
  assert.ok(checks[2].args.includes("backend/tests/unit/test_auth_routes.py"));
  assert.ok(checks[2].args.includes("backend/tests/unit/test_fe_contract_routes.py"));
  assert.ok(checks[2].args.includes("backend/tests/unit/test_track_c_store.py"));
  assert.ok(checks[2].args.includes("backend/tests/unit/test_runtime_perf.py"));
  assert.equal(checks[3].cwd, "/repo/fe");
});

test("pull-request CI invokes the fixed offline release-trust command", async () => {
  const workflowUrl = new URL("../.github/workflows/code-check.yml", import.meta.url);
  const workflow = await readFile(fileURLToPath(workflowUrl), "utf8");

  assert.match(workflow, /release-trust:\n\s+name: Offline release-trust gate/u);
  assert.match(workflow, /node --test scripts\/evaluate-release-trust\.test\.mjs/u);
  assert.match(workflow, /node scripts\/evaluate-release-trust\.mjs/u);
});
