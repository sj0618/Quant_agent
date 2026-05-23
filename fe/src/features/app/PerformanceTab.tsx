import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import type { PerformanceSummary } from "../../types/quantagent";
import { MetricCard } from "./MetricCard";
import { PerformanceChart } from "./PerformanceChart";

interface PerformanceTabProps {
  performance: PerformanceSummary;
}

export function PerformanceTab({ performance }: PerformanceTabProps) {
  return (
    <div className="workspace-content">
      <Card className="list-head">
        <div>
          <h1>{performance.headline}</h1>
          <p>{performance.period}</p>
        </div>
        <div className="segmented">
          <button className="is-active" type="button">AI 개선본</button>
          <button type="button">원본 전략</button>
          <button type="button">A/B 동시 보기</button>
        </div>
        <button className="export-button" type="button">CSV</button>
      </Card>

      <section className="metric-grid">
        {performance.metrics.map((metric) => (
          <MetricCard key={metric.key} metric={metric} />
        ))}
      </section>

      <Card className="chart-card chart-card--large" padded={false}>
        <div className="card-head">
          <div>
            <strong>누적 수익률 (10년)</strong>
            <p>Walk-forward · IS 18M 학습 + OOS 3M 검증 반복</p>
          </div>
          <div className="legend-row">
            <span><i className="line line--strategy" />AI 개선본 (분할)</span>
            <span><i className="line line--original" />원본 (일괄)</span>
            <span><i className="line line--benchmark" />KOSPI200</span>
            <Badge variant="soft">10Y</Badge>
          </div>
        </div>
        <PerformanceChart height={300} mode="full" points={performance.equityCurve} />
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
