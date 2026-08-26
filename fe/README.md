# QuantAgent FE HI-FI 구현

Figma MCP에서 확인한 순수 `HI-FI ·` 프레임 기준의 React + TypeScript + Vite 프론트엔드입니다.

## 구현 route

| Route | 기준 Figma frame |
|---|---|
| `/` | `HI-FI · 07 — / 랜딩` |
| `/app` | `HI-FI · 08 — /app · 전체 탭`, `HI-FI · 09 — /app · 매매종목 정보 탭`, `HI-FI · 10 — /app · 수익률 탭` |
| `/app/strategies/new` | 전략 생성 폼 |
| `/app/strategies/:id/edit` | 전략 수정 폼 |
| `/login` | Google 로그인 시작 |
| `/auth/google/callback` | Google OAuth callback 처리 |
| `/me`, `/me/notifications` | 마이페이지, 리포트 알림 설정 |
| `/reports` | `HI-FI · 14 — /reports 리포트 목록` |
| `/reports/:id` | `HI-FI · 11 — /reports/:id 리포트 상세` |
| `/search` | 전략·종목·리포트 통합 검색 |
| `/terms`, `/privacy`, `/disclaimer`, `/unsubscribe` | 정책, 면책, 수신 거부 |

## Rocky Linux Native 실행 전제 조건

- Rocky Linux 8.10 x86_64
- Native Bash
- Python 3.11.13 (pytest/스크립트 동기화)
- Node 24.15.0
- npm 11.12.1
- 로컬 회귀 검사는 외부 DB/Redis/OAuth/컨테이너 없이 실행 가능
- 실데이터 검증은 AI 서버에 PostgreSQL DSN과 AOAI Responses 설정 필요

## 환경변수

| Name | Purpose |
|---|---|
| `VITE_AI_API_BASE_URL` | production 빌드에서만 적용되는 AI API base URL (`/ai-api`는 dev에서 고정)
| `VITE_AUTH_API_BASE_URL` | Google OAuth 시작/콜백/로그아웃 API base URL |
| `VITE_STRATEGY_API_BASE_URL` | 전략 저장/분석 실행 API base URL |

## FE 설치

```bash
npm --prefix fe ci
```

## 실행

`npm run dev` 대신 아래 canonical 명령으로 FE를 직접 기동한다. direct Node/Vite를 leader로 쓰고, `npm` 래퍼 프로세스를 리더로 두지 않는다.

```bash
WORKTREE_ROOT=$(readlink -f "$(git rev-parse --show-toplevel)")
NODE_BIN=$(readlink -f "$(command -v node)")
VITE_ENTRY=$(readlink -f "$WORKTREE_ROOT/fe/node_modules/.bin/vite")
FE_ROOT=$(readlink -f "$WORKTREE_ROOT/fe")
[[ $FE_ROOT == "$WORKTREE_ROOT/fe" && $FE_ROOT == "$WORKTREE_ROOT/"* ]]
[[ -f "$FE_ROOT/index.html" && -f "$FE_ROOT/vite.config.ts" ]]
"$NODE_BIN" "$VITE_ENTRY" "$FE_ROOT" --host 127.0.0.1
```

- `fe/vite.config.ts`의 `server.proxy['/ai-api']`는 `http://127.0.0.1:18001`로 전달한다.
- SSH 포워딩은 `18000` 포트만 허용한다 (`-L 18000:127.0.0.1:18000`).
- 동일 브라우저 세션을 유지한다. QA 중 page reload/restart는 수행하지 않는다.

## 시작 fixture (동일 브라우저 세션, 세 개 키만 사용)

```javascript
const keys=["quantagent.auth.session.v1","quantagent.latest-analysis-job.v1","quantagent.chat-conversations.v1"];
keys.forEach((key)=>localStorage.removeItem(key));
console.assert(keys.every((key)=>localStorage.getItem(key)===null));
localStorage.setItem("quantagent.auth.session.v1",JSON.stringify({user:{id:"local-mvp-fixture",name:"Local MVP Fixture",email:"local-mvp@example.invalid",provider:"test"}}));
location.assign("/app");
```

## 종료 evidence (same-session 기준)

```javascript
const keys=["quantagent.auth.session.v1","quantagent.latest-analysis-job.v1","quantagent.chat-conversations.v1"];
keys.forEach((key)=>localStorage.removeItem(key));
const evidence={origin:location.origin,values:keys.map((key)=>localStorage.getItem(key))};
console.log(JSON.stringify(evidence));
console.assert(evidence.origin==="http://127.0.0.1:18000"&&evidence.values.every((value)=>value===null));
```

## Human QA 범위

- **ready**:
  - Overview의 `result.strategy_spec.name`
  - Performance 탭의 `result.user_payload.performance.selected_candidate_id`와 metrics
  - recent report detail의 `web_projection.title`, summary→conclusion, `sections[*].title`
- **표시 증거에서 제외**: `sections[*].items`, email projection, 종목별 근거 계약이 없는 recipient/candidates/signal axes
- **clarification**: clarification 상태 메시지와 정확히 `3`개 candidate card만 확인한다. question/options UI는 요구하지 않는다.
- **AI-down**: FE 자체는 200을 유지하고 새 분석 요청은 오류 UI를 표시하며 새 ready 결과를 만들지 않아야 한다.
- Google OAuth 성공, page reload, AI process restart 뒤 복원은 이 MVP 범위 밖이다.

## 데이터/API 경계
`src/api/quantAgentClient.ts`는 backend API의 읽기 전용 리포트와 AI API의 자연어 전략 analysis job을 함께 사용한다. 결과는 browser cache가 아니라 server job을 polling해 받는다. `import.meta.env.DEV`에서는 AI base URL이 `/ai-api`로 고정되고 production 빌드에서만 `VITE_AI_API_BASE_URL`이 적용된다.
- **정적 샘플**: 랜딩 페이지의 제품 소개용 `landingSample`만 정적 콘텐츠다. 제품 워크스페이스나 리포트 데이터로 사용하지 않는다.
- **리포트 보관 API**: `quantAgentClient.ts`는 읽기 전용 `GET /reports`와 `GET /reports/:id`만 사용한다. 보관 시각은 명시적 `createdAt`만 표시하며, 없는 값은 미확인으로 처리한다.
- **리서치 API**: `researchClient.ts`의 `POST /api/strategies/parse`와 `POST /api/research/jobs`는 비개인화 리서치 계약 검토·결과 조회 흐름이다. 과거 분석 job/run 생성·polling·SSE를 대체하거나 현재 투자 결과를 보장하지 않는다.
- **보관 화면**: 재발송과 과거 job 캐시 fallback은 제공하지 않는다. 새 분석은 `/app` 전략 검증 워크스페이스에서 server job으로 시작한다. 결과가 없거나 근거가 부족하면 성과 수치 대신 안전한 unavailable 상태를 표시한다.
- **사용자 격리**: 보호 route 진입 전에 backend `/auth/me`로 Redis session을 검증한다. 로그아웃·사용자 변경 시 사용자 범위 캐시를 함께 삭제하고, 보호된 조회의 `401`/`403`/`404`는 캐시 fallback 없이 오류로 처리한다.

보관된 결과에 없는 종목 후보, 신호 축, 수신자, 매크로 이벤트는 채워 넣지 않고 화면에 미제공 상태를 표시한다. 랜딩 CTA는 로그인 뒤 `/app` 전략 검증 워크스페이스로 연결된다.

## 검증

```bash
npm run test
```

`npm run test`는 Node 기본 회귀 검사, `tsc -b --pretty false`, `vite build`를 순차 실행합니다.
