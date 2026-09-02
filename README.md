# Quant_agent

## 커밋 메세지 양식

```
[TYPE] 간결한 제목
ex. [DOCS] README 커밋 컨벤션 추가
```
GitHub Issues는 CI 실패 자동화에 사용하므로 커밋 메시지에는 이슈 번호를 강제하지 않습니다.

| TYPE         |                               | 
| ------------ | ------------------------------------ | 
| **FEAT**     | 새로운 기능 추가                            | 
| **FIX**      | 버그 수정                                |
| **DOCS**     | 문서 수정(README, 가이드, 주석 등)             |  
| **STYLE**    | 코드 포맷/세미콜론/공백 등, 로직 변경 없음        |
| **REFACTOR** | 리팩터링(동작 동일, 구조 개선/성능 향상)             | 
| **TEST**     | 테스트 코드 추가/수정                         | 
| **CHORE**    | 빌드/배포/의존성/스크립트 등 개발환경(패키지 매니저 포함) 변경 |

---
## CI 실패 자동 이슈 봇

`.github/workflows/ci-issue-bot.yml`은 `Code checks`, 배포, 서버 헬스체크 워크플로가 실패하거나 시간 초과하면 GitHub Issue를 자동 생성한다.

- 실패 작업과 실패 단계, 브랜치, 커밋, 실행 로그 링크를 이슈에 기록한다.
- 같은 워크플로 작업의 미해결 이슈가 있으면 새 이슈 대신 최신 실패를 댓글로 남긴다.
- `automated` 라벨이 없을 경우 자동 생성한다.
- 봇이 동작하려면 저장소의 Actions가 기본 `GITHUB_TOKEN`에 Issues 쓰기 권한을 허용해야 한다.

CI 실패 자체가 아닌 취소(`cancelled`) 실행은 이슈로 만들지 않는다.

---

## 목적(현재 이 README scope)
`README`는 **Rocky Linux 8.10 Native Bash MVP spine** 실행 재현성과 안전 계약을 최상위 단에서 정리한다.
AI/FE 상세 절차는 각각 `ai/README_AI.md`, `fe/README.md`에 두고, 여기는 핵심 순서와 검증 명령만 둔다.

## 정확한 선행 조건
- Rocky Linux 8.10 x86_64
- Bash(권장 4.4+), Python 3.11.13, Node 24.15.0, npm 11.12.1
  (`/etc/rocky-release` 및 `--version`으로 고정값 확인)
- Docker/Compose 미사용
- 로컬 결정론 점검은 외부 DB/Redis/OAuth/LLM credential 없이 실행
- 실제 데이터 배포는 PostgreSQL DSN과 AOAI Responses 설정 필수
- 저장소 바깥 작업공간 사용(안전성 상의 이유)

## MVP Spine
`fe`(직접 Vite) → loopback `/ai-api` 프록시 → `ai/ai_graph/api.py` → `backtest_module` → 공개 `AnalysisJob/APIEnvelope` → 동일 브라우저 세션 FE 표시

## 실행 전제: parent/child topology
- AI와 FE는 같은 쉘에서 섞어 실행하지 않는다.
- 실행은 parent Bash가 수행하고 child가 AI/FE 런타임을 독점으로 띄운다.
- child는 canonical `FE_ROOT`와 `env -i`, bounded curl, 시간축/identity 검증을 통과해야 한다.
- loopback 포트 점검/종료 후 listener 정리는 `ss`와 bounded `curl`만으로 수행한다.

## 로컬 결정론 프로필: 저장소 외부 venv + fixture env
- venv는 반드시 저장소 경로 밖 생성
- 로컬 AI는 아래 결정론 fixture로 시작하고 FE는 그 `/analysis-jobs` 응답을 그대로 사용
  - `AUTH_ENABLED=0`
  - `AI_LLM_PROVIDER=mock`
  - `AI_JOB_STORE=memory`
  - `AI_AUDIT_SINK=noop`
  - data-source 계열 env는 제거 (`AI_DATABASE_DSN`, `QUANT_DB_DSN`, `DATABASE_URL`, `AI_DEFAULT_TICKER`, `AI_BACKTEST_LOOKBACK_DAYS`, `AI_L4_EVIDENCE_LIMIT`, `AI_DB_CONNECT_TIMEOUT_SECONDS`, `AI_DB_STATEMENT_TIMEOUT_MS`, `AI_SECTOR_CACHE_TTL_SECONDS`, `BE_JOB_STORE_MODE`, `REDIS_URL`, `AUTH_SESSION_COOKIE_NAME`, `AI_CORS_ALLOW_ORIGINS`)

## 테스트 실행: 가상환경 기준

테스트는 **항상 가상환경 안에서** 실행한다. 시스템 인터프리터로 돌린 결과는 근거로 인정하지
않는다. 전역 site-packages는 프로젝트가 고정한 버전과 어긋나기 마련이고, 실제로 그 드리프트가
`quantstats` 경로에서 pandas/pyarrow 조합 segfault로 나타나 테스트 실패가 아니라 프로세스
사망으로 끝난 적이 있다. 실패를 읽을 수 없는 실행은 실행하지 않은 것과 같다.

venv는 [로컬 결정론 프로필](#로컬-결정론-프로필-저장소-외부-venv--fixture-env) 규약대로
**저장소 경로 밖**에 만든다.

```bash
python3 -m venv ~/.venvs/quantagent
~/.venvs/quantagent/bin/python -m pip install -e ./backtest_module -e ./ai -e "./backend[test]" pytest ruff
```

설치 목록은 CI(`.github/workflows/code-check.yml`)와 같게 유지한다. 여기에 없는 패키지를
넣으면 로컬만 통과하거나 로컬만 깨지는 상태가 된다.

```bash
AUTH_ENABLED=0 AI_LLM_PROVIDER=mock AI_JOB_STORE=memory AI_AUDIT_SINK=noop ~/.venvs/quantagent/bin/python -m pytest -q ai/tests
```

위 네 env는 `ai/tests` 전용이다. `backend/tests`에 같이 넘기면 프로덕션 보안 설정을 검증하는
테스트가 완화된 값을 읽고 실패하므로, 백엔드 테스트는 env 없이 돌린다.

### SQL 마이그레이션 테스트

`service_db/tests/test_sql_migration.py`의 대부분은 마이그레이션 파일을 읽는 정적 검사지만,
`023_archive_undecodable_analysis_jobs.sql`은 실제 PostgreSQL에 적용해야만 검증된다. SQL의
3값 논리(`jsonb_typeof`는 없는 키에 NULL을 돌려주고, CHECK와 `NOT`은 둘 다 NULL을 통과시킨다)는
문자열 단언으로 볼 수 없기 때문이다. DSN이 없으면 해당 테스트는 조용히 skip되므로, 이 파일을
건드렸다면 DSN을 주고 돌린다.

```bash
SERVICE_DB_ARCHIVE_TEST_DSN=postgresql://postgres:postgres@127.0.0.1:5432/postgres ~/.venvs/quantagent/bin/python -m unittest service_db/tests/test_sql_migration.py
```

테스트는 지정한 서버에 자기 전용 데이터베이스를 만들고 끝나면 지운다. 관리용 DSN을 준다.

### 로컬에서 끝나지 않는 것

이 애플리케이션은 배포 서버에서 실행된다. 로컬에서 띄워 눌러보는 것은 실사용 검증이 아니다.
런타임 동작의 근거는 서버(배포 로그, server-health 워크플로, 서버에서 수행한 실행)에서 가져온다.
로컬 가상환경이 답할 수 있는 것은 단위·계약·lint·컴파일까지다.

## 운영 실데이터 프로필

- `AI_LLM_PROVIDER=aoai`
- `AI_AOAI_RESPONSES_URL`, `AI_AOAI_API_KEY`, `AI_AOAI_MODEL`
- `AI_DATABASE_DSN`, `QUANT_DB_DSN`, `DATABASE_URL` 중 하나
- `AUTH_ENABLED=1`, `REDIS_URL`, `VITE_AUTH_API_BASE_URL`

운영 프로필에서는 구성된 PostgreSQL 또는 AOAI 호출이 실패해도 fixture 결과로 바꾸지 않는다. `/analysis-jobs`는 실패 진단을 포함한 실패 job을 반환하며, 배포 워크플로는 인증·DB·AOAI 설정과 실제 분석 smoke test가 모두 유효한 경우에만 성공한다.

## 분석 동시성 상한

분석 한 건은 값싼 요청이 아니다. 수년치 가격 행을 올리고, 후보를 프로세스 풀로 펼치고,
그 워킹셋을 그래프가 도는 내내 붙들고 있다. 동시에 몇 개까지 돌지에 상한이 없으면
사용자 N명이 동시에 시작한 순간 백테스트 N개가 같은 메모리·CPU를 두고 경쟁하고,
어느 지점을 넘으면 프로세스는 느려지는 게 아니라 죽는다 — 그때 돌던 잡이 전부 함께 죽는다.

| 환경변수 | 기본값 | 뜻 |
|---|---|---|
| `AI_ANALYSIS_MAX_CONCURRENCY` | `1` | 동시에 실행할 분석 수. 2 vCPU 단일 프로세스 노드에서 분석 한 건도 다년 PIT 행·백테스트 워커를 함께 사용하므로, 기본값은 하나의 job만 실행하고 나머지는 큐에 둔다. 부하·메모리·회복력 측정을 마친 뒤에만 명시적으로 높일 수 있다. |
| `AI_ANALYSIS_QUEUE_WAIT_SECONDS` | `1860` | 슬롯을 기다리는 한도. 분석 1건의 wall budget보다 길게 둬서, 한 건 뒤에 선 잡이 차례를 받게 한다 |
| `AI_BACKTEST_WORKERS` | `2` | 분석 **1건**이 후보 평가에 쓸 프로세스 풀 워커 수. 실제 워커 수는 `min(후보 수, 이 값, os.cpu_count())`이고, 후보×행 수가 250,000 미만이면 직렬(1)로 떨어진다. 분석 **여러 건**에 걸친 워커 합계에는 상한이 없다 |
| `AI_BACKTEST_CANDIDATE_TIMEOUT_SECONDS` | `8` | 워커 wave 하나가 후보 평가에 쓸 수 있는 시간. 1년 창(200종·약 250세션)에서 후보 1개는 측정상 2초 미만이므로 이 값은 작업 예산이 아니라 hang 감지선이다. `AI_BACKTEST_LOOKBACK_YEARS=3`처럼 창을 넓히면 올려야 한다 |
| `AI_BACKTEST_WALL_BUDGET_SECONDS` | `25` | 백테스트 노드가 self-improvement 라운드를 **더 시작할지** 판단하는 상한. 라운드 사이에서만 검사되므로 이미 시작한 라운드를 자르지는 않는다. walk-forward 표본이 READY면 라운드 자체가 0회라 이 값은 걸리지 않는다 |

상한을 넘은 잡은 **거절이 아니라 대기**한다. 클라이언트는 이미 큐잉된 잡을 폴링하고
있으므로 기다림이 새로 드는 비용이 아니고, 1분 뒤면 처리할 수 있는 일을 거절하는 편이
사용자에게 더 나쁘다. 대기 중인 잡은 `RUNNING`이 아니라 **`QUEUED`로 남는다** — 아무것도
돌고 있지 않은데 RUNNING이라고 말하는 것이 바쁜 서비스를 멈춘 것처럼 보이게 만든다.

대기에는 한도가 있다. 창 안에 슬롯을 못 받은 잡은 재시도를 안내하며 실패한다.
영원히 파킹된 스레드는 큐가 애초에 막으려던 그 고갈로 되돌아가는 길이다.

### 백테스트 데이터 범위

슬롯을 나누는 것만으로는 부족하다. 분석 **한 건**이 5년치 전체 PIT 유니버스(1,717종,
가격 320만 행, TA 4계열, DART 타임라인)를 올리면 그 한 건만으로 875초·21GB를 쓴다.
그래서 얼마나 읽을지 자체에 상한을 둔다. 두 값 모두 매니페스트에 기록되므로
좁게 읽은 실행도 재현 가능하다.

| 환경변수 | 기본값 | 뜻 |
|---|---|---|
| `AI_BACKTEST_LOOKBACK_YEARS` | `1` | 마지막 완료 KST 세션에서 거슬러 올라가는 백테스트 창의 길이(년). `1~3`으로 clamp 되며, 범위 밖 값은 배포를 죽이는 대신 잘린다. 창 길이는 정책 id(`krx_pit_common_stock_{N}y_kst_settled_session_v3`)에 그대로 실린다 |
| `AI_BACKTEST_UNIVERSE_MAX_TICKERS` | `200` | 백테스트가 적재할 PIT 보통주 상한. 창 **시작 직전** 60세션의 평균 거래대금(`adj_close × adj_volume`)으로 순위를 매겨 상위 N종만 남긴다. 창 시작 이전 정보만 쓰므로 look-ahead가 아니고, 창 안에서 상장폐지된 종목은 그대로 남는다(생존편향 방지) |

### 요청 전역 deadline

단계별 예산은 각자 지켜지지만 그 합에는 상한이 없었다. 백테스트 노드의 wall budget은
self-improvement 라운드 **사이**에서만 검사되고, 라운드 자체의 예산은
`timeout × wave_count` 라 후보 수에 비례해 늘어난다. 상류의 스크리닝 완화 라운드와
프로바이더 호출에는 합산 예산이 아예 없다. 그래서 한 건이 코드 어디에도 적히지 않은
시간만큼 돌 수 있었고, 슬롯이 유한한 지금은 그런 한 건이 슬롯을 그동안 붙들고 있다.

| 환경변수 | 기본값 | 뜻 |
|---|---|---|
| `AI_JOB_DEADLINE_SECONDS` | `1800` | 요청 하나의 총 상한. `0` 이면 상한 없음(단계별 예산만 적용) |

노드 경계와 self-improvement 라운드 경계에서 검사한다. 넘긴 잡은 재시도를 안내하며
`cancelled` / `job_deadline_exceeded` 로 실패한다. 기본값이 넉넉한 것은 의도다 —
정상 실행을 잘라내려는 값이 아니라 **돌아오지 않는 실행이 쥔 슬롯을 놓게 하려는** 값이다.

`/health`·`/readiness`는 async다. 동기 핸들러는 분석 백그라운드 작업이 쓰는 것과 같은
anyio 워커 풀에서 돌기 때문에, 분석이 몰리면 liveness가 타임아웃해 바깥에서는 서비스가
죽은 것으로 보인다.

## 수용 기준 게이트: dev report-only, release enforced

백테스트 수용 기준(미사용 구간 Sharpe·최대 낙폭·최소 거래 수·탐색 폭 보정 Sharpe,
그리고 automatic 전략의 공식 TR 벤치마크 비교)은 **기본값이 런타임 프로필에 따라 갈린다.**
dev 프로필은 **report-only** 로, 모든 전략이 결과를 들고 돌아오게 판정만 하고 막지 않는다.
release 프로필(`AI_RELEASE_PROFILE` 또는 `APP_ENV` 가 `release`/`production`)은 **enforced**
가 기본이라, 운영이 report-only 바닥을 조용히 배포하지 않는다. 어느 쪽 기본값이든
`AI_VALIDATION_GATES` 로 양방향 재정의할 수 있다.

| 조건 | 결과 기본값 |
|---|---|
| dev 프로필, `AI_VALIDATION_GATES` 미설정 | `report_only` |
| release 프로필(`APP_ENV=release`/`production` 등), 미설정 | `enforced` |
| `AI_VALIDATION_GATES=report_only` | 판정은 하되 `strategy_validated` 를 끄지 않음(재정의) |
| `AI_VALIDATION_GATES=enforced` | 기준 미달이면 실제로 검증 보류(재정의) |

**평가는 계속 돈다.** 판정 사유는 리포트의 `수용 기준 판정 (참고)` 섹션으로 나가고,
로그에도 남는다. "잠시 꺼둔다"며 삭제한 게이트는 나중에 기억으로 다시 써야 하고,
그때는 임계값이 원래 무슨 뜻이었는지 아무도 말할 수 없다. 그래서 끄는 대신 막지만
않게 했다 — 복원은 위 변수 하나다.

`검증됨` 라벨은 유지하고, 그 옆에 위 참고 판정을 병기한다. 그래서 report-only 동안에는
`검증됨`으로 표시된 전략이 같은 리포트에서 기준 미달로 적혀 있을 수 있고, 읽는 사람은
둘 다 볼 자격이 있다.

**이 스위치가 덮지 않는 것:** freshness 게이트(가격이 낡아서 추천 보류)와 L4 증거
게이트(증거가 없어서 추천 보류)는 데이터 품질 게이트라 그대로 둔다. 둘 다 전략이
좋은지에 대한 판단이 아니므로 이 스위치 뒤에 있을 이유가 없다.

## 운영 계약: 단일 프로세스

이 서비스는 **워커 1개로만** 동작한다. SSE 이벤트 버퍼, AOAI 동시성 게이트, 요청 단위
프로세스 풀, 그리고 재시작 시 진행 중 잡을 회수하는 판별이 전부 프로세스 로컬이다.
워커를 늘리면 각 워커가 자기 버퍼·자기 게이트·자기 잡 목록을 갖게 되므로,
클라이언트는 다른 워커가 낸 이벤트를 놓치고, 프로바이더에는 의도한 두 배의 동시 호출이
나가며, 재시작 회수기가 형제 워커가 실제로 돌리고 있는 잡을 실패로 바꾼다.

그래서 배포는 `--workers 1` 을 명시하고, 앱도 기동 시 이를 검사해 2 이상이면
`MultiProcessStartupError` 로 **거부한다**(`ai/ai_graph/single_process.py`).
`WEB_CONCURRENCY` 환경변수도 같은 대상이다.

검사는 프로세스 조사가 아니라 **설정 기반**이다. gunicorn 설정 파일이나 프로세스
매니저로 N개를 띄우는 방식은 탐지되지 않는다 — 그 경우에는 이 문서가 계약의 전부다.

부하가 이 한계를 넘으면 워커를 늘리는 것이 아니라 위 상태들을 먼저 외부화해야 한다.

## 이메일 발송 운영 계약

이메일 발송은 기본적으로 꺼져 있다(`EMAIL_DELIVERY_ENABLED=false`). 배포(`deploy.yml`)는
`EMAIL_DELIVERY_WORKER_ENABLED=true` 일 때만 이메일 워커를 시작/재시작하고, `false` 이거나
미설정이면 아무것도 하지 않는다. 값은 backend `Settings`(`.env` 또는 셸 env)로 읽고, 워커 `check` 실패는
배포를 롤백하지 않고 경고로만 남긴다(`/health`의 `email_*` 필드와 `.run/email-worker.log`로 확인). 두 값 모두 원격 서버의 배포 셸(SSH 로그인 셸)에서
보여야 하므로 `~/.bashrc` export 나 `~/mvp_sp1/quant-proj/.env` 에 있어야 한다 — 워크플로 자체는
이 값을 주입하지 않는다.

허용목록(allowlist) 테스트 발송에 필요한 최소 환경변수:

- `EMAIL_DELIVERY_ENABLED=true`
- `EMAIL_REPORT_COMPLETED_TRIGGER_ENABLED=true` (리포트 완료 트리거로 발송하려는 경우)
- `EMAIL_DELIVERY_WORKER_ENABLED=true` (배포 시 워커를 띄우려는 경우)
- `EMAIL_ROLLOUT_MODE=allowlist`
- `EMAIL_LOCAL_RECIPIENT_ALLOWLIST` (허용 수신자 목록, 비어있으면 안 됨)
- `EMAIL_PROVIDER=brevo`
- `BREVO_API_KEY`
- `BREVO_SENDER_EMAIL` (`@qt-agent.kro.kr` 도메인 필수)
- `BREVO_SENDER_NAME`
- `BREVO_SANDBOX_MODE` (필요시)
- `EMAIL_PUBLIC_BASE_URL` (https, non-local 호스트)
- `EMAIL_UNSUBSCRIBE_ENABLED=true` + `EMAIL_UNSUBSCRIBE_SIGNING_SECRET` + `EMAIL_UNSUBSCRIBE_BASE_URL`
- `DATABASE_URL` / `TRADING_DATA_DATABASE_URL` (동일 `qt_db`, non-loopback 호스트)
- `REDIS_URL` (logical DB 11)
- `EMAIL_MAX_ATTEMPTS` (기본 5)
- `EMAIL_RESEND_COOLDOWN_SECONDS` (기본 600) — `/api/v1/reports/{id}/resend`가 이미 발송/실패/취소된 배송을 다시 큐에 넣을 수 있는 최소 간격. 그 안의 재요청은 204(무동작)

실제 발송(`EMAIL_ROLLOUT_MODE=production`)은 위와 동일하되 `BREVO_SANDBOX_MODE=false` 여야
한다. 검증 규칙은 `backend/app/core/config.py` 의 롤아웃 validator(~779-830줄)를 그대로
따른다 — 하나라도 빠지면 설정 로드 시점에 `ValueError` 로 fail-closed 된다.

워커 명령(`backend/scripts/manage_email_delivery_worker.sh`):

- `check` — Redis DB 11 / 발송 준비 상태를 검사 (`run_email_delivery_worker.py --check --require-send-ready`)
- `start` / `stop` / `status` — 루프 워커(`--loop`)를 기동/종료/조회
- 파이썬 인터프리터는 `QUANTAGENT_BACKEND_PYTHON` 이 있으면 그것을, 없으면
  `backend/.venv/bin/python` 이 있으면 그것을, 둘 다 없으면 `ai/.venv/bin/python` 을 쓴다.
  배포 서버는 `backend/.venv` 가 없으므로 실질적으로 `ai/.venv` 를 쓴다.

## 참고
- AI 상세 실행/테스트 가드: `ai/README_AI.md`
- FE 실행/설정 상세: `fe/README.md`
