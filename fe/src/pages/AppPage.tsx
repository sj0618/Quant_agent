import { useEffect, useState } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { Tabs, type TabItem } from "../components/common/Tabs";
import { AppLayout } from "../components/layout/AppLayout";
import {
  clearLatestAnalysisJob,
  createAnalysisJob,
  getWorkspaceTemplate,
  mergeAnalysisJobIntoOverview,
  saveLatestAnalysisJob,
} from "../api/quantAgentClient";
import { OverviewTab } from "../features/app/OverviewTab";
import { PerformanceTab } from "../features/app/PerformanceTab";
import { StrategyInputPanel } from "../features/app/StrategyInputPanel";
import { TradingInfoTab } from "../features/app/TradingInfoTab";
import { useAsyncData } from "../hooks/useAsyncData";
import type { AnalysisJob, AppOverview, ChatConversationPreview, WorkspaceAnalysisStatus } from "../types/quantagent";

type WorkspaceTab = "overview" | "trading" | "performance";

const TAB_ITEMS: Array<TabItem<WorkspaceTab>> = [
  { id: "overview", label: "전체" },
  { id: "trading", label: "매매종목 정보", count: 10 },
  { id: "performance", label: "수익률" },
];
const CONVERSATION_HISTORY_STORAGE_KEY = "quantagent.chat-conversations.v1";
const CONVERSATION_HISTORY_LIMIT = 8;

interface WorkspaceConversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  jobs: AnalysisJob[];
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

function hasWorkspaceResult(jobs: AnalysisJob[]) {
  return jobs.some((job) => Boolean(job.result?.strategy_spec || job.result?.user_payload.report || job.result?.user_payload.performance));
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

function WorkspaceEmptyState({ hasConversation }: { hasConversation: boolean }) {
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

  useEffect(() => {
    writeConversationHistory(conversationHistory);
  }, [conversationHistory]);

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
  const hasCurrentConversation = analysisJobs.length > 0;
  const canRenderWorkspace = hasWorkspaceResult(analysisJobs);
  const historyPreviews = conversationHistory.map((conversation) => conversationPreview(conversation, data));

  const handleNewConversation = () => {
    if (analysisJobs.length) {
      setConversationHistory((history) => prependConversation(history, conversationFromJobs(analysisJobs)));
    }
    clearLatestAnalysisJob();
    setAnalysisJobs([]);
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
            const job = await createAnalysisJob(query);
            setAnalysisJobs((jobs) => [...jobs, job]);
          }}
          onRestoreConversation={handleRestoreConversation}
          strategy={overview.strategy}
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
            <WorkspaceEmptyState hasConversation={hasCurrentConversation} />
          )}
        </main>
      </div>
    </AppLayout>
  );
}
