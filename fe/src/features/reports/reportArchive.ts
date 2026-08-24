import type { ReportSummary } from "../../types/quantagent";

type ArchiveTimestampSource = Pick<ReportSummary, "createdAt">;

/**
 * A report without this explicit record timestamp must not borrow a delivery,
 * publication, update, or business date as an archive timestamp.
 */
export function archiveTimestamp(report: ArchiveTimestampSource) {
  return report.createdAt || "보관 기록 시각 미확인";
}

export const ARCHIVE_RETENTION_NOTICE = "보관 정책: 리포트 snapshot은 90일 보관하며, 만료된 기록은 삭제 또는 마스킹됩니다.";
export const ARCHIVE_ACCESS_NOTICE = "열람은 인증된 사용자에게 최소 권한 원칙으로만 허용됩니다.";
export const ARCHIVE_READ_ONLY_NOTICE = "이 기록은 읽기 전용입니다. 재발송·수정·새 분석 실행은 지원하지 않습니다.";
export const ARCHIVE_AUDIT_NOTICE = "열람·다운로드·만료 처리는 365일 감사 기록 대상입니다.";
