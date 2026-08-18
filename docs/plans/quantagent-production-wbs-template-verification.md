# 계획 XLSX 템플릿 복제 검증

## 원본과 출력

- 원본 SoT: `/Users/6kiity/Downloads/QuantAgent_프로젝트관련-2.xlsx`
- 원본 SHA-256: `7aad9831163c90dc8e4fdca7e788962900d1ee174277fa7f44a005156372cf4f`
- 출력: `outputs/quantagent-production-wbs-20260813/QuantAgent_프로덕션_신뢰성_WBS_계획본.xlsx`
- 원본은 읽기 전용으로 유지한다. 출력만 새로 쓴다.

## 허용한 변경

1. `1_RnR`, `2_WBS`, `3_Members`의 셀 값만 계획 내용으로 교체했다.
2. `2_WBS`의 원본 conditional formatting 중 사용하지 않는 `C219:R1015` 구간의 `#REF!` 세 개를 `C219&lt;&gt;"Level1|2|3"` 상대 참조로 고쳤다. 규칙, 범위, style ID는 보존했다.

## 구조 검증 결과

| 항목 | 원본 | 출력 | 결과 |
|---|---:|---:|---|
| 시트 순서 | `1_RnR`, `2_WBS`, `3_Members` | 동일 | PASS |
| `styles.xml`의 xf 항목 | 100 | 100 | PASS |
| `2_WBS` conditional formatting | 281 | 281 | PASS |
| `2_WBS` pageSetup | 1 | 1 | PASS |
| `2_WBS` mergeCell | 2 | 2 | PASS |
| `2_WBS` formula cell address | 331 | 331 | PASS |
| `2_WBS` 수식 오류 토큰 | 원본 `#REF!` 3개 | 0개 | PASS |
| ZIP 무결성 | 검사 | 검사 통과 | PASS |

## 내용 검증 결과

- 기준 원장: `quantagent-production-wbs-draft.md`
- 원자 작업: 71개
- 각 행의 `의도된 커밋`: 정확한 `[TYPE] 제목` 형식
- P0: 68개, 모두 `미착수`, 증적 URI `미생성`
- 실제 담당자·가용 시간은 `사람 결정 필요`로 남겼다. 추정하지 않았다.
- Markdown backtick은 XLSX의 작업·커밋 셀에 남기지 않았다.
- `C-09`을 포함한 근거 ID와 작업별 직접 검증 명령은 각 작업 행의 마지막 열에 적는다. evidence·risk의 세부 계약은 같은 ID의 기준 원장에서 찾는다.
