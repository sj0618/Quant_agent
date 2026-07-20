# 데일리 이메일 다이제스트 — BE 요구사항

작성일: 2026-07-06
범위: FE(전략 선택 체크박스, 이메일 미리보기)와 AI 백엔드(리포트 콘텐츠 생성)는 이번 스프린트에 구현 완료. **이 문서는 BE(백엔드)가 만들어야 하는 부분만 정리한다.**

## 배경

사용자가 리포트 목록 페이지(`/reports`)에서 최대 3개 전략을 체크박스로 선택하면, 그 3개를 묶어 매일 오전 8시(KST)에 "1전략 1리포트" 형식의 다이제스트 이메일을 받는다. 이메일 섹션 구성(Header → 오늘의 전체 요약 → 전략 비교표 → 전략별 상세 카드 → AI 종합 코멘트 → 상세보기 링크 → Footer)과 각 섹션의 콘텐츠 생성은 AI 백엔드가 담당하고, BE는 "구독 정보 저장"과 "크론 실행 + 이메일 발송"을 담당한다.

## 이미 만들어진 것 (BE가 재사용/호출만 하면 됨)

- **AI 콘텐츠 생성 API**: `POST /ai/daily-digest` (`ai/ai_graph/api.py`)
  - Request:
    ```json
    {
      "user_name": "string",
      "report_date": "string (예: 2026-06-29)",
      "strategies": [
        {
          "strategy_id": "string",
          "name": "string",
          "timeframe": "string",
          "today_signal": "BUY | HOLD | DROP",
          "targets": ["종목명", "..."],
          "metrics": { "sharpe_ratio": 0.0, "max_drawdown": 0.0, "win_rate": 0.0, "total_return": 0.0, "in_sample_sharpe": 0.0, "out_sample_sharpe": 0.0, "degradation": 0.0 },
          "win_rate": 0.0,
          "trade_count": 0
        }
      ]
    }
    ```
    `strategies`는 1~3개. `metrics`/`today_signal`은 BE가 각 전략의 최신 백테스트/시그널 결과에서 채워 넣어야 한다 (이 값들의 출처는 이미 존재하는 분석 job/백테스트 결과 저장소 — `ai/ai_graph/jobs.py`의 `AnalysisJobStore`나 그 결과를 옮겨 담은 BE 자체 테이블).
  - Response: `DailyDigestReport` (`ai/ai_graph/schemas.py`) — header/overall_summary/comparison_rows/strategy_cards/ai_overall_comment/market_brief/footer. FE의 `fe/src/types/quantagent.ts`의 `DailyDigestReport`와 1:1 대응(필드명만 snake_case↔camelCase 변환 필요).
  - 3개 초과 시 422 응답.
  - `market_brief`는 AOAI Web search 실패/미설정 시에도 항상 안전하게 빈 배열 + `fallback_reasons`로 응답한다 (다른 섹션 렌더를 막지 않음). Azure 세팅은 `ai/docs/azure-aoai-websearch-setup.md` 참고.

- **FE 구독 선택 UI**: `/reports` 페이지에서 체크박스로 최대 3개 전략 선택 (`fe/src/features/reports/ReportList.tsx`). 현재는 `fe/src/api/emailDigestClient.ts`가 **localStorage mock**으로 선택 상태를 저장한다 — 아래 "필요한 저장 API"로 교체되어야 한다.

- **FE 이메일 미리보기**: `/reports`의 "이메일 다이제스트 미리보기" 버튼 → `DailyDigestPreview` 컴포넌트가 실제 이메일과 동일한 7개 섹션을 렌더링한다 (`fe/src/features/reports/DailyDigestPreview.tsx`, mock 데이터는 `fe/src/mocks/dailyDigest.mock.ts`). 이메일 HTML 템플릿을 만들 때 이 컴포넌트의 섹션 구조/문구를 그대로 참고하면 된다.

## BE가 만들어야 하는 것

### 1. 구독 선택 저장

- 테이블(가칭) `email_digest_subscriptions`: `user_id`, `strategy_id`(또는 `strategy_name`), `created_at`. 사용자당 최대 3행 제약 (앱단 검증 + DB 제약 둘 다 권장).
- API(가칭):
  - `GET /me/email-digest/strategies` → 현재 선택된 전략 목록
  - `PUT /me/email-digest/strategies` → body `{ "strategy_ids": string[] }` (최대 3개, 초과 시 422) — 전체 교체 방식
  - FE의 `emailDigestClient.ts`(`getDigestStrategySelection`/`saveDigestStrategySelection`)는 이 두 엔드포인트를 호출하도록 그대로 교체 가능한 시그니처로 짜여 있다.
- 기존 `NotificationSettings.dailyReportEmail`(마이페이지 on/off, `fe/src/api/preferencesClient.ts`)과의 관계: `dailyReportEmail=false`면 선택 전략이 있어도 발송하지 않음 (기존 전역 옵트아웃이 우선).

### 2. 매일 08:00 KST 크론

1. `email_digest_subscriptions`에서 구독 중인 유저 전체를 조회 (`dailyReportEmail=true`인 유저만).
2. 유저별로 선택된 전략들의 최신 시그널/백테스트 지표를 조회해 `DailyDigestStrategyInput[]`로 변환.
3. `POST /ai/daily-digest` 호출 → `DailyDigestReport` 수신.
4. `DailyDigestReport`를 이메일 HTML로 렌더링 (템플릿은 `DailyDigestPreview.tsx` 구조 참고) 후 발송 수단(SES/SMTP/SendGrid 등, BE 결정)으로 발송.
5. 발송 성공/실패 로그 저장 — 기존 `fe/src/pages/ReportsPage.tsx`의 "리포트" 개념과 동일한 감사 로그 수준을 유지.

### 3. 재발송 / 구독취소 연결

- 기존 FE 훅이 이미 있다: `fe/src/api/reportActionsClient.ts`의 `resendReportEmail`, `fe/src/pages/UnsubscribePage.tsx`. 다이제스트 이메일도 같은 재발송/구독취소 플로우를 태우도록 이메일 발송 시 `report_id`(또는 `digest_id`)를 발급해 두면 기존 화면을 그대로 재사용할 수 있다.

### 4. 데이터 소스 확인 필요

- `DailyDigestStrategyInput.metrics`/`today_signal`을 채우려면 "선택된 전략의 오늘자 시그널 + 최신 백테스트 지표"를 조회할 수 있어야 한다. 현재 AI 그래프는 분석 job 단위로만 결과를 들고 있으므로(`AnalysisJobStore`), 전략 단위로 "가장 최근 실행 결과"를 조회하는 인덱스/뷰가 BE 쪽에 필요할 수 있다.

## 비범위 (이번 스프린트에서 안 함)

- 실제 이메일 발송 수단 연동, 크론 등록/스케줄러, 구독 테이블 마이그레이션, `graph.py`의 rebase 충돌 해결.
