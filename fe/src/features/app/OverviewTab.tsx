import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import { ROUTES } from "../../config/routes";
import type { AppOverview } from "../../types/quantagent";
import { PerformanceChart } from "./PerformanceChart";
import { SignalCard } from "./SignalCard";

interface OverviewTabProps {
  overview: AppOverview;
}

const CHART_INITIAL_ASSET = 1_000_000;
const PERCENT_SCALE = 100;
const PERCENT_DIGITS = 2;

export function OverviewTab({ overview }: OverviewTabProps) {
  const featuredCandidates = overview.candidates.slice(0, 4);
  const strategyName = overview.strategy.name ?? "활성 전략";
  const totalReturnMetric = metricByKey(overview, "totalReturn");
  const sharpeMetric = metricByKey(overview, "sharpe");
  const maxDrawdownMetric = metricByKey(overview, "mdd");
  const chartPoints = overview.performance.equityCurve.slice(-5);
  const latestPoint = chartPoints[chartPoints.length - 1];
  const strategyReturn = latestPoint?.strategy ?? 0;
  const benchmarkReturn = latestPoint?.benchmark ?? 0;
  const currentAsset = CHART_INITIAL_ASSET * (1 + strategyReturn / PERCENT_SCALE);
  const benchmarkLabel = overview.performance.benchmarkLabel ?? "KOSPI200";
  const hasBenchmarkSeries = chartPoints.some((point) => point.benchmark !== 0);
  const candidateCounts = overview.candidates.reduce(
    (counts, candidate) => ({ ...counts, [candidate.signal]: counts[candidate.signal] + 1 }),
    { BUY: 0, HOLD: 0, DROP: 0 },
  );

  return (
    <div className="workspace-content">
      <Card className="strategy-strip">
        <div>
          <div className="eyebrow-row">
            <Badge variant="dark">ACTIVE</Badge>
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

      <section className="summary-grid">
        {[
          { label: "오늘의 권장도", value: overview.recommendationScore, delta: overview.recommendationDelta, caption: "최종 신호 신뢰도 기준" },
          { label: "활성 신호", value: `${overview.passCount}건`, delta: undefined, caption: `BUY ${overview.buyCount} · HOLD ${overview.holdCount} · DROP ${overview.dropCount}` },
          {
            label: "검증 누적 수익률",
            value: totalReturnMetric?.value ?? formatPercentValue(strategyReturn),
            delta: totalReturnMetric?.delta,
            caption: totalReturnMetric?.caption ?? `${benchmarkLabel} ${formatPercentValue(benchmarkReturn)} 대비`,
          },
          {
            label: "Sharpe (Walk-forward)",
            value: sharpeMetric?.value ?? "-",
            delta: sharpeMetric?.delta,
            caption: sharpeMetric?.caption ?? "AI 전략 검증 결과",
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
              <strong>종목별 추천 데이터</strong>
              <p>{overview.candidates.length ? `${overview.latestRunLabel} · ${overview.candidates.length}건` : "이번 분석 응답에 포함되지 않음"}</p>
            </div>
            {overview.candidates.length ? (
              <div className="filter-row">
                <Badge variant="dark">ALL {overview.candidates.length}</Badge>
                <Badge signal="BUY">BUY {candidateCounts.BUY}</Badge>
                <Badge signal="HOLD">HOLD {candidateCounts.HOLD}</Badge>
                <Badge signal="DROP">DROP {candidateCounts.DROP}</Badge>
              </div>
            ) : null}
          </div>
          {featuredCandidates.length ? featuredCandidates.map((candidate) => (
            <SignalCard candidate={candidate} compact key={candidate.id} />
          )) : <p>현재 AI 응답에는 종목별 추천 데이터가 없습니다.</p>}
          <div className="card-foot">
            {overview.candidates.length ? <>신호는 매일 08:00 자동 갱신됩니다 <a href={`${ROUTES.app}?tab=trading`}>전체 종목 정보 보기 →</a></> : "실데이터 소스 연결 시 종목별 신호가 표시됩니다."}
          </div>
        </Card>

        <Card className="recent-reports" padded={false}>
          <div className="card-head">
            <div>
              <strong>최근 리포트</strong>
              <p>최근 7일</p>
            </div>
          </div>
          {overview.recentReports.map((report) => (
            <a className="recent-report-row" href={ROUTES.reportDetail(report.id)} key={report.id}>
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
            </a>
          ))}
          <div className="card-foot"><a href={ROUTES.reports}>전체 리포트 보기 →</a></div>
        </Card>
      </div>

      <Card className="chart-card" padded={false}>
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
            <strong>{formatCurrency(currentAsset)}</strong>
            <em>{formatPercentValue(strategyReturn)}</em>
          </div>
          <div><span>초기 자산</span><strong>{formatCurrency(CHART_INITIAL_ASSET)}</strong></div>
          {hasBenchmarkSeries ? <div><span>{benchmarkLabel} 대비</span><strong>{formatPercentPoint(strategyReturn - benchmarkReturn)}</strong></div> : null}
          <div><span>최대 낙폭</span><strong>{maxDrawdownMetric?.value ?? "-"}</strong></div>
        </div>
        <PerformanceChart points={chartPoints} series={hasBenchmarkSeries ? ["benchmark", "strategy"] : ["strategy"]} />
      </Card>
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
