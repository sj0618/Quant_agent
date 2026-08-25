# 계획 XLSX 템플릿 복제 검증

## 범위와 판정 규칙

- 원본 SoT: `/Users/6kiity/Downloads/QuantAgent_프로젝트관련-2.xlsx`
- 원본 SHA-256: `7aad9831163c90dc8e4fdca7e788962900d1ee174277fa7f44a005156372cf4f`
- 계획본: `outputs/quantagent-production-wbs-20260813/QuantAgent_프로덕션_신뢰성_WBS_계획본.xlsx`
- 원본은 읽기 전용이며, 이 문서는 계획본의 현재 바이트와 증적의 결합 상태를 기록한다. 계획본을 실적·배포·승인 증적으로 해석하지 않는다.

## 2026-08-13 이력 기준선

초기 복제 검증은 `1_RnR`, `2_WBS`, `3_Members`의 셀 값만 바꾸고, 사용하지 않는
`C219:R1015` conditional-formatting 구간의 `#REF!` 세 개를 상대 참조로 고친 것으로
기록했다. 당시 문서의 71개 원자 작업/68개 P0, `A1:U79` inspect와 PNG는 그 시점의
계획본에만 적용된다.

그 이력 산출물에는 현재 계획본의 SHA가 없다. 따라서 71개라는 수나 기존 PNG/inspect를
현재 계획본의 수용 근거로 재사용하지 않는다.

## 2026-08-25 현재 계획본 재검사

현재 계획본은 SHA-256
`92311cc787929b94963f77a180343185f859bfe7e27e0af048de77398ec2fa6b`이며, 크기는
2,059,497 bytes다. 이 SHA에 직접 결합한 산출물은 같은 디렉터리의
`current-xlsx-audit.json`, `verification.ndjson`, `formula-audit.ndjson`,
`QuantAgent_프로덕션_신뢰성_WBS_계획본.xlsx.inspect.ndjson` 및 세 PNG다.

| 항목 | 현재 검사 결과 | 판정 |
|---|---|---|
| 시트 순서 | `1_RnR`, `2_WBS`, `3_Members` | PASS |
| 표의 데이터 범위 | `1_RnR!A1:G9`, `2_WBS!A1:S97`, `3_Members!A1:G8` | PASS |
| 원자 WBS 행 | 상위 `QAG-001` 요약 행을 제외하고 90개 | PASS |
| 수식 셀 | 전체 worksheet XML의 `<f>` 331개. Artifact Tool inspect는 221개만 materialize하므로 단독 근거로 쓰지 않는다. | PASS |
| 수식 오류 토큰 | 전체 worksheet XML에서 `#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, `#N/A` 각각 0건 | PASS |
| 렌더 산출물 | 세 시트 모두 SHA-bound PNG 생성 | 조건부 PASS |

## 렌더 및 독립 심사 경계

`2_WBS`는 전체 수식 범위가 길어 Artifact Tool의 보통 배율(0.5) 렌더에서
`850×16765` bitmap을 할당할 수 없다. 따라서 같은 SHA의 전체 시트 개요를 `2_WBS.png`
0.1 배율로 남기고, 사람이 읽을 수 있는 행 내용은 inspect 산출물로 교차 확인했다.
LibreOffice의 A4 기본 출력은 100쪽으로 분절되므로, 이를 인쇄 레이아웃 승인으로 주장하지
않는다.

이 재검사는 현재 계획본의 파일·수식·렌더 증적 결합을 복구한다. 한국어 문체와 읽기성의
독립 심사, 그리고 인쇄형 산출물이 필요한지의 승인 판단은 별도 수용 기준이며
`XLX-PLAN-03`을 자동으로 완료시키지 않는다.
