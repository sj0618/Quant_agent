import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { checkProductionPlan, validateControlBoard } from "./check-production-plan.mjs";

const SHA = "c3a5bc46822e0fa7f34d39060302d279293613f1";

function validBoard() {
  return {
    schemaVersion: "quantagent-control-board.v1",
    snapshot: {
      gitSha: SHA,
      localOnly: true,
      limitation: "A local structural check cannot establish server or human-review evidence.",
      scope: "planning evidence only",
    },
    transitions: [{
      id: "TR-001",
      taskId: "PM-GOAL-00",
      from: "not_started",
      to: "in_progress",
      at: "2026-08-24 10:00 KST",
      gitSha: SHA,
      evidence: [`commit:${SHA}`],
      owner: "planning-owner",
      reviewer: "independent-reviewer",
      limitation: "This records preflight implementation only.",
    }],
    blockers: [{
      id: "BL-001",
      owner: "planning-owner",
      reason: "Release evidence is unavailable.",
      impactedTaskIds: ["PM-GOAL-00"],
      openedAt: "2026-08-24 10:00 KST",
      nextReviewAt: "2026-08-25 10:00 KST",
      recurrenceCount: 0,
      lastReviewer: "independent-reviewer",
      evidence: [`commit:${SHA}`],
      releaseDisposition: "blocked",
      limitation: "No production claim is permitted.",
    }],
  };
}

test("a board binds its snapshot and evidence to a reachable Git commit", () => {
  const directory = mkdtempSync(join(tmpdir(), "quantagent-plan-contract-"));
  const boardPath = join(directory, "board.md");
  try {
    writeFileSync(boardPath, `<!-- control-board:v1\n${JSON.stringify(validBoard())}\n-->\n`, "utf8");
    const result = checkProductionPlan({ boardPath });
    assert.equal(result.result, "PASS");
    assert.equal(result.gitSha, SHA);
    assert.equal(result.transitionCount, 1);
    assert.equal(result.blockerCount, 1);
  } finally {
    rmSync(directory, { force: true, recursive: true });
  }
});

test("the preflight rejects a blocker without recurrence count", () => {
  const board = validBoard();
  delete board.blockers[0].recurrenceCount;
  assert.throws(() => validateControlBoard(board), /recurrenceCount/u);
});

test("a local-only board cannot convert a planning record into completion", () => {
  const board = validBoard();
  board.transitions[0].to = "complete";
  assert.throws(() => validateControlBoard(board), /local-only snapshot/u);
});

test("the preflight rejects a non-existent or zero snapshot SHA", () => {
  const board = validBoard();
  board.snapshot.gitSha = "0".repeat(40);
  board.transitions[0].gitSha = board.snapshot.gitSha;
  board.transitions[0].evidence = [`commit:${board.snapshot.gitSha}`];
  assert.throws(() => validateControlBoard(board), /non-zero/u);
});

test("the command reports a malformed board as non-passing", () => {
  const directory = mkdtempSync(join(tmpdir(), "quantagent-plan-contract-"));
  const boardPath = join(directory, "broken.md");
  try {
    writeFileSync(boardPath, "# broken\n", "utf8");
    const result = spawnSync(process.execPath, ["scripts/check-production-plan.mjs", "--board", boardPath], {
      encoding: "utf8",
    });
    assert.equal(result.status, 1);
    assert.match(result.stderr, /control-board:v1 JSON marker/u);
  } finally {
    rmSync(directory, { force: true, recursive: true });
  }
});
