import { useState } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { Tabs, type TabItem } from "../components/common/Tabs";
import { AppLayout } from "../components/layout/AppLayout";
import { getStrategyWorkspaceOverview } from "../api/quantAgentClient";
import { OverviewTab } from "../features/app/OverviewTab";
import { PerformanceTab } from "../features/app/PerformanceTab";
import { TradingInfoTab } from "../features/app/TradingInfoTab";
import { useAsyncData } from "../hooks/useAsyncData";

interface StrategyReportDetailPageProps {
  id: string;
}

type StrategyDetailTab = "overview" | "trading" | "performance";

const TAB_ITEMS: Array<TabItem<StrategyDetailTab>> = [
  { id: "overview", label: "전체" },
  { id: "trading", label: "매매종목 정보" },
  { id: "performance", label: "수익률" },
];

function getInitialTab(): StrategyDetailTab {
  const tab = new URLSearchParams(window.location.search).get("tab");
  return tab === "trading" || tab === "performance" ? tab : "overview";
}

export function StrategyReportDetailPage({ id }: StrategyReportDetailPageProps) {
  const { data, loading, error } = useAsyncData(() => getStrategyWorkspaceOverview(id), [id]);
  const [activeTab, setActiveTab] = useState<StrategyDetailTab>(getInitialTab);

  const handleTabChange = (tab: StrategyDetailTab) => {
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
    return <AsyncState title="전략 레포트 상세를 불러오는 중입니다" tone="loading" />;
  }

  if (error) {
    return <AsyncState title="전략 레포트 상세를 불러오지 못했습니다" description={error.message} tone="error" />;
  }

  if (!data) {
    return <AsyncState title="전략 레포트를 찾을 수 없습니다" description="요청한 부모 전략 ID에 해당하는 데이터가 없습니다." tone="empty" />;
  }

  const tabItems = TAB_ITEMS.map((item) =>
    item.id === "trading" ? { ...item, count: data.candidates.length } : item,
  );

  return (
    <AppLayout active="reports">
      <Tabs
        activeId={activeTab}
        items={tabItems}
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
    </AppLayout>
  );
}
