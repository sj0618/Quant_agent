import { Badge } from "../../components/common/Badge";
import type { BacktestMetric } from "../../types/quantagent";

interface MetricCardProps {
  metric: BacktestMetric;
}

export function MetricCard({ metric }: MetricCardProps) {
  return (
    <article className="metric-card">
      <div>
        <span>{metric.label}</span>
        {metric.delta ? <Badge variant={metric.tone}>{metric.delta}</Badge> : null}
      </div>
      <strong>{metric.value}</strong>
      <div className="metric-card__spark" />
      <p>{metric.caption}</p>
    </article>
  );
}
