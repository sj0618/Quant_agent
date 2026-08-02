# Combined Backend AI Prefix Compatibility Independent Verification Report

## 1. Independent Verdict

**PASS_WITH_LOW_FOLLOW_UP**

Independent evidence supports the combined-backend compatibility layer as implemented:

- the only code changes under test are `combined_main.py` and `backend/tests/unit/test_combined_main.py`
- the middleware is a narrow ASGI scope rewrite for the stripped `/analysis-jobs` family
- the AI app still owns the real `/analysis-jobs` routes and still enforces authentication
- the General Backend and `/combined-health` behavior still pass
- the full requested test runs pass exactly as expected
- only post-deployment smoke remains

## 2. Track and provenance

| Field | Value |
| --- | --- |
| Track | Combined Backend AI Prefix Compatibility Independent Verification |
| Source worktree | `C:\Users\kojy1\PycharmProjects\Qaunt_agent_combined_ai_prefix_fix` |
| Verification report output | `backend/docs/COMBINED_AI_PREFIX_COMPAT_INDEPENDENT_VERIFICATION_REPORT.md` |
| Branch | `fix/combined-ai-prefix-compat` |
| Starting HEAD | `2a4d1a090b355957f2fb803282b3751c09ae6f69` |
| Ending HEAD | `2a4d1a090b355957f2fb803282b3751c09ae6f69` |
| origin/main HEAD | `2a4d1a090b355957f2fb803282b3751c09ae6f69` |
| Implementation report reviewed | `backend/docs/COMBINED_AI_PREFIX_COMPAT_IMPLEMENTATION_REPORT.md` |
| Commit | not performed |
| Push | not performed |
| Deployment | not performed |

### Starting Git state

Observed at the start of verification:

- branch: `fix/combined-ai-prefix-compat`
- `HEAD`: `2a4d1a090b355957f2fb803282b3751c09ae6f69`
- `origin/main`: `2a4d1a090b355957f2fb803282b3751c09ae6f69`
- modified tracked files:
  - `combined_main.py`
  - `backend/tests/unit/test_combined_main.py`
- untracked file already present:
  - `backend/docs/COMBINED_AI_PREFIX_COMPAT_IMPLEMENTATION_REPORT.md`
- no merge, rebase, or cherry-pick in progress

### Ending Git state

At the end of verification, `HEAD` remained unchanged. The only repository content I added is this report file.

## 3. Verification scope

I independently checked the following claims against the actual source and execution results:

- stripped `/analysis-jobs` requests are recovered only for the `/analysis-jobs` family
- the rewrite becomes `/ai-api/analysis-jobs` or `/ai-api/analysis-jobs/*`
- already-prefixed `/ai-api/*` requests are not double-prefixed
- the AI backend still handles the request after rewrite
- the AI backend’s existing auth boundary is preserved
- the General Backend, FE, Vite, workflow, migration, and AI backend source surfaces are not modified outside the allowed files
- query string, method, headers, body, and streaming behavior are preserved
- the implementation tests are reproducible from the current source

I treated the implementation report as a claim source only, not as evidence.

## 4. No-modification evidence

Commands run before any verification conclusions:

```powershell
& 'C:\Program Files\Git\cmd\git.exe' fetch origin --prune
& 'C:\Program Files\Git\cmd\git.exe' rev-parse --show-toplevel
& 'C:\Program Files\Git\cmd\git.exe' branch --show-current
& 'C:\Program Files\Git\cmd\git.exe' rev-parse HEAD
& 'C:\Program Files\Git\cmd\git.exe' rev-parse origin/main
& 'C:\Program Files\Git\cmd\git.exe' status --short
& 'C:\Program Files\Git\cmd\git.exe' diff --check
& 'C:\Program Files\Git\cmd\git.exe' diff --name-status
& 'C:\Program Files\Git\cmd\git.exe' diff --stat
& 'C:\Program Files\Git\cmd\git.exe' rev-parse -q --verify MERGE_HEAD
& 'C:\Program Files\Git\cmd\git.exe' rev-parse -q --verify REBASE_HEAD
& 'C:\Program Files\Git\cmd\git.exe' rev-parse -q --verify CHERRY_PICK_HEAD
```

No command in this verification modified application source, tests, workflows, or migrations.

## 5. Git diff and file-scope review

`git diff --name-only origin/main` showed only:

- `combined_main.py`
- `backend/tests/unit/test_combined_main.py`

That matches the expected implementation surface. The untracked report file was visible in `git status --short` but is not part of the origin/main diff.

`git diff --stat origin/main` showed a small compatibility-layer change set rather than a repo-wide rewrite:

- `combined_main.py`: 20 added lines
- `backend/tests/unit/test_combined_main.py`: 227 added lines, 1 deleted line

No unexpected file touched:

- no `ai/` source change
- no `backend/app/` source change
- no `fe/` source change
- no migration change
- no workflow change
- no commit, merge, rebase, cherry-pick, reset, clean, or stash

## 6. Line-ending and formatting review

Observed outputs:

- `git diff --check` emitted one CRLF warning for `backend/tests/unit/test_combined_main.py`
- `git diff --ignore-space-at-eol --numstat origin/main -- combined_main.py backend/tests/unit/test_combined_main.py` matched the ordinary `numstat` output
- `git check-attr text eol -- combined_main.py backend/tests/unit/test_combined_main.py` reported `unspecified` for both files

Interpretation:

- the warning is real, but it is not evidence of a broad line-ending-only rewrite
- the substantive diff is still the same small source/test change set

## 7. Confirmed routing architecture

Source review confirmed the existing topology:

- `combined_main.py:create_app()` mounts `/ai-api` before `"/"` and exposes `/combined-health`
- `backend/app/api/routes/pages.py:frontend_spa_fallback()` is still a GET catch-all and still rejects reserved prefixes such as `api/`, `ai-api/`, `auth/`, `analysis-jobs`, `health`, and `combined-health`
- `fe/src/config/appConfig.ts:aiApiBaseUrl()` defaults to `/ai-api`
- `fe/src/api/quantAgentClient.ts` calls the AI job family through `AI_ENDPOINTS`
- `fe/src/api/analysisActivity.ts` listens to the job events stream through the same AI base URL
- `ai/ai_graph/api.py` still owns the actual job routes under `/analysis-jobs`

This means the compatibility layer belongs in the combined entrypoint, not in the AI backend or the General Backend.

## 8. FE analysis-job route matrix

| FE function | FE method/path | AI method/path | Compatibility rewrite needed | Verification result |
| --- | --- | --- | --- | --- |
| `createAnalysisJob(query)` | `POST /analysis-jobs` | `POST /analysis-jobs` | Only for stripped combined requests that arrive without `/ai-api` | VERIFIED |
| `listAnalysisJobs(limit)` | `GET /analysis-jobs?limit=...` | `GET /analysis-jobs?limit=...` | Only for stripped combined requests that arrive without `/ai-api` | VERIFIED |
| `getAnalysisJob(jobId)` | `GET /analysis-jobs/{jobId}` | `GET /analysis-jobs/{jobId}` | Only for stripped combined requests that arrive without `/ai-api` | VERIFIED |
| `useAnalysisActivity(jobId)` | `GET /analysis-jobs/{jobId}/events` via `EventSource` | `GET /analysis-jobs/{jobId}/events` | Only for stripped combined requests that arrive without `/ai-api` | VERIFIED |
| `cancelAnalysisJob(jobId)` | `POST /analysis-jobs/{jobId}/cancel` | `POST /analysis-jobs/{jobId}/cancel` | Only for stripped combined requests that arrive without `/ai-api` | VERIFIED |

Supporting evidence:

- `fe/src/config/appConfig.ts:29-31` keeps the AI base URL on `/ai-api` by default
- `fe/src/api/quantAgentClient.ts:340-383` uses the analysis-job family exactly once each for create/list/detail/cancel
- `fe/src/api/analysisActivity.ts:244-247` creates the event stream with `EventSource` against the same AI base URL

## 9. AI route matrix

| AI route | Method | Auth | Evidence |
| --- | --- | --- | --- |
| `/analysis-jobs` | `POST` | required | `ai/ai_graph/api.py:395-431` |
| `/analysis-jobs` | `GET` | required | `ai/ai_graph/api.py:522-532` |
| `/analysis-jobs/{job_id}` | `GET` | required | `ai/ai_graph/api.py:627-639` |
| `/analysis-jobs/{job_id}/events` | `GET` | required | `ai/ai_graph/api.py:460-520` |
| `/analysis-jobs/{job_id}/cancel` | `POST` | required | `ai/ai_graph/api.py:433-458` |
| `/api/analysis-jobs/{job_id}` | `GET` | required | `ai/ai_graph/api.py:641-647` |

Auth evidence:

- `ai/ai_graph/api.py:355` creates `require_user = RequireAuthenticatedUser(session_resolver)`
- the analysis-job routes depend on `Depends(require_user)`
- `ai/ai_graph/auth.py:106-112` raises `401 Authentication required` when no user is resolved

## 10. Middleware implementation review

The compatibility layer in `combined_main.py:28-44` was checked against the requested criteria.

| Item | Verdict | Evidence |
| --- | --- | --- |
| A. Implementation form | VERIFIED | `LegacyAiPrefixCompatibilityMiddleware` defines `__call__(scope, receive, send)` and is not `BaseHTTPMiddleware` |
| B. Scope limit | VERIFIED | rewrite logic only runs when `scope.get("type") == "http"` |
| C. Exact path boundary | VERIFIED | only `/analysis-jobs` and `/analysis-jobs/...` match |
| D. Scope mutation | VERIFIED | `dict(scope)` is created only on a matching path; `raw_path` is updated only when it is `bytes` |
| E. Preservation | VERIFIED | only `path` and sometimes `raw_path` are rewritten; method, query string, headers, body, scheme, client, server, root_path, and HTTP version are not touched |
| F. Routing and mount order | VERIFIED | middleware is added on the root app and the app still mounts `/ai-api` and `/` separately |
| G. Authentication impact | VERIFIED | the middleware contains no auth bypass logic and the AI app still performs its own auth dependency checks |

## 11. Exact path-boundary review

### Rewrite targets

- `/analysis-jobs` → rewritten to `/ai-api/analysis-jobs`
- `/analysis-jobs/` → rewritten to `/ai-api/analysis-jobs/`
- `/analysis-jobs/job-123` → rewritten to `/ai-api/analysis-jobs/job-123`
- `/analysis-jobs/job-123/events` → rewritten to `/ai-api/analysis-jobs/job-123/events`
- `/analysis-jobs/job-123/cancel` → rewritten to `/ai-api/analysis-jobs/job-123/cancel`

### Non-targets

- `/analysis-job`
- `/analysis-jobs-extra`
- `/api/analysis-jobs`
- `/api/v1/analysis-jobs`
- `/foo/analysis-jobs`
- `/ai-api/analysis-jobs`

These boundary rules are enforced by `combined_main.py:37-43` and are also exercised by the parametrized test at `backend/tests/unit/test_combined_main.py:471-484`.

## 12. Request preservation review

The compatibility stub in `backend/tests/unit/test_combined_main.py` records the received scope and request data. Those tests confirmed:

| Field | Evidence | Verdict |
| --- | --- | --- |
| Method | asserted in create/list/detail/cancel tests | VERIFIED |
| Query string | asserted in `test_legacy_ai_prefix_compatibility_rewrites_list_requests_and_preserves_query` | VERIFIED |
| Headers / Content-Type | asserted in create and cancel tests | VERIFIED |
| Body | asserted for JSON create and cancel requests | VERIFIED |
| Root path | asserted as `/ai-api` after rewrite | VERIFIED |
| Raw path | asserted as `/ai-api/...` after rewrite | VERIFIED |
| Scheme / client / server / HTTP version | not individually asserted in tests, but the middleware does not mutate them because it only rewrites `path` and `raw_path` | VERIFIED_BY_STRUCTURE |

The middleware does not read request bodies or response bodies, so it preserves streaming behavior by construction.

## 13. Streaming and SSE review

AI source evidence:

- `ai/ai_graph/api.py:460-520` returns `StreamingResponse(event_source(), media_type="text/event-stream", headers={...})`
- the event source yields SSE frames incrementally and inserts keepalive comments instead of buffering the full payload
- `ai/ai_graph/api.py:515-518` explicitly disables proxy buffering for the stream

Test evidence:

- `backend/tests/unit/test_combined_main.py:424-439` confirms the stream endpoint still returns `text/event-stream`
- the same test confirms the body contains both emitted chunks and that the stream started and finished

Compatibility verdict:

- the middleware is structurally streaming-safe because it is a pure ASGI scope rewrite and never aggregates request or response bodies

## 14. Authentication and security review

Security evidence from source:

- `ai/ai_graph/auth.py:85-112` resolves the session cookie and raises `401 Authentication required` when no user can be resolved
- `ai/ai_graph/api.py:395-463` applies that dependency to the analysis-job create/list/detail/cancel/events routes
- `combined_main.py:34-44` does not inspect or rewrite `Authorization`, cookies, or any auth-specific headers
- `combined_main.py` contains no bypass flag, no environment-variable auth override, and no test-only auth logic

Security evidence from tests:

- `backend/tests/unit/test_combined_main.py:219-268` verifies the real combined app still returns `401` for bare `/analysis-jobs`
- `backend/tests/unit/test_combined_main.py:349-383` verifies the compatibility rewrite reaches the AI stub without changing query/body/header shape

Security verdict:

- the root `/analysis-jobs` alias is a deliberate public routing surface change
- it does **not** bypass the AI app’s auth policy
- normal `/ai-api/*` requests are not duplicated or rewritten twice

## 15. Test quality review

`backend/tests/unit/test_combined_main.py` now contains 10 test functions, 15 collected cases because of parametrization.

Quality checks I confirmed:

- the existing tests were not deleted
- the old bare `/analysis-jobs` expectation was changed to match the new compat contract
- the fake AI app and General Backend startup fixture are kept separate
- requests still flow through `combined_main.create_app()`
- the tests do not rely on real provider traffic, DB access, Redis access, or external HTTP
- the tests explicitly validate method, child-app path, query string, JSON body, content type, `root_path`, and `raw_path`
- the tests cover boundary paths, prefixed `/ai-api` requests, streaming, and `/combined-health`
- `test_combined_module_import_does_not_start_child_lifespan` and the lifespan-order tests protect the mount/lifespan topology

## 16. Independently executed commands

### Git and provenance

- `git fetch origin --prune`
- `git rev-parse --show-toplevel`
- `git branch --show-current`
- `git rev-parse HEAD`
- `git rev-parse origin/main`
- `git status --short`
- `git diff --check`
- `git diff --name-status`
- `git diff --stat`
- `git rev-parse -q --verify MERGE_HEAD`
- `git rev-parse -q --verify REBASE_HEAD`
- `git rev-parse -q --verify CHERRY_PICK_HEAD`

### Diff and file-scope checks

- `git diff --name-only origin/main`
- `git diff --numstat origin/main -- combined_main.py backend/tests/unit/test_combined_main.py`
- `git diff --ignore-space-at-eol --numstat origin/main -- combined_main.py backend/tests/unit/test_combined_main.py`
- `git check-attr text eol -- combined_main.py backend/tests/unit/test_combined_main.py`
- `git diff --unified=80 origin/main -- combined_main.py`
- `git diff --unified=80 origin/main -- backend/tests/unit/test_combined_main.py`
- `git diff --unified=80 origin/main -- backend/docs/COMBINED_AI_PREFIX_COMPAT_IMPLEMENTATION_REPORT.md`

### Source inspection

- `combined_main.py`
- `backend/app/api/routes/pages.py`
- `backend/tests/unit/test_combined_main.py`
- `backend/tests/unit/test_backend_hosted_pages.py`
- `fe/src/config/appConfig.ts`
- `fe/src/api/quantAgentClient.ts`
- `fe/src/api/analysisActivity.ts`
- `ai/ai_graph/api.py`
- `ai/ai_graph/auth.py`

### Static and test execution

- `python -X utf8 -m py_compile combined_main.py backend/tests/unit/test_combined_main.py`
- `python -X utf8 -m pytest backend/tests/unit/test_combined_main.py -q`
- `Push-Location backend; python -X utf8 -m pytest tests/unit/test_backend_hosted_pages.py -q; Pop-Location`
- `Push-Location backend; PYTHONPATH=.. python -X utf8 -m pytest tests/unit/test_combined_main.py -q; Pop-Location`
- `python -X utf8 -m pytest backend/tests/unit/test_combined_main.py -k legacy_ai_prefix_compatibility -q`
- `Push-Location backend; PYTHONPATH=.. python -X utf8 -m pytest tests/unit/test_combined_main.py -k 'combined_route_surface_routes_general_and_ai_without_cross_shadowing or combined_app_lifespan_orders_general_then_ai_and_mounts_ai_first' -q; Pop-Location`

## 17. Test results

| Command | Result |
| --- | --- |
| `python -X utf8 -m py_compile combined_main.py backend/tests/unit/test_combined_main.py` | pass |
| `python -X utf8 -m pytest backend/tests/unit/test_combined_main.py -q` | `15 passed` |
| `Push-Location backend; python -X utf8 -m pytest tests/unit/test_backend_hosted_pages.py -q` | `5 passed` |
| `Push-Location backend; PYTHONPATH=.. python -X utf8 -m pytest tests/unit/test_combined_main.py -q` | `15 passed` |
| `python -X utf8 -m pytest backend/tests/unit/test_combined_main.py -k legacy_ai_prefix_compatibility -q` | `11 passed, 4 deselected` |
| `Push-Location backend; PYTHONPATH=.. python -X utf8 -m pytest tests/unit/test_combined_main.py -k 'combined_route_surface_routes_general_and_ai_without_cross_shadowing or combined_app_lifespan_orders_general_then_ai_and_mounts_ai_first' -q` | `2 passed, 13 deselected` |

Warnings observed:

- Starlette deprecation warning from the test client package
- Pytest cleanup warning on the second focused backend run
- Git CRLF warning on `backend/tests/unit/test_combined_main.py`

None of those warnings changed the pass/fail outcome.

## 18. General Backend regression review

The General Backend remains intact:

- `backend/app/api/routes/pages.py:74-95` still uses a GET catch-all for the SPA fallback
- the catch-all still treats `analysis-jobs`, `ai-api/`, `api/`, `auth/`, `static/`, `health`, and `combined-health` as reserved prefixes
- `/combined-health` still returns the combined service health payload
- `backend/tests/unit/test_combined_main.py:219-268` confirms the General Backend still serves the FE shell on the expected routes and still leaves `/api/v1/analysis-jobs` alone

The compatibility layer therefore does not shadow the General Backend or change its reservation rules.

## 19. Forbidden-path change review

`git diff --name-only origin/main` did **not** show any change under these forbidden paths:

- `ai/`
- `backend/app/`
- `fe/`
- `service_db/migrations/`
- `DE/migrations/`
- `.github/workflows/`

That is the key repository-level containment check for this task.

## 20. Differences from implementation report

The implementation report’s core technical conclusion matches the independent evidence, but I did find differences in the surrounding claim set:

- the implementation report described the starting Git state as clean; the actual verification start state already contained the two modified files plus the untracked implementation report
- I did not independently reproduce the earlier root-directory hosted-pages failure; instead, I verified the required backend-directory rerun that the task asked for
- I ran extra independent checks beyond the implementation report, including `py_compile` and focused `-k` pytest slices
- my verdict is `PASS_WITH_LOW_FOLLOW_UP` rather than a bare `PASS` because no deployment smoke was executed

I did **not** find a technical mismatch in the routing, auth, or streaming conclusions.

## 21. Remaining risks

The remaining risk is operational, not code-level:

- no live deployment smoke was performed
- no browser-driven end-to-end smoke was performed
- the task-specific external trace smoke was not executed

Low-severity tooling noise remains:

- the CRLF warning on the edited test file
- deprecation / cleanup warnings from the pytest environment

These do not invalidate the implementation result, but they are worth keeping in mind for post-deploy verification.

## 22. Post-deployment verification requirements

This verification pass did not deploy. The post-deployment smoke checks that still need to be run are:

```bash
curl -i -X POST \
  -H 'Content-Type: application/json' \
  -d '{}' \
  http://127.0.0.1:18001/analysis-jobs
```

Expected:

- not `405`
- existing AI auth policy returns `401 Authentication required`

```bash
curl -i -X POST \
  -H 'Content-Type: application/json' \
  -d '{}' \
  http://127.0.0.1:18000/ai-api/analysis-jobs
```

Expected:

- `401 Authentication required`
- no duplicate `/ai-api` prefix

```bash
MARK="qa-prefix-verify-$(date +%s)"

curl -i -X POST \
  -H 'Content-Type: application/json' \
  -d '{}' \
  "https://qt-agent.kro.kr/ai-api/analysis-jobs?trace=$MARK"

grep -F "$MARK" \
  ~/mvp_sp1/quant-proj/.run/combined.log |
  tail -n 1
```

Expected:

- `401 Authentication required`
- no General Backend `405` collision

Browser smoke still needed after deployment:

- submit a natural-language strategy
- create an analysis job
- list jobs
- poll job detail
- connect to events
- cancel a job
- refresh and re-open an existing job
- confirm the General Backend UI and API still behave normally

## 23. Final verdict

**PASS_WITH_LOW_FOLLOW_UP**

The implementation is independently verified for:

- targeted `/analysis-jobs` family recovery
- no double-prefix on normal `/ai-api/*` requests
- preserved auth boundary
- preserved streaming behavior
- preserved General Backend behavior
- exact expected test results

The only material follow-up is post-deployment smoke validation.

## 24. Ending Git state

Observed after verification and report creation:

- `HEAD`: `2a4d1a090b355957f2fb803282b3751c09ae6f69`
- branch: `fix/combined-ai-prefix-compat`
- modified tracked files remain:
  - `combined_main.py`
  - `backend/tests/unit/test_combined_main.py`
- untracked reports present:
  - `backend/docs/COMBINED_AI_PREFIX_COMPAT_IMPLEMENTATION_REPORT.md`
  - `backend/docs/COMBINED_AI_PREFIX_COMPAT_INDEPENDENT_VERIFICATION_REPORT.md`
- no merge/rebase/cherry-pick in progress
- no commit, push, or deployment performed
