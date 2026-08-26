import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import { ROUTES } from "../../config/routes";
import type { AppOverview } from "../../types/quantagent";
import { countScoredSignals } from "../../utils/signalCounts";
import { PerformanceChart } from "./PerformanceChart";
import { SignalCard } from "./SignalCard";

interface OverviewTabProps {
  overview: AppOverview;
  /**
   * Whether the backtest behind these picks cleared its objective floor. The graph already
   * decides this in recommendation_gate; the header used to ignore it and print ACTIVE with
   * a recommendation score on a strategy the system had judged unfit. `overview.recommendationGate`
   * carries the same verdict plus the reason and whether verification even finished.
   */
  validated?: boolean;
}

const CHART_INITIAL_ASSET = 1_000_000;
const PERCENT_SCALE = 100;
const PERCENT_DIGITS = 2;

export function OverviewTab({ overview, validated = true }: OverviewTabProps) {
  const featuredCandidates = overview.candidates.slice(0, 4);
  const strategyName = overview.strategy.name ?? "활성 전략";
  const gate = overview.recommendationGate;
  // A gate can pass every metric it managed to measure and still not have finished:
  // the official benchmark series it compares against may not be loaded yet. Showing
  // only `validated` reports that run as fully verified.
  const verificationIncomplete = gate?.verification_complete === false;
  const evaluationBasis = overview.performance.evaluationBasis;
  const universePolicy = overview.performance.universePolicy;
  const tickerActionByTicker = new Map(
    (overview.tickerActions ?? []).map((action) => [action.ticker, action]),
  );
  const totalReturnMetric = metricByKey(overview, "totalReturn");
  const sharpeMetric = metricByKey(overview, "sharpe");
  const maxDrawdownMetric = metricByKey(overview, "mdd");
  const chartPoints = overview.performance.equityCurve.slice(-5);
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
  const insufficient = overview.performance.reliability?.status === "insufficient";
  const candidateCounts = countScoredSignals(overview.candidates);

  return (
    <div className="workspace-content">
      <Card className="strategy-strip">
        <div>
          <div className="eyebrow-row">
            {!validated
              ? <Badge variant="soft">검증 미통과</Badge>
              : verificationIncomplete
                ? <Badge variant="warning">검증 미완료</Badge>
                : <Badge variant="dark">ACTIVE</Badge>}
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
        <Card className={`overview-reliability overview-reliability--${overview.performance.reliability.status}`}>
          <div>
            <strong>성과 신뢰도: {overview.performance.reliability.status === "sufficient" ? "충분" : overview.performance.reliability.status === "limited" ? "제한적" : "부족"}</strong>
            <span>{overview.performance.reliability.trading_days}거래일 · {overview.performance.reliability.ticker_count}종목 · 거래 {overview.performance.reliability.trade_count}회</span>
          </div>
          {overview.performance.reliability.reasons.length ? <p>{overview.performance.reliability.reasons.join(" · ")}</p> : null}
        </Card>
      ) : null}

      <section className="summary-grid">
        {[
          validated && !verificationIncomplete
            ? { label: "전략 신호 신뢰도", value: overview.recommendationScore, delta: overview.recommendationDelta, caption: "과거 데이터로 검증한 전략 신호입니다. 주문 지시가 아닙니다." }
            : {
                label: "전략 신호 신뢰도",
                value: validated ? overview.recommendationScore : "산출 안 함",
                delta: undefined,
                // The graph already wrote why - a measured shortfall reads differently
                // from an input that never arrived, and only it knows which happened.
                caption: gate?.reason ?? "백테스트 검증 결과를 확인할 수 없습니다.",
              },
          { label: "활성 신호", value: `${overview.passCount}건`, delta: undefined, caption: `BUY ${overview.buyCount} · HOLD ${overview.holdCount} · DROP ${overview.dropCount}` },
          {
            label: "검증 누적 수익률",
            value: insufficient ? "표본 부족" : totalReturnMetric?.value ?? (strategyReturn === undefined ? "—" : formatPercentValue(strategyReturn)),
            delta: totalReturnMetric?.delta,
            // Which period this number covers is decided per run by the backend, so the
            // caption is its sentence. A fixed one here was wrong for every run that took
            // the other evaluation path.
            caption: insufficient
              ? "신뢰도 기준 미달로 숫자를 표시하지 않습니다."
              : evaluationBasis?.caption ?? totalReturnMetric?.caption ?? (benchmarkReturn === undefined ? "실제 수익률 곡선 기준" : `${benchmarkLabel} ${formatPercentValue(benchmarkReturn)} 대비`),
          },
          {
            label: "Sharpe (검증 구간)",
            value: insufficient ? "표본 부족" : sharpeMetric?.value ?? "—",
            delta: sharpeMetric?.delta,
            caption: sharpeMetric?.caption ?? evaluationBasis?.caption ?? "AI 전략 검증 결과",
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
                    <Badge signal="BUY">BUY {candidateCounts.BUY}</Badge>
                    <Badge signal="HOLD">HOLD {candidateCounts.HOLD}</Badge>
                    <Badge signal="DROP">DROP {candidateCounts.DROP}</Badge>
                  </>
                ) : null}
              </div>
            ) : null}
          </div>
          {universePolicy ? (
            <div className="candidate-table__policy">
              <p>{universePolicy.summary}</p>
              {universePolicy.excluded_screening_candidate_count > 0 && universePolicy.excluded_notice
                ? <p className="candidate-table__policy-notice">{universePolicy.excluded_notice}</p>
                : null}
            </div>
          ) : null}
          {featuredCandidates.length ? featuredCandidates.map((candidate) => (
            <SignalCard
              candidate={candidate}
              compact
              key={candidate.id}
              tickerAction={tickerActionByTicker.get(candidate.ticker)}
            />
          )) : <p>현재 AI 응답에는 종목별 추천 데이터가 없습니다.</p>}
          <div className="card-foot">
            {overview.candidates.length ? <>최신 분석의 실데이터·기간·방법을 확인해 해석하세요. <a href={`${ROUTES.app}?tab=trading`}>전체 종목 정보 보기 →</a></> : "실데이터 검증을 통과한 경우에만 종목별 신호가 표시됩니다."}
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
            {/* The curve spans the whole run, selection history included - it is not the
                validation slice the summary card reports. Say so instead of letting the
                two cumulative numbers read as one. */}
            <p>{`총자산 기준 · 선택 구간 포함 전체 백테스트${evaluationBasis?.cost_model_applied ? " · 거래비용 반영" : ""}`}</p>
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
          <div><span>최대 낙폭</span><strong>{maxDrawdownMetric?.value ?? "-"}</strong></div>
        </div>
        <PerformanceChart points={chartPoints} series={hasBenchmarkSeries ? ["benchmark", "strategy"] : ["strategy"]} />
      </Card> : (
        <Card className="performance-empty">
          <strong>누적 수익률을 표시할 수 없습니다</strong>
          <p>{insufficient ? "표본이 부족해 숫자와 곡선을 숨겼습니다." : "실제 백테스트 시계열이 없습니다."}</p>
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
