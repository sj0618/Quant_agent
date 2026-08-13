import type { ReactNode } from "react";
import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import { ROUTES } from "../../config/routes";
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
            <Badge variant="dark">ARCHIVE</Badge>
            <span>{report.sentAt || "발송 시각 미확인"}</span>
          </div>
          <h3>{report.date}</h3>
          <strong>권장도 {report.recommendationScore} / 10</strong>
        </Card>
        <Card className="toc-card">
          <strong>목차</strong>
          {["헤더 · 메타", "시황 근거", "수집된 뉴스", "기록된 후보 종목", "신호 근거", "정리 · 성과 지표", "면책 · 거래비용"].map((item, index) => (
            <span className={index === 0 ? "is-active" : ""} key={item}>
              <b>{String(index + 1).padStart(2, "0")}</b> {item}
            </span>
          ))}
        </Card>
        <Card className="strategy-mini">
          <strong>기준 전략</strong>
          <h4>{report.strategyName}</h4>
          <dl>
            <div><dt>평가 범위</dt><dd>{report.marketContext || "이 기록에는 평가 범위가 보존되지 않았습니다."}</dd></div>
            <div><dt>신호</dt><dd>BUY {report.signals.BUY} · HOLD {report.signals.HOLD} · DROP {report.signals.DROP}</dd></div>
            <div><dt>권장도</dt><dd>{report.recommendationScore} / 10</dd></div>
          </dl>
        </Card>
      </aside>

      <article className="report-paper">
        <section className="report-paper__section report-paper__hero">
          <div className="report-paper__meta">
            <span>
              <Badge variant="dark">ARCHIVED REPORT</Badge> {report.date} · {report.sentAt || "발송 시각 미확인"}
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

        <Section title="시황 근거" index="02">
          <p>{report.marketContext || "이 기록에는 시황 근거가 보존되지 않았습니다. 수치를 투자 판단에 사용하지 마세요."}</p>
        </Section>

        <Section title="수집된 뉴스" index="03">
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

        <Section title="기록된 후보 종목" index="04">
          <div className="report-signal-list">
            {report.candidates.map((candidate) => (
              <SignalCard candidate={candidate} key={candidate.id} />
            ))}
          </div>
        </Section>

        <Section title="매수·보유·매도 신호 근거" index="05">
          {report.signalAxes.length ? (
            <div className="axis-grid">
              {report.signalAxes.map((axis) => (
                <div key={axis.label}>
                  <span><Badge variant="dark">{axis.label}</Badge> 가중치 {axis.weight}</span>
                  <strong>{axis.title}</strong>
                  <p>{axis.description}</p>
                </div>
              ))}
            </div>
          ) : <p>이 기록에는 신호 산출 근거가 보존되지 않았습니다. 추천으로 해석하지 마세요.</p>}
          <Card className="risk-manager">
            <span><Badge variant="dark">RISK REVIEW</Badge> 기록된 위험 조정</span>
            <p>{report.riskManagerOverride || "이 기록에는 위험 조정 근거가 보존되지 않았습니다."}</p>
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
            <span>{report.warningNote || "이 기록에는 추가 경고가 보존되지 않았습니다. 근거가 없는 수치는 추천으로 해석하지 마세요."}</span>
          </div>
          <div className="report-cta-row">
            <a href={ROUTES.reports}>리포트 목록으로 돌아가기 →</a>
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
            <a href={ROUTES.unsubscribe}>수신 거부</a>
            <a href={ROUTES.notifications}>수신 정책</a>
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
