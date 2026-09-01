import assert from "node:assert/strict";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  assertSnapshotArchiveSafe,
  buildSourceSnapshotStageCommand,
  buildSnapshotArchiveCommand,
  buildSnapshotEntryListCommand,
  buildSnapshotEntryMetadataCommand,
  buildSnapshotExtractCommand,
  buildLocalSnapshotRestoreCommand,
  buildSnapshotRestoreCommand,
  computeFileSha256,
  createRollbackSnapshot,
  mirrorSnapshotDirectory,
  protectSnapshotArtifacts,
  restoreLocalRollbackSnapshot,
  restoreRollbackSnapshot,
  verifySnapshotArchive,
  writeSnapshotChecksum,
} from "./rollback-snapshot.mjs";

test("rollback snapshot stage and restore commands preserve the source/assets exclusion contract", () => {
  const stageCommand = buildSourceSnapshotStageCommand({
    sourceRoot: "/repo",
    stagingRoot: "/stage",
  });
  const restoreCommand = buildSnapshotRestoreCommand({
    extractionRoot: "/extract",
    remoteTarget: "etluser@quant-agent.kro.kr:/home/etluser/mvp_sp1/quant-proj/",
    sshKeyPath: "/tmp/id_rsa",
    sshPort: "30233",
  });
  const archiveCommand = buildSnapshotArchiveCommand({
    stagingRoot: "/stage",
    archivePath: "/tmp/snapshot.tar.gz",
  });
  const extractCommand = buildSnapshotExtractCommand({
    archivePath: "/tmp/snapshot.tar.gz",
    extractionRoot: "/extract",
  });

  assert.equal(stageCommand.command, "rsync");
  assert.equal(archiveCommand.command, "tar");
  assert.equal(extractCommand.command, "tar");
  assert.equal(restoreCommand.command, "rsync");
  assert.deepEqual(buildSnapshotEntryMetadataCommand({ archivePath: "/tmp/snapshot.tar.gz" }), {
    command: "tar",
    args: ["-tvzf", "/tmp/snapshot.tar.gz"],
  });
  assert.ok(stageCommand.args.includes("--delete"));
  assert.ok(stageCommand.args.includes("--exclude=.env"));
  assert.ok(stageCommand.args.includes("--exclude=.env.*"));
  assert.ok(stageCommand.args.includes("--exclude=.releases/"));
  assert.ok(stageCommand.args.includes("--exclude=.run/"));
  assert.ok(stageCommand.args.includes("--exclude=ai/.venv/"));
  assert.ok(stageCommand.args.includes("--exclude=venv/"));
  assert.ok(stageCommand.args.includes("--exclude=logs/"));
  assert.ok(stageCommand.args.includes("--exclude=*.log"));
  assert.ok(stageCommand.args.includes("--exclude=.pytest_cache/"));
  assert.ok(stageCommand.args.includes("--exclude=.ruff_cache/"));
  assert.ok(stageCommand.args.includes("--exclude=.mypy_cache/"));
  assert.ok(stageCommand.args.includes("/repo/"));
  assert.ok(stageCommand.args.includes("/stage/"));
  assert.ok(restoreCommand.args.includes("--delete"));
  assert.ok(restoreCommand.args.includes("-e"));
  assert.ok(restoreCommand.args.includes("ssh -i /tmp/id_rsa -p 30233"));
  assert.ok(restoreCommand.args.includes("--exclude=.env"));
  assert.ok(restoreCommand.args.includes("--exclude=.env.*"));
  assert.ok(restoreCommand.args.includes("--exclude=.releases/"));
  assert.ok(restoreCommand.args.includes("--exclude=.run/"));
  assert.ok(restoreCommand.args.includes("--exclude=ai/.venv/"));
  assert.ok(restoreCommand.args.includes("--exclude=venv/"));
  assert.ok(restoreCommand.args.includes("/extract/"));
  assert.ok(restoreCommand.args.includes("etluser@quant-agent.kro.kr:/home/etluser/mvp_sp1/quant-proj/"));
  assert.deepEqual(buildLocalSnapshotRestoreCommand({ extractionRoot: "/extract", localTarget: "/sandbox" }), {
    command: "rsync",
    args: [
      "-a",
      "--delete",
      "--stats",
      "--old-args",
      "--omit-dir-times",
      "--no-perms",
      "--no-owner",
      "--no-group",
      "--exclude=.git/",
      "--exclude=node_modules/",
      "--exclude=DE/",
      "--exclude=.env",
      "--exclude=.env.*",
      "--exclude=.releases/",
      "--exclude=.run/",
      "--exclude=.venv/",
      "--exclude=venv/",
      "--exclude=**/.venv/",
      "--exclude=**/venv/",
      "--exclude=ai/.venv/",
      "--exclude=__pycache__/",
      "--exclude=*.pyc",
      "--exclude=logs/",
      "--exclude=*.log",
      "--exclude=.pytest_cache/",
      "--exclude=.ruff_cache/",
      "--exclude=.mypy_cache/",
      "--exclude=.cache/",
      "/extract/",
      "/sandbox/",
    ],
  });
  assert.deepEqual(buildSnapshotEntryListCommand({ archivePath: "/tmp/snapshot.tar.gz" }), {
    command: "tar",
    args: ["-tzf", "/tmp/snapshot.tar.gz"],
  });
});

test("rollback snapshot archive safety rejects path traversal and secret/runtime entries", () => {
  assert.doesNotThrow(() =>
    assertSnapshotArchiveSafe([
      "./backend/app/main.py",
      "fe/dist/index.html",
      "scripts/rollback-snapshot.mjs",
    ])
  );

  assert.throws(() => assertSnapshotArchiveSafe(["../escape.txt"]), /disallowed entries/u);
  assert.throws(() => assertSnapshotArchiveSafe(["backend/.env"]), /disallowed entries/u);
  assert.throws(() => assertSnapshotArchiveSafe(["backend/.releases/snapshot.tar.gz"]), /disallowed entries/u);
  assert.throws(() => assertSnapshotArchiveSafe(["backend/logs/server.log"]), /disallowed entries/u);
  assert.throws(() => assertSnapshotArchiveSafe(["backend/__pycache__/module.pyc"]), /disallowed entries/u);
  assert.throws(() => assertSnapshotArchiveSafe(["ai/.venv/bin/python"]), /disallowed entries/u);
  assert.throws(() => assertSnapshotArchiveSafe(["backend/venv/bin/python"]), /disallowed entries/u);
});

test("rollback snapshot archive safety rejects symlink and hardlink members", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "rollback-snapshot-link-"));
  const archivePath = join(tempDir, "snapshot.tar.gz");
  const checksumPath = join(tempDir, "snapshot.tar.gz.sha256");
  writeFileSync(archivePath, "snapshot-bytes", "utf8");
  writeSnapshotChecksum(checksumPath, computeFileSha256(archivePath));

  assert.throws(
    () =>
      verifySnapshotArchive({
        archivePath,
        checksumPath,
        run(command, args) {
          if (command === "tar" && args[0] === "-tzf") {
            return { status: 0, stdout: "./backend/app/main.py\n" };
          }
          if (command === "tar" && args[0] === "-tvzf") {
            return {
              status: 0,
              stdout:
                "lrwxrwxrwx user/group 0 2026-08-27 12:34 ./backend/app/main.py -> /etc/passwd\n" +
                "hrw-r--r-- user/group 0 2026-08-27 12:34 ./backend/app/helper.py link to ./outside.txt\n",
            };
          }
          return { status: 0, stdout: "" };
        },
      }),
    /disallowed entries/u
  );
});

test("rollback snapshot checksum files record sha256 evidence and restricted permissions are applied", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "rollback-snapshot-test-"));
  const archivePath = join(tempDir, "snapshot.tar.gz");
  const checksumPath = join(tempDir, "snapshot.tar.gz.sha256");
  writeFileSync(archivePath, "snapshot-bytes", "utf8");

  const sha256 = computeFileSha256(archivePath);
  writeSnapshotChecksum(checksumPath, sha256);

  assert.equal(readFileSync(checksumPath, "utf8").trim(), sha256);

  const chmodCalls = [];
  protectSnapshotArtifacts([archivePath, checksumPath], {
    chmod(pathValue, mode) {
      chmodCalls.push([pathValue, mode]);
    },
  });

  assert.deepEqual(chmodCalls, [
    [archivePath, 0o600],
    [checksumPath, 0o600],
  ]);
});

test("mirrorSnapshotDirectory mirrors source files and drops excluded or stale destination content", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "rollback-snapshot-mirror-"));
  const sourceRoot = join(tempDir, "source");
  const destinationRoot = join(tempDir, "destination");
  mkdirSync(join(sourceRoot, "backend", "app"), { recursive: true });
  mkdirSync(join(sourceRoot, "logs"), { recursive: true });
  mkdirSync(join(destinationRoot, "obsolete"), { recursive: true });
  writeFileSync(join(sourceRoot, "backend", "app", "main.py"), "print('ok')\n", "utf8");
  writeFileSync(join(sourceRoot, "logs", "ignored.log"), "ignore-me\n", "utf8");
  writeFileSync(join(sourceRoot, ".env"), "SECRET=1\n", "utf8");
  writeFileSync(join(destinationRoot, "obsolete", "legacy.txt"), "legacy\n", "utf8");

  mirrorSnapshotDirectory(sourceRoot, destinationRoot);

  assert.equal(readFileSync(join(destinationRoot, "backend", "app", "main.py"), "utf8"), "print('ok')\n");
  assert.equal(existsSync(join(destinationRoot, "logs", "ignored.log")), false);
  assert.equal(existsSync(join(destinationRoot, ".env")), false);
  assert.equal(existsSync(join(destinationRoot, "obsolete", "legacy.txt")), false);
});

test("rollback snapshot checksum mismatch fails closed before restore", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "rollback-snapshot-mismatch-"));
  const archivePath = join(tempDir, "snapshot.tar.gz");
  const checksumPath = join(tempDir, "snapshot.tar.gz.sha256");
  writeFileSync(archivePath, "snapshot-bytes", "utf8");
  writeFileSync(checksumPath, "deadbeef\n", "utf8");

  assert.throws(
    () =>
      verifySnapshotArchive({
        archivePath,
        checksumPath,
        run(command, args) {
          if (command === "tar" && args[0] === "-tzf") {
            return { status: 0, stdout: "./backend/app/main.py\n" };
          }
          return { status: 0, stdout: "" };
        },
      }),
    /checksum mismatch/u
  );
});

test("createRollbackSnapshot stages the source tree, archives it, and writes checksum evidence", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "rollback-snapshot-create-"));
  const sourceRoot = join(tempDir, "source");
  const archivePath = join(tempDir, "snapshot.tar.gz");
  const checksumPath = join(tempDir, "snapshot.tar.gz.sha256");
  writeFileSync(archivePath, "snapshot-bytes", "utf8");

  const calls = [];
  const chmodCalls = [];
  const result = createRollbackSnapshot({
    sourceRoot,
    archivePath,
    checksumPath,
    mkdtemp: () => join(tempDir, "staging"),
    chmod(pathValue, mode) {
      chmodCalls.push([pathValue, mode]);
    },
    run(command, args, options) {
      calls.push({ command, args, options });
      if (command === "tar" && (args[0] === "-tzf" || args[0] === "-tvzf")) {
        return { status: 0, stdout: "./backend/app/main.py\nfe/dist/index.html\n" };
      }
      return { status: 0, stdout: "" };
    },
  });

  assert.equal(result.archivePath, archivePath);
  assert.equal(result.checksumPath, checksumPath);
  assert.equal(result.sha256, computeFileSha256(archivePath));
  assert.ok(calls.some(({ command, args }) => command === "rsync" && args.includes("--exclude=.env")));
  assert.ok(calls.some(({ command, args }) => command === "rsync" && args.includes("--exclude=.releases/")));
  assert.ok(calls.some(({ command, args }) => command === "tar" && args[0] === "-C"));
  assert.ok(calls.some(({ command, args }) => command === "tar" && args[0] === "-tvzf"));
  assert.deepEqual(chmodCalls, [
    [archivePath, 0o600],
    [checksumPath, 0o600],
  ]);
  assert.equal(readFileSync(checksumPath, "utf8").trim(), result.sha256);
});

test("verifySnapshotArchive rejects tampered checksums and restore replays the snapshot with rsync", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "rollback-snapshot-restore-"));
  const archivePath = join(tempDir, "snapshot.tar.gz");
  const checksumPath = join(tempDir, "snapshot.tar.gz.sha256");
  writeFileSync(archivePath, "snapshot-bytes", "utf8");
  writeSnapshotChecksum(checksumPath, computeFileSha256(archivePath));

  const calls = [];
  const verified = verifySnapshotArchive({
    archivePath,
    checksumPath,
    run(command, args) {
      calls.push({ command, args });
      if (command === "tar" && (args[0] === "-tzf" || args[0] === "-tvzf")) {
        return { status: 0, stdout: "./backend/app/main.py\nfe/dist/index.html\n" };
      }
      return { status: 0, stdout: "" };
    },
  });

  assert.equal(verified.entries.length, 2);

  const restoreResult = restoreRollbackSnapshot({
    archivePath,
    checksumPath,
    remoteTarget: "etluser@quant-agent.kro.kr:/home/etluser/mvp_sp1/quant-proj/",
    sshKeyPath: "/tmp/id_rsa",
    sshPort: "30233",
    mkdtemp: () => join(tempDir, "restore"),
    run(command, args) {
      calls.push({ command, args });
      if (command === "tar" && args[0] === "-tzf") {
        return { status: 0, stdout: "./backend/app/main.py\nfe/dist/index.html\n" };
      }
      return { status: 0, stdout: "" };
    },
  });

  assert.equal(restoreResult.remoteTarget, "etluser@quant-agent.kro.kr:/home/etluser/mvp_sp1/quant-proj/");
  assert.ok(calls.some(({ command, args }) => command === "tar" && args[0] === "-xzf"));
  assert.ok(calls.some(({ command, args }) => command === "rsync" && args.includes("-e")));
  assert.ok(calls.some(({ command, args }) => command === "rsync" && args.includes("ssh -i /tmp/id_rsa -p 30233")));
});

test("restoreLocalRollbackSnapshot replays the snapshot into a local target without SSH", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "rollback-snapshot-local-restore-"));
  const archivePath = join(tempDir, "snapshot.tar.gz");
  const checksumPath = join(tempDir, "snapshot.tar.gz.sha256");
  writeFileSync(archivePath, "snapshot-bytes", "utf8");
  writeSnapshotChecksum(checksumPath, computeFileSha256(archivePath));

  const calls = [];
  const restoreResult = restoreLocalRollbackSnapshot({
    archivePath,
    checksumPath,
    localTarget: "/tmp/local-target",
    mkdtemp: () => join(tempDir, "restore"),
    run(command, args) {
      calls.push({ command, args });
      if (command === "tar" && (args[0] === "-tzf" || args[0] === "-tvzf")) {
        return { status: 0, stdout: "./backend/app/main.py\nfe/dist/index.html\n" };
      }
      return { status: 0, stdout: "" };
    },
  });

  assert.equal(restoreResult.localTarget, "/tmp/local-target");
  assert.ok(calls.some(({ command, args }) => command === "tar" && args[0] === "-xzf"));
  assert.ok(calls.some(({ command, args }) => command === "rsync" && !args.includes("-e")));
  assert.ok(calls.some(({ command, args }) => command === "rsync" && args.includes("/tmp/local-target/")));
});
