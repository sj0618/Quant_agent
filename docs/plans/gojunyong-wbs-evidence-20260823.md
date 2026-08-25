# 고준영 담당 WBS 재검증 및 배포 blocker — 2026-08-23

원본 계획은 [공유 WBS](https://docs.google.com/spreadsheets/d/1V7SnG_x-cLIFbrSurDIadtx5GCY9HfL9jRqdyAl70Ks/edit) `2_WBS` 시트다. 이 문서는 [2026-08-22 증적](gojunyong-wbs-evidence-20260822.md)을 현재 `main`(`fd3dbeb`) 기준으로 다시 돌려 확인한 결과이며, 원본 WBS의 상태·승인자·증적 URI를 수정하지 않는다.

두 가지가 어제와 다르다. 첫째, S 증적은 전부 그대로 유효하고 이제 실제 CI URI가 붙는다. 둘째, 어제 "대기"로만 적혀 있던 배포·서버 증적은 **대기가 아니라 차단**이다. 배포 대상 서버가 2026-08-13부터 SSH를 서비스하지 않는다.

## 1. 배포 서버 장애 — BLK-DEPLOY-SSH-001 (2026-08-24 해소)

> **2026-08-24 갱신 — 해소.** 아래 진단은 발생 당시(2026-08-23) 관측 그대로 보존한다.
> 현재 상태는 [1.1 해소 기록](#11-해소-기록--2026-08-24)에 있다.

`Deploy to SSH Server`와 `Server health check`가 모두 `ssh-keyscan` 단계에서 죽는다.

```text
quant-agent.kro.kr: Connection closed by remote host   (x5, 키 종류마다 1회)
##[error]Process completed with exit code 1
```

로컬에서 같은 대상을 조사한 결과다. 인증은 시도하지 않았고 읽기 전용 probe만 했다.

| 관측 | 결과 |
|---|---|
| DNS `quant-agent.kro.kr` | `138.2.113.134` |
| TCP 30233 | **연결됨** |
| SSH 배너 | **없음** — 서버가 `SSH-2.0-...`을 보내지 않고 즉시 끊음 (대조군 `github.com:22`는 즉시 배너 응답) |
| TCP 22 / 80 / 443 / 18000 / 18001 | 전부 닫힘 |
| HTTP `/`, `:18000/`, `:18001/healthz` | 응답 없음 |

읽어야 할 결론:

- **GitHub 러너 IP 차단이 아니다.** 로컬에서도 똑같이 재현된다.
- **네트워크·DNS 문제가 아니다.** 30233은 TCP를 받는다.
- 30233을 듣고 있는 무언가가 SSH 핸드셰이크 이전에 연결을 끊는다. 백엔드 sshd 정지, 죽은 포트포워드, 배너 이전 단계의 거부(tcpwrapper·fail2ban 류) 중 하나다.
- **코드 회귀가 아니다.** 같은 커밋 `5030ab5`가 2026-08-13T10:31+09:00에 성공했고 40분 뒤 11:11에 실패했다. 그 사이 저장소는 바뀌지 않았다.

연속 실패 13회(최초 발견 제외 재발 12회), 마지막 성공 2026-08-13T10:31+09:00.

- 최초 실패: <https://github.com/sj0618/Qaunt_agent/actions/runs/31660077571>
- 최신 실패(`fd3dbeb`): <https://github.com/sj0618/Qaunt_agent/actions/runs/32620823967/job/97148769504>
- `Server health check` 최신 실패: <https://github.com/sj0618/Qaunt_agent/actions/runs/32621204444>

[control board](quantagent-production-control-board.md)에 `BLK-DEPLOY-SSH-001`로 등재한다고 적었다.

> **2026-08-24 정정.** 실제로는 등재되지 않았다. 현재 board의 `blockers` 배열에는
> `BL-PLAN-001`, `BL-DATA-001`, `BL-METRIC-001` 셋만 있고 `BLK-DEPLOY-SSH-001`은
> 없다. 이 문장은 사실이 아니었다. 그래서 해소를 board에서 닫을 것도 없다 — 열린 적이
> 없는 항목은 닫을 수 없다. board를 다루는 사람이 사후 등재까지 원한다면 그건 별도
> 결정이며, 이 문서는 board를 고치지 않는다.

### 재시도로 덮지 않은 이유

`production-backtest-smoke.yml`은 `ssh-keyscan`에 3회 재시도를 두고 있고, 같은 패치를 배포·헬스체크 워크플로에도 넣을 수 있다. 넣지 않았다. 10일 연속·100% 실패는 일시적 흔들림이 아니라 상시 장애이고, 재시도는 실패를 늦출 뿐 배포를 복구하지 못하면서 blocker만 보이지 않게 만든다. 서버가 SSH를 다시 서비스하면 재시도 여부와 무관하게 두 워크플로는 통과한다.

### 사람이 해야 하는 일

1. `138.2.113.134`에서 sshd 상태와 30233 포트포워드 대상을 확인한다.
2. 복구 후 `Deploy to SSH Server`를 재실행하고 그 run URI를 P0-REL-01·P1-CI-01 증적으로 남긴다.
3. 10일간 배포가 없었으므로 현재 서버에 무엇이 올라가 있는지부터 확인한다. 배포본과 `main`의 차이는 이 문서로 증명할 수 없다.

### 1.1 해소 기록 — 2026-08-24

2026-08-24에 다시 관측했다. 인증은 시도하지 않았고 읽기 전용 probe와 CI 이력 조회만 했다.

| 관측 | 2026-08-23 | 2026-08-24 |
|---|---|---|
| DNS `quant-agent.kro.kr` | `138.2.113.134` | `138.2.113.134` (동일) |
| SSH 배너 (30233) | **없음** — 즉시 끊김 | **`SSH-2.0-OpenSSH_8.0`** |

`Deploy to SSH Server`가 같은 날 오전에 회복했다. 마지막 실패와 첫 성공이 9분 간격이다.

| 시각 (UTC) | 커밋 | 결과 | Run |
|---|---|---|---|
| 09:38 | `a6d9e1d` | failure | <https://github.com/sj0618/Qaunt_agent/actions/runs/32712666332> |
| 09:47 | `11ad44f` | **success** | <https://github.com/sj0618/Qaunt_agent/actions/runs/32713383696> |
| 10:38 | `2b7c010` | success | <https://github.com/sj0618/Qaunt_agent/actions/runs/32717807498> |
| 10:46 | `29eaef2` | success | <https://github.com/sj0618/Qaunt_agent/actions/runs/32718454031> |

`Server health check`는 최근 6회 연속 success이며 최신은 `29eaef2` 기준
<https://github.com/sj0618/Qaunt_agent/actions/runs/32726256341> (12:16 UTC)다.

배포된 서비스도 응답한다. `GET /ai-api/ai-api/api-status`와 `GET /ai-api/ai-api/readiness`가
각각 `200`이고, readiness는 `status: ready`로 다섯 체크가 모두 `ready: true`다.
`job_store`는 `active_mode: persistent`, `fallback: false`다.

#### 그래도 남아 있는 것

- **원인은 확인되지 않았다.** 배너가 돌아왔다는 사실만 안다. sshd가 재시작됐는지,
  포트포워드가 복구됐는지, 차단 규칙이 풀렸는지는 서버에 들어가 봐야 알 수 있다.
  원인을 모르면 재발 여부도 예측할 수 없다.
- **위 "사람이 해야 하는 일" 3번은 그대로 열려 있다.** 10일 공백 동안 서버에 무엇이
  올라가 있었는지는 여전히 이 문서로 증명되지 않는다. 8/24 배포가 성공했으므로 지금은
  `29eaef2`가 올라가 있을 것으로 보이지만, 그건 추정이지 관측이 아니다.
- `RMP-ENV-01`, `P0-REL-01`, `P1-CI-01`의 차단 사유는 이 blocker였다. 차단은 풀렸으나
  각 행의 완료 조건(서버 import·백테스트 확인, 배포 권한·release ID·rollback 절차·검토자
  2명, deploy/rollback run URI)은 별개이며 이 기록으로 충족되지 않는다.

## 2. S 증적 재검증 — 현재 `main`(`fd3dbeb`)

```text
node scripts/evaluate-release-trust.mjs
  ai-api-and-research-contracts: 109 passed        (어제 108 -> main에 1건 추가)
  backtest-metric-contracts: 44 passed
  backend-auth-report-and-deploy-contracts: 156 passed
  frontend-production-build-and-contracts: 34 passed, typecheck/build passed
  exit: 0

node --test scripts/evaluate-release-trust.test.mjs
  6 pass, 0 fail

ai/.venv/bin/python -m pytest -q ai/tests/test_control_board.py
  6 passed

python ai/scripts/validate_control_board.py --board docs/plans/quantagent-production-control-board.md
  {"valid": true, ...}

git diff --check
  exit: 0
```

어제의 S 등급 항목(EV-GATE-01, RMP-ENV-01, P0-BE-01, P0-BE-02, RMP-REPORT-01, P1-SEC-01, P1-OBS-01, P1-CI-01)은 계약 수준에서 그대로 통과한다.

## 3. 항목별 현재 상태

| WBS ID | 어제 | 오늘 | 남은 것 |
| --- | --- | --- | --- |
| EV-GATE-01 | S | **S + R** — CI에서 게이트가 실제로 green: <https://github.com/sj0618/Qaunt_agent/actions/runs/32620823963/job/97148619718> | 독립 검토자·검토일 |
| RMP-ENV-01 | S | **차단** — 배포 job이 SSH 단계에서 죽어 서버 import/백테스트 확인에 도달하지 못함 | BLK-DEPLOY-SSH-001 해소 |
| P0-BE-01 | S | **S + R** — Python checks green: <https://github.com/sj0618/Qaunt_agent/actions/runs/32620823963/job/97148619555> | 독립 검토자, 실제 인증 smoke(서버 필요) |
| P0-BE-02 | S | **S + R** — 동일 run | 실제 DB migration·durable store·signer probe 로그(서버 필요), 독립 검토자 |
| RMP-REPORT-01 | S | **S + R** — 동일 run | 구독 데이터 보존·권한·보관 정책 승인(사람), 독립 검토자 |
| P0-REL-01 | R/O/C 대기 | **차단** | 서버 복구 → 배포 권한·release ID·rollback 절차·검토자 2명 |
| P1-SEC-01 | S | **S + R** — 동일 run | Redis 운영 지표, 실제 로그인/로그아웃 E2E, 프록시 client-IP smoke(서버 필요), 검토자 |
| P1-OBS-01 | S | **S, 관측 부분 차단** | trace sink·sampling 설정, 배포 로그/대시보드(서버 필요), PII 검토 승인 |
| P1-CI-01 | S | **차단** — 워크플로 계약은 통과하나 실제 deploy/rollback run이 10일째 없음 | BLK-DEPLOY-SSH-001 해소 후 deploy/rollback run URI |
| P2-OPS-01 | R/O/C 대기 | **차단** | 부하 환경(서버 필요), 기준일·budget 승인, 측정 artifact |

## 4. 이 문서가 하지 않은 것

- 서버에 접속하거나 배포·롤백을 실행하지 않았다. 읽기 전용 네트워크 probe만 했다.
- 독립 검토자 승인을 대신 기록하지 않았다. 검토자 칸은 사람이 채워야 하고, 자리표시자를 승인으로 승격하지 않았다.
- 로컬 fixture·mock을 운영 증적으로 대체하지 않았다. 차단된 항목은 차단으로 남겼다.

## 5. 부수 수정

`ai/tests/test_control_board.py`가 board의 집계값을 리터럴로 고정하고 있어서, 실제 blocker를 한 줄 등재하자 3개 테스트가 깨졌다. 원장이 늘어나면 무조건 깨지는 결합이고 board는 정의상 살아 있는 문서이므로, 그날의 숫자 대신 불변식(모든 전이·blocker가 증적 URI를 갖는다, 집계가 원장과 일치한다, CLI 출력이 라이브러리 결과와 같다)을 검증하도록 바꿨다. 검증 의도는 유지되고 값 고정만 제거했다.
