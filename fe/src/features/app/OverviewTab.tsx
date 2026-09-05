import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import { ROUTES } from "../../config/routes";
import type { AppOverview } from "../../types/quantagent";
import { countScoredSignals } from "../../utils/signalCounts";
import { PerformanceChart } from "./PerformanceChart";
import { PerformanceReliabilityPanel } from "./PerformanceReliabilityPanel";
import { SignalCard } from "./SignalCard";

interface OverviewTabProps {
  overview: AppOverview;
  /**
   * Whether the backtest behind these picks cleared its objective floor. The graph already
   * decides this in recommendation_gate; the header used to ignore it and print ACTIVE with
   * a recommendation score on a strategy the system had judged unfit.
   */
  validated?: boolean;
}

const CHART_INITIAL_ASSET = 1_000_000;
const PERCENT_SCALE = 100;
const PERCENT_DIGITS = 2;
// The full out-of-sample curve routinely runs 60-90+ trading days; slicing to the last 5
// points left one path with 5 dots while the headline return was computed over the whole
// curve. Render the whole thing (PerformanceChart already thins its own x-axis labels) and
// only cap for pathological cases.
const CHART_POINT_LIMIT = 250;

export function OverviewTab({ overview, validated = true }: OverviewTabProps) {
  const featuredCandidates = overview.candidates.slice(0, 4);
  const strategyName = overview.strategy.name ?? "활성 전략";
  const totalReturnMetric = metricByKey(overview, "totalReturn");
  const sharpeMetric = metricByKey(overview, "sharpe");
  const maxDrawdownMetric = metricByKey(overview, "mdd");
  // The walk-forward out-of-sample Sharpe the recommendation gate actually judged against -
  // when the backend sends it, it must replace the whole-period Sharpe card above so the
  // tile and the gate's own verdict never disagree.
  const oosSharpeMetric = metricByKey(overview, "out_sample_sharpe");
  const oosMaxDrawdown = overview.performance.outOfSampleMaxDrawdown ?? null;
  const chartPoints = overview.performance.equityCurve.slice(-CHART_POINT_LIMIT);
  const latestPoint = chartPoints[chartPoints.length - 1];
  const strategyReturn = latestPoint?.strategy;
  const benchmarkReturn = latestPoint?.benchmark;
  const currentAsset = strategyReturn === undefined
    ? null
    : CHART_INITIAL_ASSET * (1 + strategyReturn / PERCENT_SCALE);
  const benchmarkLabel = overview.performance.benchmark?.label
    || overview.performance.benchmarkLabel
    || "벤치마크";
  const hasBenchmarkSeries = overview.performance.benchmark?.is_available === true
    && chartPoints.some((point) => Number.isFinite(point.benchmark));
  // An insufficient sample no longer hides the tiles - it prefixes them, and the
  // reliability card above lists which sample check fell short.
  const sampleNote = overview.performance.reliability?.status === "insufficient" ? "표본 부족 · 참고용 · " : "";
  const candidateCounts = countScoredSignals(overview.candidates);
  // Candidate rows already use the per-ticker action returned by the backtest.  The
  // summary must count that same source; `passCount` is a strategy-level fallback and
  // can be zero even while the displayed rows carry HOLD/BUY/DROP verdicts.
  const tickerSignalCounts = candidateCounts ?? { BUY: 0, HOLD: 0, DROP: 0 };
  const activeSignalCount = tickerSignalCounts.BUY + tickerSignalCounts.HOLD + tickerSignalCounts.DROP;
  // The acceptance-floor's own conclusion sentence, when the backend sends one, is more
  // specific than the gate's short reason code - prefer it, falling back to the reason.
  const gateNote = overview.objectiveFloorConclusion ?? overview.recommendationGateReason;

  return (
    <div className="workspace-content">
      <Card className="strategy-strip">
        <div>
          <div className="eyebrow-row">
            {validated ? <Badge variant="dark">ACTIVE</Badge> : <Badge variant="soft">검증 미통과</Badge>}
            <span>STRATEGY</span>
          </div>
          <strong>{strategyName}</strong>
        </div>
        <dl>
          <div>
            <dt>매수 조건</dt>
            <dd>{overview.strategy.buy_condition}</dd>
          </div>
          <div>
            <dt>매도 조건</dt>
            <dd>{overview.strategy.drop_condition}</dd>
          </div>
        </dl>
      </Card>

      {overview.performance.reliability ? (
        <PerformanceReliabilityPanel reliability={overview.performance.reliability} />
      ) : null}

      <section className="summary-grid">
        {[
          validated
            ? { label: "오늘의 권장도", value: overview.recommendationScore, delta: overview.recommendationDelta, caption: "최종 신호 등급 · BUY 8.2 / HOLD 6.8 / DROP 6.4" }
            : {
                label: "오늘의 권장도",
                value: overview.recommendationScore,
                delta: undefined,
                caption: gateNote ? `백테스트 목표 기준 미달 · 참고용 · ${gateNote}` : "백테스트 목표 기준 미달 · 참고용",
              },
          { label: "활성 신호", value: `${activeSignalCount}건`, delta: undefined, caption: `BUY ${tickerSignalCounts.BUY} · HOLD ${tickerSignalCounts.HOLD} · DROP ${tickerSignalCounts.DROP}` },
          {
            // The chart card below plots this exact out-of-sample curve, so the tile reads
            // it too - preferring the whole-period metric card here is what produced the
            // "-11.97% vs -1.95%" disagreement between this tile and the chart.
            label: "검증 구간(OOS) 누적 수익률",
            value: strategyReturn !== undefined
              ? formatPercentValue(strategyReturn)
              : totalReturnMetric?.value ?? "—",
            delta: totalReturnMetric?.delta,
            caption: sampleNote + (strategyReturn !== undefined
              ? "아래 차트와 동일한 검증 구간(OOS) 값입니다."
              : totalReturnMetric?.caption ?? (benchmarkReturn === undefined ? "실제 수익률 곡선 기준" : `${benchmarkLabel} ${formatPercentValue(benchmarkReturn)} 대비`)),
          },
          {
            label: "Sharpe (Walk-forward OOS)",
            value: oosSharpeMetric?.value ?? sharpeMetric?.value ?? "—",
            delta: sharpeMetric?.delta,
            caption: sampleNote + (oosSharpeMetric?.caption ?? sharpeMetric?.caption ?? "AI 전략 검증 결과"),
          },
        ].map((item) => (
          <Card className="summary-card" key={item.label}>
            <div>
              <span>{item.label}</span>
              {item.delta ? <Badge variant="positive">{item.delta}</Badge> : null}
            </div>
            <strong>{item.value}</strong>
            <p>{item.caption}</p>
          </Card>
        ))}
      </section>

      <div className="overview-grid">
        <Card className="candidate-table" padded={false}>
          <div className="card-head">
            <div>
              <strong>조건 일치 종목</strong>
              <p>{overview.candidates.length ? `${overview.latestRunLabel} · ${overview.candidates.length}건` : "이번 분석 응답에 포함되지 않음"}</p>
            </div>
            {overview.candidates.length ? (
              <div className="filter-row">
                <Badge variant="dark">ALL {overview.candidates.length}</Badge>
                {candidateCounts ? (
                  <>
                    <Badge signal="BUY">BUY {tickerSignalCounts.BUY}</Badge>
                    <Badge signal="HOLD">HOLD {tickerSignalCounts.HOLD}</Badge>
                    <Badge signal="DROP">DROP {tickerSignalCounts.DROP}</Badge>
                  </>
                ) : null}
              </div>
            ) : null}
          </div>
          {featuredCandidates.length ? featuredCandidates.map((candidate) => (
            <SignalCard candidate={candidate} compact key={candidate.id} />
          )) : <p>오늘은 규칙에 해당하는 종목이 없습니다 (신호 0건). 백테스트 결론과 성과는 위 카드에서 확인할 수 있습니다.</p>}
          <div className="card-foot">
            {overview.candidates.length ? <>신호는 매일 08:00 자동 갱신됩니다 <a href={`${ROUTES.app}?tab=trading`}>전체 종목 정보 보기 →</a></> : "마지막 거래일 기준으로 규칙이 진입·보유 판정을 낸 종목이 없습니다."}
          </div>
        </Card>

        <Card className="recent-reports" padded={false}>
          <div className="card-head">
            <div>
              <strong>최근 리포트</strong>
              <p>최근 7일</p>
            </div>
          </div>
          {overview.recentReports.map((report) => {
            const content = <>
              <span>
                <strong>{report.date.replace("2026.", "")}</strong>
                <small>{report.weekday}</small>
              </span>
              <span className="recent-report-row__signals">
                {report.signals.BUY ? <Badge signal="BUY">BUY {report.signals.BUY}</Badge> : null}
                {report.signals.HOLD ? <Badge signal="HOLD">HOLD {report.signals.HOLD}</Badge> : null}
                {report.signals.DROP ? <Badge signal="DROP">DROP {report.signals.DROP}</Badge> : null}
              </span>
              <strong>{report.recommendationScore}</strong>
            </>;
            return report.id.startsWith("ai-job:") ? (
              <div className="recent-report-row" key={report.id}>{content}</div>
            ) : (
              <a className="recent-report-row" href={ROUTES.reportDetail(report.id)} key={report.id}>{content}</a>
            );
          })}
          <div className="card-foot"><a href={ROUTES.reports}>전체 리포트 보기 →</a></div>
        </Card>
      </div>

      {chartPoints.length >= 2 && strategyReturn !== undefined ? <Card className="chart-card" padded={false}>
        <div className="card-head">
          <div>
            <strong>누적 수익률</strong>
            <p>총자산 기준 · 거래비용 반영</p>
          </div>
          <div className="legend-row">
            <span><i className="line line--strategy" />내 전략</span>
            {hasBenchmarkSeries ? <span><i className="line line--benchmark" />{benchmarkLabel}</span> : null}
            <Badge variant="soft">{overview.performance.source === "ai" ? "전체" : "1Y"}</Badge>
          </div>
        </div>
        <div className="chart-card__numbers">
          <div>
            <span>현재 자산</span>
            <strong>{currentAsset === null ? "—" : formatCurrency(currentAsset)}</strong>
            <em>{formatPercentValue(strategyReturn)}</em>
          </div>
          <div><span>초기 자산</span><strong>{formatCurrency(CHART_INITIAL_ASSET)}</strong></div>
          {hasBenchmarkSeries && benchmarkReturn !== undefined ? <div><span>{benchmarkLabel} 대비</span><strong>{formatPercentPoint(strategyReturn - benchmarkReturn)}</strong></div> : null}
          <div><span>최대 낙폭</span><strong>{oosMaxDrawdown !== null ? formatPercentValue(oosMaxDrawdown) : maxDrawdownMetric?.value ?? "-"}</strong></div>
        </div>
        <PerformanceChart points={chartPoints} series={hasBenchmarkSeries ? ["benchmark", "strategy"] : ["strategy"]} />
        {overview.performance.limitations?.length ? (
          <p className="card-foot">{overview.performance.limitations.join(" ")}</p>
        ) : null}
      </Card> : (
        <Card className="performance-empty">
          <strong>누적 수익률을 표시할 수 없습니다</strong>
          <p>실제 백테스트 시계열이 없습니다.</p>
        </Card>
      )}
    </div>
  );
}

function metricByKey(overview: AppOverview, key: string) {
  return overview.performance.metrics.find((metric) => metric.key === key);
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercentValue(value: number) {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(PERCENT_DIGITS)}%`;
}

function formatPercentPoint(value: number) {
  const prefix = value >= 0 ? "+" : "";
  return `${prefix}${value.toFixed(PERCENT_DIGITS)}%p`;
}
