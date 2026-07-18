import { useEffect, useState } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { Tabs, type TabItem } from "../components/common/Tabs";
import { AppLayout } from "../components/layout/AppLayout";
import {
  clearLatestAnalysisJob,
  createAnalysisJob,
  getAnalysisJob,
  getWorkspaceTemplate,
  mergeAnalysisJobIntoOverview,
  saveLatestAnalysisJob,
} from "../api/quantAgentClient";
import { OverviewTab } from "../features/app/OverviewTab";
import { PerformanceTab } from "../features/app/PerformanceTab";
import { StrategyInputPanel } from "../features/app/StrategyInputPanel";
import { TradingInfoTab } from "../features/app/TradingInfoTab";
import { useAsyncData } from "../hooks/useAsyncData";
import type { AIJobStage, AIJobStageStatus, AnalysisJob, AppOverview, ChatConversationPreview, WorkspaceAnalysisStatus } from "../types/quantagent";

type WorkspaceTab = "overview" | "trading" | "performance";

const TAB_ITEMS: Array<TabItem<WorkspaceTab>> = [
  { id: "overview", label: "전체" },
  { id: "trading", label: "매매종목 정보" },
  { id: "performance", label: "수익률" },
];
const CONVERSATION_HISTORY_STORAGE_KEY = "quantagent.chat-conversations.v1";
const CONVERSATION_HISTORY_LIMIT = 8;
const ANALYSIS_JOB_POLL_INTERVAL_MS = 2000;
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

function WorkspaceEmptyState({ hasConversation, progress }: { hasConversation: boolean; progress?: WorkspaceProgress | null }) {
  if (progress) {
    return (
      <section className="workspace-empty workspace-empty--progress">
        <div className="workspace-progress">
          <div className="workspace-progress__head">
            <span>ANALYSIS JOB</span>
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

  useEffect(() => {
    writeConversationHistory(conversationHistory);
  }, [conversationHistory]);

  useEffect(() => {
    const hasRunningJob = analysisJobs.some((job) => !job.result);
    if (!pendingAnalysis && !hasRunningJob) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      setProgressNow(Date.now());
    }, PROGRESS_TICK_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [analysisJobs, pendingAnalysis]);

  useEffect(() => {
    const pollingJobs = analysisJobs.filter((job) => !job.result);
    if (!pollingJobs.length) {
      return undefined;
    }

    let cancelled = false;
    const timeoutId = window.setTimeout(async () => {
      const refreshedJobs = await Promise.all(
        pollingJobs.map(async (job) => {
          try {
            return await getAnalysisJob(job.job_id);
          } catch (error) {
            console.warn("AI 분석 job 진행률 갱신에 실패했습니다.", error);
            return job;
          }
        }),
      );

      if (cancelled) {
        return;
      }

      setAnalysisJobs((jobs) =>
        jobs.map((job) => refreshedJobs.find((refreshedJob) => refreshedJob.job_id === job.job_id) ?? job),
      );
    }, ANALYSIS_JOB_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [analysisJobs]);

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

  if (loading) {
    return <AsyncState title="워크스페이스를 불러오는 중입니다" tone="loading" />;
  }

  if (error || !data) {
    return <AsyncState title="워크스페이스를 불러오지 못했습니다" description={error?.message} tone="error" />;
  }

  const overview = analysisJobs.reduce(
    (currentOverview, job) => mergeAnalysisJobIntoOverview(currentOverview, job),
    data,
  );
  const latestJob = analysisJobs.at(-1);
  const hasCurrentConversation = analysisJobs.length > 0;
  const canRenderWorkspace = hasWorkspaceResult(latestJob);
  const panelStrategy = canRenderWorkspace
    ? overview.strategy
    : { ...data.strategy, natural_language_strategy: latestJob?.query ?? data.strategy.natural_language_strategy };
  const historyPreviews = conversationHistory.map((conversation) => conversationPreview(conversation, data));
  const runningJob = [...analysisJobs].reverse().find((job) => !job.result);
  const workspaceProgress = buildWorkspaceProgress({ job: runningJob, pendingAnalysis, now: progressNow });

  const handleNewConversation = () => {
    if (analysisJobs.length) {
      setConversationHistory((history) => prependConversation(history, conversationFromJobs(analysisJobs)));
    }
    clearLatestAnalysisJob();
    setAnalysisJobs([]);
    setPendingAnalysis(null);
    setActiveTab("overview");
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
    setConversationHistory((history) => {
      const historyWithoutRestored = history.filter((item) => item.id !== conversationId);
      return analysisJobs.length ? prependConversation(historyWithoutRestored, conversationFromJobs(analysisJobs)) : historyWithoutRestored;
    });
    setAnalysisJobs(conversation.jobs);
    setActiveTab("overview");
  };

  return (
    <AppLayout active="workspace">
      <div className="workspace-shell">
        <StrategyInputPanel
          history={historyPreviews}
          messages={hasCurrentConversation ? overview.chatMessages : []}
          onNewConversation={handleNewConversation}
          onAnalyze={async (query) => {
            const pending = { query, startedAt: Date.now() };
            setPendingAnalysis(pending);
            setProgressNow(pending.startedAt);
            try {
              const job = await createAnalysisJob(query);
              setAnalysisJobs((jobs) => [...jobs, job]);
            } finally {
              setPendingAnalysis(null);
            }
          }}
          onRestoreConversation={handleRestoreConversation}
          strategy={panelStrategy}
        />
        <main className="workspace-main">
          {canRenderWorkspace ? (
            <>
              <Tabs
                activeId={activeTab}
                items={TAB_ITEMS}
                onChange={handleTabChange}
                rightSlot={
                  <>
                    <span className="live-dot" /> <span>{overview.latestRunLabel}</span> <span className="divider" /> <span>다음 발송</span>{" "}
                    <strong>{overview.nextRunLabel}</strong>
                  </>
                }
              />
              {activeTab === "overview" ? <OverviewTab overview={overview} /> : null}
              {activeTab === "trading" ? <TradingInfoTab candidates={overview.candidates} /> : null}
              {activeTab === "performance" ? <PerformanceTab performance={overview.performance} /> : null}
            </>
          ) : (
            <WorkspaceEmptyState hasConversation={hasCurrentConversation} progress={workspaceProgress} />
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
}: {
  job?: AnalysisJob;
  pendingAnalysis: PendingAnalysis | null;
  now: number;
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
      activeLabel: activeProgressLabel(steps),
      steps,
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
