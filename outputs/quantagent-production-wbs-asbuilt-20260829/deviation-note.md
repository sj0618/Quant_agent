# XLX-ASBUILT-03 deviation note — as-built workbook 계획 대비 이탈

- 대상 파일: `outputs/quantagent-production-wbs-asbuilt-20260829/QuantAgent_프로덕션_신뢰성_WBS_실적본.xlsx`
- 비교 기준(계획본): `outputs/quantagent-production-wbs-20260813/QuantAgent_프로덕션_신뢰성_WBS_계획본.xlsx`
- 작성 시점: 2026-08-30 (owner execution, reviewer 판정 아님)

이 문서는 `XLX-ASBUILT-03`의 Done·QA 계약 중 "deviation note 있음" 요건을 충족하기 위해 작성됐다. 계획본과 실적본을 실제로 열어 대조한 사실만 기록하며, 발견된 이탈을 임의로 수정하지 않았다.

## 1. 행(ID) 범위 이탈

| 항목 | 계획본 | 실적본 |
|---|---|---|
| ID 수(작업 항목) | 90개 + 요약행(QAG-001) 1개 = 91행 | 132행 |
| 차이 | — | 계획본 대비 **+42개 ID** |

계획본에 없고 실적본에만 있는 42개 ID(`CORE-*`, `RMP-*` 다수, `QA-DATA-AUDIT-*` 전부 등)는 `XLX-ASBUILT-02` owner evidence에 이미 명시적으로 기록된 의도된 확장이다 — 계획본이 2026-08-25 시점 스냅샷이고, 실적본은 2026-08-27 export snapshot(132행) 전체를 포함하도록 명시적으로 확정됐기 때문이다(`XLX-ASBUILT-02` 실행 확정 지시 1항). **의도된 이탈**로 분류한다.

## 2. 컬럼 구조 이탈

| 항목 | 계획본 | 실적본 |
|---|---|---|
| 컬럼 수 | 17 | 27 |
| 컬럼 성격 | 일정관리형(우선/No/소유/계획시작·종료/실행시작·종료/계획일수/실행일수/목표%/현재%) | QA-계약형(작업/DoneQA계약/실행검증/증적URI/승인자) 17개 + as-built 전용 10개 |

계획본의 진행률(%) 관리 컬럼과 실적본의 QA-계약·증적 컬럼은 **성격이 다른 목적의 표**다. 이는 `XLX-ASBUILT-02` 실행 확정 지시 2항("실제 WBS 데이터 구조는 최신 export snapshot의 QA-계약형 컬럼을 기준으로 한다")에 따른 **의도된 설계 결정**이며 사고형 이탈이 아니다.

## 3. 수식(formula) 이탈

| 항목 | 계획본 | 실적본 |
|---|---|---|
| 수식 셀 수 | 331(worksheet XML `<f>` 기준, `docs/plans/quantagent-production-wbs-template-verification.md` 기록) | **0** |

계획본은 진행률(%)을 수식으로 계산하는 살아있는 일정관리 시트인 반면, 실적본은 특정 시점의 canonical repo 상태를 고정 기록한 **정적 스냅샷**이다. 수식이 없다는 사실 자체는 formula-error 감사 기준(요소 3)을 자동으로 통과시키지만, 계획본과 성격이 다른 산출물이라는 점은 이탈로 기록한다. **의도된 이탈**(스냅샷 설계상 당연한 차이).

## 4. 한국어 humanizer 이탈 — ⚠ 의도되지 않은 이탈

`outputs/quantagent-production-wbs-asbuilt-20260829/asbuilt-xlsx-audit.json`의 `humanizer_audit` 결과:

- `As-built note` 컬럼: **17개 행**이 한글 없이 영어로만 작성됨(내부 reconciliation 스크립트의 원문 문자열이 그대로 들어감, 예: `all referenced commit SHA token(s) not found as objects in canonical repo; sha_tokens=...`).
- `Reviewer decision` 컬럼: **16개 행**이 15자 초과의 영어 전용 서술문(`execution record, no verdict-labeled decision found`)로 채워짐.
- 두 컬럼을 합쳐 **중복 없이 132행 중 29행(22.0%)**이 한글화되지 않은 영어 전용 자유서술을 포함한다.

이 워크북의 의도된 커밋 라벨은 `[DOCS] publish Korean as-built WBS workbook`이다 — "Korean" 워크북을 표방하나, 29개 행의 자유서술 컬럼이 실제로는 한글화되지 않았다. `SHA 유형`(implementation/tested-baseline 등)과 `Reviewer decision`의 `APPROVE` 같은 짧은 통제 어휘(controlled vocabulary)는 이 프로젝트 전반의 관례상 영어 라벨로 유지되는 것이 자연스러워 이탈로 보지 않았으나, **문장 단위의 자유서술이 전혀 한글화되지 않은 29개 행은 humanizer audit 기준에서 실질적 이탈로 판단**한다.

**이 이탈은 이번 owner 작업에서 임의로 수정하지 않았다** — `XLX-ASBUILT-03`의 작업 범위는 "재검사"(audit)이며, 발견된 이탈을 수정하는 것은 별도 결정 사항이다.

## 5. 원본 WBS 상태 보존 — 이탈 없음(확인 사살)

실적본의 `현재 WBS 상태` 컬럼 132행 전부가 export snapshot 원문과 정확히 일치함을 이전 pre-commit audit에서 이미 확인했고, 이번 감사에서도 재확인했다. **이탈 없음.**

## 요약

| # | 이탈 항목 | 성격 | 조치 |
|---|---|---|---|
| 1 | 행 범위(91→132) | 의도된 확장 | 없음(이미 승인된 설계) |
| 2 | 컬럼 구조(일정관리형→QA-계약형) | 의도된 설계 변경 | 없음(이미 승인된 설계) |
| 3 | 수식(331→0) | 스냅샷 설계상 당연한 차이 | 없음 |
| 4 | 한국어 humanizer(29/132행 영어 전용) | **의도되지 않은 이탈** | 수정 여부는 별도 결정 필요 — 이번 작업에서는 기록만 함 |
| 5 | 원본 상태 보존 | 이탈 없음 | — |
