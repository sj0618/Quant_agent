import type { AnalysisJob } from "../../types/quantagent";

export interface JobFailure {
  message: string;
  category?: string;
  subcause?: string;
  stage?: string;
  owner?: string;
  retryable?: boolean;
  debugRef?: string;
}

/**
 * Preserve the closed server diagnosis for a terminal job, including jobs restored
 * from the server or conversation history that never pass through the polling loop.
 */
export function terminalJobFailure(job: AnalysisJob | undefined): JobFailure | undefined {
  const cause = job?.result?.failure_cause;
  if (!job?.result || !cause) {
    return undefined;
  }
  return {
    message: cause?.safe_message ?? "분석을 완료하지 못했습니다.",
    category: cause?.category,
    subcause: cause?.subcause,
    stage: cause?.failure_stage,
    owner: cause?.owner,
    retryable: cause?.retryable,
    debugRef: job.result.debug_ref ?? undefined,
  };
}
