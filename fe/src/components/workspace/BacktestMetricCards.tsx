import type { BacktestMetric } from "../../types/quantagent";

export function BacktestMetricCards({ metrics }: { metrics: BacktestMetric[] }) {
  return (
    <section className="metric-grid">
      {metrics.map((metric) => (
        <article className={`metric-card metric-card--${metric.tone}`} key={metric.label}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
          <p>{metric.detail}</p>
        </article>
      ))}
    </section>
  );
}
