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
      <p>{metric.caption}</p>
      {metric.whyUsed || metric.caution || metric.sourceRefs?.length ? (
        <details className="metric-card__explanation">
          <summary>왜 이 지표를 보나요?</summary>
          {metric.whyUsed ? <p><b>사용 이유</b>{metric.whyUsed}</p> : null}
          {metric.caution ? <p><b>주의할 점</b>{metric.caution}</p> : null}
          {metric.sourceRefs?.length ? (
            <div className="metric-card__sources">
              {metric.sourceRefs.map((source, index) => (
                <a href={source} key={source} rel="noreferrer" target="_blank">
                  근거 자료 {index + 1}
                </a>
              ))}
            </div>
          ) : null}
        </details>
      ) : null}
    </article>
  );
}
