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
- 외부 DB/Redis/OAuth/컨테이너 없이 loopback FE→AI fixture spine을 검증

## 환경변수

| Name | Purpose |
|---|---|
| `VITE_AI_API_BASE_URL` | production 빌드에서만 적용되는 AI API base URL (`/ai-api`는 dev에서 고정)
| `VITE_AUTH_API_BASE_URL` | Google OAuth 시작/콜백/로그아웃 API base URL |
| `VITE_REPORT_ACTION_API_BASE_URL` | 리포트 이메일 재발송 API base URL |
| `VITE_STRATEGY_API_BASE_URL` | 전략 저장/분석 실행 API base URL |
| `VITE_ENABLE_TEST_LOGIN` (TEMP, dev-auth-gate) | 인증 백엔드 통합 전 로컬 테스트 로그인 버튼 활성화 (`1`이면 활성화) |
| `VITE_SITE_PASSWORD_ENTRIES` (TEMP, dev-auth-gate) | 랜딩 페이지 비밀번호 팝업이 허용하는 `salt:hash:expiresAt` 목록 (콤마 구분, 비어있으면 비활성화). `node scripts/generate-site-gate-entries.mjs`로 발급/재발급 |

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
localStorage.setItem("quantagent.auth.session.v1",JSON.stringify({user:{id:"local-mvp-fixture",name:"Local MVP Fixture",email:"local-mvp@example.invalid",provider:"google"}}));
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
- **표시 증거에서 제외**: `sections[*].items`, email projection, fixture recipient/candidates/signal axes
- **clarification**: clarification 상태 메시지와 정확히 `3`개 candidate card만 확인한다. question/options UI는 요구하지 않는다.
- **AI-down**: FE 자체는 200을 유지하고 새 분석 요청은 오류 UI를 표시하며 새 ready 결과를 만들지 않아야 한다.
- Google OAuth 성공, page reload, AI process restart 뒤 복원은 이 MVP 범위 밖이다.

## Mock API
`src/api/quantAgentClient.ts`는 `appConfig.aiApiBaseUrl`를 사용한다. `import.meta.env.DEV`에서는 항상 `/ai-api`로 고정되고, production 빌드에서만 `VITE_AI_API_BASE_URL`이 적용된다.
- **always-mock**: `getLandingSample`, `getTradingCandidates`, `getPerformanceSummary`, `getWorkspaceTemplate`, `getEmailDigestHistory`는 AI와 무관하게 fixture 데이터를 반환한다.
- **AI create/poll**: `createAnalysisJob`/`getAnalysisJob`/`getAnalysisJobStatus`는 `/analysis-jobs` API를 직접 호출해 job 생성·조회·폴링 상태를 최신 상태로 유지한다.
- **hybrid projection**: `getAppOverview`, `getReports`, `getReportById`는 fixture 기본값을 시작점으로 두고 최신 AI job이 있으면 결과를 overlay한다.
- **UI evidence source**
  - AI 유래: `result.status`, `result.trace_id`, `result.user_payload` 기반 `performance`·`report.web_projection`, stage/job 상태
  - fixture 유래: 초깃값/목록형 템플릿(`tradingCandidates`, `performanceSummary`, `reportSummary`, `candidates`, `signalAxes`, `recipient` 등)

`AI API`를 실제 UI payload로 사용하지 못할 때는 fixture fallback으로 렌더링을 이어가므로 화면에서 AI-derived와 fixture-derived 필드를 구분해 보는 것이 중요하다.
`/analysis-jobs` 응답은 화면 contract상 노출 대상인 `status`, `trace_id`, `schema_version`, `strategy_spec`, `debug_ref`, `retryable`, `user_payload`만 유지한다. `internal_payload`는 화면 노출하지 않는다.

## 검증

```bash
npm run test
```

`npm run test`는 `tsc -b --pretty false`와 `vite build`를 순차 실행합니다.
