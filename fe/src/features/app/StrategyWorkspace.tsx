import { useEffect, useMemo, useState } from "react";

import {
  cancelAnalysisJob,
  createConfirmedAnalysisJob,
  getAnalysisJob,
  reviewStrategy,
  type RuleDraftOutcome,
} from "../../api/quantAgentClient";
import { Tabs, type TabItem } from "../../components/common/Tabs";
import type { AnalysisJob } from "../../types/quantagent";
import { OverviewTab } from "./OverviewTab";
import { PerformanceTab } from "./PerformanceTab";
import { StrategyInputPanel } from "./StrategyInputPanel";
import { EMPTY_WORKSPACE, stageLabel, workspaceOverviewFromJob } from "./strategyWorkspaceMapper";
import { TradingInfoTab } from "./TradingInfoTab";

type WorkspaceTab = "overview" | "trading" | "performance";

const POLL_INTERVAL_MS = 1_500;
const TAB_ITEMS: Array<TabItem<WorkspaceTab>> = [
  { id: "overview", label: "전체" },
  { id: "trading", label: "조건 일치 종목" },
  { id: "performance", label: "백테스트" },
];

/**
 * The core product workspace reviews a natural-language strategy, waits for explicit
 * confirmation, then polls the durable server job. Browser state is never a result
 * fallback, so a refresh cannot turn a fixture or stale cache into a backtest.
 * The compatibility `createAnalysisJob` helper is intentionally not called here;
 * review and confirmation stay separate in the product flow.
 */
export function StrategyWorkspace() {
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [draft, setDraft] = useState<RuleDraftOutcome | null>(null);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("overview");
  const [requestError, setRequestError] = useState<string | null>(null);
  const [cancelRequested, setCancelRequested] = useState(false);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (!job || job.result) return undefined;
    let disposed = false;
    const poll = async () => {
      try {
        const next = await getAnalysisJob(job.job_id);
        if (!disposed) {
          setJob(next);
          setRequestError(null);
        }
      } catch {
        if (!disposed) setRequestError("분석 상태를 확인할 수 없습니다. 네트워크를 확인한 뒤 다시 시도해 주세요.");
      }
    };
    void poll();
    const interval = window.setInterval(() => void poll(), POLL_INTERVAL_MS);
    return () => {
      disposed = true;
      window.clearInterval(interval);
    };
  }, [job]);

  const overview = useMemo(() => job ? workspaceOverviewFromJob(job) : EMPTY_WORKSPACE, [job]);
  const running = Boolean(job && !job.result);
  const result = job?.result ?? null;
  const ready = result?.status === "ready";

  const submit = async (query: string) => {
    setRequestError(null);
    setCancelRequested(false);
    setActiveTab("overview");
    const review = await reviewStrategy(query);
    if (review.kind !== "rule_draft") {
      throw new Error(review.explanation);
    }
    setDraft(review);
    setJob(null);
  };

  const confirmDraft = async () => {
    if (!draft) return;
    setRequestError(null);
    setConfirming(true);
    try {
      const confirmedJob = await createConfirmedAnalysisJob(draft);
      setDraft(null);
      setJob(confirmedJob);
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "백테스트 요청을 처리할 수 없습니다.");
    } finally {
      setConfirming(false);
    }
  };

  const cancel = async () => {
    if (!job || job.result) return;
    setCancelRequested(true);
    try {
      setJob(await cancelAnalysisJob(job.job_id));
    } catch (error) {
      setCancelRequested(false);
      setRequestError(error instanceof Error ? error.message : "분석 중단 요청에 실패했습니다.");
    }
  };

  return (
    <div className="workspace-shell">
      <StrategyInputPanel
        cancelError={requestError}
        cancelRequested={cancelRequested}
        history={[]}
        presentation="dashboard"
        messages={overview.chatMessages}
        onAnalyze={submit}
        onCancel={cancel}
        onNewConversation={() => {
          setJob(null);
          setDraft(null);
          setConfirming(false);
          setRequestError(null);
          setCancelRequested(false);
          setActiveTab("overview");
        }}
        onRestoreConversation={() => undefined}
        running={running}
        strategy={overview.strategy}
      />
      <main className="workspace-main">
        {!job && !draft ? <WorkspaceIntro /> : null}
        {job && running ? <WorkspaceProgress cancelRequested={cancelRequested} job={job} /> : null}
        {draft ? <StrategyDraftConfirmation confirming={confirming} draft={draft} onConfirm={() => void confirmDraft()} /> : null}
        {job && result && !ready ? <TerminalFailure job={job} /> : null}
        {ready ? (
          <>
            <section className="workspace-core-disclosure" aria-label="전략 분석 고지">
              <strong>과거 EOD 데이터 기반 전략 검증</strong>
              <span>실제 주문을 실행하지 않으며, 과거 성과는 미래 수익을 보장하지 않습니다.</span>
            </section>
            <Tabs
              activeId={activeTab}
              items={TAB_ITEMS.map((tab) => tab.id === "trading" ? { ...tab, count: overview.candidates.length } : tab)}
              onChange={setActiveTab}
              rightSlot={<span>{overview.latestRunLabel}</span>}
            />
            {activeTab === "overview" ? <OverviewTab overview={overview} validated={overview.recommendationGate?.validated === true} /> : null}
            {activeTab === "trading" ? <TradingInfoTab candidates={overview.candidates} /> : null}
            {activeTab === "performance" ? <PerformanceTab performance={overview.performance} /> : null}
            <NaturalLanguageReport job={job!} />
          </>
        ) : null}
      </main>
    </div>
  );
}

function StrategyDraftConfirmation({
  draft,
  confirming,
  onConfirm,
}: {
  draft: RuleDraftOutcome;
  confirming: boolean;
  onConfirm: () => void;
}) {
  const conditionText = (
    condition: RuleDraftOutcome["entry_conditions"][number] | RuleDraftOutcome["exit_conditions"][number],
  ) =>
    `${condition.metric} ${condition.comparator} ${condition.value} · ${condition.lookback}일`;
  return (
    <section className="workspace-rule-review" aria-labelledby="workspace-rule-review-title">
      <strong id="workspace-rule-review-title">해석한 전략 조건을 확인해 주세요</strong>
      <p>{draft.explanation}</p>
      <dl>
        <dt>진입 조건</dt>
        <dd>{draft.entry_conditions.map(conditionText).join(" · ") || "없음"}</dd>
        <dt>종료 조건</dt>
        <dd>{draft.exit_conditions.map(conditionText).join(" · ") || "없음"}</dd>
      </dl>
      {draft.indicator_selections.length ? (
        <ul>
          {draft.indicator_selections.map((selection) => (
            <li key={selection.metric}><strong>{selection.metric}</strong> · {selection.reason}</li>
          ))}
        </ul>
      ) : null}
      {draft.unsupported_conditions.length ? (
        <ul>
          {draft.unsupported_conditions.map((item) => (
            <li key={`${item.condition}:${item.reason}`}>{item.condition} · {item.reason}</li>
          ))}
        </ul>
      ) : null}
      {draft.is_executable ? (
        <button disabled={confirming} type="button" onClick={onConfirm}>
          {confirming ? "백테스트를 준비하는 중" : "이 조건으로 백테스트 시작"}
        </button>
      ) : (
        <p>조건을 보완한 뒤 다시 확인해 주세요.</p>
      )}
    </section>
  );
}

function WorkspaceIntro() {
  return (
    <section className="workspace-empty workspace-empty--core">
      <strong>자연어로 전략을 입력해 검증하세요</strong>
      <p>예: “KRX 일봉에서 RSI가 30 이하일 때 진입하고 70 이상일 때 청산하는 전략을 최근 1년 구간으로 백테스트해줘.”</p>
      <p>실데이터·기간·체결 가정·한계가 확인된 경우에만 성과와 자연어 리포트를 표시합니다.</p>
    </section>
  );
}

function WorkspaceProgress({ job, cancelRequested }: { job: AnalysisJob; cancelRequested: boolean }) {
  const active = job.stages.find((stage) => stage.status === "running") ?? job.stages.find((stage) => stage.status === "queued");
  return (
    <section className="workspace-empty workspace-empty--progress" aria-live="polite">
      <strong>{cancelRequested ? "분석 중단을 요청했습니다" : active ? stageLabel(active.stage) : "전략 분석을 준비하는 중"}</strong>
      <p>요청은 서버의 durable job으로 처리됩니다. 서버의 terminal result가 준비된 뒤에만 결과를 표시합니다.</p>
      <ol className="workspace-progress-list">
        {job.stages.map((stage) => <li key={stage.stage} data-status={stage.status}>{stageLabel(stage.stage)} · {stage.status}</li>)}
      </ol>
    </section>
  );
}

function TerminalFailure({ job }: { job: AnalysisJob }) {
  const result = job.result;
  if (!result) return null;
  return (
    <section className="workspace-empty workspace-empty--error" role="alert">
      <strong>{result.status === "need_clarification" ? "전략 조건을 더 확인해 주세요" : "이 전략을 지금 실행할 수 없습니다"}</strong>
      <p>{result.failure_cause?.safe_message ?? result.user_payload.message}</p>
      {result.status === "need_clarification" && result.user_payload.question ? <p>{result.user_payload.question}</p> : null}
      <p>실데이터 provenance·표본·provider 오류를 임의의 성과 수치로 대체하지 않았습니다.</p>
    </section>
  );
}

function NaturalLanguageReport({ job }: { job: AnalysisJob }) {
  const report = job.result?.user_payload.report?.web_projection;
  const performance = job.result?.user_payload.performance;
  if (!report) return null;
  return (
    <section className="workspace-natural-report" aria-labelledby="natural-report-title">
      <p>자연어 전략 리포트</p>
      <h2 id="natural-report-title">{report.title}</h2>
      <p>{report.summary}</p>
      {performance?.availability === "available" ? <small>{performance.method_manifest.historical_simulation_warning}</small> : null}
    </section>
  );
}
