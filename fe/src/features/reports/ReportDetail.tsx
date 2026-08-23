import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import { PublicClaimDisclosure } from "../../components/common/PublicClaimDisclosure";
import { ResultTrustLinks } from "../../components/common/ResultTrustLinks";
import { ROUTES } from "../../config/routes";
import type { ArchivedReportDetail, PersistedReportSection } from "../../types/quantagent";

interface ReportDetailProps {
  report: ArchivedReportDetail;
}

const READER_EVIDENCE_SECTION_IDS = new Set(["reproduction_contract", "metric_registry"]);

function readerEvidenceSections(report: ArchivedReportDetail) {
  return (report.contentSections ?? []).filter((section) => (
    typeof section.id === "string"
    && READER_EVIDENCE_SECTION_IDS.has(section.id)
    && Array.isArray(section.entries)
    && section.entries.length > 0
  ));
}

/**
 * The report endpoint still carries legacy fields for backwards-compatible storage.
 * This reader deliberately projects only immutable identifiers, lifecycle facts and
 * the backend allow-listed verification sections.  In particular it never renders
 * a legacy score, action signal, candidate ranking, or generated narrative.
 */
export function ReportDetail({ report }: ReportDetailProps) {
  const evidenceSections = readerEvidenceSections(report);
  const version = report.updatedAt ?? report.publishedAt ?? report.createdAt ?? null;

  return (
    <div className="report-detail-layout">
      <aside className="report-detail-side">
        <Card>
          <div className="side-badge-line">
            <Badge variant="dark">READ-ONLY SNAPSHOT</Badge>
            <span>{report.date || "기준일 미확인"}</span>
          </div>
          <h3>결과 보관 기록</h3>
          <dl>
            <div><dt>결과 ID</dt><dd>{report.id}</dd></div>
            <div><dt>생성 시각</dt><dd>{report.createdAt ?? report.publishedAt ?? report.sentAt ?? "미확인"}</dd></div>
            <div><dt>상태</dt><dd>{statusLabel(report.status)}</dd></div>
          </dl>
        </Card>
        <Card className="toc-card">
          <strong>열람 범위</strong>
          <span className="is-active"><b>01</b> 결과 식별</span>
          <span><b>02</b> 검증 재현 계약</span>
          <span><b>03</b> 지표 산출 계약</span>
          <span><b>04</b> 신뢰센터·문제 기록</span>
        </Card>
      </aside>

      <article className="report-paper">
        <section className="report-paper__section report-paper__hero">
          <div className="report-paper__meta">
            <span><Badge variant="dark">ARCHIVED RESULT</Badge> 읽기 전용</span>
            <span>{report.date || "기준일 미확인"}</span>
          </div>
          <h1>보관된 결과 스냅샷</h1>
          <p>이 화면은 결과가 생성될 당시 보존된 식별자와 검증 계약만 보여 줍니다. 현재 시장 상태나 행동 판단을 제공하지 않습니다.</p>
          <dl className="strategy-mini">
            <div><dt>결과 ID</dt><dd>{report.id}</dd></div>
            <div><dt>결과 버전</dt><dd>{version ?? "버전 정보 미확인"}</dd></div>
            <div><dt>보관 상태</dt><dd>{statusLabel(report.status)}</dd></div>
          </dl>
        </section>

        <section className="report-paper__section" aria-labelledby="archived-snapshot-state-title">
          <h2 id="archived-snapshot-state-title"><span>02</span> 보관 시점과 현재 검증 한계</h2>
          <p>이 리포트는 과거 보관 기록입니다. 현재 시장 상태나 현재 성과를 확인하는 실행 결과가 아니므로, 현재 검증할 수 없음으로 표시합니다.</p>
          <dl className="strategy-mini">
            <div><dt>현재 검증 상태</dt><dd>현재 검증할 수 없음</dd></div>
            <div><dt>보관 기준일</dt><dd>{report.date || "기준일 미확인"}</dd></div>
            <div><dt>표시 출처</dt><dd>보관된 검증 재현·지표 계약</dd></div>
            <div><dt>다음 행동</dt><dd><a href={ROUTES.reports}>보관 리포트 목록으로 돌아가기</a></dd></div>
          </dl>
          <PublicClaimDisclosure claimKey="archivedSnapshot" asOf={report.date || undefined} />
        </section>

        {evidenceSections.length ? evidenceSections.map((section, index) => (
          <EvidenceSection index={String(index + 3).padStart(2, "0")} key={section.id} section={section} />
        )) : (
          <section className="report-paper__section">
            <h2><span>03</span> 검증 재현 계약</h2>
            <p>이 보관 기록에는 공개 열람 가능한 검증 계약이 없습니다. 근거가 없는 수치나 요약은 표시하지 않습니다.</p>
          </section>
        )}

        <section className="report-paper__section report-paper__section--cost">
          <h2><span>{String(evidenceSections.length + 3).padStart(2, "0")}</span> 한계와 문제 기록</h2>
          <p>과거 기록은 미래 결과를 보장하지 않습니다. 결과에 문제가 있으면 결과 ID와 버전을 함께 기록해 주세요.</p>
          <ResultTrustLinks resultId={report.id} version={version} />
        </section>
      </article>
    </div>
  );
}

function EvidenceSection({ index, section }: { index: string; section: PersistedReportSection }) {
  return (
    <section className="report-paper__section">
      <h2><span>{index}</span> {section.title || "검증 계약"}</h2>
      {section.note ? <p>{section.note}</p> : null}
      <dl className="strategy-mini">
        {section.entries?.map((entry, entryIndex) => (
          <div key={`${entry.label ?? "entry"}-${entryIndex}`}>
            <dt>{entry.label || "항목"}</dt>
            <dd>{entry.value}</dd>
            {entry.description ? <small>{entry.description}</small> : null}
          </div>
        ))}
      </dl>
    </section>
  );
}

function statusLabel(status: ArchivedReportDetail["status"]) {
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
