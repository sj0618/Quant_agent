import { useState } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { AppLayout } from "../components/layout/AppLayout";
import { getReportStrategies } from "../api/quantAgentClient";
import { ROUTES } from "../config/routes";
import { StrategyReportList } from "../features/reports/StrategyReportList";
import {
  DEFAULT_STRATEGY_REPORT_FILTERS,
  applyStrategyReportFilters,
  parseStrategyReportFilters,
  serializeStrategyReportFilters,
  type StrategyReportFilters,
} from "../features/reports/strategyReportFilters";
import { useAsyncData } from "../hooks/useAsyncData";

export function ReportsPage() {
  const { data, loading, error } = useAsyncData(getReportStrategies, []);
  const [filters, setFilters] = useState<StrategyReportFilters>(() => parseStrategyReportFilters(window.location.search));

  if (loading) {
    return <AsyncState title="전략 레포트 목록을 불러오는 중입니다" tone="loading" />;
  }

  if (error) {
    return <AsyncState title="전략 레포트 목록을 불러오지 못했습니다" description={error.message} tone="error" />;
  }

  const strategies = data ?? [];
  const filteredStrategies = applyStrategyReportFilters(strategies, filters);

  const handleApplyFilters = (nextFilters: StrategyReportFilters) => {
    setFilters(nextFilters);
    const query = serializeStrategyReportFilters(nextFilters);
    window.history.replaceState({}, "", query ? `${ROUTES.reports}?${query}` : ROUTES.reports);
  };

  const handleResetFilters = () => {
    handleApplyFilters(DEFAULT_STRATEGY_REPORT_FILTERS);
  };

  if (!data || data.length === 0) {
    return <AsyncState title="아직 준비된 전략 레포트가 없습니다" description="전략이 준비되면 부모 전략 목록과 이메일 이력이 함께 표시됩니다." tone="empty" />;
  }

  return (
    <AppLayout active="reports">
      <main className="reports-page">
        <div className="reports-page__head">
          <div>
            <h1>전략 레포트</h1>
            <p>/reports에서는 부모 전략을 필터링하고, 카드 우측 상단 체크박스로 어떤 전략을 이메일로 받을지 최대 3개까지 선택합니다.</p>
          </div>
        </div>
        <StrategyReportList
          allStrategies={strategies}
          filters={filters}
          onApplyFilters={handleApplyFilters}
          onResetFilters={handleResetFilters}
          strategies={filteredStrategies}
        />
      </main>
    </AppLayout>
  );
}
