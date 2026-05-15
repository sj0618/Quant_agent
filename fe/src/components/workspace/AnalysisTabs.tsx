import { useId, useState, type KeyboardEvent } from "react";
import type { ScenarioPayload, WorkspacePayload } from "../../types/quantagent";
import { CandidatesTab } from "./CandidatesTab";
import { ReportTab } from "./ReportTab";
import { SummaryTab } from "./SummaryTab";

type TabKey = "summary" | "candidates" | "report";

const TABS: Array<{ key: TabKey; label: string; description: string }> = [
  { key: "summary", label: "전체 요약", description: "전략·상태·리포트" },
  { key: "candidates", label: "매매종목 정보", description: "후보 카드·Signal" },
  { key: "report", label: "수익률 / 리포트", description: "Backtest·Report" },
];

export function AnalysisTabs({ payload, scenario }: { payload: WorkspacePayload; scenario?: ScenarioPayload }) {
  const [activeTab, setActiveTab] = useState<TabKey>("summary");
  const tabsId = useId();

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, currentKey: TabKey) => {
    const currentIndex = TABS.findIndex((tab) => tab.key === currentKey);
    const lastIndex = TABS.length - 1;

    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      const nextIndex =
        event.key === "ArrowRight"
          ? currentIndex === lastIndex
            ? 0
            : currentIndex + 1
          : currentIndex === 0
            ? lastIndex
            : currentIndex - 1;
      setActiveTab(TABS[nextIndex].key);
      document.getElementById(`${tabsId}-${TABS[nextIndex].key}`)?.focus();
    }

    if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      const nextIndex = event.key === "Home" ? 0 : lastIndex;
      setActiveTab(TABS[nextIndex].key);
      document.getElementById(`${tabsId}-${TABS[nextIndex].key}`)?.focus();
    }
  };

  return (
    <section className="analysis-panel">
      <div className="tabs" role="tablist" aria-label="QuantAgent analysis workspace tabs">
        {TABS.map((tab) => (
          <button
            className={activeTab === tab.key ? "tab-button tab-button--active" : "tab-button"}
            type="button"
            key={tab.key}
            id={`${tabsId}-${tab.key}`}
            role="tab"
            aria-selected={activeTab === tab.key}
            aria-controls={`${tabsId}-${tab.key}-panel`}
            tabIndex={activeTab === tab.key ? 0 : -1}
            onClick={() => setActiveTab(tab.key)}
            onKeyDown={(event) => handleTabKeyDown(event, tab.key)}
          >
            <span>{tab.label}</span>
            <small>{tab.description}</small>
          </button>
        ))}
      </div>

      <div id={`${tabsId}-${activeTab}-panel`} role="tabpanel" aria-labelledby={`${tabsId}-${activeTab}`} tabIndex={0}>
        {activeTab === "summary" ? <SummaryTab payload={payload} scenario={scenario} /> : null}
        {activeTab === "candidates" ? <CandidatesTab payload={payload} /> : null}
        {activeTab === "report" ? <ReportTab payload={payload} /> : null}
      </div>
    </section>
  );
}
