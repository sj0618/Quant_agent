# WBS 한국어 문체 감사

## 기준 원장

`quantagent-production-wbs-draft.md`가 71개 작업의 유일한 기준 원장이다. XLSX의 작업명과 의도된 커밋은 이 원장에서 생성한다. 따라서 Markdown과 XLSX를 따로 고치지 않는다.

기술 식별자, 코드 경로, API path, commit title, 검증 명령은 보존한다. 사용자가 읽는 작업명·완료 조건·위험 문장만 다듬는다.

## 남아 있던 AI 문체와 수정

| 위치 | 초안 표현 | 문제 | 최종 표현 |
|---|---|---|---|
| OD-INV-01 | "온디맨드 인벤토리의 file:line과 공개 범위를 HEAD에서 다시 확인한다" | 도구 중심 표현이라 실제 판단이 안 보인다. | "새 분석을 만드는 화면·API·작업을 하나씩 확인해 없앨지, 읽기 전용으로 남길지 결정한다." |
| FT-RLS-01 | "release profile의 필수 dependency와 readiness 실패 계약을 만든다" | 영어 명사가 겹쳐 사용자 영향이 숨는다. | "운영 설정에 DB나 provider가 없으면 서비스를 준비 완료로 표시하지 않게 한다." |
| MR-REG-01 | "metric registry schema와 formula version 규칙을 만든다" | 산출물이 무엇인지 알기 어렵다. | "각 지표에 이름, 계산식, 입력 기간, 기준 시각, 결측 처리 방식을 적은 목록을 만든다." |
| UX-BUILD-01 | "production 정적 번들만 배포되게 build 검사를 추가한다" | 결과와 차단 대상이 빠졌다. | "배포 화면에 개발 서버 주소와 소스 파일이 섞이면 배포가 실패하게 한다." |
| EV-GATE-01 | "backend, frontend, public smoke, formula contract를 묶은 evaluator" | 병렬 명사 나열이다. | "한 명령으로 API, 화면, 지표 계산을 검사해 P0 하나라도 틀리면 실패하게 한다." |

## 전 행 검사

- 검사 대상: 기준 원장의 71개 행 전부
- 정확한 commit 제목: 각 행에 `[TYPE] 제목` 형식이 하나 있어야 한다. `TYPE`은 `API`, `DOCS`, `E2E`, `FE`, `TEST`, `CHORE`다.
- 금지 표현: em/en dash, `개선`, `고도화`, `정리`처럼 완료를 판정할 수 없는 단어
- 문장 기준: 작업명은 동사로 시작하고, 완료 조건에는 관찰 가능한 결과를 쓴다.
- 예외: 코드 경로와 API path 안의 영문·기호, 검증 명령은 기술 식별자로 간주해 바꾸지 않는다.

## 최종본 판정

- 작업명은 동사로 시작한다.
- "개선", "고도화", "정리"처럼 판정할 수 없는 말은 쓰지 않는다.
- 과장·홍보 문구와 em/en dash는 없다.
- 71개 행은 기준 원장에서 XLSX로 직접 전사한다. 행마다 ID, 작업명, 정확한 commit 제목, 검증 명령, 근거 ID가 같은지 구조 검사한다.

## 2026-08-25 현재 계획본 독립 재검사

대상은 SHA-256
`92311cc787929b94963f77a180343185f859bfe7e27e0af048de77398ec2fa6b`의
`outputs/quantagent-production-wbs-20260813/QuantAgent_프로덕션_신뢰성_WBS_계획본.xlsx`다.
원본 XLSX의 셀, 수식, 서식은 수정하지 않았다.

### 한국어 문체와 원자 행

- `2_WBS!E8:H97`의 원자 행 90개 모두에 ID, 작업명, intended commit이 있다.
- 작업명에서 `개선`, `고도화`, `정리`, em dash, en dash는 0건이다.
- 작업명은 관찰 가능한 동작을 적고, 기술 식별자·API path·검증 명령은 바꾸지 않았다.

### 가독성 있는 렌더 증거

같은 SHA의 셀 값만을 별도 스냅샷 시트에 투영해, 전체 행이 한 장의 축소된
개요 이미지로 뭉개지지 않도록 다음 PNG를 만들었다. 이 PNG는 데이터·수식을
대체하지 않으며 읽기성 검사 전용이다.

| 원본 범위 | 읽기성 PNG |
|---|---|
| `1_RnR!A1:G9` | `readable-render-audit/1_RnR-readable.png` |
| `2_WBS!A1:S32` | `readable-render-audit/2_WBS-001-032.png` |
| `2_WBS!A33:S64` | `readable-render-audit/2_WBS-033-064.png` |
| `2_WBS!A65:S97` | `readable-render-audit/2_WBS-065-097.png` |
| `3_Members!A1:G8` | `readable-render-audit/3_Members-readable.png` |

각 PNG에서 한글 제목·작업명·담당·상태·scope/검증 원장이 잘리지 않고
표시되는지 독립 확인했다. 기존 LibreOffice의 A4 기본 인쇄 100쪽 분절은
workbook 내용 오류로 승격하지 않으며, 인쇄용 레이아웃을 승인한 증거도 아니다.

### 수식 검사

Artifact Tool regex 검사 결과는
`readable-render-audit/readable-render-formula-scan.ndjson`에 남겼고,
`#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, `#N/A` 일치 0건이다. OOXML의
namespace-qualified 실제 셀 수식은 `2_WBS` 331개, 나머지 두 시트 0개다.

이 검사는 S 등급 workbook 검사다. 현재 계획본을 배포·실데이터·사람 승인
증적으로 바꾸지 않으며, live WBS의 승인 상태는 별도 증거에 따라 유지한다.
