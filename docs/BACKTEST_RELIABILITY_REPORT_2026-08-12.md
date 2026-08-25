# 백테스트 신뢰성 보강 보고서

> 상태: 로컬 구현·회귀 검증 완료, 운영 PostgreSQL live 검증 대기. 이 문서는 교육·연구 목적의 백테스트 검증 기록이며 실제 투자수익을 보장하지 않는다.

## 1) 인터뷰에서 확정된 가정

- 시장/대상: KRX(KOSPI+KOSDAQ) 보통주, 일봉, 롱온리.
- 평가기간: 운영 PostgreSQL의 최근 5 calendar years, KST/KRX 거래세션 기준.
- 정상 판정: 수익률 수준이 아니라 비용 후 지표의 유한성, 동일 snapshot/manifest 재현성, 벤치마크 정의 정합성으로 판정한다.
- 초기자본: 100,000,000 KRW.
- 자금관리: 각 전략이 deterministic sizing 계약을 명시한다. 공통 종목 수 상한은 두지 않되 무레버리지, gross exposure 100% 이하, 현금 음수 금지, 정수주를 강제한다.
- 주문: 일별 종가 신호 후 다음 시장 세션 시가 근사. 주문은 해당 다음 세션에서 만료한다.
- 유동성: 신호 시점에 알려진 종목별 전일 raw 거래대금의 1% 이내. 거래정지·가격제한 capability 위반·0 거래량/거래대금·raw capacity 부재는 미체결 처리한다.
- 현금수익률: 0%.
- 벤치마크: 공식 KOSPI/KOSDAQ 총수익지수의 월별 fixed-unit composite가 primary이며, 기존 동일가중 프록시는 auxiliary다. 공식 입력이 없으면 primary 비교를 unavailable/limited로 표시한다.
- 재현성: 동일 snapshot/manifest 두 번 실행에서 주문·체결 exact hash, 파생 지표는 사전 정의 허용오차 이내 일치.
- 전달: 모든 구현·live/clean 검증·CI가 통과한 동일 head SHA로 PR을 생성한다.

## 2) 발견한 문제와 근본 원인

| 영역 | 발견 문제 | 영향 | 처리 |
|---|---|---|---|
| 주문 시점 | 주문이 종목 bar가 다시 나타날 때까지 무기한 대기 | 거래정지/결측 뒤 미래 시가로 낙관 체결 | 다음 시장 세션 1회 만료 및 reason audit |
| 유동성 | 거래량 참여율·부분체결·raw capacity provenance 부재 | 저유동 종목 수익 과대평가 | 전일 raw 거래대금 1%, 정수주 부분/0체결 |
| 원장 | 비용·turnover·requested/filled 수량 보존 부족 | 비용 전후 성과와 체결 가능성 해석 불가 | order audit 및 summary reconciliation 추가 |
| 포지션 | 공통 default 10종목 fallback | 전략 sizing 의도 왜곡 | canonical 경로에서 explicit sizing fail-closed |
| 자본 | AI canonical 경로가 100만원 사용 | 사용자 계약 대비 주문량·비용·MDD 100배 차이 | analysis-job 엔진 호출만 1억원 sealed contract 주입; legacy backend 상수 불변 |
| 유니버스 | 현재 시가총액 상위 KOSPI200 프록시를 과거에 사용 | look-ahead/survivorship bias | lifecycle 기반 PIT-listed KOSPI/KOSDAQ 보통주 view |
| 기간 | 10년 기본과 RSI 자동확장 | 확정한 최근 5년 계약 위반 | 5년 KST session window 고정, 자동확장 제거 |
| 가격 | adjusted OHLCV를 체결·수량·capacity에도 사용 | corporate action·현금·세금 의미 왜곡 | raw/adjusted 필드 및 capability metadata 분리 |
| 공시 | date-only DART를 같은 날 EOD 신호에 사용 가능 | 장 마감 후 공시 look-ahead | 다음 관측 KRX session부터 유효 |
| 검증 | 70/30을 walk-forward처럼 해석 가능 | 과적합/표본 부족 은폐 | holdout으로 명시, 24 folds/24 months/480 sessions 미달 시 OOS 숨김 |
| 벤치마크 | 동일가중 프록시를 primary처럼 노출 | 비교 기준 불일치 | official TR primary unavailable reason + auxiliary 라벨 |
| 로컬/운영 | fixture와 운영 결과 구분 부족 | mock 성공을 실데이터 성공으로 오해 | fixture `production_eligible=false`; configured DB 실패는 fallback 금지 |

## 3) 변경한 파일과 변경 이유

- `backtest_module/backtest_module/models.py`: 체결 용량, 무제한 종목 모드, sizing 검증 계약.
- `backtest_module/backtest_module/backtest.py`: 다음 세션 만료, 전일 raw 거래대금 capacity, 부분/미체결, 원장·비용·turnover.
- `backtest_module/tests/test_backtest.py`: 손계산 원장·만료·capacity·11종목 이상·미지원 sizing 회귀.
- `backtest_module/pyproject.toml`: 깨끗한 editable install이 생성 출력 디렉터리를 패키지로 오인하지 않도록 package discovery 고정.
- `ai/ai_graph/data_sources/db.py`: 최근 5년 KST window, PIT universe, raw/adjusted 분리, DART 다음 세션, fixture/production 명시.
- `DE/migrations/007_common_stock_mart_views.sql`: `core.symbol_listing_history` 유효구간 기반 PIT 보통주 view.
- `ai/ai_graph/nodes/backtest.py`: canonical 1억원, sizing provenance, 표본 충분성, primary/auxiliary benchmark 계약.
- `ai/ai_graph/nodes/position_sizing.py`: canonical strict sizing resolver.
- `ai/ai_graph/jobs.py`, `ai/ai_graph/job_repository_postgres.py`, `service_db/migrations/021_ai_analysis_jobs.sql`: persistent mode fail-closed, public 응답과 분리된 versioned execution manifest/ledger 영속화.
- `ai/ai_graph/quant_performance.py`: walk-forward/공식 benchmark 비가용 사유를 public metric의 NULL+reason으로 전파.
- 관련 AI·엔진 테스트: 데이터·자본·원장·persistent store·벤치마크·재현 회귀.

## 4) 수정 전후 결과 비교 표

운영 DB가 제공되지 않아 실전략의 전후 성과 수치는 아직 확정하지 않았다. 아래 숫자는 원장 공식 검증용 4-session 단일종목 fixture이며 투자 성과로 해석하면 안 된다.

| 지표 | 비용 전 | 비용 후(commission 1.5bp, tax 23bp, slippage 편도 10bp) |
|---|---:|---:|
| 초기자본 | 100,000,000 | 100,000,000 |
| 최종자산 | 109,090,900 | 108,589,913.12 |
| 총수익률 | 9.0909% | 8.5899% |
| MDD | -0.8696% | -0.8696% |
| Sharpe | 14.1079 | 13.9701 |
| Sortino | 94.2169 | 89.1260 |
| 변동성(연율) | 53.2241% | 50.8449% |
| 승률 | 100% | 100% |
| 완료 거래 | 1 | 1 |
| 총비용 | 0 | 281,696.30 |
| turnover(금액) | 209,090,700 | 208,841,499.54 |

CAGR는 4-session fixture에서 연율화되어 비정상적으로 크므로 보고하지 않는다. 실데이터 5년 결과가 확보되기 전에는 성과 판단에 사용하지 않는다.

## 5) 검증 결과와 남은 한계

### 통과

- 변경 집중 회귀(깨끗한 venv): `122 passed, 4 skipped`.
- `backtest_module` 전체: `37 passed`.
- AI 전체: `464 passed, 10 skipped`(기존 deprecation warning 2건).
- DE migration: `9 passed`.
- Service DB: `14 passed`.
- Backend 관련: `35 passed`.
- 변경 파일 Ruff: 통과.
- `git diff --check`: 통과.
- 동일 fixture 2회 실행 summary 동일.

### 환경 한계

- Windows에서 backend runtime 전체 중 POSIX `pass_fds` 기반 sandbox 테스트 3건은 플랫폼 제약으로 실패했다. 관련 backend flow/repository/subprocess 35건은 통과했다.
- DE 전체 suite는 로컬에 `pandas_ta_classic`/`pandas_ta`가 없어 수집 단계에서 중단되었고, 직접 영향 migration suite는 통과했다.
- WSL Ubuntu는 존재하지만 Python 3.14의 `ensurepip`/`python3.14-venv`가 설치되지 않아 깨끗한 Linux venv를 만들 수 없었다. Windows 임시 clean venv는 통과했으며 Linux/Rocky 검증은 여전히 필수다.

### 완료를 막는 필수 증거

현재 환경에 `AI_DATABASE_DSN`, `QUANT_DB_DSN`, `DATABASE_URL`이 모두 없다. 따라서 다음은 아직 검증하지 못했다.

- 운영 PostgreSQL 최근 5년 session coverage와 immutable snapshot hash.
- listing history의 상폐·재상장 표본 및 PIT universe future-append 불변성 live 확인.
- raw OHLCV/거래대금 coverage, corporate action, 정지·상하한 capability.
- 공식 KOSPI/KOSDAQ TR series와 lagged monthly weights.
- 실전략별 총수익률, CAGR, Sharpe/Sortino, MDD, 변동성, 승률, 거래 수, 평균 보유기간, 비용 전후, benchmark, walk-forward, 비용 민감도.

이 증거 없이 fixture 수치를 정상 운영 성과로 승격하거나 PR을 생성하지 않는다.

## 6) 재현 방법

```bash
# 엔진 전체
cd backtest_module
python -m pytest tests -q

# AI 전체
cd ../ai
python -m pytest tests -q

# 직접 영향 집중 회귀(저장소 루트)
python -m pytest backtest_module/tests/test_backtest.py \
  ai/tests/test_db_data_source.py \
  ai/tests/test_backtest_optimization.py \
  ai/tests/test_ai_graph_backtest_module_integration.py -q

# migration 계약
cd DE
python -m pytest tests/test_sql_migration.py -q
```

운영 검증에는 read-only PostgreSQL DSN을 `AI_DATABASE_DSN`으로 주입해야 한다. 비밀값은 로그·manifest·PR에 기록하지 않는다. 운영 run은 fixture metadata가 아니라 `source=postgres`, 5년 exact start/end/session count, query/policy/snapshot hash, raw capability coverage를 증명해야 한다.

## 7) 후속 개선 제안

### 필수 수정/검증

1. read-only 운영 DSN으로 migration/view/coverage audit를 수행한다.
2. 같은 cutoff/query rowset을 immutable snapshot으로 봉인하고 두 번 재실행한다.
3. 공식 세금·소매 수수료의 적용 시장/계좌/매체/tier/effective date 원문을 확정한다.
4. 공식 KOSPI/KOSDAQ TR series·월별 lagged weights를 공급하고 fixed-unit composite oracle를 검증한다.
5. 실전략 회귀 표본을 비용·slippage·capacity 민감도와 함께 실행한다.
6. Linux/Rocky 환경에서 전체 회귀와 동일 hash/tolerance를 검증한다.
7. 모든 gate와 CI 통과 후 검증 SHA로 PR을 생성하고 URL/번호/base/head/CI evidence를 이 문서에 추가한다.

### 선택적 전략 개선

- correctness 버전과 최종 OOS lockbox를 동결한 뒤 별도 experiment id에서만 진입·청산·리밸런싱 가설을 시험한다.
- 후보 수·시도 수·parameter family를 공개하고 Deflated Sharpe/PBO 등 다중시도 보정을 적용한다.
- 성과가 개선되지 않으면 기존 전략을 유지한다. 거래비용 제거, 검증기간 선택, 불리한 종목 제거로 숫자를 꾸미지 않는다.

## 근거 자료

- KRX 주문유형: https://regulation.krx.co.kr/contents/RGL/03/03010100/RGL03010100T2.jsp
- KRX 단일가매매 체결: https://regulation.krx.co.kr/contents/RGL/03/03010201/RGL03010201.jsp
- KRX 가격제한폭: https://regulation.krx.co.kr/contents/RGL/03/03010100/RGL03010100T5.jsp
- KRX 개별종목 거래정지/재개: https://regulation.krx.co.kr/contents/RGL/03/03010403/RGL03010403.jsp
- Bailey et al., *The Probability of Backtest Overfitting*: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- Bailey & López de Prado, *The Deflated Sharpe Ratio*: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551
