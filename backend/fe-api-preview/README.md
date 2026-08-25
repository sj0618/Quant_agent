# QuantAgent FE API Preview

이 폴더는 원본 `fe/`를 수정하지 않고 실제 backend API + 실제 Google OAuth 로그인을 화면에서 확인하기 위한 복사본입니다.

이 미리보기에는 테스트 로그인이나 mock fallback을 넣지 않습니다. 로그인은 `/auth/google/start` → Google → `/auth/google/callback` 실제 플로우만 사용합니다.

## 필수 실행 조건

- PostgreSQL이 실행 중이어야 합니다.
- Redis가 실행 중이어야 합니다.
- Google Cloud OAuth 클라이언트가 있어야 합니다.
- Google Cloud OAuth 승인된 리디렉션 URI에 아래 값을 등록해야 합니다.

```text
http://127.0.0.1:5173/auth/google/callback
```

## backend 실행 환경변수 예시

`backend/.env`를 만들거나 PowerShell에서 같은 값을 설정하세요.

```env
APP_ENV=local
AUTH_ENABLED=true
DATABASE_URL=postgresql://USER:PASS@localhost:5432/DB
REDIS_URL=redis://localhost:6379/0

GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://127.0.0.1:5173/auth/google/callback

AUTH_PUBLIC_BACKEND_ORIGIN=http://127.0.0.1:8000
AUTH_ALLOWED_ORIGINS=http://127.0.0.1:5173
AUTH_ALLOWED_HOSTS=localhost,127.0.0.1
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_SAMESITE=lax
```

PowerShell로 직접 넣는 경우:

```powershell
cd backend
$env:APP_ENV="local"
$env:AUTH_ENABLED="true"
$env:DATABASE_URL="postgresql://USER:PASS@localhost:5432/DB"
$env:REDIS_URL="redis://localhost:6379/0"
$env:GOOGLE_CLIENT_ID="your-google-client-id.apps.googleusercontent.com"
$env:GOOGLE_CLIENT_SECRET="your-google-client-secret"
$env:GOOGLE_REDIRECT_URI="http://127.0.0.1:5173/auth/google/callback"
$env:AUTH_PUBLIC_BACKEND_ORIGIN="http://127.0.0.1:8000"
$env:AUTH_ALLOWED_ORIGINS="http://127.0.0.1:5173"
$env:AUTH_ALLOWED_HOSTS="localhost,127.0.0.1"
$env:AUTH_COOKIE_SECURE="false"
$env:AUTH_COOKIE_SAMESITE="lax"
py -m uvicorn app.main:app --reload --port 8000
```

## preview FE 실행

```powershell
cd backend\fe-api-preview
npm install
npm run dev
```

브라우저:

```text
http://127.0.0.1:5173
```

Vite 포트는 OAuth 리디렉션 URI와 맞아야 해서 `5173` 고정입니다. 포트가 이미 사용 중이면 기존 프로세스를 종료한 뒤 다시 실행하세요.

## 서버/local 구분

화면 오른쪽 아래 `API SERVER` 패널을 열면 호출별 출처가 표시됩니다.

- `SERVER`: backend API 응답을 렌더링함
- `LOCAL`: 브라우저 내부 화면 상태
- 서버 API 오류는 mock 데이터로 숨기지 않고 화면 오류로 노출합니다.

로그인은 `LOCAL` fallback 없이 실제 Google OAuth만 사용합니다.
