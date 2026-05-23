import type { EquityPoint } from "../../types/quantagent";

interface PerformanceChartProps {
  points: EquityPoint[];
  height?: number;
  mode?: "compact" | "full";
}

const WIDTH = 960;
const PADDING = 28;

function buildPolyline(points: EquityPoint[], key: keyof Pick<EquityPoint, "strategy" | "original" | "benchmark">, height: number) {
  const values = points.flatMap((point) => [point.strategy, point.original, point.benchmark]);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 100);
  const xStep = (WIDTH - PADDING * 2) / Math.max(points.length - 1, 1);
  const scaleY = (value: number) => height - PADDING - ((value - min) / (max - min || 1)) * (height - PADDING * 2);

  return points.map((point, index) => `${PADDING + index * xStep},${scaleY(Number(point[key]))}`).join(" ");
}

export function PerformanceChart({ points, height = 240, mode = "compact" }: PerformanceChartProps) {
  return (
    <div className={`performance-chart performance-chart--${mode}`}>
      <svg aria-label="누적 수익률 차트" preserveAspectRatio="none" viewBox={`0 0 ${WIDTH} ${height}`}>
        {[0.25, 0.5, 0.75].map((ratio) => (
          <line className="performance-chart__grid" key={ratio} x1={PADDING} x2={WIDTH - PADDING} y1={height * ratio} y2={height * ratio} />
        ))}
        <polyline className="performance-chart__line performance-chart__line--benchmark" points={buildPolyline(points, "benchmark", height)} />
        <polyline className="performance-chart__line performance-chart__line--original" points={buildPolyline(points, "original", height)} />
        <polyline className="performance-chart__line performance-chart__line--strategy" points={buildPolyline(points, "strategy", height)} />
        <circle cx={WIDTH - PADDING} cy={height * 0.18} r="7" className="performance-chart__point" />
      </svg>
      <div className="performance-chart__axis">
        {points.map((point) => (
          <span key={point.date}>{point.date}</span>
        ))}
      </div>
    </div>
  );
}
