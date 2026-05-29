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

## 환경변수

| Name | Purpose |
|---|---|
| `VITE_AI_API_BASE_URL` | QuantAgent AI `/analysis-jobs` API base URL |
| `VITE_AUTH_API_BASE_URL` | Google OAuth 시작/콜백/로그아웃 API base URL |
| `VITE_REPORT_ACTION_API_BASE_URL` | 리포트 이메일 재발송 API base URL |
| `VITE_STRATEGY_API_BASE_URL` | 전략 저장/분석 실행 API base URL |
| `VITE_ENABLE_TEST_LOGIN` | 인증 백엔드 통합 전 로컬 테스트 로그인 버튼 활성화 (`1`이면 활성화) |

## 실행

```bash
npm install
npm run dev
npm run build
```

## Mock API

`src/api/quantAgentClient.ts`는 `VITE_AI_API_BASE_URL`이 설정된 경우 AI
`/analysis-jobs`를 호출하고, AI가 아직 제공하지 않는 목록/성과/랜딩 데이터는
기존 mock fixture를 fallback으로 사용합니다.

- `getLandingSample()`
- `getAppOverview()`
- `getTradingCandidates()`
- `getPerformanceSummary()`
- `getReports()`
- `getReportById()`
- `getAnalysisJobStatus()`

AI envelope는 `status`, `trace_id`, `schema_version`, `user_payload`, `strategy_spec`, `debug_ref`, `retryable` 필드를 유지합니다. `internal_payload`는 화면에 노출하지 않습니다.

## 검증

```bash
npm run test
```

`npm run test`는 `tsc -b --pretty false`와 `vite build`를 순차 실행합니다.
