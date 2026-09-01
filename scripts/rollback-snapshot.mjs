#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  copyFileSync,
  chmodSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  readlinkSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, posix, relative } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
export const REPOSITORY_ROOT = join(scriptDirectory, "..");

export const DEFAULT_SNAPSHOT_EXCLUDES = [
  ".git/",
  "node_modules/",
  "DE/",
  ".env",
  ".env.*",
  ".releases/",
  ".run/",
  ".venv/",
  "venv/",
  "**/.venv/",
  "**/venv/",
  "ai/.venv/",
  "__pycache__/",
  "*.pyc",
  "logs/",
  "*.log",
  ".pytest_cache/",
  ".ruff_cache/",
  ".mypy_cache/",
  ".cache/",
];

function ensureTrailingSlash(pathValue) {
  return pathValue.endsWith("/") ? pathValue : `${pathValue}/`;
}

function normalizeSnapshotRelPath(rootPath, entryPath) {
  const rel = relative(rootPath, entryPath);
  if (!rel || rel === ".") {
    return "";
  }
  return rel.replace(/\\/g, "/");
}

function normalizeSnapshotPattern(pattern) {
  return String(pattern).replace(/\\/g, "/").replace(/^\.\/+/u, "").replace(/^\/+/u, "");
}

function matchesSnapshotExcludePattern(relPath, pattern) {
  const normalizedPattern = normalizeSnapshotPattern(pattern);
  if (!normalizedPattern) {
    return false;
  }

  const pathValue = relPath.replace(/\\/g, "/");
  const leaf = pathValue.split("/").at(-1) ?? "";

  if (normalizedPattern.includes("**/")) {
    const shortPattern = normalizedPattern.replace(/\*\*\//gu, "");
    return (
      pathValue === shortPattern ||
      pathValue.startsWith(`${shortPattern}/`) ||
      pathValue.split("/").includes(shortPattern)
    );
  }

  if (normalizedPattern.endsWith("/")) {
    const directoryName = normalizedPattern.slice(0, -1);
    return (
      pathValue === directoryName ||
      pathValue.startsWith(`${directoryName}/`) ||
      pathValue.split("/").includes(directoryName)
    );
  }

  if (normalizedPattern === ".env.*") {
    return leaf === ".env" || leaf.startsWith(".env.");
  }

  if (normalizedPattern.startsWith("*")) {
    return leaf.endsWith(normalizedPattern.slice(1));
  }

  return (
    pathValue === normalizedPattern ||
    pathValue.startsWith(`${normalizedPattern}/`) ||
    pathValue.split("/").includes(normalizedPattern)
  );
}

function shouldExcludeSnapshotPath(relPath, excludePatterns) {
  return excludePatterns.some((pattern) => matchesSnapshotExcludePattern(relPath, pattern));
}

function mirrorSnapshotDirectoryContents(sourceRoot, destinationRoot, excludePatterns) {
  mkdirSync(destinationRoot, { recursive: true });
  for (const entry of existsSync(sourceRoot) ? readdirSync(sourceRoot, { withFileTypes: true }) : []) {
    const sourceEntryPath = join(sourceRoot, entry.name);
    const destinationEntryPath = join(destinationRoot, entry.name);
    const relativePath = normalizeSnapshotRelPath(sourceRoot, sourceEntryPath);
    if (shouldExcludeSnapshotPath(relativePath, excludePatterns)) {
      continue;
    }
    if (entry.isDirectory()) {
      mirrorSnapshotDirectoryContents(sourceEntryPath, destinationEntryPath, excludePatterns);
      continue;
    }
    if (entry.isFile()) {
      mkdirSync(dirname(destinationEntryPath), { recursive: true });
      copyFileSync(sourceEntryPath, destinationEntryPath);
      continue;
    }
    if (entry.isSymbolicLink()) {
      const linkTargetPath = readlinkSync(sourceEntryPath);
      symlinkSync(linkTargetPath, destinationEntryPath);
    }
  }
}

export function mirrorSnapshotDirectory(sourceRoot, destinationRoot, excludePatterns = DEFAULT_SNAPSHOT_EXCLUDES) {
  rmSync(destinationRoot, { recursive: true, force: true });
  mirrorSnapshotDirectoryContents(sourceRoot, destinationRoot, excludePatterns);
}

function isMissingCommandError(result, commandName) {
  return Boolean(
    result?.error &&
      (result.error.code === "ENOENT" ||
        String(result.error.message ?? "").includes(`spawnSync ${commandName} ENOENT`))
  );
}

function normalizeArchiveEntry(entry) {
  const trimmed = entry.trim().replace(/\\/g, "/").replace(/^\.\/+/, "").replace(/^\/+/, "");
  const normalized = posix.normalize(trimmed);
  return normalized === "." ? "" : normalized;
}

function isDisallowedArchiveEntry(entry) {
  if (!entry) {
    return false;
  }

  if (entry === ".." || entry.startsWith("../") || entry.includes("/../")) {
    return true;
  }

  const segments = entry.split("/");
  const leaf = segments[segments.length - 1];

  if (segments.some((segment) => [".git", "node_modules", "DE", ".run", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".cache", ".venv"].includes(segment))) {
    return true;
  }
  if (segments.includes(".releases") || segments.includes("venv")) {
    return true;
  }
  if (entry.includes("ai/.venv/") || entry === "ai/.venv") {
    return true;
  }
  if (segments.includes("logs")) {
    return true;
  }
  if (leaf === ".env" || leaf.startsWith(".env.")) {
    return true;
  }
  if (leaf.endsWith(".pyc") || leaf.endsWith(".log") || leaf.endsWith(".pid") || leaf.endsWith(".sock")) {
    return true;
  }
  return false;
}

export function assertSnapshotArchiveSafe(entries) {
  const disallowed = [];
  for (const rawEntry of entries) {
    const entry = normalizeArchiveEntry(rawEntry);
    if (!entry) {
      continue;
    }
    if (isDisallowedArchiveEntry(entry)) {
      disallowed.push(rawEntry);
    }
  }
  if (disallowed.length > 0) {
    throw new Error(`Snapshot archive contains disallowed entries: ${disallowed.join(", ")}`);
  }
}

export function buildSourceSnapshotStageCommand({
  sourceRoot = REPOSITORY_ROOT,
  stagingRoot,
  excludePatterns = DEFAULT_SNAPSHOT_EXCLUDES,
} = {}) {
  if (!stagingRoot) {
    throw new Error("stagingRoot is required");
  }

  return {
    command: "rsync",
    args: [
      "-a",
      "--delete",
      "--omit-dir-times",
      "--no-perms",
      "--no-owner",
      "--no-group",
      ...excludePatterns.map((pattern) => `--exclude=${pattern}`),
      ensureTrailingSlash(sourceRoot),
      ensureTrailingSlash(stagingRoot),
    ],
  };
}

export function buildSnapshotArchiveCommand({
  stagingRoot,
  archivePath,
} = {}) {
  if (!stagingRoot) {
    throw new Error("stagingRoot is required");
  }
  if (!archivePath) {
    throw new Error("archivePath is required");
  }

  return {
    command: "tar",
    args: ["-C", stagingRoot, "-czf", archivePath, "."],
  };
}

export function buildSnapshotEntryListCommand({ archivePath } = {}) {
  if (!archivePath) {
    throw new Error("archivePath is required");
  }
  return {
    command: "tar",
    args: ["-tzf", archivePath],
  };
}

export function buildSnapshotEntryMetadataCommand({ archivePath } = {}) {
  if (!archivePath) {
    throw new Error("archivePath is required");
  }
  return {
    command: "tar",
    args: ["-tvzf", archivePath],
  };
}

export function buildSnapshotExtractCommand({ archivePath, extractionRoot } = {}) {
  if (!archivePath) {
    throw new Error("archivePath is required");
  }
  if (!extractionRoot) {
    throw new Error("extractionRoot is required");
  }
  return {
    command: "tar",
    args: ["-xzf", archivePath, "-C", extractionRoot],
  };
}

export function buildSnapshotRestoreCommand({
  extractionRoot,
  remoteTarget,
  sshKeyPath,
  sshPort = "30233",
  excludePatterns = DEFAULT_SNAPSHOT_EXCLUDES,
} = {}) {
  if (!extractionRoot) {
    throw new Error("extractionRoot is required");
  }
  if (!remoteTarget) {
    throw new Error("remoteTarget is required");
  }
  if (!sshKeyPath) {
    throw new Error("sshKeyPath is required");
  }

  return {
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
      ...excludePatterns.map((pattern) => `--exclude=${pattern}`),
      "-e",
      `ssh -i ${sshKeyPath} -p ${sshPort}`,
      ensureTrailingSlash(extractionRoot),
      ensureTrailingSlash(remoteTarget),
    ],
  };
}

export function buildLocalSnapshotRestoreCommand({
  extractionRoot,
  localTarget,
  excludePatterns = DEFAULT_SNAPSHOT_EXCLUDES,
} = {}) {
  if (!extractionRoot) {
    throw new Error("extractionRoot is required");
  }
  if (!localTarget) {
    throw new Error("localTarget is required");
  }

  return {
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
      ...excludePatterns.map((pattern) => `--exclude=${pattern}`),
      ensureTrailingSlash(extractionRoot),
      ensureTrailingSlash(localTarget),
    ],
  };
}

export function computeFileSha256(filePath) {
  const digest = createHash("sha256");
  digest.update(readFileSync(filePath));
  return digest.digest("hex");
}

export function writeSnapshotChecksum(checksumPath, sha256) {
  mkdirSync(dirname(checksumPath), { recursive: true });
  writeFileSync(checksumPath, `${sha256}\n`, "utf8");
}

export function protectSnapshotArtifacts(paths, { chmod = chmodSync } = {}) {
  for (const pathValue of paths) {
    chmod(pathValue, 0o600);
  }
}

function ensureRunSucceeded(result, description) {
  if (result.error) {
    throw new Error(`${description} failed: ${result.error.message}`);
  }
  if (typeof result.status === "number" && result.status !== 0) {
    const stderr = typeof result.stderr === "string" ? result.stderr.trim() : "";
    throw new Error(`${description} failed with exit ${result.status}${stderr ? `: ${stderr}` : ""}`);
  }
}

function splitArchiveEntries(stdout) {
  return stdout
    .split(/\r?\n/u)
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function splitArchiveMetadataLines(stdout) {
  return stdout
    .split(/\r?\n/u)
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function assertSnapshotArchiveLinkSafety(metadataLines) {
  const disallowed = [];
  for (const rawLine of metadataLines) {
    const line = rawLine.trimStart();
    if (!line) {
      continue;
    }
    const type = line[0];
    if (type === "l" || type === "h") {
      disallowed.push(rawLine);
    }
  }
  if (disallowed.length > 0) {
    throw new Error(`Snapshot archive contains disallowed entries: ${disallowed.join(", ")}`);
  }
}

export function verifySnapshotArchive({
  archivePath,
  checksumPath,
  run = spawnSync,
} = {}) {
  if (!archivePath) {
    throw new Error("archivePath is required");
  }
  if (!checksumPath) {
    throw new Error("checksumPath is required");
  }
  if (!existsSync(archivePath)) {
    throw new Error(`Snapshot archive does not exist: ${archivePath}`);
  }
  if (!existsSync(checksumPath)) {
    throw new Error(`Snapshot checksum does not exist: ${checksumPath}`);
  }

  const expectedSha256 = readFileSync(checksumPath, "utf8").trim();
  const actualSha256 = computeFileSha256(archivePath);
  if (expectedSha256 !== actualSha256) {
    throw new Error(`Snapshot checksum mismatch for ${archivePath}`);
  }

  const listResult = run(buildSnapshotEntryListCommand({ archivePath }).command, buildSnapshotEntryListCommand({ archivePath }).args, {
    encoding: "utf8",
    shell: false,
    stdio: "pipe",
  });
  ensureRunSucceeded(listResult, "Snapshot archive listing");

  const entries = splitArchiveEntries(listResult.stdout ?? "");
  assertSnapshotArchiveSafe(entries);
  const metadataCommand = buildSnapshotEntryMetadataCommand({ archivePath });
  const metadataResult = run(metadataCommand.command, metadataCommand.args, {
    encoding: "utf8",
    shell: false,
    stdio: "pipe",
  });
  ensureRunSucceeded(metadataResult, "Snapshot archive metadata");
  assertSnapshotArchiveLinkSafety(splitArchiveMetadataLines(metadataResult.stdout ?? ""));
  return { archivePath, checksumPath, sha256: actualSha256, entries };
}

export function createRollbackSnapshot({
  sourceRoot = REPOSITORY_ROOT,
  archivePath,
  checksumPath,
  run = spawnSync,
  chmod = chmodSync,
  mkdtemp = mkdtempSync,
  tmpdirBase = join(tmpdir(), "quantagent-rollback-snapshot-stage-"),
} = {}) {
  if (!sourceRoot) {
    throw new Error("sourceRoot is required");
  }
  if (!archivePath) {
    throw new Error("archivePath is required");
  }
  if (!checksumPath) {
    throw new Error("checksumPath is required");
  }

  const stagingRoot = mkdtemp(tmpdirBase);
  try {
    const stageCommand = buildSourceSnapshotStageCommand({ sourceRoot, stagingRoot });
    const stageResult = run(stageCommand.command, stageCommand.args, {
      encoding: "utf8",
      shell: false,
      stdio: "inherit",
    });
    if (isMissingCommandError(stageResult, "rsync")) {
      mirrorSnapshotDirectory(sourceRoot, stagingRoot);
    } else {
      ensureRunSucceeded(stageResult, "Snapshot staging");
    }

    const archiveCommand = buildSnapshotArchiveCommand({ stagingRoot, archivePath });
    const archiveResult = run(archiveCommand.command, archiveCommand.args, {
      encoding: "utf8",
      shell: false,
      stdio: "inherit",
    });
    ensureRunSucceeded(archiveResult, "Snapshot archive creation");

    writeSnapshotChecksum(checksumPath, computeFileSha256(archivePath));
    const verification = verifySnapshotArchive({ archivePath, checksumPath, run });
    protectSnapshotArtifacts([archivePath, checksumPath], { chmod });
    return verification;
  } finally {
    rmSync(stagingRoot, { recursive: true, force: true });
  }
}

export function restoreRollbackSnapshot({
  archivePath,
  checksumPath,
  remoteTarget,
  sshKeyPath,
  sshPort = "30233",
  run = spawnSync,
  mkdtemp = mkdtempSync,
  tmpdirBase = join(tmpdir(), "quantagent-rollback-snapshot-restore-"),
} = {}) {
  const verification = verifySnapshotArchive({ archivePath, checksumPath, run });
  const extractionRoot = mkdtemp(tmpdirBase);
  try {
    const extractCommand = buildSnapshotExtractCommand({ archivePath, extractionRoot });
    const extractResult = run(extractCommand.command, extractCommand.args, {
      encoding: "utf8",
      shell: false,
      stdio: "inherit",
    });
    ensureRunSucceeded(extractResult, "Snapshot extraction");

    const restoreCommand = buildSnapshotRestoreCommand({
      extractionRoot,
      remoteTarget,
      sshKeyPath,
      sshPort,
    });
    const restoreResult = run(restoreCommand.command, restoreCommand.args, {
      encoding: "utf8",
      shell: false,
      stdio: "inherit",
    });
    ensureRunSucceeded(restoreResult, "Snapshot restore");

    return { ...verification, extractionRoot, remoteTarget, sshKeyPath, sshPort };
  } finally {
    rmSync(extractionRoot, { recursive: true, force: true });
  }
}

export function restoreLocalRollbackSnapshot({
  archivePath,
  checksumPath,
  localTarget,
  run = spawnSync,
  mkdtemp = mkdtempSync,
  tmpdirBase = join(tmpdir(), "quantagent-rollback-local-restore-"),
} = {}) {
  const verification = verifySnapshotArchive({ archivePath, checksumPath, run });
  const extractionRoot = mkdtemp(tmpdirBase);
  try {
    const extractCommand = buildSnapshotExtractCommand({ archivePath, extractionRoot });
    const extractResult = run(extractCommand.command, extractCommand.args, {
      encoding: "utf8",
      shell: false,
      stdio: "inherit",
    });
    ensureRunSucceeded(extractResult, "Snapshot extraction");

    const restoreCommand = buildLocalSnapshotRestoreCommand({
      extractionRoot,
      localTarget,
    });
    const restoreResult = run(restoreCommand.command, restoreCommand.args, {
      encoding: "utf8",
      shell: false,
      stdio: "inherit",
    });
    if (isMissingCommandError(restoreResult, "rsync")) {
      mirrorSnapshotDirectory(extractionRoot, localTarget);
    } else {
      ensureRunSucceeded(restoreResult, "Local snapshot restore");
    }

    return { ...verification, extractionRoot, localTarget };
  } finally {
    rmSync(extractionRoot, { recursive: true, force: true });
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

export async function runRollbackSnapshotCli(argv = process.argv.slice(2)) {
  const [commandName, ...rest] = argv;
  const options = parseCliArguments(rest);

  switch (commandName) {
    case "archive": {
      const result = createRollbackSnapshot({
        sourceRoot: options.sourceRoot,
        archivePath: options.archive,
        checksumPath: options.checksum,
      });
      process.stdout.write(
        `${JSON.stringify(
          {
            archivePath: result.archivePath,
            checksumPath: result.checksumPath,
            sha256: result.sha256,
          },
          null,
          2
        )}\n`
      );
      return 0;
    }
    case "verify": {
      const result = verifySnapshotArchive({
        archivePath: options.archive,
        checksumPath: options.checksum,
      });
      process.stdout.write(
        `${JSON.stringify(
          {
            archivePath: result.archivePath,
            checksumPath: result.checksumPath,
            sha256: result.sha256,
            entries: result.entries.length,
          },
          null,
          2
        )}\n`
      );
      return 0;
    }
    case "restore": {
      restoreRollbackSnapshot({
        archivePath: options.archive,
        checksumPath: options.checksum,
        remoteTarget: options.remoteTarget,
        sshKeyPath: options.sshKey,
        sshPort: options.sshPort ?? "30233",
      });
      process.stdout.write(
        `${JSON.stringify(
          {
            archivePath: options.archive,
            checksumPath: options.checksum,
            remoteTarget: options.remoteTarget,
            status: "restored",
          },
          null,
          2
        )}\n`
      );
      return 0;
    }
    default:
      throw new Error(
        "Usage: rollback-snapshot.mjs <archive|verify|restore> --archive PATH --checksum PATH [--source-root PATH] [--remote-target USER@HOST:PATH] [--ssh-key PATH] [--ssh-port PORT]"
      );
  }
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  try {
    process.exitCode = await runRollbackSnapshotCli();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`${message}\n`);
    process.exitCode = 1;
  }
}

export {
  createRollbackSnapshot as createDeploySnapshot,
  restoreRollbackSnapshot as restoreDeploySnapshot,
  restoreLocalRollbackSnapshot as restoreLocalDeploySnapshot,
  runRollbackSnapshotCli as runDeploySnapshotCli,
};
