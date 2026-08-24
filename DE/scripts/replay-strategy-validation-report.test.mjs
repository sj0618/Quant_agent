import assert from "node:assert/strict";
import test from "node:test";

import {
  canonicalJson,
  parseArgs,
  replayOnce,
  runReplay,
  validateManifest,
} from "./replay-strategy-validation-report.mjs";

const MANIFEST = {
  schema_version: "pit-universe-evidence.v1",
  source: "fixture",
  as_of: "2026-08-22",
  source_version: "synthetic-pit-fixture-v1",
  lineage_hash: "4c0e3389b02630cf642596ad608b3160d4b26b644bbb0b3eece25c28ab8b3a0e",
  universe_snapshot_hash: "6cb8f8293820a9f07ab19b666db9bf6eb0c3a43f7a58eaa26111c8a1c0aa284d",
  indicator_input_hash: "e2ef68d1b5737374f02090df394a18d4c846fb0b7734f9188443e8cd99cc5bef",
  formula_version: "quant-strategy-formula.v1",
  seed_hash: "bbc81dc0d3938f51eef9dd4de5e3523f0e5ed7c4b635e3ece25a94f83acaa7d4",
};

test("canonical JSON is key-order independent", () => {
  assert.equal(canonicalJson({ b: 2, a: 1 }), canonicalJson({ a: 1, b: 2 }));
});

test("manifest rejects invalid evidence hashes", () => {
  assert.throws(
    () => validateManifest({ ...MANIFEST, lineage_hash: "not-a-hash" }),
    /lineage_hash must be lowercase SHA-256/u,
  );
});

test("fixture replay is deterministic and explicitly non-production", () => {
  const result = runReplay([
    "--input-manifest", "release", "--runs", "2", "--assert-identical-output-hash",
  ]);
  assert.equal(result.release_eligible, false);
  assert.match(result.limitation, /not production/u);
  assert.equal(result.runs[0].output_hash, result.runs[1].output_hash);
});

test("two direct runs have the same output hash", () => {
  const manifest = validateManifest(MANIFEST);
  assert.equal(replayOnce(manifest).output_hash, replayOnce(manifest).output_hash);
});

test("argument parsing refuses a one-run comparison", () => {
  assert.throws(() => parseArgs(["--runs", "1"]), /at least 2/u);
});
