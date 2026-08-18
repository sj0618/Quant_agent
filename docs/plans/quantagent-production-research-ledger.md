# QuantAgent 신뢰성 리서치 원장

## 판정 규칙

- 이 원장은 `2026-08-13`에 수행한 다섯 각도 조사와 현재 HEAD의 읽기 전용 감사 결과를 분리한다.
- `현재 HEAD 상태`는 구현 완료 주장이 아니다. `active`는 감사에서 아직 위험 경로가 확인됐다는 뜻이고, `unreproduced`는 과거 문서의 주장을 이번 실행에서 다시 입증하지 못했다는 뜻이다.
- confidence는 주장 자체의 신뢰도다. 제품이 그 기준을 충족한다는 confidence가 아니다.
- 권위 A는 1차 표준·공식 문서·원저 연구, B는 유지되는 공개 프로젝트의 공식 문서다.

| Claim ID | 주장 | 다섯 각도 | 권위 있는 근거 | 반증·한계 | confidence | 현재 HEAD 상태 | WBS 수용 기준 |
|---|---|---|---|---|---:|---|---|
| R-01 | 백테스트는 배포·추천의 증명이 아니다. point-in-time 데이터, OOS 경계, 비용·체결 가정, 후보 수가 없으면 성과 수치의 해석을 보류해야 한다. | 편향·OOS | [CFA Backtesting & Simulation](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation), [QuantConnect reconciliation](https://www.quantconnect.com/docs/v2/writing-algorithms/live-trading/reconciliation) | 어느 한 도구도 모든 시장 충격을 모델링하지 못한다. 기준을 충족해도 미래 수익을 보장하지 않는다. | 0.96 | `unreproduced`: 과거 문서의 지적은 존재하나 현 HEAD에서 각 항목을 다시 실행해 판정해야 한다. | QV-PTI-01, QV-OOS-01, QV-EXE-01 |
| R-02 | look-ahead 검사는 별도 실행·결과 파일로 남기고, 미발화 신호의 false negative 한계를 같이 공개해야 한다. | 편향·OOS | [Freqtrade lookahead analysis](https://docs.freqtrade.io/en/stable/lookahead-analysis/) | 이 방식도 발화하지 않은 신호를 검증하지 못한다. 따라서 `무편향` 단정이 아니라 커버한 범위를 기록해야 한다. | 0.94 | `unreproduced`: 현재 프로젝트에 동등한 검사와 결과물 존재 여부를 별도 확인해야 한다. | QV-PTI-02 |
| R-03 | 지표에는 공식뿐 아니라 입력·기간·as-of·변환 실행·결측 정책이 있어야 사용자가 수치를 재현·해석할 수 있다. | 지표·계보 | [BCBS 239](https://www.bis.org/publ/bcbs239.htm), [W3C PROV](https://www.w3.org/TR/prov-overview/) | 계보 메타데이터만으로 데이터 자체의 경제적 타당성은 증명하지 못한다. | 0.95 | `active`: `quant_explanations.py`의 profit factor 설명과 `nodes/backtest.py` 구현이 같은 계약으로 강제되지 않는 경로가 감사에서 확인됐다. | MR-REG-01, MR-PF-01 |
| R-04 | 테스트 fixture와 mock은 필요하지만 운영 오류에서 정상 분석으로 보이면 안 된다. 운영 프로필은 필요한 provider·데이터·내구성 저장소가 없을 때 분석 불가로 끝나야 한다. | 오류·fail-closed | [NIST AI RMF 1.0](https://doi.org/10.6028/NIST.AI.100-1), [NIST AI RMF MEASURE](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/) | 개발·데모 모드까지 막을 필요는 없다. 모드·배지·추천 차단을 분리해 검증하면 된다. | 0.94 | `active`: no-DSN fixture, default mock, L4 기본 증적 생성이 `ready`/양수 수익률처럼 흐를 수 있는 경로가 감사와 표적 테스트에서 확인됐다. | FT-RLS-01, FT-L4-01, FT-MOCK-01 |
| R-05 | 사용자가 수용할 금융 UX는 예쁜 화면이 아니라 위험·신선도·오류 범주·다음 행동을 이해하고 복구할 수 있는 상태다. | 금융·인증 UX | [FCA Consumer Understanding](https://www.fca.org.uk/publications/good-and-poor-practice/consumer-understanding-good-practice-areas-improvement), [NIST SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html) | 인증 후 플로우는 유효한 테스트 계정·세션 없이 검증할 수 없다. 이번 공개 QA에서는 명시적으로 미검증이다. | 0.93 | `active`: 공개 환경에서 로그인 벽 CTA, 공개 dev 이메일 화면, dev asset/HMR, 내부 404 문구, mock 수치의 사실형 표시가 확인됐다. | UX-PUB-01…06, UX-AUTH-01 |
| R-06 | 실험·백테스트의 설정·데이터·결과물은 재실행 가능한 기록으로 남아야 한다. | 증적·일정 | [Qlib workflow](https://qlib.readthedocs.io/en/latest/component/workflow.html), [Qlib data layer](https://qlib.readthedocs.io/en/latest/component/data.html) | Qlib의 기능 존재는 QuantAgent의 구현 품질을 보증하지 않는다. 비교는 기능 흉내가 아니라 재현성 기준선으로만 쓴다. | 0.91 | `active`: job store가 memory fallback을 허용하며, 브라우저 E2E가 패키지 표준 검사에 포함되지 않는다. | JB-DUR-01, EV-E2E-01 |
| R-07 | 일정은 완료율이 아니라 증적을 갖춘 원자 작업과 의존성·위험·용량으로 운영해야 한다. | 증적·일정 | [GAO Schedule Assessment Guide](https://www.gao.gov/products/gao-16-89g) | 문서화 자체는 실행을 보장하지 않는다. 같은 revision의 테스트 결과와 승인 연결이 필요하다. | 0.91 | `active`: 기존 보드는 진행 상태가 있었지만 주장 원장·상태 전이·증적 경로가 아직 완결되지 않았다. | PM-BOARD-01, PM-CAP-01 |

## 출처 등록부

`발행일 미표기`는 빈 칸이 아니다. 공식 페이지에 날짜가 보이지 않았다는 사실과 접근일을 함께 남긴다. 이 경우 재조사 때 문서 version·release를 다시 고정한다.

| Claim ID | 출처 | 발행일 또는 문서 버전 | 접근일 | 권위 등급 |
|---|---|---|---|---|
| R-01 | CFA Backtesting & Simulation | 2026 refresher reading | 2026-08-13 | A, 전문 협회 교육 자료 |
| R-01 | QuantConnect reconciliation | Docs v2, 발행일 미표기 | 2026-08-13 | B, 공식 운영 문서 |
| R-02 | Freqtrade lookahead analysis | stable docs, 발행일 미표기 | 2026-08-13 | B, 공식 프로젝트 문서 |
| R-03 | BCBS 239 | 2013-01 | 2026-08-13 | A, 국제 감독 표준 |
| R-03 | W3C PROV overview | 2013-04-30 | 2026-08-13 | A, W3C 권고안 |
| R-04 | NIST AI RMF 1.0 | 2023-01-26 | 2026-08-13 | A, NIST 표준 자료 |
| R-04 | NIST AI RMF MEASURE | 웹 가이드, 발행일 미표기 | 2026-08-13 | A, NIST 공식 가이드 |
| R-05 | FCA Consumer Understanding good practice | 공식 페이지 발행일 미표기 | 2026-08-13 | A, 금융 규제기관 가이드 |
| R-05 | NIST SP 800-63B | SP 800-63-4 초안/온라인판, 날짜는 재확인 필요 | 2026-08-13 | A, NIST 공식 가이드 |
| R-06 | Qlib workflow/data layer | docs `0.9.8.dev11` | 2026-08-13 | B, 공식 프로젝트 문서 |
| R-07 | GAO Schedule Assessment Guide | GAO-16-89G, 2015-12 | 2026-08-13 | A, 정부 감사 가이드 |

## 로컬 감사 근거

| Local ID | 현재 코드·테스트 관찰 | 의미 | WBS 연결 |
|---|---|---|---|
| L-01 | `ai/ai_graph/data_sources/db.py:1290-1315`는 DSN이 없으면 fixture bundle을 만들고, `nodes/backtest.py:2869-2872`는 price rows가 없으면 기본 가격 행으로 바꾼다. `ai/tests/test_api.py:267-324`는 mock·memory·DSN 미설정에서 ready·양수 total return을 기대한다. | 개발 fixture가 운영 성공처럼 노출될 수 있다. | FT-RLS-01 |
| L-02 | `ai/ai_graph/nodes/signal.py:170-234`는 L4가 `None`일 때 freshness 0의 기본 증적을 만든다. | 증적 부재가 증적 존재처럼 보일 수 있다. | FT-L4-01 |
| L-03 | `ai/ai_graph/llm/factory.py:55-66`의 기본 provider는 mock이고, `api.py:352-397`에는 production 시작 차단이 없다. | 배포 profile의 명시적 fail-closed gate가 필요하다. | FT-MOCK-01 |
| L-04 | `ai/ai_graph/quant_explanations.py:75-82`와 `ai/ai_graph/nodes/backtest.py:2766-2776`의 profit factor 의미가 다르다. | 설명·엔진·JSON·카드 계약 테스트가 필요하다. | MR-PF-01 |
| L-05 | `ai/ai_graph/jobs.py:423-485`는 persistence가 없을 때 memory fallback을 쓴다. | 재시작 뒤 작업 추적·복구 계약이 필요하다. | JB-DUR-01 |

## 조사 한계와 재조사 규칙

이번 조사는 공식 문서·원저·공개 프로젝트 문서를 우선했지만, 외부 LLM 좌석 세 개를 이용한 완전 독립 병렬 투표는 하지 못했다. 따라서 이 원장은 계획의 근거이지 출시 승인 증거가 아니다. 코드가 바뀌거나 comparator의 버전·문서가 바뀌면, 해당 Claim의 출처 날짜·반증·current HEAD 상태를 다시 채운 뒤 WBS 상태를 갱신한다.
