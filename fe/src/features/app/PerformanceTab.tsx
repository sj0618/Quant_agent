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

const RANGE_YEARS: Record<"1Y" | "5Y" | "10Y", number> = { "1Y": 1, "5Y": 5, "10Y": 10 };

/** Trim the curve to the requested window.
 *
 * This used to be `slice(-2)` / `slice(-4)` - the last two or four *points*, which has
 * nothing to do with one or five years and produced a two-point "1Y" chart.
 */
function sliceByYears(points: EquityPoint[], range: "1Y" | "5Y" | "10Y"): EquityPoint[] {
  if (!points.length) {
    return points;
  }
  const lastDate = new Date(points[points.length - 1].date);
  if (Number.isNaN(lastDate.getTime())) {
    return points;
  }
  const cutoff = new Date(lastDate);
  cutoff.setFullYear(cutoff.getFullYear() - RANGE_YEARS[range]);
  const windowed = points.filter((point) => {
    const parsed = new Date(point.date);
    return Number.isNaN(parsed.getTime()) || parsed >= cutoff;
  });
  // A window that lands on a single point cannot be drawn as a line.
  return windowed.length >= 2 ? windowed : points;
}

export function PerformanceTab({ performance }: PerformanceTabProps) {
  const [mode, setMode] = useState<"selected" | "baseline" | "combined">("selected");
  const [range, setRange] = useState<"1Y" | "5Y" | "10Y">("10Y");
  const points = performance.source === "ai" ? performance.equityCurve : sliceByYears(performance.equityCurve, range);
  const benchmarkLabel = performance.benchmark?.label || performance.benchmarkLabel || "벤치마크";
  const hasMacroEvents = performance.macroEvents.length > 0;
  const hasBenchmarkSeries = performance.benchmark?.is_available === true
    && points.some((point) => Number.isFinite(point.benchmark));
  const hasOriginalSeries = points.some((point) => Number.isFinite(point.original));
  const hasStrategySeries = points.some((point) => Number.isFinite(point.strategy));
  const series: Array<keyof Pick<EquityPoint, "strategy" | "original" | "benchmark">> =
    [
      ...(hasBenchmarkSeries ? ["benchmark" as const] : []),
      ...(mode !== "baseline" && hasStrategySeries ? ["strategy" as const] : []),
      ...(mode !== "selected" && hasOriginalSeries ? ["original" as const] : []),
    ];
  const reliability = performance.reliability;
  const strategyExplanation = performance.strategyExplanation;
  const generatedStrategies = strategyExplanation?.generated_strategies ?? [];

  return (
    <div className="workspace-content">
      <Card className="list-head">
        <div>
          <h1>{performance.headline}</h1>
          <p>{performance.period}</p>
        </div>

        <button className="export-button" onClick={() => downloadPerformanceCsv(performance)} type="button">CSV</button>
      </Card>

      {reliability ? (
        <Card className={`reliability-panel reliability-panel--${reliability.status}`}>
          <div className="reliability-panel__head">
            <div>
              <strong>성과 수치 신뢰도</strong>
              <p>{reliabilityMessage(reliability.status)}</p>
            </div>
            <Badge variant={reliabilityTone(reliability.status)}>
              {reliabilityLabel(reliability.status)}
            </Badge>
          </div>
          <dl className="reliability-panel__samples">
            <div><dt>데이터</dt><dd>{sourceLabel(reliability.source)}</dd></div>
            <div><dt>기간</dt><dd>{formatHistoryPeriod(reliability.history_start, reliability.history_end)}</dd></div>
            <div><dt>표본</dt><dd>{reliability.row_count.toLocaleString("ko-KR")}행 · {reliability.ticker_count}종목</dd></div>
            <div><dt>검증량</dt><dd>{reliability.trading_days}거래일 · 거래 {reliability.trade_count}회</dd></div>
          </dl>
          {[...reliability.reasons, ...reliability.warnings].length ? (
            <ul className="reliability-panel__reasons">
              {[...reliability.reasons, ...reliability.warnings].map((reason) => <li key={reason}>{reason}</li>)}
            </ul>
          ) : null}
        </Card>
      ) : null}

      {performance.metrics.length ? (
        <section className="metric-grid">
          {performance.metrics.map((metric) => (
            <MetricCard key={metric.key} metric={metric} />
          ))}
        </section>
      ) : (
        <Card className="performance-empty">
          <strong>표시할 성과 수치가 없습니다</strong>
          <p>{reliability?.status === "insufficient"
            ? "짧거나 좁은 표본의 숫자를 실제 성과처럼 보이지 않도록 숨겼습니다. 위 부족 사유를 확인해 주세요."
            : "백테스트 응답에 검증 가능한 지표가 포함되지 않았습니다."}</p>
        </Card>
      )}

      {strategyExplanation ? (
        <Card className="strategy-explanation">
          <div className="strategy-explanation__head">
            <div>
              <Badge variant="info">{strategyExplanation.selection_mode === "automatic" ? "전략 생성 · 별도 평가" : "입력 규칙"}</Badge>
              <h2>{strategyExplanation.title}</h2>
            </div>
          </div>
          <p>{strategyExplanation.summary}</p>
          {generatedStrategies.length ? (
            <section className="strategy-blueprints">
              <div className="strategy-blueprints__head">
                <strong>백테스트 전에 생성한 전략 목록</strong>
                <p>아직 승자를 정하지 않은 독립 전략들입니다. 아래 백테스트가 별도로 비교합니다.</p>
              </div>
              <div className="strategy-blueprints__grid">
                {generatedStrategies.map((blueprint, index) => (
                  <article key={blueprint.blueprint_id}>
                    <Badge variant="soft">전략 {index + 1}</Badge>
                    <h3>{blueprint.title}</h3>
                    <p><b>계산식</b><code>{blueprint.formula}</code></p>
                    <p><b>도출 근거</b>{blueprint.derivation}</p>
                    <p><b>생성 이유</b>{blueprint.why_generated}</p>
                    <dl>
                      <div><dt>보유</dt><dd>최대 {blueprint.max_positions}종목</dd></div>
                      <div><dt>교체</dt><dd>{blueprint.rebalance_interval_days}거래일</dd></div>
                      <div><dt>손절</dt><dd>{formatPercent(blueprint.stop_loss_pct)}</dd></div>
                      <div><dt>추적손절</dt><dd>{formatPercent(blueprint.trailing_stop_pct)}</dd></div>
                    </dl>
                  </article>
                ))}
              </div>
            </section>
          ) : null}
          <p><b>왜 이 전략인가요?</b>{strategyExplanation.why_selected}</p>
          {strategyExplanation.rebalance_explanation ? <p><b>매매 주기</b>{strategyExplanation.rebalance_explanation}</p> : null}
          <div className="strategy-explanation__indicators">
            {strategyExplanation.indicators.map((indicator) => (
              <article key={indicator.key}>
                <strong>{indicator.label}</strong>
                <p>{indicator.plain_explanation}</p>
                {indicator.formula ? <p><b>계산식</b><code>{indicator.formula}</code></p> : null}
                {indicator.derivation ? <p><b>도출 근거</b>{indicator.derivation}</p> : null}
                {indicator.customization ? <p><b>입력별 변경</b>{indicator.customization}</p> : null}
                <p><b>사용 이유</b>{indicator.why_used}</p>
                <p><b>주의</b>{indicator.caution}</p>
                {indicator.source_refs.length ? (
                  <div>{indicator.source_refs.map((source, index) => (
                    <a href={source} key={source} rel="noreferrer" target="_blank">근거 {index + 1}</a>
                  ))}</div>
                ) : null}
              </article>
            ))}
          </div>
          <p className="strategy-explanation__caution">{strategyExplanation.caution}</p>
        </Card>
      ) : null}

      {points.length >= 2 && series.length ? <Card className="chart-card chart-card--large" padded={false}>
        <div className="card-head">
          <div>
            <strong>누적 수익률</strong>
            <p>{performance.period}</p>
          </div>
          <div className="legend-row">
            {mode !== "baseline" && hasStrategySeries ? <span><i className="line line--strategy" />선택 후보</span> : null}
            {mode !== "selected" && hasOriginalSeries ? <span><i className="line line--original" />기준선</span> : null}
            {hasBenchmarkSeries ? <span><i className="line line--benchmark" />{benchmarkLabel}</span> : null}
            {performance.source === "ai" ? <Badge variant="soft">전체</Badge> : (["1Y", "5Y", "10Y"] as const).map((item) => (
              <button className={range === item ? "is-active" : ""} key={item} onClick={() => setRange(item)} type="button">
                {item}
              </button>
            ))}
          </div>
        </div>
        <PerformanceChart height={300} mode="full" points={points} series={series} />
        {performance.benchmark ? (
          <div className="benchmark-note">
            <strong>{benchmarkLabel}</strong>
            <span>{performance.benchmark.method}</span>
            {performance.benchmark.warning ? <p>{performance.benchmark.warning}</p> : null}
          </div>
        ) : null}
        <div className="disclaimer"><Badge variant="dark">신뢰구간</Badge>{performance.disclaimer}</div>
      </Card> : (
        <Card className="performance-empty">
          <strong>수익률 곡선을 표시하지 않습니다</strong>
          <p>{performance.benchmark?.unavailable_reason || "전략과 벤치마크의 실제 시계열이 충분하지 않습니다."}</p>
        </Card>
      )}

      {/* 매크로 이벤트는 AI 응답에 실려 오지 않는 경우가 대부분이라, 비어 있으면 카드를
          아예 렌더하지 않는다. 빈 상자를 남겨두면 화면만 차지하고 알려주는 게 없다. */}
      <div className={hasMacroEvents ? "performance-bottom" : "performance-bottom performance-bottom--single"}>
        <Card padded={false}>
          <div className="card-head">
            <strong>선택 후보 성능 요약</strong>
            <p>후보 코드 백테스트 objective score 기준</p>
          </div>
          {performance.comparison.length ? <div className="table-scroll">
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
          </div> : <p className="performance-empty__inline">신뢰할 수 있는 비교 수치가 없습니다.</p>}
        </Card>
        {hasMacroEvents ? (
          <Card padded={false}>
            <div className="card-head">
              <div>
                <strong>주요 매크로 이벤트 매핑</strong>
                <p>{`OOS 구간 내 변동성 이벤트 ${performance.macroEvents.length}건`}</p>
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
        ) : null}
      </div>
    </div>
  );
}

function reliabilityLabel(status: "sufficient" | "limited" | "insufficient") {
  return { sufficient: "충분", limited: "제한적", insufficient: "부족" }[status];
}

function reliabilityTone(
  status: "sufficient" | "limited" | "insufficient",
): "positive" | "warning" | "negative" {
  if (status === "sufficient") {
    return "positive";
  }
  return status === "limited" ? "warning" : "negative";
}

function reliabilityMessage(status: "sufficient" | "limited" | "insufficient") {
  return {
    sufficient: "기간·종목·거래 수가 공개 성과 기준을 충족했습니다.",
    limited: "수치는 계산됐지만 표본 한계가 있어 참고용으로 해석해야 합니다.",
    insufficient: "표본이 너무 작아 수익률·샤프·낙폭 같은 숫자를 숨겼습니다.",
  }[status];
}

function sourceLabel(source: "fixture" | "postgres" | "unknown") {
  return { fixture: "예시 데이터", postgres: "PostgreSQL 실데이터", unknown: "출처 미확인" }[source];
}

function formatHistoryPeriod(start: string | null, end: string | null) {
  if (!start && !end) {
    return "기간 없음";
  }
  return `${start || "?"} ~ ${end || "?"}`;
}

function formatPercent(value: number) {
  return `${(value * 100).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}%`;
}
