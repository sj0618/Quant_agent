# RMP-QA-02 착수 가능 통지 — 배포 서버 SSH 복구 (2026-08-24)

이 문서는 **상태 통지**다. WBS의 상태값·승인자·증적 URI를 바꾸지 않고,
`RMP-QA-02`(서버 PostgreSQL smoke)의 실행 담당자가 착수할 수 있게 된 사실과
그 근거만 기록한다.

- 역할: 실행 **조은채**, 검토 **윤서준**. 이 문서는 검토자 쪽 통지이며 승인이 아니다.
- 기준 시각: 2026-08-24 KST
- 기준 커밋: `29eaef2295d2e2c04c63bbfdd705cbf2d90ce61a` (= `origin/main`)

## 무엇이 바뀌었나

`BLK-DEPLOY-SSH-001`(2026-08-13부터 배포 대상 서버가 SSH를 서비스하지 않던 장애,
[2026-08-23 기록](gojunyong-wbs-evidence-20260823.md) 참조)의 증상이 사라졌다.
서버 접근이 전제인 QA 항목은 더 이상 차단 상태가 아니다.

## 측정한 근거

### 1. SSH가 다시 핸드셰이크를 완료한다

8/23 기록의 증상은 "TCP 30233은 열리지만 `SSH-2.0-...` 배너 이전에 연결이 끊긴다"였다.
오늘 같은 대상에 대해 측정한 결과는 다르다.

```sh
nc -z -w 5 quant-agent.kro.kr 30233
# Connection to quant-agent.kro.kr port 30233 [tcp/*] succeeded!

ssh -o BatchMode=yes -p 30233 etluser@quant-agent.kro.kr
# etluser@quant-agent.kro.kr: Permission denied
#   (publickey,gssapi-keyex,gssapi-with-mic,keyboard-interactive)
```

`Permission denied` + 인증 방식 목록은 **sshd가 프로토콜 협상을 끝내고 인증 단계까지
갔다**는 뜻이다. 배너 이전에 끊기던 8/23 증상과 다른 상태다.

(이 기록을 만든 로컬 머신에는 배포용 키가 없다. 배포 키는 GitHub Actions 시크릿이며,
`Permission denied`는 키 부재의 결과이지 서버 장애의 결과가 아니다.)

### 2. 배포·헬스체크 워크플로가 다시 통과한다

```sh
gh run list --workflow=server-health.yml --limit 6
gh run list --workflow=deploy.yml --limit 5
```

| 워크플로 | 최근 결과 |
|---|---|
| `Server health check` | 최근 **6회 연속 success** (최신 `2026-08-24T12:16:48Z`, run `32726256341`) |
| `Deploy to SSH Server` | 최근 **3회 연속 success** (최신 `2026-08-24T10:46:17Z`, run `32718454031`). 직전 두 건(`32712666332`, `32708278234`)은 failure였다. |

### 3. 배포된 서비스가 운영 데이터 소스로 응답한다

```sh
curl -sS https://qt-agent.kro.kr/ai-api/ai-api/api-status
```

```json
{"data_source":{"configured":true,"dsn_env":"AI_DATABASE_DSN",
  "price_source":"feature.kis_adjusted_ohlcv_daily","macro_usable":false,
  "fallback_when_unset":"fixture"},
 "job_store":{"requested_mode":"persistent","active_mode":"persistent",
  "dsn_configured":true,"fallback":false,"fallback_reason":null}}
```

`data_source.configured=true`이고 job store가 `persistent`로 fallback 없이 떠 있다.
PostgreSQL smoke가 향할 대상이 실제로 서 있다는 뜻이다.

## 실행 담당자가 이제 할 수 있는 것

`RMP-QA-02`의 서버 PostgreSQL smoke는 착수 가능하다. 착수 시 다음을 함께 남기면
검토가 한 번에 끝난다.

- 실행 시각과 대상 커밋 SHA
- `source` / `as_of` / `freshness` / `lineage` 값 — fixture가 아니라 `postgres`임을 보이는 필드
- 실행 중 서버 부하(load average, 메모리). 부하를 보면서 순차로 실행할 것.
  **동시 요청을 몰아넣지 말 것** — 아래 미확인 사항 참조.

## 함께 남기는 미확인 사항

배포 서버의 CPU 코어 수와 `AI_ANALYSIS_MAX_CONCURRENCY` 실제 값은 **이 문서를 쓰는
시점에 확인하지 못했다.** 로컬에 배포 키가 없어 서버 셸에 접근할 수 없고,
`api-status`는 그 두 값을 노출하지 않는다. 코드 기본값은 `4`이며 저장소의 어떤
배포 설정에도 이 키가 없다(`grep -rn AI_ANALYSIS_MAX_CONCURRENCY` 결과는 README 한 줄뿐).
따라서 서버 `.env`가 이 키를 설정하지 않았다면 동시 분석 4건이 상한이다.

smoke를 도는 사람이 서버 셸에 접근할 수 있다면 `nproc`와 그 env 값을 함께 기록해
주기를 요청한다. 동시성 상한 재검토가 그 값에 걸려 있다.

## 이 문서가 하지 않는 것

- WBS 상태 전이를 기록하지 않는다.
- `BLK-DEPLOY-SSH-001`의 control board 항목을 닫지 않는다. 그 정정은 별도 작업이다.
- `RMP-QA-02`를 승인하지 않는다. 산출물이 나온 뒤 검토자가 판정한다.
