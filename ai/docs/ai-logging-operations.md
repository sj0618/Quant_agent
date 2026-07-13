# AI 로깅 운영 런북

이 문서는 AI trace, agent execution, model call, prompt/response, error 로그를
PostgreSQL에 저장하는 기능의 활성화·검증·롤백 절차다. 로그 조회 API,
관리 UI, 외부 observability 플랫폼은 제공하지 않는다.

## 실행 경로와 실패 규칙

- `ai_graph`는 실제 실행된 Supervisor, Ambiguity Classifier, Data, Research,
  BacktestCode, Backtest, Signal, Risk Manager, Report, Envelope 노드를 같은
  trace 아래 기록한다. 작업 노드가 예외를 내면 해당 execution과 error를
  연결하고 이후 노드를 실행하지 않은 채 trace를 실패로 종료한다.
- backend 생성형 백테스트는 `code_generation`, `code_validation`,
  `code_execution`, `report_generation` 네 단계를 기록한다. 모델 호출은 해당
  단계의 `execution_id`와 연결되고 system/user prompt 및 assistant response
  원문을 `masked=false`로 저장한다.
- 재시도는 하나의 논리적 model call 안에서 수행한다. 모델 호출이 끝내
  실패해도 deterministic fallback이 성공하면 model call과 error는 실패로
  남지만 agent와 trace는 성공할 수 있다. fallback도 실패하면 agent와 trace를
  실패로 종료하되 이미 캡처한 model call, prompt, error는 해당 execution에
  연결해 저장한다. `error_message`에는 timeout, provider HTTP 상태, transport,
  JSON 해석, 코드 검증, 실행 상태 및 안전한 내부 오류 코드처럼 조치 가능한
  실패 이유를 남기되 secret이나 내부 예외 원문은 복사하지 않는다.
- audit 테이블 저장이 한 번 실패하면 rollback 후 해당 세션의 추가 audit DB
  쓰기를 중단하고 연결을 닫으며, 안전한 stderr 이벤트와 실패 카운터만 남긴다.
  AI 결과는 바뀌지 않는다. 반면 백테스트 결과·전략·실행 결과 같은 업무
  데이터 저장 실패는 audit 실패가 아니므로 기존 API 실패 처리 대상이다.

## 1. 실행 설정

| 설정 | 값 | 동작 |
|---|---|---|
| `AI_AUDIT_SINK` | `noop` | 기본값. AI는 정상 실행하고 DB 로그는 저장하지 않는다. |
| `AI_AUDIT_SINK` | `postgres` | PostgreSQL 로깅을 활성화한다. DSN이 없거나 연결이 실패하면 fail-open으로 `noop`과 같이 AI 실행을 계속한다. |
| `AI_AUDIT_CONNECT_TIMEOUT_SECONDS` | 양의 정수, 기본 `2` | 로깅 DB 연결 제한 시간. |
| `AI_AUDIT_STATEMENT_TIMEOUT_MS` | 양의 정수, 기본 `2000` | 로깅 SQL 제한 시간. |

DSN은 첫 번째 비어 있지 않은 값을 아래 순서로 사용한다.

1. `AI_DATABASE_DSN`
2. `QUANT_DB_DSN`
3. `DATABASE_URL`

`AI_AUDIT_SINK`의 알 수 없는 값은 오류를 기록하고 fail-open `noop`으로
동작한다. DSN과 인증 정보는 배포 환경의 secret 저장소로 주입하고 로그나
증거 문서에 원문을 남기지 않는다.

예시:

```bash
AI_AUDIT_SINK=postgres
AI_DATABASE_DSN='postgresql://<user>:<secret>@<db-host>:5432/<db>?sslmode=verify-full&sslrootcert=/path/to/ca.pem'
AI_AUDIT_CONNECT_TIMEOUT_SECONDS=2
AI_AUDIT_STATEMENT_TIMEOUT_MS=2000
```

## 2. 마이그레이션

선행 조건은 `service_db/migrations/011_app_ai_backtest_erd.sql`이 적용된 DB다. 코드
활성화 전에 additive migration 013을 적용한다.

```bash
psql "$AI_DATABASE_DSN" -v ON_ERROR_STOP=1 \
  -f service_db/migrations/013_ai_runtime_logging.sql
```

013은 다음만 추가하며 기존 컬럼이나 데이터를 삭제하지 않는다.

- model call의 `execution_id`, `response_schema_name`, `web_search_used`
- model call → agent execution FK (`ON DELETE SET NULL`)
- execution correlation index
- prompt 90일 삭제용 `(created_at, prompt_log_id)` index

적용 후 카탈로그 검증:

```sql
SELECT column_name
FROM information_schema.columns
WHERE table_schema = 'app'
  AND table_name = 'ai_model_call_log'
  AND column_name IN ('execution_id', 'response_schema_name', 'web_search_used')
ORDER BY column_name;

SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'fk_ai_model_call_log_execution';

SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'app'
  AND indexname IN (
    'idx_ai_model_call_log_execution_created',
    'idx_ai_prompt_log_retention'
  )
ORDER BY indexname;
```

## 3. 스테이징 활성화와 canary

1. Gate A 테스트와 migration 013 적용을 완료한다.
2. 스테이징에 `sslmode=verify-full`인 DSN과 `AI_AUDIT_SINK=postgres`를 주입한다.
3. AI 요청 한 건을 실행하고 public `trace_id`를 기록한다.
4. 아래 read-only SQL로 trace, 실제 실행 agent, model call, prompt가 연결되고
   terminal 상태인지 확인한다. 오류 시나리오는 error가 같은 trace/call에
   연결되는지 확인한다.
5. 원문 prompt/response를 인가된 운영자가 canary 입력과 직접 비교한다.
6. 로깅 DB를 의도적으로 차단한 동일 요청에서 AI 결과가 정상으로 반환되는지
   확인한다.

```sql
WITH target AS (
    SELECT trace_id, status, started_at, ended_at
    FROM app.ai_trace
    WHERE metadata_jsonb ->> 'public_trace_id' = :'public_trace_id'
    ORDER BY started_at DESC
    LIMIT 1
)
SELECT
    target.trace_id,
    target.status AS trace_status,
    agent.execution_id,
    agent.agent_name,
    agent.status AS agent_status,
    model.call_id,
    model.status AS model_status,
    prompt.prompt_log_id,
    prompt.masked,
    error.error_id,
    error.error_type
FROM target
LEFT JOIN app.ai_agent_execution_log AS agent USING (trace_id)
LEFT JOIN app.ai_model_call_log AS model
  ON model.trace_id = target.trace_id
 AND model.execution_id IS NOT DISTINCT FROM agent.execution_id
LEFT JOIN app.ai_prompt_log AS prompt USING (call_id)
LEFT JOIN app.ai_error_log AS error
  ON error.trace_id = target.trace_id
 AND error.execution_id IS NOT DISTINCT FROM agent.execution_id
 AND (error.call_id IS NULL OR error.call_id = model.call_id)
ORDER BY agent.started_at, model.created_at, error.created_at;
```

정상 canary에서 `masked=false`다. 이는 원문 저장 정책을 의미하며, 응답을
받은 API가 제공된다는 의미가 아니다.

## 4. 즉시 롤백과 forward schema 정책

로깅 장애가 의심되면 배포 설정을 다음과 같이 바꾸고 AI 서비스를
재시작한다.

```bash
AI_AUDIT_SINK=noop
```

- 013에서 추가한 nullable 컬럼·FK·인덱스는 그대로 둔다.
- `DROP COLUMN`, `DROP CONSTRAINT`, `DROP INDEX`로 기존 로그를 훼손하지 않는다.
- 후속 오류는 삭제형 down migration 대신 additive forward migration으로 수정한다.
- 잘못 삭제된 90일 초과 prompt/response는 DB에서 복원하지 않는다. purge
  오류는 수정 후 재실행한다.

## 5. 오래된 `running` 로그 진단

terminal DB transaction이 실패하면 로깅은 fail-open이므로 AI 결과는 정상이고
시작 row만 `running`으로 남을 수 있다. 아래 SQL은 15분 이상 종료되지 않은
row를 조회만 한다. 자동 수정은 이번 범위가 아니다.

```sql
SELECT 'trace' AS log_kind, trace_id::text AS log_id, started_at AS running_since
FROM app.ai_trace
WHERE status = 'running'
  AND started_at < now() - INTERVAL '15 minutes'
UNION ALL
SELECT 'agent_execution', execution_id::text, started_at
FROM app.ai_agent_execution_log
WHERE status = 'running'
  AND started_at < now() - INTERVAL '15 minutes'
UNION ALL
SELECT 'model_call', call_id::text, created_at
FROM app.ai_model_call_log
WHERE status = 'running'
  AND created_at < now() - INTERVAL '15 minutes'
ORDER BY running_since;
```

## 6. 90일 prompt/response 삭제

`DE/scripts/purge_ai_prompt_logs.py`는 DB 시계로 한 번 생성한
`now() - INTERVAL '90 days'`보다 `created_at`이 작은 prompt row만 1,000건씩
삭제하고 batch마다 commit한다. 경계시각과 보존 기간 이내 row는 유지되며,
여러 번 실행해도 결과가 같다. 연결은 5초, SQL은 30초 timeout으로 제한한다.

수동 실행:

```bash
cd DE
AI_DATABASE_DSN="$AI_DATABASE_DSN" python3 scripts/purge_ai_prompt_logs.py
```

성공하면 `deleted <N> expired AI prompt log rows`를 출력하고 0으로 종료한다.
실패하면 비밀을 제외한 예외 타입만 stderr에 출력하고 1로 종료한다.

Airflow의 `quant_agent_ai_prompt_retention` DAG는 매일 05:00 Asia/Seoul에 독립적으로
실행된다. `max_active_runs=1`, 5분 간격 3회 retry이며 AI 실행 DAG와 의존
관계가 없다. purge 실패는 AI 요청을 실패로 변경하지 않는다.

삭제 전후 확인:

```sql
SELECT
    count(*) FILTER (WHERE created_at < now() - INTERVAL '90 days') AS expired,
    count(*) FILTER (WHERE created_at >= now() - INTERVAL '90 days') AS retained
FROM app.ai_prompt_log;
```

active DB 삭제는 backup, snapshot, export 사본의 삭제를 의미하지 않는다. 이들의
retention/expiry는 Gate B에서 별도로 증명한다.

## 7. 완료 gate

### Gate A — 코드 완료

- [ ] migration 013이 전체 migration과 함께 두 번 적용되고 FK/index가 확인된다.
- [ ] API entrypoint와 direct `run_analysis()`가 하나의 trace로 agent/model/prompt/error를 연결한다.
- [ ] system/user/variables/assistant 원문이 손실 없이 round-trip된다.
- [ ] DB 연결·timeout·제약조건·직렬화 실패에서 AI 결과가 변하지 않는다.
- [ ] 90일 purge가 배치·재시도·반복 실행에 안전하고 metadata를 유지한다.
- [ ] test, lint, migration, integration, OpenAPI non-scope contract가 통과한다.

Gate A는 아래 Gate B의 대체 증거가 아니다.

### Gate B — 운영 인프라 보안 완료

- [ ] 실제 app DB session이 TLS이고 CA/hostname 검증이 통과한다.
- [ ] primary/replica/temp storage, snapshot, backup, archived WAL의 암호화가 확인된다.
- [ ] backup retention/expiry와 격리 restore drill이 통과한다.
- [ ] writer/purge/DBA 권한과 원문 log 접근 감사가 확인된다.
- [ ] 모든 증거에 owner, reviewer, date, resource, observed value가 있다.

Gate A만 통과하고 Gate B가 미확인이면 상태는
**`코드 완료 / 운영 full-content logging 비활성`**이다.

## 8. TLS 검증

운영 DSN은 CA와 hostname을 검증하는 `sslmode=verify-full`을 사용한다.
`SHOW ssl` 결과는 서버 capability일 뿐 현재 session의 TLS 증거가 아니다.
실제 AI writer가 사용하는 DSN으로 아래를 실행한다.

```sql
SELECT ssl, version, cipher
FROM pg_stat_ssl
WHERE pid = pg_backend_pid();
```

통과 조건은 row가 있고 `ssl=true`, `version`/`cipher`가 비어 있지 않은 것이다.

음성 테스트도 필수다.

1. 운영 DB를 신뢰하지 않는 다른 CA를 `sslrootcert`로 설정한 연결이 실패한다.
2. 운영 CA는 유지하되 인증서 SAN에 없는 hostname/IP로 연결하면 실패한다.
3. 각 실패의 non-zero exit, 오류 분류, 시각을 증거로 보관하고 DSN secret은
   삭제한다.

근거:

- PostgreSQL libpq SSL: <https://www.postgresql.org/docs/current/libpq-ssl.html>
- PostgreSQL `pg_stat_ssl`: <https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-SSL-VIEW>

## 9. storage, snapshot, backup, WAL, 권한 증거

PostgreSQL 저장소 암호화는 DB 코드가 아니라 실제 provider/host 설정으로
증명한다. 다음 템플릿의 빈칸이 채워지기 전에는 Gate B를 PASS로 표시하지
않는다.

| control | resource | evidence link/command | observed value | owner | reviewer | checked_at | result |
|---|---|---|---|---|---|---|---|
| primary/replica/temp storage encryption |  |  |  |  |  |  | PASS/FAIL |
| automatic/manual snapshot encryption + key |  |  |  |  |  |  | PASS/FAIL |
| logical/physical backup encryption + key |  |  |  |  |  |  | PASS/FAIL |
| archived WAL encryption + key |  |  |  |  |  |  | PASS/FAIL |
| backup retention/expiry and expired-copy deletion |  |  |  |  |  |  | PASS/FAIL |
| backup location access control/audit |  |  |  |  |  |  | PASS/FAIL |
| isolated restore drill + encrypted restore storage |  |  |  |  |  |  | PASS/FAIL |
| writer least privilege |  |  |  |  |  |  | PASS/FAIL |
| purge SELECT/DELETE-only privilege |  |  |  |  |  |  | PASS/FAIL |
| DBA plaintext access approval/audit |  |  |  |  |  |  | PASS/FAIL |
| prompt copies/exports/backups retention policy |  |  |  |  |  |  | PASS/FAIL |

권한 증거 조회:

```sql
SELECT grantee, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'app'
  AND table_name IN (
    'ai_trace',
    'ai_model_call_log',
    'ai_prompt_log',
    'ai_agent_execution_log',
    'ai_error_log'
  )
ORDER BY grantee, table_name, privilege_type;
```

물리 base backup을 사용하는 환경은 해당 backup에 `pg_verifybackup`을 실행하고
결과를 보관한다. 이 검사는 restore drill을 대체하지 않는다. 격리 복원 환경에서
DB를 기동하고 AI 로그 sample의 trace→agent/model→prompt/error 연결을 조회한다.

근거:

- PostgreSQL encryption options: <https://www.postgresql.org/docs/current/encryption-options.html>
- PostgreSQL `pg_verifybackup`: <https://www.postgresql.org/docs/current/app-pgverifybackup.html>
- PostgreSQL continuous archiving: <https://www.postgresql.org/docs/current/continuous-archiving.html>
- OWASP Logging Cheat Sheet: <https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html>
- OWASP Secrets Management Cheat Sheet: <https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html#downtime-break-glass-backup-and-restore>
