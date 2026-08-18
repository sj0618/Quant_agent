# QuantAgent UX 상태·증적 행렬

## 공통 판정

- 화면 PASS는 HTTP 200이 아니라 기대 문구·다음 행동·DOM·network·console·스크린샷·접근성 조건을 모두 만족할 때만 가능하다.
- `미검증`은 실패도 PASS도 아니다. 유효한 테스트 세션 또는 사람이 남긴 증적이 들어오기 전까지 출시 판정에서 제외하지 않고 blocker로 센다.
- 모든 공개 사실형 수치에는 `claim ID | source | as-of | 검증 명령 | sample/live 표시 정책`을 연결한다.
- 모든 공개 화면은 키보드 Tab 순서, 보이는 focus, `h1` 하나, landmark, 390×844와 1280×720 viewport의 가로 overflow 0을 공통 PASS 조건으로 한다.

| UX ID | URL·viewport | 인증·seed | 시나리오와 기대 결과 | 증적 필드 | 현 상태 | WBS |
|---|---|---|---|---|---|---|
| UX-PUB-01 | `/`, 1280×720·1440×900 | 비인증·없음 | 랜딩의 수치가 sample이면 sample·as-of·제한을 보이고, live가 아니면 실적처럼 말하지 않는다. | DOM, screenshot, console 0, claim ledger | FAIL: `landing.mock`에서 온 수치가 사실형으로 보임 | UX-CLAIM-01 |
| UX-PUB-02 | `/reports/2026-04-18`, 1280×720 | 비인증·없음 | 샘플 CTA는 로그인 벽이 아니라 공개 sample을 열거나, 로그인 이유·복귀·대체 행동을 보인다. | click trace, heading, return URL, screenshot | FAIL: CTA가 protected route로 감 | UX-CTA-01 |
| UX-PUB-03 | `/dev/email-template`, 1280×720 | 비인증·없음 | dev route는 production에서 404 또는 권한 거부이며 mock·내부 경로를 공개하지 않는다. | status, DOM, response headers, screenshot | FAIL: HTTP 200·내부 문구 노출 | UX-ROUTE-01 |
| UX-PUB-04 | 임의 존재하지 않는 route, 1280×720 | 비인증·없음 | 실제 404와 사용자용 복귀 행동을 보이며 Figma·내부 구현 문구를 보이지 않는다. | status, DOM, console, screenshot | FAIL: HTTP 200·내부 문구 | UX-ROUTE-02 |
| UX-PUB-05 | `/`, 1280×720 | 비인증·없음 | production HTML은 dev client·source module·localhost HMR 연결을 포함하지 않는다. | response body, network, console 0 | FAIL: `/@vite/client`, `/src/main.tsx`, HMR 실패 | UX-BUILD-01 |
| UX-PUB-06 | `/app`, `/reports/:id`, 1280×720 | 비인증·없음 | 로그인 필요 이유, 접근성 있는 heading, 로그인 뒤 돌아갈 주소, 안전한 이전 행동을 보인다. | heading role, keyboard, return param, screenshot | FAIL: heading·복귀 계약 미흡 | UX-AUTH-01 |
| UX-MOB-01 | `/`, 390×844 | 비인증·없음 | navigation, CTA, 수치 표가 가로로 잘리지 않고 키보드 focus가 보인다. | DOM width, screenshot, axe, click trace | 미검증 | UX-MOB-01 |
| UX-MOB-02 | `/app`, `/reports/:id`, 존재하지 않는 route, 390×844 | 비인증·없음 | auth wall·샘플 대체 행동·404가 한 화면에서 이해 가능하고 overflow가 없다. | DOM width, heading, screenshot, axe | 미검증 | UX-MOB-02 |
| UX-AUTH-01 | `/login`, 1280×720 | 잘못된 테스트 credential·사람 제공 | 로그인 실패는 인증 실패 문구·재시도 행동을 보이고 보호 데이터와 내부 사유를 노출하지 않는다. | exact status, DOM, screenshot, a11y | 미검증 | UX-AUTH-02 |
| UX-AUTH-02 | `/app`, 1280×720 | 유효한 테스트 세션·사람 제공 | 정상 로그인·redirect·세션 갱신·로그아웃을 확인한다. | test account provenance, Playwright trace, network, screenshot | 미검증 | UX-AUTH-03 |
| UX-AUTH-03 | `/app`, 1280×720 | 만료된 테스트 세션·사람 제공 | 세션 만료 시 데이터 노출 없이 이유·재로그인·복귀 행동을 보인다. | trace, DOM, screenshot, a11y | 미검증 | UX-AUTH-04 |
| UX-AUTH-04 | protected read route, 1280×720 | rate-limit fixture·사람 제공 | rate limit은 보호 데이터 없이 기다림·복귀 행동을 보인다. | exact status/code, DOM, screenshot | 미검증 | UX-AUTH-05 |
| UX-EVAL-01 | internal release evaluator | local release profile·DSN 없음 | evaluator는 readiness FAIL을 내며 public create·추천·양수 metric을 만들지 않는다. | exact exit code/output, API body, no-create assertion | 미검증: 구현 전 | FT-RLS-01 |
| UX-EVAL-02 | internal release evaluator | local release profile·DB 연결 실패 | evaluator는 DB 실패 범주를 기록하고 mock·cache로 성공하지 않는다. | exact exit code/output, no-mock assertion | 미검증: 구현 전 | FT-DB-02 |
| UX-EVAL-03 | internal release evaluator | provider timeout | evaluator는 provider failure를 기록하고 생성 결과·추천을 만들지 않는다. | exact exit code/output, no-result assertion | 미검증: 구현 전 | FT-LLM-03 |
| UX-EVAL-04 | internal release evaluator | schema mismatch | evaluator는 schema error를 반환하고 0 또는 과거 결과를 채우지 않는다. | exact exit code/output, no-zero-fill assertion | 미검증: 구현 전 | FT-SCH-04 |
| UX-EVAL-05 | internal release evaluator | 빈 응답 | evaluator는 empty result를 별도 error code로 반환한다. | exact exit code/output, no-cache assertion | 미검증: 구현 전 | FT-EMPTY-05 |
| UX-EVAL-06 | internal release evaluator | L4 증적 없음 | evaluator는 생성한 fixture 증적 없이 `provenance_absent`로 실패한다. | exact exit code/output, fixture assertion | 미검증: 구현 전 | FT-L4-06 |
| UX-EVAL-07 | internal release evaluator | persistent job store 없음 | evaluator는 new job을 만들지 않고 내구성 미충족으로 실패한다. | exact exit code/output, restart trace | 미검증: 구현 전 | FT-JOB-07 |
| UX-EVAL-08 | development profile | 명시적 fixture | fixture 배지·입력 한계·추천 차단이 있고 release profile에서는 해당 mode가 부팅하지 않는다. | profile proof, DOM, screenshot | 미검증: 구현 전 | FT-FIX-08 |
| UX-ARCH-01 | read-only report, 1280×720 | stale input | stale record는 수치 대신 `현재 검증할 수 없음`, as-of, 보관 목록 행동을 보인다. | contract response, DOM, screenshot | 미검증: 구현 전 | MT-STALE-01 |
| UX-ARCH-02 | read-only report, 1280×720 | non-finite input | non-finite metric은 숫자 대신 `검증 불가`와 이유를 보인다. | contract response, DOM, screenshot | 미검증: 구현 전 | MT-NF-02 |
| UX-ARCH-03 | read-only report, 1280×720 | 데이터 부족 | 최소 입력·기간·유니버스가 부족하면 `데이터 부족`과 보관 목록 행동을 보인다. | exact code, DOM, screenshot | 미검증: 구현 전 | MT-DATA-03 |
