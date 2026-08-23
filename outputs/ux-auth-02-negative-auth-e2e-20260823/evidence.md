# UX-AUTH-02 local negative-auth CDP E2E evidence

## Execution identity

- WBS ID: `UX-AUTH-02`
- Verification SHA: `a63fc23d2e3e6380018ba05d67f5ea7daf125962`
- Executed at: `2026-08-23 13:52:04 KST` (`2026-08-23T04:52:04.117Z`)
- Scope: `local negative-auth E2E contract`
- Browser: system Chrome with a unique temporary profile, localhost CDP, and Codex-bundled Playwright
- Application: production FE preview and the actual local FastAPI auth router
- Negative path: missing OAuth transaction cookie; rejection occurred before provider exchange
- Actual Google credential or authorization code used: no
- External Google request transmitted: 0
- Production, node3, or PVE verified/accessed: no
- Final verdict: `PASS`

## Done conditions

| Condition | Fresh browser/runtime evidence | Result |
| --- | --- | --- |
| auth failure code | callback POST 1; HTTP 401; `oauth_transaction_invalid` | PASS |
| no data leak | authenticated session cookie 0; protected-route request 0; DOM and console sensitive match 0 | PASS |
| retry action | accessible retry link 1; click succeeded; `/login`; auth-start GET 1 | PASS |

## Browser result

| Measurement | Result |
| --- | ---: |
| Callback request count | 1 |
| Callback HTTP status | 401 |
| Callback application code | `oauth_transaction_invalid` |
| Authenticated session cookie count after failure/retry/final | 0 / 0 / 0 |
| Protected-route request count | 0 |
| Failure protected-data DOM match count | 0 |
| Login protected-data DOM match count | 0 |
| Failure/login sensitive marker match count | 0 / 0 |
| Failure/login stack trace match count | 0 / 0 |
| Failure/login internal-info match count | 0 / 0 |
| Console error count | 2 |
| Console warning count | 0 |
| Console page-error count | 0 |
| Console sensitive marker match count | 0 |
| Retry accessible locator match count | 1 |
| Retry click | PASS |
| Path after retry | `/login` |
| Google action accessible locator match count | 1 |
| Auth-start request count | 1 |
| External Google intercepted attempt count | 0 |
| External Google transmitted request count | 0 |

## Redacted network summary

Only method, pathname, and status are retained. Query values, request bodies, headers, cookies, credentials, tokens, and authorization-code values are not retained.

| Method | Pathname | Status |
| --- | --- | ---: |
| GET | `/auth/google/callback` | 200 |
| POST | `/api/v1/auth/google/callback` | 401 |
| GET | `/login` | 200 |
| GET | `/api/v1/auth/google/start` | 503 |

## Retry and Redis boundary

- Retry UI operation: PASS
- Navigation back to `/login`: PASS
- New auth-start request emitted: PASS
- Auth-start completion: HTTP 503 / `redis_write_failed`, because no local Redis state store was used
- External Google request transmitted: 0

The Redis limitation is recorded separately from the UX-AUTH-02 retry-action result. This evidence does not claim Google-provider authentication, production authentication, or an actual Google password-error flow.

## Screenshots

- `callback-failure.png`: safe callback failure UI after the screenshot gate passed
- `retry-login.png`: login UI after retry navigation and before the auth-start action
- Screenshot gate: PASS for both images
- Visual inspection: no personal user data or sensitive value was visible

## Test summary

| Test | Result |
| --- | --- |
| CDP browser harness | exit 0; PASS |
| `cd fe && npm test` | 34 passed; 0 failed; 0 skipped; typecheck PASS; production build PASS; exit 0 |
| Backend targeted auth tests | 2 passed; 0 failed; 2 deprecation warnings; exit 0 |

## Non-blocking accessibility observation

- Failure visual title count: 1
- Semantic heading role count: 0
- Visual title element: `<strong>`

This is a non-blocking follow-up observation and is not mixed into the three official UX-AUTH-02 Done conditions.

## Evidence safety and scope

- Sensitive values retained: 0
- Raw query/body/header/cookie content retained: 0
- Credential, token, session, personal-data, DSN, and sensitive-path value matches: 0
- Application source changes: 0
- Test source changes: 0
- Package/dependency changes: 0
- WBS changes: 0

## Workspace lock suitability

These files are QA evidence records under the existing `outputs/<scope>/` convention. They are within `LOCK-QA-EVIDENCE-01` and do not alter application source, test source, packages, dependencies, or WBS records.

## Intended commit

`[E2E] verify failed login is safe`
