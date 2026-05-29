import { useState } from "react";
import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import { copyReportShareLink, printCurrentView, resendReportEmail } from "../../api/reportActionsClient";
import { ROUTES } from "../../config/routes";
import type { ReportSummary, SignalType } from "../../types/quantagent";
import { DEFAULT_REPORT_FILTERS, type ReportFilters, type ReportRange } from "./reportFilters";

interface ReportListProps {
  allReports: ReportSummary[];
  filters: ReportFilters;
  onApplyFilters: (filters: ReportFilters) => void;
  onResetFilters: () => void;
  reports: ReportSummary[];
}

const SIGNALS: SignalType[] = ["BUY", "HOLD", "DROP"];
const RANGE_OPTIONS: Array<[string, ReportRange]> = [["오늘", "1"], ["최근 7일", "7"], ["최근 30일", "30"], ["최근 3개월", "90"], ["전체", "all"]];
const PAST_REPORT_PAGE_SIZE = 5;

export function ReportList({ allReports, filters, onApplyFilters, onResetFilters, reports }: ReportListProps) {
  const [draftFilters, setDraftFilters] = useState(filters);
  const [status, setStatus] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const today = reports[0];
  const pastReports = reports.slice(1);
  const totalPages = Math.max(Math.ceil(pastReports.length / PAST_REPORT_PAGE_SIZE), 1);
  const visiblePastReports = pastReports.slice((page - 1) * PAST_REPORT_PAGE_SIZE, page * PAST_REPORT_PAGE_SIZE);
  const strategyNames = Array.from(new Set(allReports.map((report) => report.strategyName)));

  const updateSignal = (signal: SignalType, checked: boolean) => {
    setDraftFilters((current) => ({ ...current, signals: { ...current.signals, [signal]: checked } }));
  };

  const handleReportAction = async (action: "print" | "share" | "resend", report: ReportSummary) => {
    setStatus(null);
    try {
      if (action === "print") {
        printCurrentView();
        setStatus(`${report.date} 리포트를 브라우저 PDF로 저장할 수 있습니다.`);
      }

      if (action === "share") {
        const url = await copyReportShareLink(report.id);
        setStatus(`공유 링크를 복사했습니다: ${url}`);
      }

      if (action === "resend") {
        await resendReportEmail(report.id);
        setStatus(`${report.date} 리포트를 이메일로 재발송했습니다.`);
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "리포트 액션 처리에 실패했습니다.");
    }
  };

  return (
    <div className="reports-layout">
      <aside className="reports-sidebar">
        <Card className="filter-group">
          <strong>기간</strong>
          {RANGE_OPTIONS.map(([label, value]) => (
            <button
              className={draftFilters.range === value ? "is-active" : ""}
              key={value}
              onClick={() => setDraftFilters((current) => ({ ...current, range: value }))}
              type="button"
            >
              <span className="filter-check" />
              <span>{label}</span>
            </button>
          ))}
        </Card>
        <Card className="filter-group">
          <strong>전략</strong>
          <button
            className={draftFilters.strategyName === "all" ? "is-active" : ""}
            onClick={() => setDraftFilters((current) => ({ ...current, strategyName: "all" }))}
            type="button"
          >
            <span className="filter-check" />
            <span>전체 전략</span>
            <Badge variant="soft">{allReports.length}</Badge>
          </button>
          {strategyNames.map((strategyName) => (
            <button
              className={draftFilters.strategyName === strategyName ? "is-active" : ""}
              key={strategyName}
              onClick={() => setDraftFilters((current) => ({ ...current, strategyName }))}
              type="button"
            >
              <span className="filter-check" />
              <span>{strategyName}</span>
              <Badge variant="soft">{allReports.filter((report) => report.strategyName === strategyName).length}</Badge>
            </button>
          ))}
        </Card>
        <Card className="filter-group">
          <strong>포함 신호</strong>
          {SIGNALS.map((signal) => (
            <label className={draftFilters.signals[signal] ? "is-active" : ""} key={signal}>
              <input checked={draftFilters.signals[signal]} onChange={(event) => updateSignal(signal, event.target.checked)} type="checkbox" />
              <span className="filter-check" />
              <span>{signal} 포함</span>
            </label>
          ))}
        </Card>
        <Card className="manual-filter">
          <strong>직접 입력</strong>
          <label>
            <span>시작</span>
            <input onChange={(event) => setDraftFilters((current) => ({ ...current, startDate: event.target.value }))} type="date" value={draftFilters.startDate} />
          </label>
          <label>
            <span>종료</span>
            <input onChange={(event) => setDraftFilters((current) => ({ ...current, endDate: event.target.value }))} type="date" value={draftFilters.endDate} />
          </label>
        </Card>
        <Card className="score-filter">
          <strong>권장도</strong>
          <span>최소 점수 <b>{draftFilters.minScore.toFixed(1)}</b></span>
          <input
            max="10"
            min="0"
            onChange={(event) => setDraftFilters((current) => ({ ...current, minScore: Number(event.target.value) }))}
            step="0.1"
            type="range"
            value={draftFilters.minScore}
          />
          <div>
            <button onClick={() => { setDraftFilters(DEFAULT_REPORT_FILTERS); setPage(1); onResetFilters(); }} type="button">초기화</button>
            <button onClick={() => { setPage(1); onApplyFilters(draftFilters); }} type="button">적용</button>
          </div>
        </Card>
      </aside>

      <section className="reports-main">
        {status ? <div className="action-feedback">{status}</div> : null}
        {today ? <FeaturedReport onAction={handleReportAction} report={today} /> : null}
        <div className="report-list-head">
          <strong>지난 리포트</strong>
          <span>{pastReports.length}건</span>
        </div>
        <Card className="report-list" padded={false}>
          {!today && pastReports.length === 0 ? (
            <div className="empty-inline">
              <strong>조건에 맞는 리포트가 없습니다</strong>
              <p>기간, 신호, 권장도 필터를 조정하세요.</p>
            </div>
          ) : null}
          {visiblePastReports.map((report) => (
            <a className="report-row" href={ROUTES.reportDetail(report.id)} key={report.id}>
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
        {pastReports.length > PAST_REPORT_PAGE_SIZE ? (
          <div className="pagination">
            <button disabled={page === 1} onClick={() => setPage((current) => Math.max(current - 1, 1))} type="button">‹ 이전</button>
            {Array.from({ length: totalPages }, (_, index) => index + 1).map((item) => (
              <button className={item === page ? "is-active" : ""} key={item} onClick={() => setPage(item)} type="button">
                {item}
              </button>
            ))}
            <button disabled={page === totalPages} onClick={() => setPage((current) => Math.min(current + 1, totalPages))} type="button">다음 ›</button>
          </div>
        ) : null}
        <Card className="tip-card">
          <Badge variant="dark">TIP</Badge>
          <strong>리포트가 적게 보이시나요?</strong>
          <p>
            전략 활성화 다음 날부터 일일 리포트가 자동 생성됩니다.{" "}
            <a href={ROUTES.notifications}>마이페이지 &gt; 알림 설정</a>에서 Daily 리포트 수신을 켜두시면 이메일로도 함께 받아보실 수 있습니다.
          </p>
        </Card>
      </section>
    </div>
  );
}

function FeaturedReport({
  onAction,
  report,
}: {
  onAction: (action: "print" | "share" | "resend", report: ReportSummary) => void;
  report: ReportSummary;
}) {
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
        <button onClick={() => onAction("print", report)} type="button">↓ PDF</button>
        <button onClick={() => onAction("share", report)} type="button">공유</button>
        <button onClick={() => onAction("resend", report)} type="button">재발송</button>
        <a href={ROUTES.reportDetail(report.id)}>리포트 열기 →</a>
      </div>
    </Card>
  );
}
