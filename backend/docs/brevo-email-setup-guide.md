# Brevo 이메일 발송 셋업 가이드

리포트 완료 이메일을 실제로 발송하기 위해 무엇을, 어디에, 어떤 순서로 넣어야 하는지 정리한 운영자용 가이드입니다.
모든 값·규칙·경로는 코드에서 그대로 가져왔습니다
(`backend/app/core/config.py`, `backend/.env.example`, `backend/scripts/manage_email_delivery_worker.sh`, `.github/workflows/deploy.yml`).

---

## 0. 한 줄 요약

- **이메일 기능의 "코드"는 이미 전부 구현되어 있습니다.** (Brevo 연동 · 발송 워커 · 템플릿 · 수신거부 · 웹훅 · 발송 이력 화면)
- 실제 발송은 안전을 위해 기본적으로 꺼져 있고(dark-by-default), **Brevo 계정·API 키·인증 발신 주소를 서버 환경변수로 넣어야** 켜집니다.
- "환경변수가 필요하다"는 건 버그·미완성이 아니라, **코드에 담을 수 없는 비밀값(API 키 등)을 서버에 넣는 정상적인 운영 단계**입니다.

> ⚠️ **보안**: `BREVO_API_KEY`, `EMAIL_UNSUBSCRIBE_SIGNING_SECRET` 같은 시크릿은 **절대 저장소(git)에 커밋하지 마세요.** 서버의 `.env` 파일에만 넣습니다. (프로덕션 서버는 read-only이며 코드는 `main → 배포` 파이프라인으로만 전달됩니다.)

---

## 0-1. 누가 무엇을 하나 (역할 경계)

이 셋업은 **일부가 사람만 할 수 있는 일**입니다(계정·DNS·시크릿). 그 부분은 자동화가 불가능합니다.

| 단계 | 누가 | 이유 |
|---|---|---|
| Brevo 가입 · API 키 발급 | **운영자(사람)** | 계정 생성·인증은 사람만 가능 |
| `qt-agent.kro.kr` DNS 인증(DKIM/SPF/DMARC) | **운영자(사람)** | 도메인 DNS 로그인 필요 |
| 서버 `.env`에 시크릿 입력 (SSH) | **운영자(사람)** | 프로덕션 접근·비밀값 입력 |
| 받은편지함 도달 확인 | **운영자(사람)** | 실제 수신 확인 |
| 나머지(코드·배포 자동화·워커 기동 로직·이 문서) | **이미 코드에 구현됨** | 추가 작업 불필요 |

아래 STEP 1~3의 굵은 부분만 사람이 하면, 발송 파이프라인·워커 기동은 자동으로 동작합니다.

---

## 1. 발송이 실제로 나가려면 필요한 조건

이메일 한 통이 사용자 받은편지함에 도달하려면 아래가 **모두** 갖춰져야 합니다. 하나라도 빠지면 조용히 안 갑니다.

| 축 | 내용 | 상태 |
|---|---|---|
| **A. Brevo 계정** | 가입 → API 키 → 발신 도메인(`qt-agent.kro.kr`) 인증 | 사람이 해야 함 (STEP 1~2) |
| **B. 서버 환경변수** | 발송 스위치 + 키 + 발신 주소 + 공개 URL + 수신거부 | 사람이 값 입력 (STEP 3) |
| **C. 발송 워커** | 큐의 메일을 Brevo에 실제로 쏘는 백그라운드 프로세스 | **배포가 자동 기동** (STEP 4) |
| **D. 발송 트리거 + 수신 동의** | "언제 보낼지" 플래그 + 사용자별 수신 ON | 환경변수 + 앱 토글 (STEP 5) |
| **E. 인프라 전제** | qt_db 공유 · Redis DB 11 · 리포트 저장 정상 | 배포 환경 (STEP 6) |

---

## STEP 1. Brevo 가입 & API 키 발급  〔사람〕

1. [https://www.brevo.com](https://www.brevo.com) 가입 (무료 요금제: 하루 300통).
2. **SMTP & API → API Keys → Generate a new API key** 로 키 발급.
3. 발급된 키를 안전하게 보관 (한 번만 보이므로 즉시 복사). → 나중에 `BREVO_API_KEY` 값.

## STEP 2. 발신 도메인 인증 (`qt-agent.kro.kr`)  〔사람〕

코드가 발신 주소 도메인을 **`qt-agent.kro.kr` 로 고정 검사**합니다
(`_EXPECTED_EMAIL_SENDER_DOMAIN`, `backend/app/core/config.py`). 다른 도메인 주소는 서버 기동 시 거부됩니다.

1. Brevo → **Senders, Domains & Dedicated IPs → Domains → Add a domain** 에서 `qt-agent.kro.kr` 등록.
2. Brevo가 주는 **DKIM / SPF (및 DMARC 권장)** 레코드를 `kro.kr` DNS에 등록.
3. Brevo에서 도메인이 **Authenticated** 상태가 될 때까지 대기(DNS 전파로 시간 걸림).
4. 발신 주소로 쓸 메일박스(예: `no-reply@qt-agent.kro.kr`)를 Sender로 추가.

> 도메인 인증을 건너뛰면 메일이 스팸 처리되거나 Brevo가 발송을 거부합니다. 이 단계가 가장 오래 걸립니다.

---

## STEP 3. 서버 환경변수 설정  〔사람: 값 입력〕

### 넣는 위치 — 서버의 영속 `.env`

값은 프로덕션 서버의 **`~/mvp_sp1/quant-proj/.env`** 파일에 넣습니다.
배포 파이프라인은 이 `.env`를 **덮어쓰지 않고**(rsync 제외), Google 인증 키만 교체하며 **`EMAIL_*`·`BREVO_*` 키는 그대로 보존**합니다
(`.github/workflows/deploy.yml`). 즉 **한 번 넣으면 배포해도 유지**됩니다.

```bash
# 서버 접속 후
cd ~/mvp_sp1/quant-proj
# .env 편집기로 아래 블록을 append (기존 키는 두고 추가)
```

### 3-A. allowlist 모드 (테스트 단계, 권장 시작점)

`.env` 에 추가할 블록 — `<...>` 부분만 실제 값으로 채우세요:

```dotenv
EMAIL_ROLLOUT_MODE=allowlist
EMAIL_DELIVERY_ENABLED=true
EMAIL_DELIVERY_WORKER_ENABLED=true
EMAIL_REPORT_COMPLETED_TRIGGER_ENABLED=true
EMAIL_PROVIDER=brevo

BREVO_API_KEY=<STEP 1에서 발급한 키>
BREVO_SENDER_EMAIL=no-reply@qt-agent.kro.kr
BREVO_SENDER_NAME=QuantAgent
BREVO_SANDBOX_MODE=false

EMAIL_PUBLIC_BASE_URL=https://qt-agent.kro.kr
EMAIL_UNSUBSCRIBE_ENABLED=true
EMAIL_UNSUBSCRIBE_SIGNING_SECRET=<아래 명령으로 생성한 값>
EMAIL_UNSUBSCRIBE_BASE_URL=https://qt-agent.kro.kr

EMAIL_LOCAL_RECIPIENT_ALLOWLIST=<본인 테스트 이메일>   # 여기 적힌 주소로만 실제 발송 (쉼표로 여러 개)
```

수신거부 서명 시크릿 생성(둘 중 아무거나):

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# 또는
openssl rand -base64 48
```

### 3-B. production 모드 (전체 사용자 대상)

테스트가 끝나면 아래만 바꿉니다. 나머지는 동일:

```dotenv
EMAIL_ROLLOUT_MODE=production
# EMAIL_LOCAL_RECIPIENT_ALLOWLIST 는 더 이상 필수 아님 (전체 사용자 발송)
# BREVO_SANDBOX_MODE=false 는 production에서 필수 (true면 서버 기동 거부)
```

### 필수값 검증 규칙 (서버가 뜰 때 검사 → 없으면 기동 거부)

| 서버 에러 메시지 | 원인 / 빠진 값 |
|---|---|
| `server email rollout requires EMAIL_DELIVERY_ENABLED=true` | `EMAIL_DELIVERY_ENABLED=false` |
| `server email rollout requires EMAIL_PROVIDER=brevo` | `EMAIL_PROVIDER` 가 brevo 아님 |
| `server email rollout requires BREVO_API_KEY` | `BREVO_API_KEY` 없음 |
| `server_email_sender_invalid` | `BREVO_SENDER_EMAIL` 없음 또는 `@qt-agent.kro.kr` 아님 |
| `EMAIL_PUBLIC_BASE_URL must be an absolute https URL ...` | 공개 URL이 http이거나 로컬/미설정 |
| `server email rollout requires EMAIL_UNSUBSCRIBE_ENABLED=true` | 수신거부 미활성 |
| `EMAIL_ROLLOUT_MODE=allowlist requires EMAIL_LOCAL_RECIPIENT_ALLOWLIST` | allowlist인데 수신 목록 비어 있음 |
| `EMAIL_ROLLOUT_MODE=production requires BREVO_SANDBOX_MODE=false` | production인데 샌드박스 ON |
| `server email rollout requires a non-local PostgreSQL qt_db endpoint` | DB가 로컬이거나 이름이 `qt_db` 아님 |
| `server email rollout requires a non-local Redis endpoint using logical DB 11` | Redis가 로컬이거나 논리 DB가 11 아님 |

---

## STEP 4. 발송 워커  〔배포가 자동 기동 — 확인만〕

환경변수만 켜면 메일은 **큐(`app.email_delivery_history` PENDING)에 쌓이기만** 하고, 실제 발송은 **워커 프로세스**가 합니다.

**좋은 소식: 배포 파이프라인이 이미 워커를 자동 관리합니다.**
`.github/workflows/deploy.yml` 은 매 배포마다 `EMAIL_DELIVERY_WORKER_ENABLED=true` 이면 워커를 stop → start → check 합니다(이메일 준비 실패는 경고만, 웹 배포는 롤백 안 함). 즉 STEP 3을 서버 `.env`에 넣고 배포하면 워커는 자동으로 뜹니다.

수동 확인/제어가 필요하면(SSH):

```bash
backend/scripts/manage_email_delivery_worker.sh check    # 설정·DB·Redis 준비 상태 검사 (발송 없이)
backend/scripts/manage_email_delivery_worker.sh status   # 워커 상태
backend/scripts/manage_email_delivery_worker.sh start    # 수동 시작
backend/scripts/manage_email_delivery_worker.sh stop     # 중지
```

- `check` 는 `run_email_delivery_worker.py --check --require-send-ready` 를 실행해 키·발신자·DB·Redis 준비 여부를 확인합니다. 여기 통과 = 환경변수 셋업 정상.
- 서버에 `backend/.venv` 가 없으면 스크립트가 `ai/.venv/bin/python` 으로 폴백합니다(기존 배포 관례).

---

## STEP 5. 발송 트리거 & 사용자 수신 설정

- **트리거**: `EMAIL_REPORT_COMPLETED_TRIGGER_ENABLED=true` (STEP 3에 포함) 여야 "리포트 완료 → 발송"이 동작합니다. 꺼져 있으면 `trigger_disabled` 로 스킵.
- **사용자별 수신 동의**: 각 사용자 계정의 `daily_report_email` 이 `TRUE` 여야 발송(기본 TRUE). 앱 **프로필 → "Daily 리포트 이메일 수신"** 토글이 이 값입니다. **"리포트 수신 이메일"** 칸에 실제 받을 주소를 넣습니다.

---

## STEP 6. 인프라 전제 (코드가 아니라 배포 환경)

이메일 rollout을 켜면 아래가 강제됩니다. 로컬 개발값 그대로는 켜지지 않습니다.

- **PostgreSQL**: non-local 호스트 + DB 이름이 정확히 `qt_db`. 그리고 `DATABASE_URL` 과 `TRADING_DATA_DATABASE_URL` 이 **같은 `qt_db`** 를 가리켜야 함(완료 경로가 trading engine으로 이메일 행을 씀).
- **Redis**: non-local 호스트 + **논리 DB 11** (`redis://…:PORT/11`).
- **공개 URL**: `EMAIL_PUBLIC_BASE_URL`, `EMAIL_UNSUBSCRIBE_BASE_URL` 은 절대 https, 비-로컬 호스트(`https://qt-agent.kro.kr`).

---

## STEP 7. 발송 검증 (end-to-end)

1. (SSH) `manage_email_delivery_worker.sh check` → 준비 상태 통과 확인. 또는 `/health` 응답의 `email_*` 필드 확인.
2. `EMAIL_LOCAL_RECIPIENT_ALLOWLIST` 에 넣은 본인 주소를, 앱 프로필의 "리포트 수신 이메일"에도 동일하게 설정.
3. 자연어 전략 분석을 하나 돌려 **리포트를 완료**시킴(`analysis-jobs → ready → 리포트 저장`).
4. 받은편지함 확인. 동시에 앱 **프로필 → 이메일 발송 타임라인** 또는 API `GET /api/v1/me/email-deliveries` 에서 상태가 `SENT` 인지 확인.
5. 실패 시 `RETRY_PENDING`(일시 오류, 재시도) / `FAILED`(영구 오류)로 보입니다.

전체 파이프라인 실측 기록: [`email-delivery-e2e-20260902.md`](email-delivery-e2e-20260902.md)

---

## 🔴 발송이 안 될 때 체크리스트 (과거 실제 원인 순)

3축(계정·env·워커)을 다 맞춰도 안 나갈 때, 아래를 위에서부터 확인하세요. 운영에서 실제로 막혔던 것들입니다.

1. **리포트가 실제로 저장되고 있나?** ← 가장 흔한 진짜 원인
   이메일은 **리포트가 완료·저장되는 순간에만** 큐에 들어갑니다(`complete_analysis_run_from_db` 가 유일한 enqueue 지점). 분석→리포트 저장 경로가 막혀 앱에 "분석 결과를 리포트로 저장하지 못했습니다" 배너가 뜨면, 이메일 설정이 아무리 맞아도 한 통도 안 나갑니다. → 먼저 리포트 저장이 정상인지 확인.
2. **트리거 + 사용자 수신 동의**: `EMAIL_REPORT_COMPLETED_TRIGGER_ENABLED=true` 이고 사용자의 `daily_report_email=TRUE` 인지.
3. **워커가 실제로 떠 있나**: `manage_email_delivery_worker.sh status`. 큐(PENDING)에 쌓이는데 안 나가면 워커 미실행.
4. **샌드박스**: `BREVO_SANDBOX_MODE=true` 면 Brevo가 접수만 하고 드롭 → `false` 로.
5. **allowlist 누락**: allowlist 모드에서 특정 주소가 `EMAIL_LOCAL_RECIPIENT_ALLOWLIST` 에 없으면 그 주소는 스킵.
6. **인프라**: qt_db 공유(`DATABASE_URL`==`TRADING_DATA_DATABASE_URL`), Redis 논리 DB 11.
7. **스팸함**: STEP 2 DKIM/SPF/DMARC 미완료 또는 DNS 미전파. `kro.kr` 무료 도메인은 평판이 낮아 초반엔 꼭 스팸함 확인.
8. **한도**: Brevo 무료 요금제는 하루 300통. 초과 시 요금제 업그레이드.

### (선택) 발송 관측 강화
`BREVO_WEBHOOK_ENABLED=true` + `BREVO_WEBHOOK_BEARER_TOKEN=<시크릿>` 을 켜면 반송(bounce)·스팸신고·오픈 이벤트를 추적할 수 있습니다.

---

## 관련 파일

- 설정·검증: `backend/app/core/config.py`, `backend/.env.example`
- 발송 로직: `backend/app/services/email_delivery.py`, `email_provider.py`, `email_templates.py`, `email_unsubscribe.py`
- 워커: `backend/app/workers/email_delivery_worker.py`, `backend/scripts/manage_email_delivery_worker.sh`, `run_email_delivery_worker.py`
- 배포 자동화: `.github/workflows/deploy.yml` (워커 stop/start/check, `.env` 보존)
- 실측 기록: `backend/docs/email-delivery-e2e-20260902.md`
