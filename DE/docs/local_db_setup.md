# Local DB Setup: PostgreSQL + TimescaleDB

## 결론

로컬 개발 DB는 Docker Compose로 실행한다. 사용자가 DB를 수동으로 생성할 필요는 없고, `compose.yaml`이 TimescaleDB 컨테이너와 volume을 만든다.

## 전제 조건

| 항목 | 필요 |
|---|---|
| Docker Desktop | 설치 및 실행 |
| PowerShell | Windows 로컬 실행 |
| `.env` 사용 | 금지. 이 프로젝트의 `.env`는 읽거나 쓰지 않는다. |

## 1. 환경변수 설정

PowerShell 세션에만 비밀번호를 설정한다. 파일에 저장하지 않는다.

```powershell
$env:COMPOSE_DISABLE_ENV_FILE = "1"
$env:QUANT_DB_PASSWORD = "local-dev-password-change-me"
$env:QUANT_DB_NAME = "quant_agent"
$env:QUANT_DB_USER = "quant_agent"
$env:QUANT_DB_PORT = "5432"
```

`COMPOSE_DISABLE_ENV_FILE=1`은 Docker Compose가 repo의 `.env`를 자동으로 읽지 않도록 하기 위한 안전장치다.

## 2. DB 컨테이너 실행

```powershell
docker compose up -d db
```

상태 확인:

```powershell
docker compose ps db
```

## 3. 마이그레이션 적용

권장: 제공된 스크립트를 사용한다.

```powershell
.\scripts\apply_migrations.ps1
```

동일 작업을 직접 실행하려면:

```powershell
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U $env:QUANT_DB_USER -d $env:QUANT_DB_NAME -f /migrations/001_data_engineering_m0.sql
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U $env:QUANT_DB_USER -d $env:QUANT_DB_NAME -f /migrations/002_data_engineering_runtime.sql
```

## 4. 접속 문자열

애플리케이션이나 테스트에서 사용할 `DATABASE_URL`:

```powershell
$env:DATABASE_URL = "postgresql://$env:QUANT_DB_USER`:$env:QUANT_DB_PASSWORD@127.0.0.1:$env:QUANT_DB_PORT/$env:QUANT_DB_NAME"
```

## 5. 생성 확인

```powershell
docker compose exec -T db psql -U $env:QUANT_DB_USER -d $env:QUANT_DB_NAME -c "\dn"
docker compose exec -T db psql -U $env:QUANT_DB_USER -d $env:QUANT_DB_NAME -c "\dt meta.*"
docker compose exec -T db psql -U $env:QUANT_DB_USER -d $env:QUANT_DB_NAME -c "SELECT extname FROM pg_extension WHERE extname = 'timescaledb';"
```

기대 schema:

| Schema |
|---|
| `meta` |
| `raw` |
| `core` |
| `feature` |
| `mart` |

## 6. 중지와 재시작

컨테이너만 중지:

```powershell
docker compose stop db
```

다시 시작:

```powershell
docker compose up -d db
```

## 7. 데이터 초기화 주의

아래 명령은 DB volume을 삭제하므로 데이터가 사라진다. 명시적으로 초기화할 때만 사용한다.

```powershell
docker compose down -v
```

## 8. 다음 단계

DB가 준비되면 M1 source pilot 결과를 바탕으로 M2 subset backfill을 구현한다.

```powershell
python scripts/run_source_pilot.py --source both --symbol 005930 --krx-trade-date 2026-07-03 --start-date 2026-07-02 --end-date 2026-07-03
```

실제 적재 small-run:

```powershell
$env:QUANT_DB_EXECUTION_MODE = "docker"
python scripts/ingest_ohlcv.py --source KRX --start-date 2026-07-03 --end-date 2026-07-03 --db-mode docker
python scripts/compute_ta_indicators.py --start-date 2026-07-02 --end-date 2026-07-03 --symbols 005930 --db-mode docker
```
