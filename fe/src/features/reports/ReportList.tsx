import { useState } from "react";
import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import { ROUTES } from "../../config/routes";
import type { ArchivedReportSummary } from "../../types/quantagent";
import { archiveTimestamp } from "./reportArchive";
import { DEFAULT_REPORT_FILTERS, type ReportFilters, type ReportRange } from "./reportFilters";

interface ReportListProps {
  filters: ReportFilters;
  onApplyFilters: (filters: ReportFilters) => void;
  onResetFilters: () => void;
  reports: ArchivedReportSummary[];
}

const RANGE_OPTIONS: Array<[string, ReportRange]> = [["오늘", "1"], ["최근 7일", "7"], ["최근 30일", "30"], ["최근 3개월", "90"], ["전체", "all"]];
const PAGE_SIZE = 10;

export function ReportList({ filters, onApplyFilters, onResetFilters, reports }: ReportListProps) {
  const [draftFilters, setDraftFilters] = useState(filters);
  const [page, setPage] = useState(1);
  const totalPages = Math.max(Math.ceil(reports.length / PAGE_SIZE), 1);
  const visibleReports = reports.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="reports-layout">
      <aside className="reports-sidebar">
        <Card className="filter-group">
          <strong>보관 시점</strong>
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
          <div>
            <button onClick={() => { setDraftFilters(DEFAULT_REPORT_FILTERS); setPage(1); onResetFilters(); }} type="button">초기화</button>
            <button onClick={() => { setPage(1); onApplyFilters(draftFilters); }} type="button">적용</button>
          </div>
        </Card>
      </aside>

      <section className="reports-main">
        <div className="report-list-head">
          <strong>보관된 결과</strong>
          <span>{reports.length}건</span>
        </div>
        <Card className="report-list" padded={false}>
          {visibleReports.length === 0 ? (
            <div className="empty-inline">
              <strong>조건에 맞는 보관 결과가 없습니다</strong>
              <p>보관 시점을 조정해 보세요.</p>
            </div>
          ) : null}
          {visibleReports.map((report) => (
            <a className="report-row" href={ROUTES.reportDetail(report.id)} key={report.id}>
              <div className="report-row__date">
                <strong>{report.date || "기준일 미확인"}</strong>
                <span>보관 기록 시각: {archiveTimestamp(report)}</span>
              </div>
              <div className="report-row__content">
                <strong>읽기 전용 결과 스냅샷</strong>
                <p>결과 ID {report.id}</p>
              </div>
              <Badge variant="soft">{statusLabel(report.status)}</Badge>
              <span className="report-row__arrow">›</span>
            </a>
          ))}
        </Card>
        {reports.length > PAGE_SIZE ? (
          <div className="pagination">
            <button disabled={page === 1} onClick={() => setPage((current) => Math.max(current - 1, 1))} type="button">‹ 이전</button>
            {Array.from({ length: totalPages }, (_, index) => index + 1).map((item) => (
              <button className={item === page ? "is-active" : ""} key={item} onClick={() => setPage(item)} type="button">{item}</button>
            ))}
            <button disabled={page === totalPages} onClick={() => setPage((current) => Math.min(current + 1, totalPages))} type="button">다음 ›</button>
          </div>
        ) : null}
        <Card className="tip-card">
          <Badge variant="dark">읽기 전용</Badge>
          <strong>이전 결과는 당시의 보관 기록입니다.</strong>
          <p>새 분석을 시작하거나 현재 시장 상태를 대신하지 않습니다. 기준일과 검증 재현 계약을 확인한 뒤 해석해 주세요.</p>
        </Card>
      </section>
    </div>
  );
}

function statusLabel(status: ArchivedReportSummary["status"]) {
  return {
    sent: "보관됨",
    delivered: "보관됨",
    draft: "준비 중",
    submitted: "처리 중",
    processing: "처리 중",
    failed: "확인 필요",
    resent: "보관됨",
    cancelled: "취소됨",
    unknown: "상태 미확인",
  }[status];
}
