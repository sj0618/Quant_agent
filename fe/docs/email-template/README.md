# 데일리 다이제스트 이메일 템플릿 (BE 핸드오프)

FE가 만든 이메일 HTML 템플릿과 그 렌더 결과물이다. 발송 요구사항(구독 저장, 08:00 KST 크론,
재발송/구독취소)은 `ai/docs/email-digest-be-requirements.md`를 따르고, 이 문서는 **본문 HTML**만 다룬다.

## 파일

| 경로 | 역할 |
| --- | --- |
| `fe/src/features/reports/DailyDigestEmail.tsx` | `<DailyDigestEmail digest baseUrl />` 컴포넌트 + `renderDailyDigestEmailHtml(props)`. 나머지 FE와 같은 React/TSX이고, 발송용 HTML 문자열은 `renderToStaticMarkup`으로 뽑는다. |
| `fe/docs/email-template/daily-digest.sample.html` | 위 컴포넌트 + `dailyDigest.mock.ts`로 생성한 실제 이메일 HTML. 브라우저나 메일 클라이언트로 바로 열어보면 된다. |
| `fe/scripts/generate-daily-digest-email.mjs` | 샘플 재생성 스크립트. |
| `/dev/email-template` | 예비 라우트. 로그인 없이 열리고, iframe 미리보기 + HTML 복사/다운로드 + 구성안 대조표를 보여준다. |

샘플 재생성:

```bash
node fe/scripts/generate-daily-digest-email.mjs
```

node 22는 `.tsx`를 직접 실행할 수 없어서(`ERR_UNKNOWN_FILE_EXTENSION`) 이 스크립트는 vite의
`ssrLoadModule`로 컴포넌트를 로드한다.

## 입력

`POST /ai/daily-digest`가 돌려주는 `DailyDigestReport` 그대로다 (`ai/ai_graph/schemas.py` ↔
`fe/src/types/quantagent.ts`, snake_case↔camelCase만 변환). 별도 view model이 없다.

제목은 `dailyDigestEmailSubject(digest)`가 만든다 → `[QuantAgent] 2026-06-29 데일리 전략 리포트`.

렌더는 두 갈래로 쓸 수 있다.

- **컴포넌트로**: `<DailyDigestEmail digest={digest} baseUrl="https://..." />` — FE 화면에 그대로 붙일 때.
- **HTML 문자열로**: `renderDailyDigestEmailHtml({ digest, baseUrl })` — 발송/저장용. doctype과 `<head>`까지 붙은
  완성된 문서를 돌려준다. `<title>`/`<meta>`는 React 19가 head로 hoist 하면서 순서를 흔들기 때문에 컴포넌트 밖에서
  문자열로 조립한다.

## 섹션 구성 (구성안 대조)

| 구성안 | 섹션 | 데이터 |
| --- | --- | --- |
| 1 | Header | `header.reportDate` / `userName` / `strategyCount` |
| 2 | 오늘의 전체 요약 | `overallSummary[]` |
| 3 | 전략 비교표 | `comparisonRows[]` (전략명 / 오늘 신호 / 수익률 / MDD / Sharpe / 상태) |
| 4 | 전략별 상세 카드 | `strategyCards[]` (신호 / 대상 종목 / 성과 5항목 / AI 해석 / 주의사항) |
| 5 | AI 종합 코멘트 | `aiOverallComment` |
| 추가 | 시황 및 경제 기사 | `marketBrief.headline` / `items[]` |
| 6 | 상세보기 링크 | `baseUrl` + `/reports`, `/app` |
| 7 | Footer | `footer[]` + 수신 거부 / 알림 설정 링크 |

## 서버 템플릿으로 옮길 때 지켜야 하는 것

- **`baseUrl`은 항상 절대 주소.** 메일 클라이언트에는 페이지 컨텍스트가 없어 상대 경로 링크가 조용히 깨진다.
- **table + inline style만.** Gmail/Outlook/Naver가 `<style>` 블록, flex, grid, CSS 변수를 제거한다.
  앱 컴포넌트와 달리 `className`을 쓰지 않고 `styles/tokens.ts` 값을 hex 리터럴로 복제해 둔 이유다.
- **모든 문자열은 이스케이프.** 본문 대부분이 LLM 생성 텍스트다. FE는 React가 자동으로 처리하지만,
  Jinja 등으로 옮길 때는 autoescape가 켜져 있는지 확인해야 한다.
- **`marketBrief.items`가 비면 시황 섹션만 안내 문구로 대체**되고 나머지 섹션은 그대로 렌더된다.
  AOAI web search 미설정/실패 시 빈 배열 + `fallback_reasons`로 오기 때문이다.

## 결정 필요

- **WATCH 신호가 타입에 없다.** 구성안 3번 표에는 `WATCH`(관망)가 있지만 `SignalType`은 BUY / HOLD / DROP뿐이다.
  현재 mock은 관망 전략을 `DROP`으로 넣어뒀는데 DROP은 매도라 의미가 다르다. AI 응답 스키마에 WATCH를 추가할지
  결정이 필요하고, 그때까지 비교표의 `status`("주목/유지/관망") 컬럼이 관망 여부를 실제로 알려주는 유일한 값이다.
- **제목 날짜 형식.** 제목은 `2026-06-29`, 본문 `header.reportDate`는 `2026년 6월 29일`이다. 지금은 본문 값을
  파싱해서 변환하니, BE가 ISO 날짜를 따로 들고 있으면 `options.subjectDate`로 넘기는 편이 안전하다.
