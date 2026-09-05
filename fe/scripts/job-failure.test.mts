import assert from "node:assert/strict";
import test from "node:test";
import { terminalJobFailure } from "../src/features/app/jobFailure.ts";
import type { AnalysisJob } from "../src/types/quantagent.ts";

test("restored provider failures retain only the server-safe diagnosis", () => {
  const restoredJob = {
    job_id: "job-restored-failure",
    result: {
      status: "need_clarification",
      debug_ref: "job-error:job-restored-failure",
      failure_cause: {
        category: "infrastructure_failure",
        subcause: "aoai_http_4xx",
        failure_stage: "interpreting",
        owner: "ai_graph",
        retryable: false,
        safe_message: "AI 제공자 응답을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
      },
    },
  } as AnalysisJob;

  assert.deepEqual(terminalJobFailure(restoredJob), {
    message: "AI 제공자 응답을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
    category: "infrastructure_failure",
    subcause: "aoai_http_4xx",
    stage: "interpreting",
    owner: "ai_graph",
    retryable: false,
    debugRef: "job-error:job-restored-failure",
  });
  assert.equal(terminalJobFailure({ result: { status: "need_clarification" } } as AnalysisJob), undefined);
});
