import { useEffect, useState } from "react";

import type { EquityPoint } from "../../types/quantagent";

interface PerformanceChartProps {
  points: EquityPoint[];
  height?: number;
  mode?: "compact" | "full";
  series?: Array<keyof Pick<EquityPoint, "strategy" | "original" | "benchmark">>;
}

/** The viewBox scales uniformly, so its aspect ratio *is* the rendered aspect ratio.
 *  960 wide against a 300 tall box collapses to a 94px-tall smear on a 375px phone;
 *  a narrower box keeps the curve readable at the same rendered width. */
const WIDTH_WIDE = 960;
const WIDTH_NARROW = 420;
const NARROW_QUERY = "(max-width: 767px)";
const PAD_TOP = 18;
const PAD_BOTTOM = 26;
/** Room for the y-axis value labels, which the chart never used to draw at all. */
const PAD_LEFT = 56;
const PAD_RIGHT = 20;
const MIN_DOMAIN_SPAN = 2;
const DOMAIN_PADDING_RATIO = 0.08;
const Y_TICK_TARGET = 5;
const X_LABEL_TARGET = 6;
const X_LABEL_TARGET_NARROW = 3;

function useNarrowViewport() {
  const [narrow, setNarrow] = useState(
    () => typeof window !== "undefined" && window.matchMedia(NARROW_QUERY).matches,
  );

  useEffect(() => {
    const query = window.matchMedia(NARROW_QUERY);
    const onChange = () => setNarrow(query.matches);
    onChange();
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return narrow;
}

type EquitySeriesKey = keyof Pick<EquityPoint, "strategy" | "original" | "benchmark">;

interface Domain {
  min: number;
  max: number;
}

function getDomain(points: EquityPoint[], series: EquitySeriesKey[]): Domain {
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

/** Round tick steps to 1/2/5 x 10^n so labels read as numbers a person would pick. */
function niceStep(rawStep: number) {
  if (!Number.isFinite(rawStep) || rawStep <= 0) {
    return 1;
  }
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalized = rawStep / magnitude;
  const rounded = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return rounded * magnitude;
}

function buildYTicks(domain: Domain) {
  const step = niceStep((domain.max - domain.min) / Y_TICK_TARGET);
  const first = Math.ceil(domain.min / step) * step;
  const ticks: number[] = [];
  for (let value = first; value <= domain.max + step / 1_000; value += step) {
    ticks.push(Number(value.toFixed(6)));
  }
  return ticks;
}

function formatTick(value: number) {
  if (Math.abs(value) < 0.005) {
    return "0%";
  }
  const digits = Math.abs(value) >= 10 || Number.isInteger(value) ? 0 : 1;
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

export function PerformanceChart({
  points,
  height = 240,
  mode = "compact",
  series = ["benchmark", "original", "strategy"],
}: PerformanceChartProps) {
  const narrow = useNarrowViewport();
  const WIDTH = narrow ? WIDTH_NARROW : WIDTH_WIDE;
  const domain = getDomain(points, series);
  const plotHeight = height - PAD_TOP - PAD_BOTTOM;
  const plotWidth = WIDTH - PAD_LEFT - PAD_RIGHT;
  const xStep = plotWidth / Math.max(points.length - 1, 1);

  const scaleY = (value: number) =>
    height - PAD_BOTTOM - ((value - domain.min) / (domain.max - domain.min || 1)) * plotHeight;
  const scaleX = (index: number) => PAD_LEFT + index * xStep;

  const buildPolyline = (key: EquitySeriesKey) =>
    points.map((point, index) => `${scaleX(index)},${scaleY(Number(point[key]))}`).join(" ");

  const yTicks = buildYTicks(domain);
  const zeroInRange = domain.min <= 0 && domain.max >= 0;
  // Every date used to be rendered as its own label, so a daily curve produced hundreds of
  // overlapping 10px strings. Show a handful of evenly spaced ones instead.
  const labelStride = Math.max(
    1,
    Math.ceil(points.length / (narrow ? X_LABEL_TARGET_NARROW : X_LABEL_TARGET)),
  );

  return (
    <div className={`performance-chart performance-chart--${mode}`}>
      <svg aria-label="누적 수익률 차트" role="img" viewBox={`0 0 ${WIDTH} ${height}`}>
        {yTicks.map((tick) => (
          <g key={`tick-${tick}`}>
            <line
              className="performance-chart__grid"
              x1={PAD_LEFT}
              x2={WIDTH - PAD_RIGHT}
              y1={scaleY(tick)}
              y2={scaleY(tick)}
            />
            <text className="performance-chart__ytick" x={PAD_LEFT - 10} y={scaleY(tick)}>
              {formatTick(tick)}
            </text>
          </g>
        ))}
        {zeroInRange ? (
          <line
            className="performance-chart__zero"
            x1={PAD_LEFT}
            x2={WIDTH - PAD_RIGHT}
            y1={scaleY(0)}
            y2={scaleY(0)}
          />
        ) : null}
        {series.includes("benchmark") ? (
          <polyline
            className="performance-chart__line performance-chart__line--benchmark"
            points={buildPolyline("benchmark")}
          />
        ) : null}
        {series.includes("original") ? (
          <polyline
            className="performance-chart__line performance-chart__line--original"
            points={buildPolyline("original")}
          />
        ) : null}
        {series.includes("strategy") ? (
          <polyline
            className="performance-chart__line performance-chart__line--strategy"
            points={buildPolyline("strategy")}
          />
        ) : null}
        {points.map((point, index) =>
          index % labelStride === 0 || index === points.length - 1 ? (
            <text
              className="performance-chart__xtick"
              key={`${point.date}-${index}`}
              x={scaleX(index)}
              y={height - 8}
            >
              {point.date}
            </text>
          ) : null,
        )}
      </svg>
    </div>
  );
}
