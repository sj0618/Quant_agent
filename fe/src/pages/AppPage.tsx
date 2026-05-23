import { useState } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { Tabs, type TabItem } from "../components/common/Tabs";
import { AppLayout } from "../components/layout/AppLayout";
import { getAppOverview } from "../api/quantAgentClient";
import { OverviewTab } from "../features/app/OverviewTab";
import { PerformanceTab } from "../features/app/PerformanceTab";
import { StrategyInputPanel } from "../features/app/StrategyInputPanel";
import { TradingInfoTab } from "../features/app/TradingInfoTab";
import { useAsyncData } from "../hooks/useAsyncData";

type WorkspaceTab = "overview" | "trading" | "performance";

const TAB_ITEMS: Array<TabItem<WorkspaceTab>> = [
  { id: "overview", label: "전체" },
  { id: "trading", label: "매매종목 정보", count: 10 },
  { id: "performance", label: "수익률" },
];

function getInitialTab(): WorkspaceTab {
  const tab = new URLSearchParams(window.location.search).get("tab");
  return tab === "trading" || tab === "performance" ? tab : "overview";
}

export function AppPage() {
  const { data, loading, error } = useAsyncData(getAppOverview, []);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>(getInitialTab);

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

  return (
    <AppLayout active="workspace">
      <div className="workspace-shell">
        <StrategyInputPanel messages={data.chatMessages} strategy={data.strategy} />
        <main className="workspace-main">
          <Tabs
            activeId={activeTab}
            items={TAB_ITEMS}
            onChange={handleTabChange}
            rightSlot={
              <>
                <span className="live-dot" /> <span>{data.latestRunLabel}</span> <span className="divider" /> <span>다음 발송</span>{" "}
                <strong>{data.nextRunLabel}</strong>
              </>
            }
          />
          {activeTab === "overview" ? <OverviewTab overview={data} /> : null}
          {activeTab === "trading" ? <TradingInfoTab candidates={data.candidates} /> : null}
          {activeTab === "performance" ? <PerformanceTab performance={data.performance} /> : null}
        </main>
      </div>
    </AppLayout>
  );
}
