#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const DEFAULT_BOARD = "docs/plans/quantagent-production-control-board.md";
const BOARD_MARKER = /<!--\s*control-board:v1\s*\n([\s\S]*?)\n\s*-->/u;
const SHA = /^[0-9a-f]{40}$/u;
const ZERO_SHA = /^0{40}$/u;
const KST_TIMESTAMP = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2} KST$/u;
const TRANSITION_STATES = new Set(["not_started", "in_progress", "blocked", "evidence_pending", "complete", "superseded"]);

function fail(message) {
  const error = new Error(message);
  error.code = "PLAN_CONTRACT_INVALID";
  throw error;
}

function requireNonEmptyString(value, field) {
  if (typeof value !== "string" || !value.trim()) fail(`${field} must be a non-empty string`);
  return value;
}

function requireArray(value, field) {
  if (!Array.isArray(value) || value.length === 0) fail(`${field} must be a non-empty array`);
  return value;
}

function requireCommitSha(value, field) {
  const sha = requireNonEmptyString(value, field);
  if (!SHA.test(sha) || ZERO_SHA.test(sha)) fail(`${field} must be a non-zero 40-character lowercase Git SHA`);
  return sha;
}

function runGit(args, repositoryRoot) {
  const result = spawnSync("git", args, { cwd: repositoryRoot, encoding: "utf8" });
  if (result.error || result.status !== 0) {
    fail(`git ${args.join(" ")} failed: ${(result.stderr || result.error?.message || "unknown error").trim()}`);
  }
  return result.stdout.trim();
}

function assertReachableCommit(sha, repositoryRoot) {
  runGit(["cat-file", "-e", `${sha}^{commit}`], repositoryRoot);
  runGit(["merge-base", "--is-ancestor", sha, "HEAD"], repositoryRoot);
}

function assertRepositoryEvidence(path, sha, repositoryRoot, field) {
  if (!/^(?!.*(?:^|\/)\.\.(?:\/|$))[A-Za-z0-9._/-]+$/u.test(path)) {
    fail(`${field} must name a repository-relative path without traversal`);
  }
  const result = spawnSync("git", ["cat-file", "-e", `${sha}:${path}`], { cwd: repositoryRoot, encoding: "utf8" });
  if (result.error || result.status !== 0) fail(`${field} is not present at ${sha}: ${path}`);
}

function requireEvidence(value, field, snapshotSha, repositoryRoot) {
  for (const [index, uri] of requireArray(value, field).entries()) {
    const normalized = requireNonEmptyString(uri, `${field}[${index}]`);
    if (normalized.startsWith("commit:")) {
      assertReachableCommit(requireCommitSha(normalized.slice("commit:".length), `${field}[${index}]`), repositoryRoot);
      continue;
    }
    if (normalized.startsWith("repo:")) {
      const marker = normalized.lastIndexOf("@");
      if (marker <= "repo:".length) fail(`${field}[${index}] must use repo:<path>@<sha>`);
      const path = normalized.slice("repo:".length, marker);
      const evidenceSha = requireCommitSha(normalized.slice(marker + 1), `${field}[${index}]`);
      if (evidenceSha !== snapshotSha) fail(`${field}[${index}] must be pinned to snapshot.gitSha`);
      assertRepositoryEvidence(path, evidenceSha, repositoryRoot, `${field}[${index}]`);
      continue;
    }
    fail(`${field}[${index}] must be commit:<sha> or repo:<path>@<snapshot sha>`);
  }
}

function parseBoard(markdown) {
  const match = BOARD_MARKER.exec(markdown);
  if (!match) fail("control-board:v1 JSON marker is missing");
  try {
    return JSON.parse(match[1]);
  } catch (error) {
    fail(`control-board:v1 JSON is invalid: ${error.message}`);
  }
}

export function validateControlBoard(board, { repositoryRoot = process.cwd() } = {}) {
  if (!board || typeof board !== "object" || Array.isArray(board)) fail("control board must be an object");
  if (board.schemaVersion !== "quantagent-control-board.v1") fail("schemaVersion must be quantagent-control-board.v1");

  const snapshot = board.snapshot;
  if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot)) fail("snapshot must be an object");
  const snapshotSha = requireCommitSha(snapshot.gitSha, "snapshot.gitSha");
  assertReachableCommit(snapshotSha, repositoryRoot);
  if (snapshot.localOnly !== true) fail("snapshot.localOnly must be true until a server evidence bundle exists");
  requireNonEmptyString(snapshot.limitation, "snapshot.limitation");
  requireNonEmptyString(snapshot.scope, "snapshot.scope");

  const transitionIds = new Set();
  for (const transition of requireArray(board.transitions, "transitions")) {
    if (!transition || typeof transition !== "object" || Array.isArray(transition)) fail("transition must be an object");
    const id = requireNonEmptyString(transition.id, "transition.id");
    if (transitionIds.has(id)) fail(`duplicate transition ID: ${id}`);
    transitionIds.add(id);
    requireNonEmptyString(transition.taskId, `${id}.taskId`);
    if (!TRANSITION_STATES.has(transition.from) || !TRANSITION_STATES.has(transition.to)) fail(`${id} has an unsupported state`);
    if (transition.from === transition.to) fail(`${id} must change state`);
    if (snapshot.localOnly && transition.to === "complete") fail(`${id} cannot transition to complete in a local-only snapshot`);
    if (!KST_TIMESTAMP.test(requireNonEmptyString(transition.at, `${id}.at`))) fail(`${id}.at must use YYYY-MM-DD HH:mm KST`);
    if (transition.gitSha !== snapshotSha) fail(`${id}.gitSha must equal snapshot.gitSha`);
    requireEvidence(transition.evidence, `${id}.evidence`, snapshotSha, repositoryRoot);
    requireNonEmptyString(transition.owner, `${id}.owner`);
    const reviewer = requireNonEmptyString(transition.reviewer, `${id}.reviewer`);
    if (reviewer === transition.owner) fail(`${id}.reviewer must be independent from owner`);
    if (transition.to === "complete" && reviewer.startsWith("pending-")) fail(`${id} cannot complete with a pending reviewer`);
    requireNonEmptyString(transition.limitation, `${id}.limitation`);
  }

  const blockerIds = new Set();
  for (const blocker of requireArray(board.blockers, "blockers")) {
    if (!blocker || typeof blocker !== "object" || Array.isArray(blocker)) fail("blocker must be an object");
    const id = requireNonEmptyString(blocker.id, "blocker.id");
    if (blockerIds.has(id)) fail(`duplicate blocker ID: ${id}`);
    blockerIds.add(id);
    requireNonEmptyString(blocker.owner, `${id}.owner`);
    requireNonEmptyString(blocker.reason, `${id}.reason`);
    requireArray(blocker.impactedTaskIds, `${id}.impactedTaskIds`).forEach((taskId, index) =>
      requireNonEmptyString(taskId, `${id}.impactedTaskIds[${index}]`),
    );
    if (!KST_TIMESTAMP.test(requireNonEmptyString(blocker.openedAt, `${id}.openedAt`))) fail(`${id}.openedAt must use YYYY-MM-DD HH:mm KST`);
    if (!KST_TIMESTAMP.test(requireNonEmptyString(blocker.nextReviewAt, `${id}.nextReviewAt`))) fail(`${id}.nextReviewAt must use YYYY-MM-DD HH:mm KST`);
    if (!Number.isInteger(blocker.recurrenceCount) || blocker.recurrenceCount < 0) fail(`${id}.recurrenceCount must be a non-negative integer`);
    requireNonEmptyString(blocker.lastReviewer, `${id}.lastReviewer`);
    requireEvidence(blocker.evidence, `${id}.evidence`, snapshotSha, repositoryRoot);
    requireNonEmptyString(blocker.releaseDisposition, `${id}.releaseDisposition`);
    requireNonEmptyString(blocker.limitation, `${id}.limitation`);
  }

  return {
    blockerCount: board.blockers.length,
    gitSha: snapshotSha,
    result: "PASS",
    transitionCount: board.transitions.length,
  };
}

export function checkProductionPlan({ boardPath = DEFAULT_BOARD, repositoryRoot = process.cwd() } = {}) {
  const absolutePath = resolve(repositoryRoot, boardPath);
  return validateControlBoard(parseBoard(readFileSync(absolutePath, "utf8")), { repositoryRoot });
}

function parseArgs(argv) {
  if (argv.length === 0) return { boardPath: DEFAULT_BOARD };
  if (argv.length === 2 && argv[0] === "--board") return { boardPath: argv[1] };
  fail("usage: node scripts/check-production-plan.mjs [--board <path>]");
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  try {
    process.stdout.write(JSON.stringify(checkProductionPlan(parseArgs(process.argv.slice(2))), null, 2) + "\n");
  } catch (error) {
    process.stderr.write(`[production-plan] ${error.message}\n`);
    process.exitCode = 1;
  }
}
