import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const appPage = () => readFile(new URL("../src/pages/AppPage.tsx", import.meta.url), "utf8");

test("a 409 completion_payload_conflict counts as saved, not as a save failure", async () => {
  const source = await appPage();

  // The run id is deterministic per aiJobId, so re-saving a finished job replays the same
  // completion. When the server refuses because the snapshot it re-derives drifted from
  // the persisted one, the report is already in the DB - banner-ing that is a lie.
  const conflictGuard = source.indexOf('error.status === 409 && error.code === "completion_payload_conflict"');
  const banner = source.indexOf("분석 결과를 리포트로 저장하지 못했습니다. (");

  assert.ok(conflictGuard > 0, "409 completion_payload_conflict must be handled explicitly");
  assert.ok(conflictGuard < banner, "the 409 guard must return before the save-failed banner is set");
});

test("a save that lands clears the save-failed banner", async () => {
  const source = await appPage();

  // Retrying is only worth doing if a retry that succeeds also takes the banner down;
  // otherwise the user is told the save failed for a report that is in the DB.
  assert.match(
    source,
    /await completeAnalysisRun\(run\.id, persistable\);\s*\/\/[\s\S]*?setReportSaveError\(null\);/,
  );
  // The 409 replay is a save that already landed, so it clears the banner too.
  assert.match(
    source,
    /error\.code === "completion_payload_conflict"\) \{\s*setReportSaveError\(null\);\s*return;/,
  );
});

test("the retired-endpoint 410 stays terminal", async () => {
  const source = await appPage();

  assert.match(source, /error\.status === 410 && error\.code === "public_create_retired"/);
});

test("a failing save retries with backoff at most twice and then stops for the session", async () => {
  const source = await appPage();

  assert.match(source, /const REPORT_SAVE_RETRY_DELAYS_MS = \[5_000, 20_000\];/);
  assert.match(source, /const retryDelay = REPORT_SAVE_RETRY_DELAYS_MS\[attempts - 1\];/);
  // Out of retries: the job stays marked persisted so nothing schedules another attempt.
  assert.match(source, /if \(retryDelay === undefined\) \{\s*\/\/[\s\S]*?return;/);
  // The only way back into the queue is the scheduled retry, never an unconditional
  // delete that lets every later poll try the same failing save again.
  const deletions = source.match(/persistedJobIdsRef\.current\.delete\(/g) ?? [];
  assert.equal(deletions.length, 1);
  assert.match(source, /window\.setTimeout\(\(\) => \{\s*persistedJobIdsRef\.current\.delete\(persistable\.job_id\);\s*setReportSaveRetry\(\(tick\) => tick \+ 1\);\s*\}, retryDelay\);/);
  // The retry tick has to be an effect dependency or the scheduled retry never reruns
  // the persist effect once polling has stopped.
  assert.match(source, /\}, \[analysisJobs, reportSaveRetry\]\);/);
});

test("the save-failed banner can be dismissed", async () => {
  const source = await appPage();

  assert.match(source, /리포트 저장 실패 알림 닫기/);
  assert.match(source, /onClick=\{\(\) => setReportSaveError\(null\)\}/);
});
