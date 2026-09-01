import assert from "node:assert/strict";
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  CONTROLLED_FAILURE_EXIT_CODE,
  CONTROLLED_FAILURE_POINT,
  DEFAULT_TARGET_NAME,
  MUTATION_MARKER_NAME,
  ROLLBACK_MARKER_NAME,
  buildRollbackDrillFixture,
  runControlledRollbackDrill,
} from "./rollback-drill-harness.mjs";
import {
  REQUIRED_AI_READINESS_CHECKS,
  REQUIRED_READINESS_CHECKS,
} from "./readiness-semantic-gate.mjs";

function cloneDirectory(sourceRoot, targetRoot) {
  rmSync(targetRoot, { recursive: true, force: true });
  cpSync(sourceRoot, targetRoot, { recursive: true });
}

test("rollback drill fixture pins the backend and AI readiness profiles plus same-SHA provenance", () => {
  const baselineSha = "a".repeat(40);
  const fixture = buildRollbackDrillFixture({
    baselineSha,
    candidateSha: baselineSha,
    workflowRunId: "run-123",
    targetName: "release-test-sandbox",
  });

  assert.deepEqual(
    fixture.backend.checks.map((check) => check.name),
    REQUIRED_READINESS_CHECKS,
  );
  assert.deepEqual(fixture.ai.checks.map((check) => check.name), REQUIRED_AI_READINESS_CHECKS);
  assert.equal(fixture.runtime.aiJobStore, "persistent");
  assert.equal(fixture.runtime.aiAuditSink, "file");
  assert.equal(fixture.gateway.unknownRouteStatus, 404);
  assert.equal(fixture.provenance.baselineSha, baselineSha);
  assert.equal(fixture.provenance.candidateSha, baselineSha);
  assert.equal(fixture.provenance.workflowRunId, "run-123");
  assert.equal(fixture.provenance.failurePoint, CONTROLLED_FAILURE_POINT);
});

test("rollback drill harness snapshots, injects bounded failure, restores, and writes provenance evidence", () => {
  const workspaceRoot = mkdtempSync(join(tmpdir(), "rollback-drill-harness-"));
  const snapshotRoot = join(workspaceRoot, "snapshot");
  const artifactPath = join(workspaceRoot, "evidence", "rollback-drill-report.json");
  const calls = [];
  const baselineSha = "b".repeat(40);

  const result = runControlledRollbackDrill({
    workspaceRoot,
    artifactPath,
    baselineSha,
    candidateSha: baselineSha,
    workflowRunId: "run-456",
    createSnapshot({ sourceRoot, archivePath, checksumPath }) {
      calls.push(["snapshot", sourceRoot, archivePath, checksumPath]);
      cloneDirectory(sourceRoot, snapshotRoot);
      return {
        archivePath,
        checksumPath,
        sha256: "f".repeat(64),
        entries: [
          "backend/readiness.json",
          "ai/readiness.json",
          "runtime/runtime.json",
          "db/schema.json",
          "telemetry/audit.json",
          "fe/gateway.json",
          "provenance/rollback-provenance.json",
        ],
      };
    },
    restoreSnapshot({ archivePath, checksumPath, localTarget }) {
      calls.push(["restore", archivePath, checksumPath, localTarget]);
      cloneDirectory(snapshotRoot, localTarget);
      return {
        archivePath,
        checksumPath,
        sha256: "f".repeat(64),
        entries: [
          "backend/readiness.json",
          "ai/readiness.json",
          "runtime/runtime.json",
          "db/schema.json",
          "telemetry/audit.json",
          "fe/gateway.json",
          "provenance/rollback-provenance.json",
        ],
        extractionRoot: join(workspaceRoot, "restore-stage"),
        localTarget,
      };
    },
    triggerFailure({ failureExitCode }) {
      calls.push(["failure", failureExitCode]);
      return {
        status: failureExitCode,
        signal: null,
        stderr: "simulated controlled failure",
        stdout: "",
      };
    },
  });

  const targetRoot = join(workspaceRoot, DEFAULT_TARGET_NAME);
  const markerPath = join(targetRoot, ROLLBACK_MARKER_NAME);
  const mutationMarkerPath = join(targetRoot, MUTATION_MARKER_NAME);

  assert.equal(result.kind, "rollback-controlled-drill");
  assert.equal(result.status, "passed");
  assert.deepEqual(calls.map(([kind]) => kind), ["snapshot", "failure", "restore"]);
  assert.equal(result.controlledFailure.status, CONTROLLED_FAILURE_EXIT_CODE);
  assert.equal(result.markerPath, markerPath);
  assert.ok(result.parity.backendReady);
  assert.ok(result.parity.aiReady);
  assert.ok(result.parity.runtimeParity);
  assert.ok(result.parity.dbCompatibility);
  assert.ok(result.parity.telemetryParity);
  assert.ok(result.parity.gatewayParity);
  assert.ok(result.parity.provenanceParity);
  assert.ok(result.parity.mutationMarkerRemoved);
  assert.ok(!existsSync(mutationMarkerPath));
  assert.ok(existsSync(markerPath));
  assert.deepEqual(
    JSON.parse(readFileSync(markerPath, "utf8")),
    result.marker,
  );
  assert.deepEqual(
    JSON.parse(readFileSync(artifactPath, "utf8")),
    result,
  );
  assert.equal(
    JSON.parse(readFileSync(join(targetRoot, "provenance", "rollback-provenance.json"), "utf8")).workflowRunId,
    "run-456",
  );
});

test("rollback drill harness fails closed when the controlled failure does not fail", () => {
  const workspaceRoot = mkdtempSync(join(tmpdir(), "rollback-drill-harness-closed-"));
  const snapshotRoot = join(workspaceRoot, "snapshot");

  assert.throws(
    () =>
      runControlledRollbackDrill({
        workspaceRoot,
        baselineSha: "c".repeat(40),
        candidateSha: "c".repeat(40),
        createSnapshot({ sourceRoot }) {
          cloneDirectory(sourceRoot, snapshotRoot);
          return {
            archivePath: join(workspaceRoot, "evidence", "snapshot.tar.gz"),
            checksumPath: join(workspaceRoot, "evidence", "snapshot.tar.gz.sha256"),
            sha256: "f".repeat(64),
            entries: ["backend/readiness.json"],
          };
        },
        restoreSnapshot() {
          throw new Error("restore should not be called when the failure gate does not fail");
        },
        triggerFailure() {
          return {
            status: 0,
            signal: null,
            stderr: "",
            stdout: "",
          };
        },
      }),
    /unexpectedly succeeded/u,
  );
});
