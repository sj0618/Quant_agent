# Combined Backend AI Prefix Compatibility Implementation Report

## Verdict
PASS

The compatibility layer is implemented in the combined entrypoint, both required regression checks pass when executed from the backend directory, and the earlier root-directory failure was an execution-context issue rather than a code or asset defect.

## Track and provenance
- Track: Combined Backend AI Prefix Compatibility
- Source worktree: `C:\Users\kojy1\PycharmProjects\Qaunt_agent_combined_ai_prefix_fix`
- Report output: `backend/docs/COMBINED_AI_PREFIX_COMPAT_IMPLEMENTATION_REPORT.md`
- Branch: `fix/combined-ai-prefix-compat`
- Starting HEAD: `2a4d1a090b355957f2fb803282b3751c09ae6f69`
- Ending HEAD: `2a4d1a090b355957f2fb803282b3751c09ae6f69`
- origin/main HEAD: `2a4d1a090b355957f2fb803282b3751c09ae6f69`
- Starting Git state: clean, with no merge/rebase/cherry-pick in progress
- Ending Git state: modified `combined_main.py`, `backend/tests/unit/test_combined_main.py`, and untracked `backend/docs/COMBINED_AI_PREFIX_COMPAT_IMPLEMENTATION_REPORT.md`
- Commit status: not performed
- Push status: not performed
- Deployment status: not performed

## Safety and no-mutation evidence
- Initial provenance commands were run immediately after entering the worktree:
  - `git rev-parse --show-toplevel`
  - `git branch --show-current`
  - `git rev-parse HEAD`
  - `git rev-parse origin/main`
  - `git status --short`
  - `git diff --check`
  - `git rev-parse -q --verify MERGE_HEAD`
  - `git rev-parse -q --verify REBASE_HEAD`
  - `git rev-parse -q --verify CHERRY_PICK_HEAD`
- The worktree started clean and on `fix/combined-ai-prefix-compat`.
- No merge, rebase, or cherry-pick was active.
- No AI, General Backend, FE, migration, workflow, DB, Redis, deploy, commit, or push changes were made.
- `git diff --check` stayed clean apart from Git’s CRLF warning on the edited test file; no semantic diff errors were present.

## Problem reproduction evidence
The provided trace established the failure shape:
- External request: `POST https://qt-agent.kro.kr/ai-api/analysis-jobs`
- Combined Backend log: `POST /analysis-jobs` then `405 Method Not Allowed`
- Node3 Vite direct request: `POST http://127.0.0.1:18000/ai-api/analysis-jobs`
- Combined Backend log for the direct request: `POST /ai-api/analysis-jobs` then `401 Authentication required`

From source inspection, that matches the current topology:
- `/ai-api/*` is the AI mount in `combined_main.py`.
- `backend/app/api/routes/pages.py` still owns the General Backend SPA fallback and is GET-only.
- The stripped `/analysis-jobs` request therefore falls into the General Backend path surface and collides with the GET catch-all before the AI app can handle it.

## Confirmed routing architecture
- FE Vite default AI base URL is `/ai-api` in development unless explicitly overridden.
- Combined Backend mounts:
  - `/combined-health`
  - `/ai-api` -> AI app
  - `/` -> General Backend app
- The AI app owns the analysis-job family under `/analysis-jobs`.
- The General Backend continues to own `/api/v1/*` and the SPA shell routes.

## Scope and non-goals
### In scope
- Add a limited Combined Backend compatibility layer for stripped root `/analysis-jobs` requests.
- Preserve the mounted AI app, General Backend app, and lifespan ordering.
- Update unit tests and add a report.

### Out of scope
- AI Backend source changes.
- General Backend source changes.
- FE source changes.
- Vite changes.
- Nginx, SSH tunnel, deploy, workflow, migration, DB, Redis, env-var, commit, push, or reset changes.
- Aliasing any other root path family.
- Self-HTTP fallback or response-code-based rerouting.

## Files inspected
- `combined_main.py`
- `backend/app/api/routes/pages.py`
- `backend/tests/unit/test_combined_main.py`
- `backend/tests/unit/test_backend_hosted_pages.py`
- `fe/src/config/appConfig.ts`
- `fe/src/api/quantAgentClient.ts`
- `fe/src/api/analysisActivity.ts`
- `ai/ai_graph/api.py`
- `ai/ai_graph/auth.py`

## Actual FE analysis-job route matrix
The FE analysis-job callers all target the AI base URL and the `/analysis-jobs` family:

| FE caller | Method | Path |
| --- | --- | --- |
| `createAnalysisJob(query)` | `POST` | `/analysis-jobs` |
| `listAnalysisJobs(limit)` | `GET` | `/analysis-jobs?limit=...` |
| `getAnalysisJob(jobId)` | `GET` | `/analysis-jobs/{jobId}` |
| `useAnalysisActivity(jobId)` | `GET` via `EventSource` | `/analysis-jobs/{jobId}/events` |
| `cancelAnalysisJob(jobId)` | `POST` | `/analysis-jobs/{jobId}/cancel` |

Supporting FE facts:
- `appConfig.aiApiBaseUrl()` defaults to `/ai-api` in dev and otherwise falls back to `/ai-api` unless `VITE_AI_API_BASE_URL` is set.
- `refreshLatestAnalysisJob()` first prefers a stored job detail fetch and otherwise falls back to list polling.
- `getReportStrategies()`, `getStrategyReportById()`, and `getStrategyWorkspaceOverview()` all read from the same analysis-job collection.

## Actual AI route matrix
The AI app in `ai/ai_graph/api.py` owns the actual analysis-job surface:

| Route | Method | Auth | Notes |
| --- | --- | --- | --- |
| `/analysis-jobs` | `POST` | required | Create a job and enqueue the analysis |
| `/analysis-jobs` | `GET` | required | List the authenticated user’s jobs |
| `/analysis-jobs/{job_id}` | `GET` | required | Return one owned job |
| `/analysis-jobs/{job_id}/events` | `GET` | required | SSE stream of job events |
| `/analysis-jobs/{job_id}/cancel` | `POST` | required | Cancel a running job |
| `/api/analysis-jobs/{job_id}` | `GET` | required | Spec compatibility alias |

Additional AI endpoints remain unchanged:
- `/health`
- `/api-status`
- `/api/strategies/parse`
- `/api/strategies/descriptions`
- `/api/backtests/{strategy_id}`
- `/api/reports/{report_id}`
- `/ai/daily-digest`

## General Backend collision analysis
- `backend/app/api/routes/pages.py` still exposes a GET catch-all at `@router.get("/{full_path:path}")`.
- That fallback explicitly rejects paths beginning with `analysis-jobs`, `api/`, `ai-api/`, `auth/`, `static/`, `health`, `combined-health`, and other reserved prefixes.
- A stripped `POST /analysis-jobs` therefore reaches the General Backend path surface and collides with the GET-only fallback, producing a 405 before the AI app can be reached.
- The fix therefore has to live in the Combined Backend entrypoint, before mount dispatch.

## Implementation design
I added a pure ASGI middleware class in `combined_main.py`:
- It only inspects `scope["type"] == "http"`.
- It rewrites only the exact `/analysis-jobs` path family:
  - `/analysis-jobs`
  - `/analysis-jobs/{suffix}`
- It rewrites those to `/ai-api/...`.
- It shallow-copies the scope only when a rewrite is needed.
- It updates `raw_path` only when the original `raw_path` is bytes.
- It leaves method, query string, headers, body, receive, send, root_path, client, server, scheme, and HTTP version untouched.
- It is registered on the root Combined app with `app.add_middleware(...)` so the rewrite happens before mount routing.

## Exact rewrite rule
- `/analysis-jobs` → `/ai-api/analysis-jobs`
- `/analysis-jobs/{suffix}` → `/ai-api/analysis-jobs/{suffix}`
- All other paths are untouched, including:
  - `/analysis-jobs-extra`
  - `/analysis-job`
  - `/api/analysis-jobs`
  - `/api/v1/analysis-jobs`
  - `/foo/analysis-jobs`
  - already-prefixed `/ai-api/...` paths

## Why pure ASGI middleware was used
- `BaseHTTPMiddleware` would be the wrong tool here because it can interfere with request/response streaming behavior.
- The AI events endpoint is an SSE stream, so the compatibility layer must not read or buffer the body.
- The implemented middleware forwards `scope`, `receive`, and `send` unchanged after a targeted scope rewrite.
- That keeps the compatibility layer transparent to the AI app’s existing auth and streaming behavior.

## Middleware ordering verification
- `combined_main.create_app()` still produces the same route order:
  - `/combined-health`
  - `/ai-api`
  - `""` for the root General Backend mount
- The new middleware appears in `application.user_middleware`.
- The existing lifespan test still observes the same startup/shutdown order:
  - general enter
  - AI enter
  - AI exit
  - general exit
- The combined app therefore retains the same mount/lifespan topology while gaining the stripped-prefix compat layer.

## Changed files
- `combined_main.py`
- `backend/tests/unit/test_combined_main.py`
- `backend/docs/COMBINED_AI_PREFIX_COMPAT_IMPLEMENTATION_REPORT.md`

## Test changes
### `backend/tests/unit/test_combined_main.py`
- Updated the existing high-level Combined Backend contract so bare `/analysis-jobs` is now expected to route to the AI app and return 401 rather than 404.
- Added a dedicated compat AI stub that records:
  - scope path
  - mounted-relative path
  - root path
  - raw path
  - query string
  - content type
  - body text / JSON
  - job id
- Added tests for:
  - POST create
  - GET list
  - GET detail
  - POST cancel
  - GET events
  - already-prefixed `/ai-api/analysis-jobs`
  - boundary paths that must not be rewritten
- Patched the existing general-startup fixture to avoid the AI app’s auth-config error by returning a test resolver that yields no authenticated user, so the real AI app still returns 401 on protected routes.

## Test results
### Passed
- `python -m py_compile combined_main.py backend\tests\unit\test_combined_main.py`
- `python -m pytest tests/unit/test_backend_hosted_pages.py -q`
  - `5 passed`
- `PYTHONPATH=.. python -m pytest tests/unit/test_combined_main.py -q`
  - `15 passed`
- Compat route-specific tests inside `tests/unit/test_combined_main.py` passed for:
  - create
  - list
  - detail/cancel
  - streaming events
  - prefixed AI requests
  - non-matching boundary paths

## Regression verification
- The root Combined app still reports `/combined-health` as `200`.
- The General Backend still serves the FE shell on non-reserved routes.
- The AI prefix rewrite does not apply to similar-but-different paths.
- Query string, request body, method, and `Content-Type` are preserved by the compat layer tests.
- The streamed events endpoint still returns `text/event-stream` and emits the expected chunks.
- The backend-hosted-pages regression now passes from the `backend/` directory, which confirms the earlier failure was only due to test execution context.

## Query, body and streaming preservation
- Query strings were verified on `GET /analysis-jobs?limit=20`.
- JSON body preservation was verified on `POST /analysis-jobs` and `POST /analysis-jobs/{job_id}/cancel`.
- Method preservation was verified on create, list, detail, cancel, and the prefixed-path test.
- The streaming endpoint was verified as a live `text/event-stream` response whose body contained both emitted chunks.
- The compatibility middleware itself never reads the request body and never rewrites the response body.

## Security impact
- The root `/analysis-jobs` family is now an explicit compatibility alias to the mounted AI app.
- The actual AI app still owns authentication and authorization.
- The middleware does not bypass auth and does not alias any other root path families.
- `/api/v1/*` and General Backend ownership remain unchanged.
- Normal `/ai-api/*` requests are untouched and do not receive a second prefix.

## Remaining operational dependency
- None for the verified task path.
- The earlier failure mode was caused by running `backend/tests/unit/test_backend_hosted_pages.py` from the repository root, which misresolved the relative `app/static` paths.
- Rerunning from the `backend/` directory resolves that pathing issue.

## Post-deployment smoke commands
This task did not deploy. The following commands are the intended smoke checks after a deployment:

```bash
MARK="qa-prefix-compat-$(date +%s)"

curl -i -X POST \
  -H 'Content-Type: application/json' \
  -d '{}' \
  "https://qt-agent.kro.kr/ai-api/analysis-jobs?trace=$MARK"

grep -F "$MARK" \
  ~/mvp_sp1/quant-proj/.run/combined.log |
  tail -n 1
```

Expected:
- HTTP 401 `Authentication required`
- no General Backend 405
- the request reaches the AI app’s auth path

```bash
curl -i -X POST \
  -H 'Content-Type: application/json' \
  -d '{}' \
  http://127.0.0.1:18000/ai-api/analysis-jobs
```

Expected:
- 401 `Authentication required`
- no double prefix

```bash
curl -i -X POST \
  -H 'Content-Type: application/json' \
  -d '{}' \
  http://127.0.0.1:18001/analysis-jobs
```

Expected:
- AI-app 401 instead of General Backend 405

Browser smoke items:
- natural-language strategy submission
- analysis job creation
- job list refresh
- job detail polling
- event stream connection
- cancel request
- refresh after navigation
- no regression on General Backend screens or APIs

## Git state
- Final `git status --short` before writing this report showed:
  - `M backend/tests/unit/test_combined_main.py`
  - `M combined_main.py`
- After writing this report, it is also present as an untracked file in the working tree as the requested output artifact.
- `git diff --name-status` shows only the approved files touched.
- `git diff --stat` shows only the Combined entrypoint, the Combined test file, and this report.

## Commit and push status
- Commit status: not performed
- Push status: not performed
