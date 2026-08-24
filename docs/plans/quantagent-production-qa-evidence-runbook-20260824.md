# 2026-08-24 QA 증적 실행표 (로컬 격리 검증)

## 목적과 경계

이 실행표는 `QA-DATA-AUDIT-01~04`, `UX-AUTH-03~05`, `MR-API-01`의
**로컬에서 재현 가능한 최소 검증 명령**을 고정한다. 이전의
`cd DE && pytest -q tests -k '…'` 방식은 관련 없는 ETL 테스트를 함께
수집하면서 선택 의존성 `pandas_ta_classic` 또는 `pandas_ta` import에서 중단됐다.

여기서 지정한 명령은 그 선택 의존성을 import하지 않는 정확한 계약 테스트만 실행한다.
운영 DB·운영 API·사용자 인증 세션·실거래 데이터에는 접근하지 않았고, fixture나
로컬 합성 입력은 완료 근거가 아니다. 이 문서는 `완료` 전환이나 독립 승인 기록을
대체하지 않는다.

## 실행 환경

- 실행일: 2026-08-24 KST
- 비밀·운영 연결 제거: `AI_DATABASE_DSN`, `QUANT_DB_DSN`, `DATABASE_URL`,
  `AI_AOAI_API_KEY`, `AOAI_API_KEY` unset
- Python: `./ai/.venv/bin/python`
- 실행 결과: AI 계약 테스트 30 passed (0.37s), DE SQL/ingestion 계약 테스트
  5 passed (0.02s), FE source/typing/build 40 passed

## 데이터 감사: 수집 실패를 피하는 정확한 명령

```sh
env -u AI_DATABASE_DSN -u QUANT_DB_DSN -u DATABASE_URL \
  -u AI_AOAI_API_KEY -u AOAI_API_KEY \
  ./ai/.venv/bin/python -m pytest -q \
  ai/tests/test_source_manifest.py \
  ai/tests/test_db_split_source_manifest.py \
  ai/tests/test_research_eligibility.py \
  ai/tests/test_graph_risk_report.py::test_public_performance_reliability_marks_fixture_4row_single_ticker_as_insufficient \
  ai/tests/contracts/test_metric_api_serialization_contract.py

cd DE && env -u AI_DATABASE_DSN -u QUANT_DB_DSN -u DATABASE_URL \
  ../ai/.venv/bin/python -m pytest -q \
  tests/test_sql_migration.py::SqlMigrationTests::test_point_in_time_universe_migration_uses_listing_history_not_current_status \
  tests/test_security_type_history.py
```

| WBS ID | 로컬에서 검증한 계약 | 통과한 범위 | 완료 전 남는 실증 |
|---|---|---|---|
| QA-DATA-AUDIT-01 | source, as-of, freshness, extract/snapshot/lineage hash의 필수 필드와 canonical hash 재계산 | 합성 `postgres` manifest의 구조·hash 일치 및 서로 다른 extract 거부 | 실제 PostgreSQL 추출본의 immutable URI, source/as-of/freshness/lineage와 표본 hash 재계산, 독립 reviewer |
| QA-DATA-AUDIT-02 | stale manifest와 누락 세션이 release eligibility를 실패시키고 `freshness_not_current`가 결정 사유가 됨 | stale·fixture가 release 불가이며 fixture performance는 수치 없이 insufficient 상태 | 실제 API/리포트 response의 stale/as-of/reason, recommendation 비활성화 trace, 독립 reviewer |
| QA-DATA-AUDIT-03 | PIT universe view가 현재 master 상태가 아닌 listing/security-type history interval을 사용 | SQL과 ingestion 계약에서 as-of interval, delisting/security-type history 경로 확인 | 같은 운영 입력 두 번의 universe/delisting output hash, PostgreSQL read-only 표본, 독립 reviewer |
| QA-DATA-AUDIT-04 | fixture·stale source가 release profile을 통과하지 못하고 public performance가 수치를 꾸며내지 않음 | fixture release 거부와 insufficient metric null 처리 | release-profile server run에서 fallback 0, dev badge/추천 차단 response, 독립 reviewer |

`pandas_ta*`는 이 네 WBS의 source-manifest·PIT·release-admission 수용기준과
무관한 technical-indicator ETL 의존성이다. 해당 모듈이 필요한 지표 ETL 전체 회귀는
별도 환경에서 실행해야 하며, 이 명령의 PASS로 대체하지 않는다.

## MR-API-01: metric serialization 계약

동일 Python 명령의
`ai/tests/contracts/test_metric_api_serialization_contract.py`는 public metric마다
API JSON의 `key`, `label`, `unit`, 설명, source reference, value/null,
`is_available`, `unavailable_reason`가 registry 기반 설명과 일치하는지를 검사한다.
이 검증은 field-by-field projection regression을 막지만 local synthetic backtest를 쓴다.

종료에 필요한 증거는 실제 release SHA의 API response, registry version·implementation
hash가 담긴 immutable bundle, 그리고 독립 reviewer 기록이다. 로컬 test output만으로는
API 배포본 또는 실데이터 계산을 증명하지 않는다.

## UX-AUTH-03~05: 세션 증거를 대체하지 않는 preflight

```sh
cd fe && npm test
```

이 명령은 40개의 source contract, TypeScript typecheck, production build를 실행했다.
그중 인증 경계 검사는 protected route의 heading/main/return target/safe escape,
callback의 one-time exchange, 사용자 전환·sign-out 시 scoped storage 제거를 확인한다.

그러나 다음 WBS 수용기준은 사람이 제공한 테스트 세션과 trace 없이는 실행할 수 없다.

| WBS ID | 필요한 실제 증거 | 로컬 preflight가 증명하지 않는 것 |
|---|---|---|
| UX-AUTH-03 | 승인된 test-account provenance, login→refresh→logout Playwright trace, redacted network log, screenshot, reviewer | 실제 OAuth callback, refresh, logout, 다른 사용자 데이터 비노출 |
| UX-AUTH-04 | 의도적으로 만료시킨 test session의 trace, protected data가 없는 DOM/screenshot, relogin→return evidence | 실제 expiry 원인/status와 server-side data non-disclosure |
| UX-AUTH-05 | 격리 환경에서 재현한 exact rate-limit status/code, wait/retry copy가 보이는 trace, redacted network log | 운영 rate limit의 실제 동작 또는 retry 후 권한/데이터 경계 |

세션 token, cookie, Authorization header, 사용자 개인정보를 이 저장소·WBS·댓글에
기록하지 않는다. 증거에는 trace 식별자, SHA, 실행 시각, redaction 방식과 reviewer만
남긴다.

## 상태 해석

모든 행은 이 문서와 로컬 PASS만으로 `완료`가 아니다. 데이터 감사와 MR-API-01은
**증적대기 후보**에 필요한 deterministic command가 준비된 상태이고, UX-AUTH-03~05는
실제 세션/trace가 제공될 때까지 `대기`가 맞다.
