import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  buildReleaseTrustChecks,
  createOfflineTestEnvironment,
  exitCodeFromResult,
  runReleaseTrust,
  validateReleaseEvidence,
  validateRollbackDrillEvidence,
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
    AI_BACKTEST_CACHE_DIR: "/stale/other-revision-cache",
    KEEP_ME: "yes",
  });

  assert.equal(environment.AI_AOAI_API_KEY, undefined);
  assert.equal(environment.AI_DATABASE_DSN, undefined);
  assert.equal(environment.AI_LLM_DIGEST_API_KEY, undefined);
  assert.equal(environment.AUTH_ENABLED, "0");
  assert.equal(environment.AI_LLM_PROVIDER, "mock");
  assert.match(environment.AI_BACKTEST_CACHE_DIR, /quantagent-release-trust-/u);
  assert.notEqual(environment.AI_BACKTEST_CACHE_DIR, "/stale/other-revision-cache");
  assert.equal(environment.KEEP_ME, "yes");
});

test("release evidence accepts only same-SHA immutable S/R/O/C records", () => {
  const revision = "a".repeat(40);
  const environment = {
    RELEASE_TRUST_REVISION: revision,
    RELEASE_TRUST_REPOSITORY: "example/quant",
  };
  for (const kind of ["S", "R", "O", "C"]) {
    environment[`RELEASE_EVIDENCE_${kind}_REF`] = `https://github.com/example/quant/actions/runs/12345`;
    environment[`RELEASE_EVIDENCE_${kind}_SHA`] = revision;
  }

  assert.deepEqual(validateReleaseEvidence(environment), {
    revision,
    kinds: ["S", "R", "O", "C"],
  });
});

test("release evidence fails closed for missing, mutable, or mismatched evidence", () => {
  const revision = "a".repeat(40);
  const valid = {
    RELEASE_TRUST_REVISION: revision,
    RELEASE_TRUST_REPOSITORY: "example/quant",
  };
  for (const kind of ["S", "R", "O", "C"]) {
    valid[`RELEASE_EVIDENCE_${kind}_REF`] = `https://github.com/example/quant/commit/${revision}`;
    valid[`RELEASE_EVIDENCE_${kind}_SHA`] = revision;
  }

  assert.throws(() => validateReleaseEvidence({}), /full target revision SHA/u);
  assert.throws(
    () => validateReleaseEvidence({ RELEASE_TRUST_REVISION: revision }),
    /trusted GitHub repository/u
  );
  assert.throws(
    () => validateReleaseEvidence({ ...valid, RELEASE_EVIDENCE_R_REF: "https://example.test/result" }),
    /immutable R evidence reference/u
  );
  assert.throws(
    () =>
      validateReleaseEvidence({
        ...valid,
        RELEASE_EVIDENCE_C_REF: `https://github.com/other/repo/commit/${revision}`,
      }),
    /immutable C evidence reference/u
  );
  assert.throws(
    () => validateReleaseEvidence({ ...valid, RELEASE_EVIDENCE_O_SHA: "b".repeat(40) }),
    /O evidence for the target revision/u
  );
});

test("rollback drill evidence accepts only same-SHA immutable drill records", () => {
  const revision = "a".repeat(40);
  const environment = {
    RELEASE_TRUST_REVISION: revision,
    RELEASE_TRUST_REPOSITORY: "example/quant",
    ROLLBACK_DRILL_EVIDENCE_REF: "https://github.com/example/quant/actions/runs/12345",
    ROLLBACK_DRILL_EVIDENCE_SHA: revision,
  };

  assert.deepEqual(validateRollbackDrillEvidence(environment), {
    revision,
    kinds: ["rollback-drill"],
  });
});

test("rollback drill evidence fails closed for missing, mutable, or mismatched evidence", () => {
  const revision = "a".repeat(40);
  const valid = {
    RELEASE_TRUST_REVISION: revision,
    RELEASE_TRUST_REPOSITORY: "example/quant",
    ROLLBACK_DRILL_EVIDENCE_REF: `https://github.com/example/quant/commit/${revision}`,
    ROLLBACK_DRILL_EVIDENCE_SHA: revision,
  };

  assert.throws(() => validateRollbackDrillEvidence({}), /full target revision SHA/u);
  assert.throws(
    () => validateRollbackDrillEvidence({ RELEASE_TRUST_REVISION: revision }),
    /trusted GitHub repository/u
  );
  assert.throws(
    () =>
      validateRollbackDrillEvidence({
        ...valid,
        ROLLBACK_DRILL_EVIDENCE_REF: "https://example.test/result",
      }),
    /immutable rollback drill evidence reference/u
  );
  assert.throws(
    () =>
      validateRollbackDrillEvidence({
        ...valid,
        ROLLBACK_DRILL_EVIDENCE_REF: `https://github.com/other/repo/commit/${revision}`,
      }),
    /immutable rollback drill evidence reference/u
  );
  assert.throws(
    () => validateRollbackDrillEvidence({ ...valid, ROLLBACK_DRILL_EVIDENCE_SHA: "b".repeat(40) }),
    /rollback drill evidence for the target revision/u
  );
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
    "release-failure-mode-contracts",
    "backend-auth-report-and-deploy-contracts",
    "frontend-production-build-and-contracts",
  ]);
  assert.ok(checks[0].args.includes("ai/tests/test_research_request_preflight.py"));
  assert.ok(checks[1].args.includes("backtest_module/tests/test_backtest.py"));
  assert.ok(checks[3].args.includes("backend/tests/unit/test_auth_routes.py"));
  assert.ok(
    checks[2].args.includes(
      "ai/tests/test_db_data_source.py::test_configured_database_failure_is_not_replaced_with_fixture"
    )
  );
  assert.ok(
    checks[2].args.includes(
      "ai/tests/test_source_manifest.py::test_release_profile_fails_before_fixture_analysis_can_return_a_result"
    )
  );
  assert.ok(
    checks[2].args.includes(
      "ai/tests/test_api.py::test_release_readiness_requires_durable_job_store_before_other_dependencies"
    )
  );
  assert.ok(
    checks[2].args.includes(
      "ai/tests/test_legacy_job_rows.py::test_startup_settles_an_undecodable_active_row_instead_of_refusing"
    )
  );
  assert.ok(
    checks[2].args.includes(
      "ai/tests/test_legacy_job_rows.py::test_startup_still_refuses_when_an_undecodable_row_cannot_be_settled"
    )
  );
  assert.ok(
    checks[2].args.includes(
      "ai/tests/test_legacy_job_rows.py::test_active_rows_over_reconciliation_limit_refuse_startup"
    )
  );
  assert.ok(checks[3].args.includes("backend/tests/unit/test_fe_contract_routes.py"));
  assert.ok(checks[3].args.includes("backend/tests/unit/test_track_c_store.py"));
  assert.ok(checks[3].args.includes("backend/tests/unit/test_runtime_perf.py"));
  assert.equal(checks[4].cwd, join("/repo", "fe"));
});

test("pull-request CI invokes the fixed offline release-trust command", async () => {
  const workflowUrl = new URL("../.github/workflows/code-check.yml", import.meta.url);
  const workflow = await readFile(fileURLToPath(workflowUrl), "utf8");

  assert.match(workflow, /release-trust:\r?\n\s+name: Offline release-trust gate/u);
  assert.match(workflow, /node --test scripts\/evaluate-release-trust\.test\.mjs/u);
  assert.match(workflow, /node scripts\/evaluate-release-trust\.mjs/u);
  assert.ok(
    workflow.includes("node --test scripts/rollback-snapshot.test.mjs scripts/rollback-drill-harness.test.mjs"),
  );
});
