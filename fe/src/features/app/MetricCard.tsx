import { Badge } from "../../components/common/Badge";
import type { BacktestMetric } from "../../types/quantagent";
import { isFiniteMetricValue, metricDisplay } from "./metricAvailability";

interface MetricCardProps {
  metric: BacktestMetric;
}

export function MetricCard({ metric }: MetricCardProps) {
  const display = metricDisplay(metric);

  return (
    <article className={display.isUnavailable ? "metric-card metric-card--unavailable" : "metric-card"}>
      <div>
        <span>{metric.label}</span>
        {!display.isUnavailable && isFiniteMetricValue(metric.delta) ? <Badge variant={metric.tone}>{metric.delta}</Badge> : null}
      </div>
      <strong>{display.value}</strong>
      <p>{display.isUnavailable ? display.reason : metric.caption}</p>
      {display.isUnavailable ? (
        <dl className="metric-card__provenance">
          <div><dt>검증 사유</dt><dd>{display.reason}</dd></div>
          <div><dt>기준일</dt><dd>{display.asOf}</dd></div>
          <div><dt>출처</dt><dd>{display.source}</dd></div>
        </dl>
      ) : null}
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
