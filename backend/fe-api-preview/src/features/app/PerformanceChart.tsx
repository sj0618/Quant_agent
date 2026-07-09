import type { EquityPoint } from "../../types/quantagent";

interface PerformanceChartProps {
  points: EquityPoint[];
  height?: number;
  mode?: "compact" | "full";
  series?: Array<keyof Pick<EquityPoint, "strategy" | "original" | "benchmark">>;
}

const WIDTH = 960;
const PADDING = 28;
const MIN_DOMAIN_SPAN = 2;
const DOMAIN_PADDING_RATIO = 0.12;

type EquitySeriesKey = keyof Pick<EquityPoint, "strategy" | "original" | "benchmark">;

function getDomain(points: EquityPoint[], series: EquitySeriesKey[]) {
  const values = points.flatMap((point) => series.map((key) => Number(point[key]))).filter(Number.isFinite);
  if (!values.length) {
    return { min: 0, max: 1 };
  }

  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const span = Math.max(rawMax - rawMin, MIN_DOMAIN_SPAN);
  const center = (rawMin + rawMax) / 2;
  const paddedSpan = span * (1 + DOMAIN_PADDING_RATIO * 2);

  return {
    min: center - paddedSpan / 2,
    max: center + paddedSpan / 2,
  };
}

function buildPolyline(points: EquityPoint[], key: EquitySeriesKey, height: number, domain: { min: number; max: number }) {
  const xStep = (WIDTH - PADDING * 2) / Math.max(points.length - 1, 1);
  const scaleY = (value: number) =>
    height - PADDING - ((value - domain.min) / (domain.max - domain.min || 1)) * (height - PADDING * 2);

  return points.map((point, index) => `${PADDING + index * xStep},${scaleY(Number(point[key]))}`).join(" ");
}

export function PerformanceChart({ points, height = 240, mode = "compact", series = ["benchmark", "original", "strategy"] }: PerformanceChartProps) {
  const domain = getDomain(points, series);

  return (
    <div className={`performance-chart performance-chart--${mode}`}>
      <svg aria-label="누적 수익률 차트" preserveAspectRatio="none" viewBox={`0 0 ${WIDTH} ${height}`}>
        {[0.25, 0.5, 0.75].map((ratio) => (
          <line className="performance-chart__grid" key={ratio} x1={PADDING} x2={WIDTH - PADDING} y1={height * ratio} y2={height * ratio} />
        ))}
        {series.includes("benchmark") ? <polyline className="performance-chart__line performance-chart__line--benchmark" points={buildPolyline(points, "benchmark", height, domain)} /> : null}
        {series.includes("original") ? <polyline className="performance-chart__line performance-chart__line--original" points={buildPolyline(points, "original", height, domain)} /> : null}
        {series.includes("strategy") ? <polyline className="performance-chart__line performance-chart__line--strategy" points={buildPolyline(points, "strategy", height, domain)} /> : null}
      </svg>
      <div className="performance-chart__axis">
        {points.map((point, index) => (
          <span key={`${point.date}-${index}`}>{point.date}</span>
        ))}
      </div>
    </div>
  );
}
