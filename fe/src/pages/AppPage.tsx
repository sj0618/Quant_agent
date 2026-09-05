import { useEffect, useRef, useState } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { AppLayout } from "../components/layout/AppLayout";
import { BackendApiError } from "../api/backendClient";
import {
  clearLatestAnalysisJob,
  completeAnalysisRun,
  createAnalysisJob,
  createAnalysisRun,
  aiResponseStatus,
  cancelAnalysisJob,
  getAnalysisJob,
  getWorkspaceTemplate,
  mergeAnalysisJobIntoOverview,
  refreshLatestAnalysisJob,
  saveLatestAnalysisJob,
} from "../api/quantAgentClient";
import { useAnalysisActivity, type ActivityState } from "../api/analysisActivity";
import { DebateActivityPanel } from "../features/app/DebateActivityPanel";
import { terminalJobFailure, type JobFailure } from "../features/app/jobFailure";
import { StrategyInputPanel } from "../features/app/StrategyInputPanel";
import { WorkspaceResultPanel, type WorkspaceResultTab } from "../features/app/WorkspaceResultPanel";
import { useAsyncData } from "../hooks/useAsyncData";
import type { AIJobStage, AIJobStageStatus, AnalysisJob, AppOverview, ChatConversationPreview, WorkspaceAnalysisStatus } from "../types/quantagent";

const CONVERSATION_HISTORY_STORAGE_KEY = "quantagent.chat-conversations.v1";
const CONVERSATION_HISTORY_LIMIT = 8;
const ANALYSIS_JOB_POLL_INTERVAL_MS = 2000;
// Transient blips should not kill a running analysis, but repeated failures mean the
// job will never resolve on its own and the user needs to be told rather than left
// watching a progress bar that can no longer move.
const MAX_POLL_FAILURES = 3;
// A report save that keeps failing must not retry forever: every retry re-raises the
// save-failed banner on a workspace the user is already reading, and a save that failed
// twice with backoff is not going to succeed on the third poll either.
const REPORT_SAVE_RETRY_DELAYS_MS = [5_000, 20_000];
const WORKSPACE_PROGRESS_STEPS: Array<{ stage: AIJobStage; label: string }> = [
  { stage: "interpreting", label: "전략 해석 중" },
  { stage: "code_generation", label: "코드 생성 중" },
  { stage: "backtest", label: "백테스트 실행 중" },
  { stage: "debate", label: "정반 토론 중" },
  { stage: "finalizing", label: "최종 결정 중" },
];

interface WorkspaceConversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  jobs: AnalysisJob[];
}

interface PendingAnalysis {
  query: string;
}

interface WorkspaceProgress {
  query: string;
  percent: number;
  activeLabel: string;
  steps: Array<{ label: string; status: AIJobStageStatus }>;
  error?: JobFailure;
  cancelRequested?: boolean;
}

function getInitialTab(): WorkspaceResultTab {
  const tab = new URLSearchParams(window.location.search).get("tab");
  return tab === "trading" || tab === "performance" ? tab : "overview";
}

function readConversationHistory(): WorkspaceConversation[] {
  const raw = window.localStorage.getItem(CONVERSATION_HISTORY_STORAGE_KEY);
  if (!raw) {
    return [];
  }
  try {
    const parsed = JSON.parse(raw) as WorkspaceConversation[];
    return Array.isArray(parsed) ? parsed.filter((conversation) => conversation.jobs?.length) : [];
  } catch {
    window.localStorage.removeItem(CONVERSATION_HISTORY_STORAGE_KEY);
    return [];
  }
}

function writeConversationHistory(history: WorkspaceConversation[]) {
  window.localStorage.setItem(CONVERSATION_HISTORY_STORAGE_KEY, JSON.stringify(history));
}

function conversationFromJobs(jobs: AnalysisJob[]): WorkspaceConversation {
  const firstJob = jobs[0];
  const lastJob = jobs[jobs.length - 1];
  return {
    id: firstJob.job_id,
    title: firstJob.query,
    createdAt: firstJob.created_at,
    updatedAt: lastJob.updated_at,
    jobs,
  };
}

function prependConversation(history: WorkspaceConversation[], conversation: WorkspaceConversation) {
  return [conversation, ...history.filter((item) => item.id !== conversation.id)].slice(0, CONVERSATION_HISTORY_LIMIT);
}

function conversationStatus(jobs: AnalysisJob[]): WorkspaceAnalysisStatus {
  return jobs[jobs.length - 1]?.result?.status ?? "running";
}

function hasWorkspaceResult(job: AnalysisJob | undefined) {
  return Boolean(job?.result?.status === "ready" && (job.result.strategy_spec || job.result.user_payload.report || job.result.user_payload.performance));
}

function conversationPreview(conversation: WorkspaceConversation, template: AppOverview): ChatConversationPreview {
  const emptyConversationOverview: AppOverview = { ...template, chatMessages: [] };
  const overview = conversation.jobs.reduce<AppOverview>(
    (currentOverview, job) => mergeAnalysisJobIntoOverview(currentOverview, job),
    emptyConversationOverview,
  );
  return {
    id: conversation.id,
    title: conversation.title,
    updatedAt: conversation.updatedAt,
    status: conversationStatus(conversation.jobs),
    messages: overview.chatMessages,
  };
}

function WorkspaceEmptyState({
  hasConversation,
  progress,
  activity,
}: {
  hasConversation: boolean;
  progress?: WorkspaceProgress | null;
  activity?: ActivityState;
}) {
  if (progress?.error) {
    const failure = progress.error;
    // Retryable and permanent failures need different next steps from the reader: one
    // is "try again", the other "this data does not exist yet". Saying only "분석을
    // 이어갈 수 없습니다" left both looking like a transient glitch.
    const permanent = failure.retryable === false;
    const details: Array<[string, string]> = [];
    if (failure.category) details.push(["분류", failure.category]);
    if (failure.subcause) details.push(["원인", failure.subcause]);
    if (failure.stage) details.push(["단계", failure.stage]);
    if (failure.owner) details.push(["담당", failure.owner]);
    if (failure.debugRef) details.push(["debug_ref", failure.debugRef]);
    return (
      <section className="workspace-empty workspace-empty--error" role="alert">
        <strong>{permanent ? "이 조건으로는 분석할 수 없습니다" : "분석을 이어갈 수 없습니다"}</strong>
        <p>{failure.message}</p>
        <p className="workspace-empty__query">{progress.query}</p>
        {permanent ? (
          <p className="workspace-empty__hint">
            같은 조건으로 다시 시도해도 결과는 같습니다. 조건을 바꿔 요청해 주세요.
          </p>
        ) : null}
        {details.length ? (
          <details className="workspace-empty__diagnostics">
            <summary>진단 정보</summary>
            <dl>
              {details.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </details>
        ) : null}
      </section>
    );
  }

  if (progress) {
    return (
      <section className="workspace-empty workspace-empty--progress">
        <div className={`workspace-progress${progress.cancelRequested ? " is-cancelling" : ""}`}>
          <div className="workspace-progress__head">
            <span>{progress.cancelRequested ? "ANALYSIS JOB · 중단 중" : "ANALYSIS JOB"}</span>
            <strong>{progress.activeLabel}</strong>
            <p>{progress.query}</p>
          </div>
          <div
            className="workspace-progress__bar"
            aria-label="분석 진행률"
            aria-valuemax={100}
            aria-valuemin={0}
            aria-valuenow={progress.percent}
            role="progressbar"
          >
            <span style={{ width: `${progress.percent}%` }} />
          </div>
          <ol className="workspace-progress__steps">
            {progress.steps.map((step) => (
              <li className={`workspace-progress__step is-${step.status}`} key={step.label}>
                <span />
                <strong>{step.label}</strong>
              </li>
            ))}
          </ol>
          {activity ? <DebateActivityPanel activity={activity} /> : null}
        </div>
      </section>
    );
  }

  return (
    <section className="workspace-empty">
      <strong>{hasConversation ? "전략 후보를 선택해 주세요" : "전략 채팅으로 시작해 주세요"}</strong>
      <p>
        {hasConversation
          ? "AI가 후보 카드를 준비했습니다. 왼쪽 채팅에서 카드를 선택하면 전략과 리포트 워크스페이스가 채워집니다."
          : "왼쪽 전략 채팅에 원하는 조건을 한 문장으로 입력하면 AI가 전략 필드, 검증 결과, 리포트 초안을 자동으로 구성합니다."}
      </p>
    </section>
  );
}

export function AppPage() {
  const { data, loading, error } = useAsyncData(getWorkspaceTemplate, []);
  const [activeTab, setActiveTab] = useState<WorkspaceResultTab>(getInitialTab);
  const [analysisJobs, setAnalysisJobs] = useState<AnalysisJob[]>([]);
  const [conversationHistory, setConversationHistory] = useState<WorkspaceConversation[]>(readConversationHistory);
  const [pendingAnalysis, setPendingAnalysis] = useState<PendingAnalysis | null>(null);
  const [jobErrors, setJobErrors] = useState<Record<string, JobFailure>>({});
  // Jobs restored from a past conversation that never recorded a result. The server's
  // in-memory store is long gone, so polling them can only ever end in the wall-clock
  // timeout - they are kept for their chat messages and excluded from every live path.
  const [inertJobIds, setInertJobIds] = useState<string[]>([]);
  // Set the instant the user hits stop, before the server has answered. Cancelling only
  // takes effect at the next node boundary, which can be minutes away; leaving the UI
  // unchanged until then reads as "the button did nothing".
  const [cancelledJobIds, setCancelledJobIds] = useState<string[]>([]);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [reportSaveError, setReportSaveError] = useState<string | null>(null);
  // Phone only: which of the two panes is on screen. Ignored from md up, where both fit.
  const [mobilePane, setMobilePane] = useState<"chat" | "result">("chat");
  // Consecutive polling failures per job; a kept ref so retry counting does not
  // itself retrigger the polling effect.
  const pollAttemptsRef = useRef<Record<string, number>>({});
  // Jobs already written to the service DB, so a re-render does not save them twice.
  const persistedJobIdsRef = useRef<Set<string>>(new Set());
  // Failed save attempts per job, capped by REPORT_SAVE_RETRY_DELAYS_MS.
  const saveAttemptsRef = useRef<Record<string, number>>({});
  // Bumped by a scheduled retry so the persist effect reruns without waiting for a poll:
  // once every job has a result the polling loop stops replacing `analysisJobs`.
  const [reportSaveRetry, setReportSaveRetry] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void refreshLatestAnalysisJob()
      .then((latestJob) => {
        if (!cancelled && latestJob) {
          setAnalysisJobs((jobs) => (jobs.length ? jobs : [latestJob]));
        }
      })
      .catch((refreshError) => {
        console.warn("최신 AI 분석을 불러오지 못했습니다.", refreshError);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    writeConversationHistory(conversationHistory);
  }, [conversationHistory]);

  useEffect(() => {
    const pollingJobs = analysisJobs.filter(
      (job) => !job.result && !jobErrors[job.job_id] && !inertJobIds.includes(job.job_id),
    );
    if (!pollingJobs.length) {
      return undefined;
    }

    let cancelled = false;
    const timeoutId = window.setTimeout(async () => {
      const failures: Record<string, JobFailure> = {};
      const missingJobIds = new Set<string>();
      const refreshedJobs = await Promise.all(
        pollingJobs.map(async (job) => {
          try {
            return await getAnalysisJob(job.job_id);
          } catch (error) {
            // Swallowing this used to leave the job stuck at result: null forever, so
            // the UI polled and showed "진행 중" indefinitely. A missing job is gone for
            // good (the in-memory store is cleared on restart); anything else is only
            // treated as fatal once it keeps failing, to ride out a brief blip.
            const status = aiResponseStatus(error);
            const attempts = (pollAttemptsRef.current[job.job_id] ?? 0) + 1;
            pollAttemptsRef.current[job.job_id] = attempts;
            if (status === 404) {
              missingJobIds.add(job.job_id);
              clearLatestAnalysisJob();
            } else if (attempts >= MAX_POLL_FAILURES) {
              failures[job.job_id] = {
                message: status
                  ? `분석 진행 상태를 불러오지 못했습니다. (서버 응답 ${status})`
                  : "분석 진행 상태를 불러오지 못했습니다. 네트워크 연결을 확인해 주세요.",
                category: "fe_polling",
                retryable: true,
              };
            }
            console.warn("AI 분석 job 진행률 갱신에 실패했습니다.", error);
            return job;
          }
        }),
      );

      if (cancelled) {
        return;
      }

      for (const job of refreshedJobs) {
        if (missingJobIds.has(job.job_id)) {
          continue;
        }
        if (!failures[job.job_id]) {
          delete pollAttemptsRef.current[job.job_id];
        }
        // A finished-but-failed job carries its own diagnosis. Surface that instead of
        // waiting for the wall-clock cap, which would blame a timeout for a run that had
        // already stopped for a known reason.
        const terminalFailure = terminalJobFailure(job);
        if (terminalFailure && !failures[job.job_id]) {
          failures[job.job_id] = terminalFailure;
        }
      }
      if (Object.keys(failures).length) {
        setJobErrors((current) => ({ ...current, ...failures }));
      }

      setAnalysisJobs((jobs) =>
        jobs
          .filter((job) => !missingJobIds.has(job.job_id))
          .map((job) => refreshedJobs.find((refreshedJob) => refreshedJob.job_id === job.job_id) ?? job),
      );
    }, ANALYSIS_JOB_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [analysisJobs, inertJobIds, jobErrors]);

  // Persist finished analyses into the service DB so they show up under 리포트.
  //
  // Deliberately NOT gated on recommendation_gate.validated: a backtest that missed its
  // target is still a result the user asked for and should be able to look up later. The
  // gate travels with the report and shows up as a 참고용 label, not as a reason to drop it.
  useEffect(() => {
    const persistable = analysisJobs.find(
      (job) =>
        job.result?.status === "ready" &&
        Boolean(job.result.user_payload.report) &&
        !persistedJobIdsRef.current.has(job.job_id),
    );
    if (!persistable) {
      return;
    }

    persistedJobIdsRef.current.add(persistable.job_id);
    void (async () => {
      try {
        const run = await createAnalysisRun(persistable);
        await completeAnalysisRun(run.id, persistable);
        // A retry that lands has to take the banner down with it, or a save that failed
        // once and succeeded on the retry still reads as failed for the rest of the page.
        setReportSaveError(null);
      } catch (error) {
        // A 410 public_create_retired means the save endpoint itself was retired server
        // side: retrying on every future poll would just repeat the same permanent
        // failure and keep flashing the save-failed banner, so treat it as terminal and
        // leave the job marked persisted.
        if (error instanceof BackendApiError && error.status === 410 && error.code === "public_create_retired") {
          return;
        }
        // A 409 completion_payload_conflict means this exact job is already completed in
        // the service DB - the report the user is after is saved. Only the snapshot the
        // server re-derives differs (the AI result schema moved on since the first save),
        // so this is a successful save, not a failure to report.
        if (error instanceof BackendApiError && error.status === 409 && error.code === "completion_payload_conflict") {
          setReportSaveError(null);
          return;
        }
        setReportSaveError(
          error instanceof Error
            ? `분석 결과를 리포트로 저장하지 못했습니다. (${error.message})`
            : "분석 결과를 리포트로 저장하지 못했습니다.",
        );
        const attempts = (saveAttemptsRef.current[persistable.job_id] ?? 0) + 1;
        saveAttemptsRef.current[persistable.job_id] = attempts;
        const retryDelay = REPORT_SAVE_RETRY_DELAYS_MS[attempts - 1];
        if (retryDelay === undefined) {
          // Out of retries: leave the job marked persisted so nothing retries it again
          // this session. A failed save must not block the workspace being read.
          return;
        }
        window.setTimeout(() => {
          persistedJobIdsRef.current.delete(persistable.job_id);
          setReportSaveRetry((tick) => tick + 1);
        }, retryDelay);
      }
    })();
  }, [analysisJobs, reportSaveRetry]);

  // Derived above the loading/error returns below: hooks must run on every render, and
  // useAnalysisActivity would otherwise be skipped while the workspace template loads.
  const runningJob = [...analysisJobs]
    .reverse()
    .find((job) => !job.result && !inertJobIds.includes(job.job_id));
  const latestJob = analysisJobs.at(-1);
  // A terminal failure is no longer "running", but it still needs the exact
  // server diagnosis rendered in the workspace instead of falling through to
  // the generic candidate-selection empty state.
  const terminalFailureJob = latestJob?.result?.failure_cause ? latestJob : undefined;
  const progressJob = runningJob ?? terminalFailureJob;
  const analysisActivity = useAnalysisActivity(runningJob?.job_id ?? null);

  const handleTabChange = (tab: WorkspaceResultTab) => {
    const url = new URL(window.location.href);
    if (tab === "overview") {
      url.searchParams.delete("tab");
    } else {
      url.searchParams.set("tab", tab);
    }
    window.history.replaceState({}, "", url);
    setActiveTab(tab);
  };

  if (loading || error || !data) {
    return (
      <AppLayout active="workspace">
        {loading ? (
          <AsyncState title="워크스페이스를 불러오는 중입니다" tone="loading" />
        ) : (
          <AsyncState title="워크스페이스를 불러오지 못했습니다" description={error?.message} tone="error" />
        )}
      </AppLayout>
    );
  }

  const overview = analysisJobs.reduce(
    (currentOverview, job) => mergeAnalysisJobIntoOverview(currentOverview, job),
    data,
  );
  const hasCurrentConversation = analysisJobs.length > 0;
  const canRenderWorkspace = hasWorkspaceResult(latestJob);
  // Today's picks are only a recommendation if the strategy behind them cleared its
  // backtest. When it did not, the picks still render but under an explicit not-validated
  // banner so they read as reference, not a buy list.
  const latestPayload = latestJob?.result?.user_payload;
  const explorationReport = latestPayload?.report?.base_report_v2 ?? null;
  const recommendationGate = latestPayload?.recommendation_gate ?? null;
  const panelStrategy = canRenderWorkspace
    ? overview.strategy
    : { ...data.strategy, natural_language_strategy: latestJob?.query ?? data.strategy.natural_language_strategy };
  const historyPreviews = conversationHistory.map((conversation) => conversationPreview(conversation, data));
  const cancelRequested = Boolean(runningJob && cancelledJobIds.includes(runningJob.job_id));
  const workspaceProgress = buildWorkspaceProgress({
    job: progressJob,
    pendingAnalysis,
    error: progressJob ? jobErrors[progressJob.job_id] ?? terminalJobFailure(progressJob) : undefined,
    cancelRequested,
  });

  const archiveCurrentConversation = () => {
    if (analysisJobs.length) {
      setConversationHistory((history) => prependConversation(history, conversationFromJobs(analysisJobs)));
    }
    clearLatestAnalysisJob();
    setAnalysisJobs([]);
    setPendingAnalysis(null);
    setCancelError(null);
  };

  const handleNewConversation = () => {
    archiveCurrentConversation();
    setActiveTab("overview");
    setMobilePane("chat");
  };

  const handleRestoreConversation = (conversationId: string) => {
    const conversation = conversationHistory.find((item) => item.id === conversationId);
    if (!conversation) {
      return;
    }
    const lastJob = conversation.jobs[conversation.jobs.length - 1];
    if (lastJob) {
      saveLatestAnalysisJob(lastJob);
    }
    // Opening a past conversation used to *remove* it from the list and put the current
    // one back in its place - so opening one from an empty workspace deleted it outright.
    // The list is a list: the opened conversation stays, the one being replaced joins it.
    setConversationHistory((history) =>
      analysisJobs.length ? prependConversation(history, conversationFromJobs(analysisJobs)) : history,
    );
    setInertJobIds((current) => [
      ...current,
      ...conversation.jobs.filter((job) => !job.result).map((job) => job.job_id),
    ]);
    setAnalysisJobs(conversation.jobs);
    setCancelError(null);
    setActiveTab("overview");
    setMobilePane("result");
  };

  return (
    <AppLayout active="workspace">
      {/* On a phone the chat panel and the result pane cannot both be full height - the
          panel filled the viewport and pushed every result below the fold. Below md only
          one is mounted at a time and this control switches between them. */}
      <div className="sticky top-14 z-20 flex gap-1 border-b border-line bg-surface/95 p-2 backdrop-blur-md md:hidden">
        {(["chat", "result"] as const).map((pane) => (
          <button
            aria-pressed={mobilePane === pane}
            className={`min-h-11 flex-1 rounded-lg text-[13px] font-bold transition-colors ${
              mobilePane === pane ? "bg-ink text-white" : "bg-soft text-muted"
            }`}
            key={pane}
            onClick={() => setMobilePane(pane)}
            type="button"
          >
            {pane === "chat" ? "전략 채팅" : "분석 결과"}
          </button>
        ))}
      </div>
      <div className="workspace-shell">
        <StrategyInputPanel
          className={mobilePane === "chat" ? undefined : "workspace-pane-hidden"}
          history={historyPreviews}
          messages={hasCurrentConversation ? overview.chatMessages : []}
          cancelError={cancelError}
          cancelRequested={cancelRequested}
          onCancel={async () => {
            if (!runningJob) {
              return;
            }
            // Flip the UI first. The POST only registers the request - the run keeps going
            // until the current node ends - so waiting for the response before showing
            // anything makes the button look broken.
            setCancelledJobIds((current) => [...current, runningJob.job_id]);
            setCancelError(null);
            try {
              const cancelled = await cancelAnalysisJob(runningJob.job_id);
              setAnalysisJobs((jobs) =>
                jobs.map((job) => (job.job_id === cancelled.job_id ? cancelled : job)),
              );
            } catch (error) {
              setCancelledJobIds((current) => current.filter((id) => id !== runningJob.job_id));
              setCancelError(error instanceof Error ? error.message : "분석 중단 요청에 실패했습니다.");
            }
          }}
          running={Boolean(runningJob) || Boolean(pendingAnalysis)}
          onNewConversation={handleNewConversation}
          onAnalyze={async (query) => {
            // A brand-new strategy starts a brand-new conversation; answering a
            // clarification or picking a candidate card continues the current one.
            const awaitingUserInput = latestJob?.result?.status === "need_clarification";
            if (!awaitingUserInput) {
              archiveCurrentConversation();
            }
            const pending = { query };
            setPendingAnalysis(pending);
            // The progress card and the live activity log live in the result pane; on a
            // phone the user would otherwise stare at a chat that looks like it did nothing.
            setMobilePane("result");
            try {
              const job = await createAnalysisJob(query);
              setAnalysisJobs((jobs) => [...jobs, job]);
            } catch (error) {
              setCancelError(
                error instanceof Error ? error.message : "전략 검증 요청을 처리할 수 없습니다.",
              );
            } finally {
              setPendingAnalysis(null);
            }
          }}
          onRestoreConversation={handleRestoreConversation}
          strategy={panelStrategy}
        />
        <main className={`workspace-main${mobilePane === "result" ? "" : " workspace-pane-hidden"}`}>
          {canRenderWorkspace ? (
            <>
              {reportSaveError ? (
                <div className="warning-box warning-box--error" role="status">
                  <strong>리포트 저장 실패</strong>
                  <span>{reportSaveError} 화면의 결과는 그대로 사용할 수 있습니다.</span>
                  <button aria-label="리포트 저장 실패 알림 닫기" onClick={() => setReportSaveError(null)} type="button">
                    닫기 ✕
                  </button>
                </div>
              ) : null}
              <WorkspaceResultPanel
                activeTab={activeTab}
                baseReport={explorationReport}
                jobId={latestJob?.job_id}
                onTabChange={handleTabChange}
                overview={overview}
                recommendationGate={recommendationGate}
              />
            </>
          ) : (
            <WorkspaceEmptyState activity={analysisActivity} hasConversation={hasCurrentConversation} progress={workspaceProgress} />
          )}
        </main>
      </div>
    </AppLayout>
  );
}

function buildWorkspaceProgress({
  job,
  pendingAnalysis,
  error,
  cancelRequested = false,
}: {
  job?: AnalysisJob;
  pendingAnalysis: PendingAnalysis | null;
  error?: JobFailure;
  cancelRequested?: boolean;
}): WorkspaceProgress | null {
  if (job) {
    const steps = WORKSPACE_PROGRESS_STEPS.map(({ stage, label }) => ({
      label,
      status: job.stages.find((step) => step.stage === stage)?.status ?? "queued",
    }));
    const percent = progressPercentFromSteps(steps);

    return {
      query: job.query,
      percent,
      activeLabel: cancelRequested ? "중단 요청됨 · 현재 단계까지만 실행합니다" : activeProgressLabel(steps),
      steps,
      error,
      cancelRequested,
    };
  }

  if (!pendingAnalysis) {
    return null;
  }

  // The request has been accepted locally but the server has not published its first
  // stage yet. Show only that first pending stage; never infer later progress from time.
  const steps: WorkspaceProgress["steps"] = WORKSPACE_PROGRESS_STEPS.map(({ label }, index) => ({
    label,
    status: index === 0 ? "running" : "queued",
  }));

  return {
    query: pendingAnalysis.query,
    percent: progressPercentFromSteps(steps),
    activeLabel: activeProgressLabel(steps),
    steps,
  };
}

function progressPercentFromSteps(steps: WorkspaceProgress["steps"]) {
  const completed = steps.filter((step) => step.status === "succeeded").length;
  const hasRunning = steps.some((step) => step.status === "running");
  return Math.min(100, completed * 20 + (hasRunning ? 10 : 0));
}

function activeProgressLabel(steps: WorkspaceProgress["steps"]) {
  return steps.find((step) => step.status === "running")?.label ?? steps.find((step) => step.status === "queued")?.label ?? "최종 결정 중";
}
