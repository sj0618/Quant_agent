# 구현 필요 페이지 정리 및 반영 현황

작성일: 2026-05-28  
반영일: 2026-05-28  
범위: React 목업 코드와 README 기준으로, 버튼/링크/텍스트는 있으나 실제 페이지 또는 동작이 없던 영역을 정리하고 구현 반영 상태를 추적한다.

## 결론

초기에는 명시적으로 구현된 라우트가 `/`, `/app`, `/reports`, `/reports/:id` 4개뿐이었다. 2026-05-28 반영분에서 Google 로그인 진입/콜백, 마이페이지/알림 설정, 리포트 필터와 액션, 검색, 정책/수신거부, 전략 생성/수정, FAQ 상호작용을 프론트 라우트와 UI 동작으로 연결했다.

| 구현 대상 | 상태 | 구현 위치 |
|---|---|---|
| Google 로그인/세션 | 반영 | `src/pages/LoginPage.tsx`, `src/pages/AuthCallbackPage.tsx`, `src/api/authClient.ts` |
| 마이페이지/알림 설정 | 반영 | `src/pages/ProfilePage.tsx`, `src/api/preferencesClient.ts` |
| `/reports` 세부 설정 | 반영 | `src/pages/ReportsPage.tsx`, `src/features/reports/ReportList.tsx`, `src/features/reports/reportFilters.ts` |
| 리포트 내보내기/공유/재발송 | 반영 | `src/api/reportActionsClient.ts`, `src/pages/ReportDetailPage.tsx`, `src/features/reports/ReportList.tsx` |
| 전략 관리 | 반영 | `src/pages/StrategyFormPage.tsx`, `src/api/strategyClient.ts` |
| 전역 검색 | 반영 | `src/pages/SearchPage.tsx`, `src/components/layout/TopBar.tsx` |
| 정책/수신거부 | 반영 | `src/pages/LegalPage.tsx`, `src/pages/UnsubscribePage.tsx`, `src/components/layout/Footer.tsx` |
| 성과 탭 세부 동작 | 반영 | `src/features/app/PerformanceTab.tsx`, `src/features/app/PerformanceChart.tsx` |
| FAQ 상호작용 | 반영 | `src/pages/LandingPage.tsx`, `src/mocks/landing.mock.ts` |

| 우선순위 | 구현 대상 | 권장 라우트 | 현재 상태 | 필요한 구현 |
|---|---|---|---|---|
| P0 | Google 로그인/세션 | `/login`, `/auth/google/callback` | 랜딩 CTA가 `/app`으로 바로 이동 | Google OAuth 시작, 콜백 처리, 세션 저장, 비로그인 접근 보호, 로그인 실패/취소 화면 |
| P0 | 마이페이지/알림 설정 | `/me`, `/me/notifications` | TopBar에 "마이페이지"가 비활성 텍스트 | 사용자 프로필, 이메일, Daily 리포트 수신 설정, 로그아웃, 약관/개인정보 동의 상태 |
| P1 | `/reports` 세부 설정 | `/reports` 내 필터 패널 또는 `/reports/settings` | 필터/날짜/점수 UI가 정적 | 기간/전략/신호/권장도 필터 상태, URL query 동기화, 초기화/적용, 빈 결과 상태 |
| P1 | 리포트 내보내기/공유 | `/reports`, `/reports/:id` | PDF/CSV/공유/재발송 버튼만 존재 | PDF 다운로드, CSV export, 공유 링크 생성/복사, 이메일 재발송, 액션 성공/실패 상태 |
| P1 | 전략 관리 | `/app/strategies/new`, `/app/strategies/:id/edit` | 새 대화, 전략 수정, 비활성화 버튼만 존재 | 전략 생성/수정 폼, 비활성화 확인, 분석 실행 상태, 결과 화면 연결 |
| P2 | 전역 검색 | `/search` 또는 command palette | 검색 pill만 표시 | 전략/종목/리포트 검색, 키보드 단축키, 검색 결과 empty/loading/error |
| P2 | 정책/수신거부 | `/terms`, `/privacy`, `/disclaimer`, `/unsubscribe` | Footer/리포트 하단 텍스트 또는 홈 링크 | 약관/개인정보/면책 문서 페이지, 이메일 수신거부 처리 |
| P2 | 성과 탭 세부 동작 | `/app?tab=performance` 유지 | 원본 전략/A-B/CSV 버튼이 정적 | 원본/AI 개선본/동시보기 전환, CSV export, 차트 범위 옵션 |
| P3 | FAQ 상호작용 | `/` 유지 | FAQ 첫 항목만 펼쳐진 정적 UI | 아코디언 토글, 전체 답변 데이터, 접근성 상태 |

## 초기 근거

| 사실 | 근거 |
|---|---|
| README가 구현 라우트를 `/`, `/app`, `/reports`, `/reports/:id`로 한정한다. | `README.md:5-12` |
| 실제 라우팅도 `window.location.pathname`으로 위 4개 라우트만 분기한다. | `src/App.tsx:10-27` |
| `package.json` 의존성은 `react`, `react-dom`뿐이라 라우터/인증 SDK가 없다. | `package.json:13-16` |
| 랜딩의 로그인/Google CTA는 인증 화면이 아니라 `/app`으로 직접 이동한다. | `src/pages/LandingPage.tsx:34-35`, `src/pages/LandingPage.tsx:51`, `src/pages/LandingPage.tsx:167` |
| 랜딩 카피는 "Google 로그인 30초"를 약속하지만 구현은 없다. | `src/pages/LandingPage.tsx:166` |
| TopBar의 마이페이지는 비활성 텍스트이고 사용자명은 `홍길동` 고정 표시다. | `src/components/layout/TopBar.tsx:19`, `src/components/layout/TopBar.tsx:28-30` |
| 리포트 목록의 기간/전략/신호/직접입력/권장도 필터는 UI만 있고 상태/핸들러가 없다. | `src/features/reports/ReportList.tsx:17-39` |
| 리포트 목록 상단의 전체 PDF/CSV 버튼은 `type="button"`만 있고 동작이 없다. | `src/pages/ReportsPage.tsx:30-33` |
| 리포트 상세의 이메일 재발송/PDF 저장/공유 링크 버튼은 동작이 없다. | `src/pages/ReportDetailPage.tsx:32-36` |
| 리포트 목록의 PDF/공유/재발송 버튼도 정적이다. | `src/features/reports/ReportList.tsx:138-142` |
| 리포트 안내 문구는 "마이페이지 > 알림 설정"을 전제로 하지만 해당 페이지가 없다. | `src/features/reports/ReportList.tsx:83-87` |
| 전략 수정/비활성화 버튼과 채팅 입력/새 대화 버튼은 실제 전략 관리 흐름이 없다. | `src/features/app/OverviewTab.tsx:38-40`, `src/features/app/StrategyInputPanel.tsx:17`, `src/features/app/StrategyInputPanel.tsx:37-44` |
| 전역 검색 pill은 표시만 있고 입력/검색 페이지/command palette가 없다. | `src/components/layout/TopBar.tsx:23-27` |
| Footer의 이용약관/개인정보처리방침/면책/수신 거부는 링크가 아닌 텍스트다. | `src/components/layout/Footer.tsx:11-15` |
| 리포트 상세 하단의 수신 거부/수신 정책은 모두 홈(`/`)으로 연결된다. | `src/features/reports/ReportDetail.tsx:133-136` |
| API 계층은 mock 데이터 지연 응답만 제공한다. | `src/api/quantAgentClient.ts:1-3`, `src/api/quantAgentClient.ts:14-22`, `src/api/quantAgentClient.ts:25-61` |

## 권장 구현 순서

| 순서 | 작업 | 이유 | 완료 기준 |
|---|---|---|---|
| 1 | 인증/세션 골격 | 랜딩 CTA와 보호 페이지의 전제가 됨 | `/login`에서 Google OAuth 시작, 콜백 후 `/app` 진입, 실패 상태 표시 |
| 2 | 마이페이지/알림 설정 | 리포트 수신 설정과 사용자 상태의 홈 | `/me/notifications`에서 Daily 리포트 이메일 수신 on/off 저장 |
| 3 | 리포트 필터/설정 | 사용자가 직접 언급한 `/reports` 세부 설정 | 필터 적용 시 목록/URL query/empty state가 함께 변함 |
| 4 | 리포트 액션 | 기존 버튼의 기대 동작을 채움 | PDF/CSV/공유/재발송의 성공/실패 피드백 |
| 5 | 전략 관리 | `/app` 버튼들이 실제 workflow로 이어짐 | 새 전략, 수정, 비활성화, 분석 재실행 흐름 |
| 6 | 정책/수신거부/검색 | 랜딩과 리포트 하단의 보조 신뢰 기능 | 링크가 실제 페이지로 이동하고 기본 상태를 표시 |

## 페이지별 세부 요구

### `/login`, `/auth/google/callback`

| 항목 | 요구 |
|---|---|
| 진입점 | 랜딩의 로그인, Google 시작 CTA |
| UI 상태 | 기본, 로딩, 실패, 취소, 이미 로그인됨 |
| 데이터 | Google OAuth redirect URL, callback code/state, 사용자 세션 |
| 연결 | 로그인 성공 후 원래 목적지 또는 `/app` 이동 |
| 주의 | client id, redirect URI, API base URL은 환경변수/설정으로 관리 |

### `/me`, `/me/notifications`

| 항목 | 요구 |
|---|---|
| 진입점 | TopBar 마이페이지, 리포트 TIP의 알림 설정 |
| UI 상태 | 프로필 정보, 이메일, 로그아웃, 수신 설정 |
| 데이터 | 사용자 프로필, 이메일 수신 여부, 약관 동의 상태 |
| 연결 | 리포트 이메일 재발송/수신거부와 설정 일관성 유지 |

### `/reports` 필터/설정

| 항목 | 요구 |
|---|---|
| 필터 | 기간, 전략, 포함 신호, 직접 날짜, 최소 권장도 |
| 동작 | 초기화, 적용, query string 동기화, 결과 개수 표시 |
| 상태 | loading, empty, error, filtered-empty |
| 확장 | 세부 설정이 커지면 `/reports/settings` 또는 우측 drawer로 분리 |

### `/reports`, `/reports/:id` 액션

| 항목 | 요구 |
|---|---|
| PDF | 목록 전체 PDF, 개별 PDF 저장 |
| CSV | 목록 CSV, 성과 탭 CSV |
| 공유 | 공유 링크 생성, 클립보드 복사, 만료/권한 안내 |
| 재발송 | 이메일 재발송 요청, 성공/실패 토스트 |

### `/app/strategies/new`, `/app/strategies/:id/edit`

| 항목 | 요구 |
|---|---|
| 생성 | 자연어 전략 입력, 분석 실행, 진행 단계 표시 |
| 수정 | 기존 StrategySpec 편집, 재분석, 결과 반영 |
| 비활성화 | 확인 모달, 비활성 상태, 재활성화 진입 |
| 연결 | `/app` 탭과 최근 리포트 생성 흐름 |

## 비범위

| 제외 | 이유 |
|---|---|
| 실제 투자/주문 기능 | 현재 목업은 분석/리포트 중심이고 주문 UI가 없다. |
| 신규 디자인 시스템 재작성 | 현재 컴포넌트와 CSS 토큰 기반 확장이 더 안전하다. |
| 백엔드 API 계약 확정 | 현재 프론트는 mock client만 있으므로 별도 API 계약 문서가 필요하다. |
| 의존성 추가 확정 | OAuth/라우팅/상태관리 방식은 구현 전 기술 결정이 필요하다. |

## 결정 필요

| 결정 | 권장안 | 사유 |
|---|---|---|
| 라우터 도입 | `react-router` 또는 기존 경량 라우팅 중 택일 | 보호 라우트, callback, nested settings가 늘어나면 현재 pathname 분기는 유지보수 비용이 커진다. |
| 인증 방식 | 백엔드 세션 기반 Google OAuth | client secret 노출을 피하고 API 연동/세션 만료 처리가 단순해진다. |
| 리포트 세부 설정 위치 | 1차는 `/reports` 내부 패널, 커지면 `/reports/settings` | 현재 목업의 필터가 목록 페이지 맥락 안에 있어 첫 구현 비용이 낮다. |
| 마이페이지 범위 | 프로필 + 알림 설정 + 로그아웃부터 | 리포트 수신과 Google 로그인의 최소 완성 흐름이다. |

## 검증 체크리스트

| 기능 | 확인 |
|---|---|
| 랜딩 CTA | 로그인 전 CTA가 `/login`으로 가고 로그인 후 목적지로 복귀 |
| 보호 페이지 | 비로그인 상태에서 `/app`, `/reports` 접근 시 로그인 유도 |
| `/reports` 필터 | 필터 적용/초기화가 목록과 URL query에 반영 |
| 리포트 액션 | PDF/CSV/공유/재발송 성공/실패 상태 표시 |
| 마이페이지 | 알림 설정 저장 후 리포트 TIP/수신거부 흐름과 충돌 없음 |
| 정책 링크 | Footer와 리포트 하단 링크가 실제 문서/수신거부 페이지로 이동 |
