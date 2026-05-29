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
  const [mode, setMode] = useState<"improved" | "original" | "ab">("improved");
  const [range, setRange] = useState<"1Y" | "5Y" | "10Y">("10Y");
  const points = range === "1Y" ? performance.equityCurve.slice(-2) : range === "5Y" ? performance.equityCurve.slice(-4) : performance.equityCurve;
  const benchmarkLabel = performance.benchmarkLabel ?? "KOSPI200";
  const series: Array<keyof Pick<EquityPoint, "strategy" | "original" | "benchmark">> =
    mode === "improved" ? ["benchmark", "strategy"] : mode === "original" ? ["benchmark", "original"] : ["benchmark", "original", "strategy"];

  return (
    <div className="workspace-content">
      <Card className="list-head">
        <div>
          <h1>{performance.headline}</h1>
          <p>{performance.period}</p>
        </div>
        <div className="segmented">
          <button className={mode === "improved" ? "is-active" : ""} onClick={() => setMode("improved")} type="button">선택 후보</button>
          <button className={mode === "original" ? "is-active" : ""} onClick={() => setMode("original")} type="button">원본 전략</button>
          <button className={mode === "ab" ? "is-active" : ""} onClick={() => setMode("ab")} type="button">A/B 동시 보기</button>
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
            {mode !== "original" ? <span><i className="line line--strategy" />선택 후보</span> : null}
            {mode !== "improved" ? <span><i className="line line--original" />원본 (일괄)</span> : null}
            <span><i className="line line--benchmark" />{benchmarkLabel}</span>
            {(["1Y", "5Y", "10Y"] as const).map((item) => (
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
            <strong>원본 vs AI 개선본</strong>
            <p>BacktestCode Loop3 최고 Sharpe 선택</p>
          </div>
          <table className="comparison-table">
            <thead>
              <tr>
                <th>지표</th>
                <th>원본</th>
                <th>AI 개선본</th>
                <th>개선</th>
              </tr>
            </thead>
            <tbody>
              {performance.comparison.map((row) => (
                <tr key={row.metric}>
                  <td>{row.metric}</td>
                  <td>{row.original}</td>
                  <td><strong>{row.improved}</strong></td>
                  <td><em className="is-positive">{row.delta}</em></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card padded={false}>
          <div className="card-head">
            <div>
              <strong>주요 매크로 이벤트 매핑</strong>
              <p>OOS 구간 내 변동성 이벤트 6건</p>
            </div>
          </div>
          <div className="macro-list">
            {performance.macroEvents.map((event) => (
              <div key={`${event.date}-${event.label}`}>
                <strong>{event.date}</strong>
                <span>{event.label}</span>
                <Badge variant={event.tone}>{event.impact}</Badge>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
