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
| `AI_ANALYSIS_MAX_CONCURRENCY` | `4` | 동시에 실행할 분석 수. AOAI 게이트 capacity(8)보다 낮게 둔다 — 분석 1건이 프로바이더 호출을 여러 번 내므로 |
| `AI_ANALYSIS_QUEUE_WAIT_SECONDS` | `600` | 슬롯을 기다리는 한도. 분석 1건의 wall budget보다 길게 둬서, 한 건 뒤에 선 잡이 차례를 받게 한다 |

상한을 넘은 잡은 **거절이 아니라 대기**한다. 클라이언트는 이미 큐잉된 잡을 폴링하고
있으므로 기다림이 새로 드는 비용이 아니고, 1분 뒤면 처리할 수 있는 일을 거절하는 편이
사용자에게 더 나쁘다. 대기 중인 잡은 `RUNNING`이 아니라 **`QUEUED`로 남는다** — 아무것도
돌고 있지 않은데 RUNNING이라고 말하는 것이 바쁜 서비스를 멈춘 것처럼 보이게 만든다.

대기에는 한도가 있다. 창 안에 슬롯을 못 받은 잡은 재시도를 안내하며 실패한다.
영원히 파킹된 스레드는 큐가 애초에 막으려던 그 고갈로 되돌아가는 길이다.

`/health`·`/readiness`는 async다. 동기 핸들러는 분석 백그라운드 작업이 쓰는 것과 같은
anyio 워커 풀에서 돌기 때문에, 분석이 몰리면 liveness가 타임아웃해 바깥에서는 서비스가
죽은 것으로 보인다.

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

## 참고
- AI 상세 실행/테스트 가드: `ai/README_AI.md`
- FE 실행/설정 상세: `fe/README.md`
