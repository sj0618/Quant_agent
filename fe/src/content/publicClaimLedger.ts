/**
 * Public-facing statements are deliberately kept separate from result data.
 * These records describe the UI contract, not investment performance or a
 * substitute for an immutable release-evidence bundle.
 */
export const PUBLIC_CLAIM_LEDGER = {
  landingArchiveScope: {
    id: "CLAIM-UI-ARCHIVE-001",
    source: "공개 UI 계약: 보관 리포트 열람 범위",
    asOfPolicy: "개별 보관 리포트의 기준일과 검증 계약을 함께 확인",
    valuePolicy: "랜딩에는 sample·live 성과 수치를 표시하지 않음",
  },
  archivedSnapshot: {
    id: "CLAIM-UI-ARCHIVE-002",
    source: "보관 리포트의 allow-listed 검증 재현·지표 계약",
    asOfPolicy: "해당 리포트의 보관 기준일",
    valuePolicy: "현재 검증할 수 없는 과거 기록에 현재 성과·추천 수치를 덧붙이지 않음",
  },
} as const;

export type PublicClaimKey = keyof typeof PUBLIC_CLAIM_LEDGER;
