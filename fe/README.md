# QuantAgent FE HI-FI 구현

Figma MCP에서 확인한 순수 `HI-FI ·` 프레임 기준의 React + TypeScript + Vite 프론트엔드입니다.

## 구현 route

| Route | 기준 Figma frame |
|---|---|
| `/` | `HI-FI · 07 — / 랜딩` |
| `/app` | `HI-FI · 08 — /app · 전체 탭`, `HI-FI · 09 — /app · 매매종목 정보 탭`, `HI-FI · 10 — /app · 수익률 탭` |
| `/reports` | `HI-FI · 14 — /reports 리포트 목록` |
| `/reports/:id` | `HI-FI · 11 — /reports/:id 리포트 상세` |

## 실행

```bash
npm install
npm run dev
npm run build
```

## Mock API

`src/api/quantAgentClient.ts`에서 다음 mock client를 제공합니다.

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
