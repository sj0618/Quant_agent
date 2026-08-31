#!/usr/bin/env node

/**
 * Local deterministic replay for a strategy-validation manifest. It neither opens
 * a network connection nor a database; fixture output is never production evidence.
 */
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const SCRIPT_DIRECTORY = dirname(fileURLToPath(import.meta.url));
export const REPOSITORY_ROOT = resolve(SCRIPT_DIRECTORY, "..", "..");
const DEFAULT_MANIFEST = resolve(
  SCRIPT_DIRECTORY,
  "..",
  "fixtures",
  "release-strategy-validation-manifest.json",
);
const SHA256 = /^[a-f0-9]{64}$/u;

export function canonicalJson(value) {
  if (Array.isArray(value)) return "[" + value.map(canonicalJson).join(",") + "]";
  if (value && typeof value === "object") {
    return "{" + Object.keys(value).sort()
      .map((key) => JSON.stringify(key) + ":" + canonicalJson(value[key]))
      .join(",") + "}";
  }
  if (typeof value === "number" && !Number.isFinite(value)) {
    throw new TypeError("manifest cannot contain non-finite numbers");
  }
  if (typeof value === "undefined" || typeof value === "function") {
    throw new TypeError("manifest must be JSON serializable");
  }
  return JSON.stringify(value);
}

export function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function requireString(value, name) {
  if (typeof value !== "string" || !value.trim()) {
    throw new TypeError(name + " must be a non-empty string");
  }
  return value;
}

export function validateManifest(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new TypeError("input manifest must be an object");
  }
  const manifest = {
    schema_version: requireString(input.schema_version, "schema_version"),
    source: requireString(input.source, "source"),
    as_of: requireString(input.as_of, "as_of"),
    source_version: requireString(input.source_version, "source_version"),
    lineage_hash: requireString(input.lineage_hash, "lineage_hash"),
    universe_snapshot_hash: requireString(input.universe_snapshot_hash, "universe_snapshot_hash"),
    indicator_input_hash: requireString(input.indicator_input_hash, "indicator_input_hash"),
    formula_version: requireString(input.formula_version, "formula_version"),
    seed_hash: requireString(input.seed_hash, "seed_hash"),
  };
  if (manifest.schema_version !== "pit-universe-evidence.v1") {
    throw new TypeError("unsupported schema_version");
  }
  if (!["fixture", "postgres"].includes(manifest.source)) {
    throw new TypeError("source must be fixture or postgres");
  }
  if (!/^\d{4}-\d{2}-\d{2}$/u.test(manifest.as_of)) {
    throw new TypeError("as_of must be an ISO-8601 date");
  }
  for (const field of [
    "lineage_hash",
    "universe_snapshot_hash",
    "indicator_input_hash",
    "seed_hash",
  ]) {
    if (!SHA256.test(manifest[field])) {
      throw new TypeError(field + " must be lowercase SHA-256");
    }
  }
  return manifest;
}

export function gitSha({ repositoryRoot = REPOSITORY_ROOT } = {}) {
  return execFileSync("git", ["rev-parse", "HEAD"], {
    cwd: repositoryRoot,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  }).trim();
}

export function limitationRecord(manifest) {
  return manifest.source === "postgres"
    ? {
        release_eligible: true,
        reason: "postgres manifest still needs independently reviewed server execution evidence",
        source: manifest.source,
      }
    : {
        release_eligible: false,
        reason: "fixture manifest: local deterministic contract only; not production or live-data evidence",
        source: manifest.source,
      };
}

export function replayOnce(manifest, { repositoryRoot = REPOSITORY_ROOT } = {}) {
  const inputHash = sha256(canonicalJson(manifest));
  const environmentHash = sha256(canonicalJson({
    arch: process.arch,
    node: process.version,
    platform: process.platform,
  }));
  const provenanceTrace = [
    {
      as_of: manifest.as_of,
      indicator_input_hash: manifest.indicator_input_hash,
      lineage_hash: manifest.lineage_hash,
      source: manifest.source,
      source_version: manifest.source_version,
      stage: "immutable_input",
      universe_snapshot_hash: manifest.universe_snapshot_hash,
    },
    {
      environment_hash: environmentHash,
      formula_version: manifest.formula_version,
      git_sha: gitSha({ repositoryRoot }),
      seed_hash: manifest.seed_hash,
      stage: "strategy_validation",
    },
  ];
  const output = {
    as_of: manifest.as_of,
    environment_hash: environmentHash,
    formula_version: manifest.formula_version,
    git_sha: gitSha({ repositoryRoot }),
    indicator_input_hash: manifest.indicator_input_hash,
    input_hash: inputHash,
    lineage_hash: manifest.lineage_hash,
    limitation_record: limitationRecord(manifest),
    provenance_trace: provenanceTrace,
    seed_hash: manifest.seed_hash,
    source: manifest.source,
    source_version: manifest.source_version,
    universe_snapshot_hash: manifest.universe_snapshot_hash,
  };
  return {
    ...output,
    provenance_trace_hash: sha256(canonicalJson(provenanceTrace)),
    output_hash: sha256(canonicalJson(output)),
  };
}

export function parseArgs(argv) {
  let inputManifest = "release";
  let runs = 2;
  let assertIdenticalOutputHash = false;
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--input-manifest") inputManifest = argv[++index];
    else if (argument === "--runs") runs = Number.parseInt(argv[++index], 10);
    else if (argument === "--assert-identical-output-hash") assertIdenticalOutputHash = true;
    else throw new TypeError("unknown argument: " + argument);
  }
  if (!Number.isInteger(runs) || runs < 2) {
    throw new TypeError("--runs must be an integer of at least 2");
  }
  if (!inputManifest) throw new TypeError("--input-manifest requires a value");
  return { assertIdenticalOutputHash, inputManifest, runs };
}

export function runReplay(argv = process.argv.slice(2), { repositoryRoot = REPOSITORY_ROOT } = {}) {
  const options = parseArgs(argv);
  const path = options.inputManifest === "release"
    ? DEFAULT_MANIFEST
    : resolve(repositoryRoot, options.inputManifest);
  const manifest = validateManifest(JSON.parse(readFileSync(path, "utf8")));
  const runs = Array.from({ length: options.runs }, () =>
    replayOnce(manifest, { repositoryRoot }),
  );
  const first = runs[0];
  const equality = {
    immutable_input_hash: runs.every((run) => run.input_hash === first.input_hash),
    git_sha: runs.every((run) => run.git_sha === first.git_sha),
    environment_hash: runs.every((run) => run.environment_hash === first.environment_hash),
    formula_version: runs.every((run) => run.formula_version === first.formula_version),
    seed_hash: runs.every((run) => run.seed_hash === first.seed_hash),
    output_hash: runs.every((run) => run.output_hash === first.output_hash),
    provenance_trace: runs.every((run) => run.provenance_trace_hash === first.provenance_trace_hash),
    limitation_record: runs.every((run) => canonicalJson(run.limitation_record) === canonicalJson(first.limitation_record)),
  };
  if (options.assertIdenticalOutputHash && Object.values(equality).some((value) => value !== true)) {
    throw new Error("replay provenance or output hashes differ");
  }
  return {
    contract: "strategy-validation-replay.v1",
    input_manifest: path,
    limitation_record: first.limitation_record,
    release_eligible: first.limitation_record.release_eligible,
    equality,
    runs,
  };
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  try {
    process.stdout.write(JSON.stringify(runReplay(), null, 2) + "\n");
  } catch (error) {
    process.stderr.write("[strategy-replay] " + error.message + "\n");
    process.exitCode = 1;
  }
}
