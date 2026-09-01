#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
import { pathToFileURL } from "node:url";

import { createRollbackSnapshot, restoreLocalRollbackSnapshot } from "./rollback-snapshot.mjs";
import {
  REQUIRED_AI_READINESS_CHECKS,
  REQUIRED_READINESS_CHECKS,
  validateReadinessPayload,
} from "./readiness-semantic-gate.mjs";

export const CONTROLLED_FAILURE_EXIT_CODE = 23;
export const CONTROLLED_FAILURE_POINT = "after-mutation-marker";
export const DEFAULT_TARGET_NAME = "local-release-sandbox";
export const DEFAULT_WORKSPACE_PREFIX = "quantagent-rollback-drill-";
export const ROLLBACK_MARKER_NAME = "rollback-applied.marker";
export const MUTATION_MARKER_NAME = "mutation/mutation-marker.json";

function ensureDirectory(pathValue) {
  mkdirSync(pathValue, { recursive: true });
}

function writeJsonFile(pathValue, value) {
  ensureDirectory(dirname(pathValue));
  writeFileSync(pathValue, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function readJsonFile(pathValue) {
  return JSON.parse(readFileSync(pathValue, "utf8"));
}

function buildReadinessPayload(requiredChecks) {
  return {
    status: "ready",
    checks: requiredChecks.map((name) => ({
      name,
      ready: true,
      reason: null,
    })),
  };
}

export function buildRollbackDrillFixture({
  baselineSha,
  candidateSha = baselineSha,
  workflowRunId = "local-run",
  targetName = DEFAULT_TARGET_NAME,
} = {}) {
  if (!baselineSha) {
    throw new Error("baselineSha is required");
  }
  if (!candidateSha) {
    throw new Error("candidateSha is required");
  }

  return Object.freeze({
    backend: buildReadinessPayload(REQUIRED_READINESS_CHECKS),
    ai: buildReadinessPayload(REQUIRED_AI_READINESS_CHECKS),
    runtime: {
      appEnv: "release-test",
      aiJobStore: "persistent",
      aiAuditSink: "file",
      aiAuditProductionEnabled: false,
      signerPresent: true,
      traceCorrelation: true,
    },
    db: {
      source: "postgres",
      schemaCompatibility: "compatible",
      schemaVersion: "ai-mvp.v1",
      sourceRevision: baselineSha,
      candidateRevision: candidateSha,
      restoredRevision: baselineSha,
    },
    telemetry: {
      auditSink: "file",
      auditParity: "match",
      redaction: true,
      traceCorrelation: true,
    },
    gateway: {
      gatewayHealthy: true,
      unknownRouteStatus: 404,
      allowedRoutes: ["/", "/health", "/readiness", "/ai-api/readiness"],
    },
    provenance: {
      drill: true,
      drillMode: "controlled-failure",
      targetName,
      baselineSha,
      candidateSha,
      restoredSha: baselineSha,
      workflowRunId,
      rollbackMarkerName: ROLLBACK_MARKER_NAME,
      mutationMarkerName: MUTATION_MARKER_NAME,
      failurePoint: CONTROLLED_FAILURE_POINT,
    },
  });
}

export function seedRollbackDrillFixture(targetRoot, fixture) {
  if (!targetRoot) {
    throw new Error("targetRoot is required");
  }
  if (!fixture) {
    throw new Error("fixture is required");
  }

  writeJsonFile(join(targetRoot, "backend", "readiness.json"), fixture.backend);
  writeJsonFile(join(targetRoot, "ai", "readiness.json"), fixture.ai);
  writeJsonFile(join(targetRoot, "runtime", "runtime.json"), fixture.runtime);
  writeJsonFile(join(targetRoot, "db", "schema.json"), fixture.db);
  writeJsonFile(join(targetRoot, "telemetry", "audit.json"), fixture.telemetry);
  writeJsonFile(join(targetRoot, "fe", "gateway.json"), fixture.gateway);
  writeJsonFile(join(targetRoot, "provenance", "rollback-provenance.json"), fixture.provenance);
}

export function mutateRollbackDrillFixture(targetRoot, {
  workflowRunId = "local-run",
} = {}) {
  const backendPath = join(targetRoot, "backend", "readiness.json");
  const aiPath = join(targetRoot, "ai", "readiness.json");
  const runtimePath = join(targetRoot, "runtime", "runtime.json");
  const dbPath = join(targetRoot, "db", "schema.json");
  const telemetryPath = join(targetRoot, "telemetry", "audit.json");
  const gatewayPath = join(targetRoot, "fe", "gateway.json");
  const provenancePath = join(targetRoot, "provenance", "rollback-provenance.json");

  const backend = readJsonFile(backendPath);
  backend.status = "degraded";
  backend.checks = backend.checks.filter((check) => check.name !== "redis");
  writeJsonFile(backendPath, backend);

  const ai = readJsonFile(aiPath);
  ai.status = "degraded";
  ai.checks = ai.checks.filter((check) => check.name !== "rule_draft_signer");
  writeJsonFile(aiPath, ai);

  const runtime = readJsonFile(runtimePath);
  runtime.appEnv = "broken";
  runtime.aiJobStore = "memory";
  runtime.aiAuditSink = "noop";
  runtime.aiAuditProductionEnabled = true;
  runtime.signerPresent = false;
  runtime.traceCorrelation = false;
  writeJsonFile(runtimePath, runtime);

  const db = readJsonFile(dbPath);
  db.schemaCompatibility = "broken";
  db.sourceRevision = "mutated";
  db.restoredRevision = "mutated";
  writeJsonFile(dbPath, db);

  const telemetry = readJsonFile(telemetryPath);
  telemetry.auditSink = "noop";
  telemetry.auditParity = "mismatch";
  telemetry.redaction = false;
  telemetry.traceCorrelation = false;
  writeJsonFile(telemetryPath, telemetry);

  const gateway = readJsonFile(gatewayPath);
  gateway.gatewayHealthy = false;
  gateway.unknownRouteStatus = 500;
  gateway.allowedRoutes = ["/broken"];
  writeJsonFile(gatewayPath, gateway);

  writeJsonFile(join(targetRoot, MUTATION_MARKER_NAME), {
    kind: "mutation-marker",
    failurePoint: CONTROLLED_FAILURE_POINT,
    workflowRunId,
    status: "armed",
  });

  const provenance = readJsonFile(provenancePath);
  provenance.drillMode = "mutation-armed";
  provenance.workflowRunId = workflowRunId;
  writeJsonFile(provenancePath, provenance);
}

export function triggerControlledFailure({
  run = spawnSync,
  failureExitCode = CONTROLLED_FAILURE_EXIT_CODE,
  failurePoint = CONTROLLED_FAILURE_POINT,
} = {}) {
  const result = run(
    process.execPath,
    [
      "-e",
      `process.stderr.write(${JSON.stringify(`controlled rollback drill failure at ${failurePoint}\\n`)}); process.exit(${Number(failureExitCode)});`,
    ],
    {
      encoding: "utf8",
      shell: false,
      stdio: "pipe",
    },
  );

  return {
    status: typeof result.status === "number" ? result.status : null,
    signal: result.signal ?? null,
    stdout: typeof result.stdout === "string" ? result.stdout : "",
    stderr: typeof result.stderr === "string" ? result.stderr.trim() : "",
  };
}

export function validateRollbackDrillFixture(targetRoot, expectedFixture) {
  const backend = readJsonFile(join(targetRoot, "backend", "readiness.json"));
  const ai = readJsonFile(join(targetRoot, "ai", "readiness.json"));
  const runtime = readJsonFile(join(targetRoot, "runtime", "runtime.json"));
  const db = readJsonFile(join(targetRoot, "db", "schema.json"));
  const telemetry = readJsonFile(join(targetRoot, "telemetry", "audit.json"));
  const gateway = readJsonFile(join(targetRoot, "fe", "gateway.json"));
  const provenance = readJsonFile(join(targetRoot, "provenance", "rollback-provenance.json"));

  validateReadinessPayload(backend, { requiredChecks: REQUIRED_READINESS_CHECKS });
  validateReadinessPayload(ai, { requiredChecks: REQUIRED_AI_READINESS_CHECKS });

  assert.deepStrictEqual(runtime, expectedFixture.runtime, "runtime parity mismatch");
  assert.deepStrictEqual(db, expectedFixture.db, "database compatibility mismatch");
  assert.deepStrictEqual(telemetry, expectedFixture.telemetry, "telemetry parity mismatch");
  assert.deepStrictEqual(gateway, expectedFixture.gateway, "frontend gateway parity mismatch");
  assert.deepStrictEqual(provenance, expectedFixture.provenance, "rollback provenance mismatch");

  if (existsSync(join(targetRoot, MUTATION_MARKER_NAME))) {
    throw new Error("mutation marker survived rollback");
  }

  return {
    backendReady: true,
    aiReady: true,
    runtimeParity: true,
    dbCompatibility: true,
    telemetryParity: true,
    gatewayParity: true,
    provenanceParity: true,
    mutationMarkerRemoved: true,
  };
}

function acquireWorkspaceRoot({
  workspaceRoot,
  mkdtemp = mkdtempSync,
  tmpdirBase = join(tmpdir(), DEFAULT_WORKSPACE_PREFIX),
} = {}) {
  if (workspaceRoot) {
    ensureDirectory(workspaceRoot);
    return {
      workspaceRoot,
      cleanup: () => {},
    };
  }

  const createdWorkspaceRoot = mkdtemp(tmpdirBase);
  return {
    workspaceRoot: createdWorkspaceRoot,
    cleanup: () => rmSync(createdWorkspaceRoot, { recursive: true, force: true }),
  };
}

export function runControlledRollbackDrill({
  workspaceRoot,
  targetName = DEFAULT_TARGET_NAME,
  baselineSha = process.env.GITHUB_SHA ?? process.env.RELEASE_TRUST_REVISION ?? "local-baseline",
  candidateSha = baselineSha,
  workflowRunId = process.env.GITHUB_RUN_ID ?? "local-run",
  createSnapshot = createRollbackSnapshot,
  restoreSnapshot = restoreLocalRollbackSnapshot,
  triggerFailure = triggerControlledFailure,
  run = spawnSync,
  mkdtemp = mkdtempSync,
  tmpdirBase = join(tmpdir(), DEFAULT_WORKSPACE_PREFIX),
  artifactPath,
  failureExitCode = CONTROLLED_FAILURE_EXIT_CODE,
  failurePoint = CONTROLLED_FAILURE_POINT,
} = {}) {
  const { workspaceRoot: activeWorkspaceRoot, cleanup } = acquireWorkspaceRoot({
    workspaceRoot,
    mkdtemp,
    tmpdirBase,
  });

  const targetRoot = join(activeWorkspaceRoot, targetName);
  const evidenceRoot = join(activeWorkspaceRoot, "evidence");
  ensureDirectory(targetRoot);
  ensureDirectory(evidenceRoot);

  const expectedFixture = buildRollbackDrillFixture({
    baselineSha,
    candidateSha,
    workflowRunId,
    targetName,
  });
  const archivePath = join(evidenceRoot, "rollback-drill-snapshot.tar.gz");
  const checksumPath = `${archivePath}.sha256`;

  try {
    seedRollbackDrillFixture(targetRoot, expectedFixture);

    const snapshot = createSnapshot({
      sourceRoot: targetRoot,
      archivePath,
      checksumPath,
      run,
    });

    mutateRollbackDrillFixture(targetRoot, { workflowRunId });

    const controlledFailure = triggerFailure({
      run,
      failureExitCode,
      failurePoint,
    });
    if (typeof controlledFailure.status !== "number" || controlledFailure.status === 0) {
      throw new Error("controlled rollback failure unexpectedly succeeded");
    }

    const restored = restoreSnapshot({
      archivePath,
      checksumPath,
      localTarget: targetRoot,
      run,
    });

    const parity = validateRollbackDrillFixture(targetRoot, expectedFixture);
    const markerPath = join(targetRoot, ROLLBACK_MARKER_NAME);
    const marker = {
      kind: "rollback-applied",
      baselineSha,
      candidateSha,
      restoredSha: baselineSha,
      workflowRunId,
      failurePoint,
      failureExitCode: controlledFailure.status,
      snapshotSha256: snapshot.sha256,
      snapshotEntries: snapshot.entries.length,
      provenanceChecksumPath: checksumPath,
    };
    writeJsonFile(markerPath, marker);

    const report = {
      kind: "rollback-controlled-drill",
      status: "passed",
      workspaceRoot: activeWorkspaceRoot,
      targetRoot,
      evidenceRoot,
      baselineSha,
      candidateSha,
      restoredSha: baselineSha,
      workflowRunId,
      targetName,
      failurePoint,
      controlledFailure,
      snapshot: {
        archivePath,
        checksumPath,
        sha256: snapshot.sha256,
        entries: snapshot.entries,
      },
      restore: {
        localTarget: restored.localTarget,
        extractionRoot: restored.extractionRoot,
      },
      parity,
      provenance: {
        ...expectedFixture.provenance,
        snapshotSha256: snapshot.sha256,
        failureExitCode: controlledFailure.status,
        markerPath,
      },
      markerPath,
      marker,
    };

    if (artifactPath) {
      writeJsonFile(artifactPath, report);
    }

    return report;
  } finally {
    cleanup();
  }
}

function parseCliArguments(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (!argument.startsWith("--")) {
      throw new Error(`Unexpected argument: ${argument}`);
    }
    const key = argument.slice(2).replace(/-([a-z])/gu, (_, letter) => letter.toUpperCase());
    const next = argv[index + 1];
    if (!next || next.startsWith("--")) {
      options[key] = true;
      continue;
    }
    options[key] = next;
    index += 1;
  }
  return options;
}

export async function runControlledRollbackDrillCli(argv = process.argv.slice(2)) {
  const options = parseCliArguments(argv);
  const result = runControlledRollbackDrill({
    workspaceRoot: options.workspaceRoot,
    artifactPath: options.artifact,
    baselineSha: options.baselineSha,
    candidateSha: options.candidateSha,
    workflowRunId: options.workflowRunId,
    targetName: options.targetName,
    failureExitCode: options.failureExitCode == null ? CONTROLLED_FAILURE_EXIT_CODE : Number(options.failureExitCode),
    failurePoint: typeof options.failurePoint === "string" ? options.failurePoint : CONTROLLED_FAILURE_POINT,
  });

  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  return 0;
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  try {
    process.exitCode = await runControlledRollbackDrillCli();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`${message}\n`);
    process.exitCode = 1;
  }
}
