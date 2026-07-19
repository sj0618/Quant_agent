import { useState } from "react";
import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import { downloadPerformanceCsv } from "../../api/reportActionsClient";
import type { EquityPoint, PerformanceSummary } from "../../types/quantagent";
import { MetricCard } from "./MetricCard";
import { PerformanceChart } from "./PerformanceChart";

interface PerformanceTabProps {
  performance: PerformanceSummary;
}

export function PerformanceTab({ performance }: PerformanceTabProps) {
  const [mode, setMode] = useState<"selected" | "baseline" | "combined">("selected");
  const [range, setRange] = useState<"1Y" | "5Y" | "10Y">("10Y");
  const points = performance.source === "ai"
    ? performance.equityCurve
    : range === "1Y" ? performance.equityCurve.slice(-2) : range === "5Y" ? performance.equityCurve.slice(-4) : performance.equityCurve;
  const benchmarkLabel = performance.benchmarkLabel ?? "KOSPI200";
  const hasBenchmarkSeries = points.some((point) => point.benchmark !== 0);
  const series: Array<keyof Pick<EquityPoint, "strategy" | "original" | "benchmark">> =
    [
      ...(hasBenchmarkSeries ? ["benchmark" as const] : []),
      ...(mode !== "baseline" ? ["strategy" as const] : []),
      ...(mode !== "selected" ? ["original" as const] : []),
    ];

  return (
    <div className="workspace-content">
      <Card className="list-head">
        <div>
          <h1>{performance.headline}</h1>
          <p>{performance.period}</p>
        </div>

        <button className="export-button" onClick={() => downloadPerformanceCsv(performance)} type="button">CSV</button>
      </Card>

      <section className="metric-grid">
        {performance.metrics.map((metric) => (
          <MetricCard key={metric.key} metric={metric} />
        ))}
      </section>

      <Card className="chart-card chart-card--large" padded={false}>
        <div className="card-head">
          <div>
            <strong>누적 수익률</strong>
            <p>{performance.period}</p>
          </div>
          <div className="legend-row">
            {mode !== "baseline" ? <span><i className="line line--strategy" />선택 후보</span> : null}
            {mode !== "selected" ? <span><i className="line line--original" />기준선</span> : null}
            {hasBenchmarkSeries ? <span><i className="line line--benchmark" />{benchmarkLabel}</span> : null}
            {performance.source === "ai" ? <Badge variant="soft">전체</Badge> : (["1Y", "5Y", "10Y"] as const).map((item) => (
              <button className={range === item ? "is-active" : ""} key={item} onClick={() => setRange(item)} type="button">
                {item}
              </button>
            ))}
          </div>
        </div>
        <PerformanceChart height={300} mode="full" points={points} series={series} />
        <div className="disclaimer"><Badge variant="dark">신뢰구간</Badge>{performance.disclaimer}</div>
      </Card>

      <div className="performance-bottom">
        <Card padded={false}>
          <div className="card-head">
            <strong>선택 후보 성능 요약</strong>
            <p>후보 코드 백테스트 objective score 기준</p>
          </div>
          <table className="comparison-table">
            <thead>
              <tr>
                <th>지표</th>
                <th>값</th>
                <th>보조 정보</th>
                <th>판단</th>
              </tr>
            </thead>
            <tbody>
              {performance.comparison.map((row) => (
                <tr key={row.metric}>
                  <td>{row.metric}</td>
                  <td><strong>{row.value}</strong></td>
                  <td>{row.context}</td>
                  <td><em className={`is-${row.tone}`}>{row.assessment}</em></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card padded={false}>
          <div className="card-head">
            <div>
              <strong>주요 매크로 이벤트 매핑</strong>
              <p>{performance.macroEvents.length ? `OOS 구간 내 변동성 이벤트 ${performance.macroEvents.length}건` : "이번 분석 응답에 포함되지 않음"}</p>
            </div>
          </div>
          <div className="macro-list">
            {performance.macroEvents.length ? performance.macroEvents.map((event) => (
              <div key={`${event.date}-${event.label}`}>
                <strong>{event.date}</strong>
                <span>{event.label}</span>
                <Badge variant={event.tone}>{event.impact}</Badge>
              </div>
            )) : <p>현재 AI 응답에는 매크로 이벤트 매핑 데이터가 없습니다.</p>}
          </div>
        </Card>
      </div>
    </div>
  );
}
