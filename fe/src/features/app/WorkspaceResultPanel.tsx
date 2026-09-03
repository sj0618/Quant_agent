import { Tabs, type TabItem } from "../../components/common/Tabs";
import type { AIBaseReportV2, AIRecommendationGate, AppOverview } from "../../types/quantagent";
import { ExplorationBaseReport } from "../reports/ExplorationBaseReport";
import { OverviewTab } from "./OverviewTab";
import { PerformanceTab } from "./PerformanceTab";
import { TradingInfoTab } from "./TradingInfoTab";

export type WorkspaceResultTab = "overview" | "trading" | "performance";

const TAB_ITEMS: Array<TabItem<WorkspaceResultTab>> = [
  { id: "overview", label: "전체" },
  { id: "trading", label: "매매종목 정보" },
  { id: "performance", label: "수익률" },
];

interface WorkspaceResultPanelProps {
  overview: AppOverview;
  activeTab: WorkspaceResultTab;
  onTabChange: (tab: WorkspaceResultTab) => void;
  baseReport?: AIBaseReportV2 | null;
  jobId?: string | null;
  recommendationGate?: AIRecommendationGate | null;
}

/**
 * The analysis result surface shared by the live workspace and its saved report.
 *
 * Keeping this as one component prevents a saved report from silently drifting into
 * the delivery-email layout or losing panels that were visible immediately after a
 * workspace run completed.
 */
export function WorkspaceResultPanel({
  overview,
  activeTab,
  onTabChange,
  baseReport = null,
  jobId = null,
  recommendationGate = null,
}: WorkspaceResultPanelProps) {
  const showGateWarning = recommendationGate !== null && !recommendationGate.validated;

  return (
    <>
      {showGateWarning ? (
        <div className="warning-box" role="alert">
          <strong>검증 미통과</strong>
          <span>{recommendationGate.reason} 아래 종목은 추천이 아닌 참고용입니다.</span>
        </div>
      ) : null}
      {baseReport && jobId ? (
        <ExplorationBaseReport jobId={jobId} report={baseReport} />
      ) : (
        <>
          <Tabs
            activeId={activeTab}
            items={TAB_ITEMS.map((item) => item.id === "trading" ? { ...item, count: overview.candidates.length } : item)}
            onChange={onTabChange}
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
      )}
    </>
  );
}
