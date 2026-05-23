import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import type { ReportSummary, SignalType } from "../../types/quantagent";

interface ReportListProps {
  reports: ReportSummary[];
}

const SIGNALS: SignalType[] = ["BUY", "HOLD", "DROP"];

export function ReportList({ reports }: ReportListProps) {
  const today = reports[0];
  const pastReports = reports.slice(1);

  return (
    <div className="reports-layout">
      <aside className="reports-sidebar">
        <FilterGroup title="기간" items={[["오늘", "1"], ["최근 7일", "7", true], ["최근 30일", "28"], ["최근 3개월", "84"], ["전체", "142"]]} />
        <FilterGroup title="전략" items={[["반도체 모멘텀 + 기관 매수", "18", true], ["PBR·PER 가치주 전략", "12"], ["퀄리티 팩터 우량주", "8"]]} />
        <FilterGroup title="포함 신호" items={[["BUY 포함", "", true], ["HOLD 포함", "", true], ["DROP 포함", ""]]} />
        <Card className="manual-filter">
          <strong>직접 입력</strong>
          <div>
            <span>시작</span>
            <b>2026.04.12 📅</b>
          </div>
          <div>
            <span>종료</span>
            <b>2026.04.18 📅</b>
          </div>
        </Card>
        <Card className="score-filter">
          <strong>권장도</strong>
          <span>최소 점수 <b>6.0</b></span>
          <div>
            <button type="button">초기화</button>
            <button type="button">적용</button>
          </div>
        </Card>
      </aside>

      <section className="reports-main">
        {today ? <FeaturedReport report={today} /> : null}
        <div className="report-list-head">
          <strong>지난 리포트</strong>
          <span>{pastReports.length}건</span>
        </div>
        <Card className="report-list" padded={false}>
          {pastReports.map((report) => (
            <a className="report-row" href={`/reports/${report.id}`} key={report.id}>
              <div className="report-row__date">
                <strong>{report.date}</strong>
                <span>{report.weekday}</span>
              </div>
              <div className="report-row__content">
                <strong>{report.title}</strong>
                <p>{report.summary}</p>
              </div>
              <div className="report-row__signals">
                {SIGNALS.map((signal) =>
                  report.signals[signal] ? (
                    <Badge key={signal} signal={signal}>
                      {signal} {report.signals[signal]}
                    </Badge>
                  ) : null,
                )}
              </div>
              <div className="report-row__score">
                <strong>{report.recommendationScore}</strong>
                <span>권장도</span>
              </div>
              <span className="report-row__arrow">›</span>
            </a>
          ))}
        </Card>
        <div className="pagination">
          {["‹ 이전", "1", "2", "3", "···", "24", "다음 ›"].map((item) => (
            <button className={item === "1" ? "is-active" : ""} key={item} type="button">
              {item}
            </button>
          ))}
        </div>
        <Card className="tip-card">
          <Badge variant="dark">TIP</Badge>
          <strong>리포트가 적게 보이시나요?</strong>
          <p>전략 활성화 다음 날부터 일일 리포트가 자동 생성됩니다. 마이페이지 &gt; 알림 설정에서 Daily 리포트 수신을 켜두시면 이메일로도 함께 받아보실 수 있습니다.</p>
        </Card>
      </section>
    </div>
  );
}

function FilterGroup({ title, items }: { title: string; items: Array<[string, string, boolean?]> }) {
  return (
    <Card className="filter-group">
      <strong>{title}</strong>
      {items.map(([label, count, active]) => (
        <div className={active ? "is-active" : ""} key={label}>
          <span className="filter-check" />
          <span>{label}</span>
          {count ? <Badge variant="soft">{count}</Badge> : null}
        </div>
      ))}
    </Card>
  );
}

function FeaturedReport({ report }: { report: ReportSummary }) {
  return (
    <Card className="featured-report">
      <div className="featured-report__top">
        <div>
          <Badge variant="dark">TODAY</Badge>
          <strong>2026년 4월 18일 (목)</strong>
          <span>· {report.sentAt}</span>
        </div>
        <Badge variant="dark">권장도 {report.recommendationScore} / 10</Badge>
      </div>
      <h2>{report.title}</h2>
      <p>{report.summary}</p>
      <div className="sample-market-grid">
        {report.marketSnapshot.map((item) => (
          <span key={item.label}>
            <small>{item.label}</small>
            <strong>{item.value}</strong>
          </span>
        ))}
      </div>
      <div className="sample-signal-row">
        {SIGNALS.map((signal) =>
          report.signals[signal] ? (
            <Badge key={signal} signal={signal}>
              {signal} {report.signals[signal]}
            </Badge>
          ) : null,
        )}
      </div>
      <div className="featured-report__actions">
        <button type="button">↓ PDF</button>
        <button type="button">공유</button>
        <button type="button">재발송</button>
        <a href={`/reports/${report.id}`}>리포트 열기 →</a>
      </div>
    </Card>
  );
}
