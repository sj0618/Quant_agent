import type { ReactNode } from "react";
import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import type { ReportDetail as ReportDetailType, SignalType } from "../../types/quantagent";
import { SignalCard } from "../app/SignalCard";

interface ReportDetailProps {
  report: ReportDetailType;
}

const SIGNALS: SignalType[] = ["BUY", "HOLD", "DROP"];

export function ReportDetail({ report }: ReportDetailProps) {
  return (
    <div className="report-detail-layout">
      <aside className="report-detail-side">
        <Card>
          <div className="side-badge-line">
            <Badge variant="dark">TODAY</Badge>
            <span>오전 8:00 발송</span>
          </div>
          <h3>{report.date}</h3>
          <strong>권장도 {report.recommendationScore} / 10</strong>
        </Card>
        <Card className="toc-card">
          <strong>목차</strong>
          {["헤더 · 메타", "전일 시황", "주요 뉴스 5건", "오늘의 후보 종목", "매수·보유·매도 신호", "정리 · 백테스트", "면책 · 거래비용"].map((item, index) => (
            <span className={index === 0 ? "is-active" : ""} key={item}>
              <b>{String(index + 1).padStart(2, "0")}</b> {item}
            </span>
          ))}
        </Card>
        <Card className="strategy-mini">
          <strong>기준 전략</strong>
          <h4>{report.strategyName}</h4>
          <dl>
            <div><dt>유니버스</dt><dd>KOSPI200 · 반도체</dd></div>
            <div><dt>신호</dt><dd>BUY {report.signals.BUY} · HOLD {report.signals.HOLD} · DROP {report.signals.DROP}</dd></div>
            <div><dt>권장도</dt><dd>{report.recommendationScore} / 10</dd></div>
          </dl>
        </Card>
      </aside>

      <article className="report-paper">
        <section className="report-paper__section report-paper__hero">
          <div className="report-paper__meta">
            <span>
              <Badge variant="dark">DAILY REPORT</Badge> {report.date} · {report.sentAt}
            </span>
            <span>{report.recipient}</span>
          </div>
          <h1>{report.title}</h1>
          <p>{report.marketBrief}</p>
          <div className="sample-market-grid">
            {report.marketSnapshot.map((item) => (
              <span key={item.label}>
                <small>{item.label}</small>
                <strong>{item.value}</strong>
              </span>
            ))}
          </div>
        </section>

        <Section title="전일 시황" index="02">
          <p>외국인 순매수와 환율 안정이 동시에 관측되며 반도체 대형주의 모멘텀이 유지됐습니다. 화학·2차전지 소재는 컨센서스 하향과 수급 약세가 동반됐습니다.</p>
        </Section>

        <Section title="주요 뉴스 5건" index="03">
          <ol className="news-list">
            {report.news.map((news) => (
              <li key={news.rank}>
                <b>{news.rank}</b>
                <span>{news.title}</span>
                <Badge variant={news.tone}>{news.source}</Badge>
              </li>
            ))}
          </ol>
        </Section>

        <Section title="오늘의 후보 종목" index="04">
          <div className="report-signal-list">
            {report.candidates.map((candidate) => (
              <SignalCard candidate={candidate} key={candidate.id} />
            ))}
          </div>
        </Section>

        <Section title="매수·보유·매도 신호 근거" index="05">
          <p>각 신호는 정/반/합 3-agent 토론 + 매도결손 3축 보강으로 도출됩니다. 점수는 호재·악재·기관 수급의 가중 합이며, 0.7 이상은 강한 신호로 분류합니다.</p>
          <div className="axis-grid">
            {report.signalAxes.map((axis) => (
              <div key={axis.label}>
                <span><Badge variant="dark">{axis.label}</Badge> 가중치 {axis.weight}</span>
                <strong>{axis.title}</strong>
                <p>{axis.description}</p>
              </div>
            ))}
          </div>
          <Card className="risk-manager">
            <span><Badge variant="dark">RISK MANAGER</Badge> 오늘 매크로 override 없음</span>
            <p>{report.riskManagerOverride}</p>
          </Card>
        </Section>

        <Section title="정리" index="06">
          <p className="report-conclusion">{report.conclusion}</p>
          <div className="report-metrics">
            {report.performance.metrics.map((metric) => (
              <span key={metric.key}>
                <small>{metric.label}</small>
                <strong>{metric.value}</strong>
                <em>{metric.delta}</em>
              </span>
            ))}
          </div>
          <div className="warning-box">
            <Badge variant="warning">주의</Badge>
            <span>환율 변동성이 확대되는 구간입니다. 추가 매수는 분할 진입을 권장합니다.</span>
          </div>
          <div className="report-cta-row">
            <a href="/app">워크스페이스에서 상세 보기 →</a>
            <button type="button">전략 수정하기</button>
          </div>
        </Section>

        <section className="report-paper__section report-paper__section--cost">
          <h2><span>07</span> 면책 · 거래비용 안내</h2>
          <ul>
            {report.costNotes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
          <div>
            <a href="/">수신 거부</a>
            <a href="/">수신 정책</a>
            <span>© 2026 QuantAgent</span>
          </div>
        </section>
      </article>
    </div>
  );
}

function Section({ index, title, children }: { index: string; title: string; children: ReactNode }) {
  return (
    <section className="report-paper__section">
      <h2><span>{index}</span> {title}</h2>
      {children}
    </section>
  );
}
