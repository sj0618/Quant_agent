import { useEffect, useRef, useState } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { Tabs, type TabItem } from "../components/common/Tabs";
import { AppLayout } from "../components/layout/AppLayout";
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
import { OverviewTab } from "../features/app/OverviewTab";
import { PerformanceTab } from "../features/app/PerformanceTab";
import { StrategyInputPanel } from "../features/app/StrategyInputPanel";
import { TradingInfoTab } from "../features/app/TradingInfoTab";
import { useAsyncData } from "../hooks/useAsyncData";
import type { AIJobStage, AIJobStageStatus, AnalysisJob, AppOverview, ChatConversationPreview, WorkspaceAnalysisStatus } from "../types/quantagent";

type WorkspaceTab = "overview" | "trading" | "performance";

const TAB_ITEMS: Array<TabItem<WorkspaceTab>> = [
  { id: "overview", label: "전체" },
  { id: "trading", label: "매매종목 정보", count: 10 },
  { id: "performance", label: "수익률" },
];
const CONVERSATION_HISTORY_STORAGE_KEY = "quantagent.chat-conversations.v1";
const CONVERSATION_HISTORY_LIMIT = 8;
const ANALYSIS_JOB_POLL_INTERVAL_MS = 2000;
// Transient blips should not kill a running analysis, but repeated failures mean the
// job will never resolve on its own and the user needs to be told rather than left
// watching a progress bar that can no longer move.
const MAX_POLL_FAILURES = 3;
// Wall-clock safety net. Polling only gives up when the request itself keeps failing;
// a job that stays RUNNING forever (e.g. the server died mid-run, or a failure never got
// recorded) returns clean 200s with result:null and would otherwise spin the progress bar
// indefinitely. Past this age we surface a timeout instead of leaving the user watching
// forever. Generous on purpose - a 200-name universe backtest legitimately takes minutes.
const MAX_ANALYSIS_DURATION_MS = 10 * 60_000;
const PROGRESS_TICK_INTERVAL_MS = 250;
const CLIENT_PROGRESS_DURATION_MS = 90_000;
const CLIENT_PROGRESS_START_PERCENT = 6;
const CLIENT_PROGRESS_MAX_PERCENT = 92;
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
  startedAt: number;
}

interface WorkspaceProgress {
  query: string;
  percent: number;
  activeLabel: string;
  steps: Array<{ label: string; status: AIJobStageStatus }>;
  error?: string;
  cancelRequested?: boolean;
}

function getInitialTab(): WorkspaceTab {
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
    return (
      <section className="workspace-empty workspace-empty--error">
        <strong>분석을 이어갈 수 없습니다</strong>
        <p>{progress.error}</p>
        <p className="workspace-empty__query">{progress.query}</p>
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
  const [activeTab, setActiveTab] = useState<WorkspaceTab>(getInitialTab);
  const [analysisJobs, setAnalysisJobs] = useState<AnalysisJob[]>([]);
  const [conversationHistory, setConversationHistory] = useState<WorkspaceConversation[]>(readConversationHistory);
  const [pendingAnalysis, setPendingAnalysis] = useState<PendingAnalysis | null>(null);
  const [progressNow, setProgressNow] = useState(Date.now());
  const [jobErrors, setJobErrors] = useState<Record<string, string>>({});
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
    const hasRunningJob = analysisJobs.some((job) => !job.result && !inertJobIds.includes(job.job_id));
    if (!pendingAnalysis && !hasRunningJob) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      setProgressNow(Date.now());
    }, PROGRESS_TICK_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [analysisJobs, inertJobIds, pendingAnalysis]);

  useEffect(() => {
    const pollingJobs = analysisJobs.filter(
      (job) => !job.result && !jobErrors[job.job_id] && !inertJobIds.includes(job.job_id),
    );
    if (!pollingJobs.length) {
      return undefined;
    }

    let cancelled = false;
    const timeoutId = window.setTimeout(async () => {
      const failures: Record<string, string> = {};
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
              failures[job.job_id] = status
                ? `분석 진행 상태를 불러오지 못했습니다. (서버 응답 ${status})`
                : "분석 진행 상태를 불러오지 못했습니다. 네트워크 연결을 확인해 주세요.";
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
        // A job the server keeps reporting as still-running past the wall-clock cap is
        // treated as stuck: successful polls alone would never end the loading state.
        if (!job.result && !failures[job.job_id]) {
          const startedAt = Date.parse(job.created_at);
          if (Number.isFinite(startedAt) && Date.now() - startedAt > MAX_ANALYSIS_DURATION_MS) {
            failures[job.job_id] =
              "분석이 시간 내에 완료되지 않았습니다. 잠시 후 다시 시도해 주세요.";
          }
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
      } catch (error) {
        // Retry on the next result rather than on a loop - a failed save must not block
        // the workspace the user is already looking at.
        persistedJobIdsRef.current.delete(persistable.job_id);
        setReportSaveError(
          error instanceof Error
            ? `분석 결과를 리포트로 저장하지 못했습니다. (${error.message})`
            : "분석 결과를 리포트로 저장하지 못했습니다.",
        );
      }
    })();
  }, [analysisJobs]);

  // Derived above the loading/error returns below: hooks must run on every render, and
  // useAnalysisActivity would otherwise be skipped while the workspace template loads.
  const runningJob = [...analysisJobs]
    .reverse()
    .find((job) => !job.result && !inertJobIds.includes(job.job_id));
  const analysisActivity = useAnalysisActivity(runningJob?.job_id ?? null);

  const handleTabChange = (tab: WorkspaceTab) => {
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
  const latestJob = analysisJobs.at(-1);
  const hasCurrentConversation = analysisJobs.length > 0;
  const canRenderWorkspace = hasWorkspaceResult(latestJob);
  // Today's picks are only a recommendation if the strategy behind them cleared its
  // backtest. When it did not, the picks still render but under an explicit not-validated
  // banner so they read as reference, not a buy list.
  const latestPayload = latestJob?.result?.user_payload;
  const recommendationGate =
    latestPayload && "recommendation_gate" in latestPayload ? latestPayload.recommendation_gate ?? null : null;
  const showGateWarning = canRenderWorkspace && recommendationGate !== null && !recommendationGate.validated;
  const panelStrategy = canRenderWorkspace
    ? overview.strategy
    : { ...data.strategy, natural_language_strategy: latestJob?.query ?? data.strategy.natural_language_strategy };
  const historyPreviews = conversationHistory.map((conversation) => conversationPreview(conversation, data));
  const cancelRequested = Boolean(runningJob && cancelledJobIds.includes(runningJob.job_id));
  const workspaceProgress = buildWorkspaceProgress({
    job: runningJob,
    pendingAnalysis,
    now: progressNow,
    error: runningJob ? jobErrors[runningJob.job_id] : undefined,
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
            const previousJobs = awaitingUserInput ? analysisJobs : [];
            if (!awaitingUserInput) {
              archiveCurrentConversation();
            }
            const pending = { query, startedAt: Date.now() };
            setPendingAnalysis(pending);
            setProgressNow(pending.startedAt);
            // The progress card and the live activity log live in the result pane; on a
            // phone the user would otherwise stare at a chat that looks like it did nothing.
            setMobilePane("result");
            try {
              const job = await createAnalysisJob(query);
              setAnalysisJobs([...previousJobs, job]);
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
              {showGateWarning && recommendationGate ? (
                <div className="warning-box" role="alert">
                  <strong>검증 미통과</strong>
                  <span>{recommendationGate.reason} 아래 종목은 추천이 아닌 참고용입니다.</span>
                </div>
              ) : null}
              {reportSaveError ? (
                <div className="warning-box warning-box--error" role="status">
                  <strong>리포트 저장 실패</strong>
                  <span>{reportSaveError} 화면의 결과는 그대로 사용할 수 있습니다.</span>
                </div>
              ) : null}
              <Tabs
                activeId={activeTab}
                items={TAB_ITEMS.map((item) => item.id === "trading" ? { ...item, count: overview.candidates.length } : item)}
                onChange={handleTabChange}
                rightSlot={
                  <>
                    <span className="live-dot" /> <span>{overview.latestRunLabel}</span> <span className="divider" /> <span>다음 발송</span>{" "}
                    <strong>{overview.nextRunLabel}</strong>
                  </>
                }
              />
              {activeTab === "overview" ? <OverviewTab overview={overview} validated={!showGateWarning} /> : null}
              {activeTab === "trading" ? <TradingInfoTab candidates={overview.candidates} /> : null}
              {activeTab === "performance" ? <PerformanceTab performance={overview.performance} /> : null}
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
  now,
  error,
  cancelRequested = false,
}: {
  job?: AnalysisJob;
  pendingAnalysis: PendingAnalysis | null;
  now: number;
  error?: string;
  cancelRequested?: boolean;
}): WorkspaceProgress | null {
  if (job) {
    const steps = WORKSPACE_PROGRESS_STEPS.map(({ stage, label }) => ({
      label,
      status: job.stages.find((step) => step.stage === stage)?.status ?? "queued",
    }));
    const percent = Math.max(progressPercentFromSteps(steps), progressPercentFromElapsed(new Date(job.created_at).getTime(), now));

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

  const percent = progressPercentFromElapsed(pendingAnalysis.startedAt, now);
  const steps = WORKSPACE_PROGRESS_STEPS.map(({ label }, index) => ({
    label,
    status: clientStageStatus(index, percent),
  }));

  return {
    query: pendingAnalysis.query,
    percent,
    activeLabel: activeProgressLabel(steps),
    steps,
  };
}

function progressPercentFromElapsed(startedAt: number, now: number) {
  const elapsedRatio = Math.max(0, Math.min(1, (now - startedAt) / CLIENT_PROGRESS_DURATION_MS));
  const easedRatio = 1 - (1 - elapsedRatio) ** 2;
  return Math.round(CLIENT_PROGRESS_START_PERCENT + easedRatio * (CLIENT_PROGRESS_MAX_PERCENT - CLIENT_PROGRESS_START_PERCENT));
}

function progressPercentFromSteps(steps: WorkspaceProgress["steps"]) {
  const completed = steps.filter((step) => step.status === "succeeded").length;
  const hasRunning = steps.some((step) => step.status === "running");
  return Math.min(CLIENT_PROGRESS_MAX_PERCENT, completed * 20 + (hasRunning ? 10 : 0));
}

function clientStageStatus(index: number, percent: number): AIJobStageStatus {
  const activeIndex = Math.min(WORKSPACE_PROGRESS_STEPS.length - 1, Math.floor(percent / 20));
  if (index < activeIndex) {
    return "succeeded";
  }
  if (index === activeIndex) {
    return "running";
  }
  return "queued";
}

function activeProgressLabel(steps: WorkspaceProgress["steps"]) {
  return steps.find((step) => step.status === "running")?.label ?? steps.find((step) => step.status === "queued")?.label ?? "최종 결정 중";
}
