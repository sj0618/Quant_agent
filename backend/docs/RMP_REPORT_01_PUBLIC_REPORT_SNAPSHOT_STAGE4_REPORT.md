# RMP Report 01 — Public Report Snapshot Stage 4 Implementation

## 1. Execution Metadata

| Field | Value |
| --- | --- |
| Timestamp (KST) | 2026-09-04 23:23:23 +09:00 |
| Worktree | `C:\Users\kojy1\PycharmProjects\Qaunt_agent_rmp_report01_stage4` |
| Branch | `fix/rmp-report01-public-snapshot` |
| Implementation commit SHA | `87dfac66552f73120ae0acdeeceec1460f90c110` |
| Canonical remote | `origin https://github.com/sj0618/Quant_agent.git` |

## 2. Objective

Expose the immutable public report snapshot already stored with each completed analysis result through the archived report detail and email report detail surfaces, while keeping the workspace-report path unchanged.

## 3. Implemented Behavior

### Backend

- `backend/app/db/existing_report_queries.py`
  - `get_reader_report(...)` now joins `app.analysis_result`, selects `public_snapshot_jsonb`, and returns it as `publicReportSnapshot` on archived reader detail payloads.
  - `get_report(...)` now joins `app.analysis_result`, selects `public_snapshot_jsonb`, and returns it as `publicReportSnapshot` on full email report payloads.
- `backend/app/schemas/report_snapshot.py`
  - added `PublicReportSnapshotV1` with:
    - `schemaVersion: "1"`
    - `analysisResultId: str`
    - `result: dict[str, Any]`
- `backend/app/schemas/report_archive.py`
  - `ArchivedReportDetail` now includes `publicReportSnapshot: PublicReportSnapshotV1 | None`.

### Frontend

- `fe/src/types/quantagent.ts`
  - added `PublicReportSnapshot`.
  - added `publicReportSnapshot?: PublicReportSnapshot | null` to `ReportDetail`.
- `fe/src/api/quantAgentClient.ts`
  - `normalizeEmailReportDetail(...)` now preserves the new field explicitly as `publicReportSnapshot: report.publicReportSnapshot ?? null`.

### Test coverage

- `backend/tests/unit/test_track_c_queries.py`
  - verifies the new join/field in both reader-detail and email-detail query paths.
  - verifies `publicReportSnapshot` shape in both returned payloads.
- `backend/tests/unit/test_fe_contract_routes.py`
  - verifies the owner-scoped email report detail and archived reader detail both surface `publicReportSnapshot`.
- `backend/tests/integration/test_track_c_server_run_report_qt_db.py`
  - verifies the archived detail route continues to allowlist content while exposing the public snapshot.
- `fe/scripts/api-source.test.mts`
  - verifies the FE client and type surface retain the new field and normalization path.

## 4. Changed Files

| File | Why changed |
| --- | --- |
| `backend/app/db/existing_report_queries.py` | Surface the stored immutable snapshot through reader and email detail queries. |
| `backend/app/schemas/report_archive.py` | Extend the archived detail schema to include the public snapshot. |
| `backend/app/schemas/report_snapshot.py` | Define the public snapshot response model. |
| `backend/tests/integration/test_track_c_server_run_report_qt_db.py` | Confirm the archived detail route still allowlists content and now includes the public snapshot. |
| `backend/tests/unit/test_fe_contract_routes.py` | Keep route-contract tests aligned with the new response shape. |
| `backend/tests/unit/test_track_c_queries.py` | Validate query-layer projection and returned snapshot payloads. |
| `fe/scripts/api-source.test.mts` | Assert the FE client/type surface preserves the new snapshot field. |
| `fe/src/api/quantAgentClient.ts` | Preserve `publicReportSnapshot` during email-report normalization. |
| `fe/src/types/quantagent.ts` | Add the FE type for the public snapshot. |

## 5. Verification

| Command | Result |
| --- | --- |
| `python -m pytest backend/tests/unit/test_track_c_queries.py backend/tests/unit/test_fe_contract_routes.py backend/tests/integration/test_track_c_server_run_report_qt_db.py -q` | `23 passed, 3 skipped` |
| `C:\Program Files\nodejs\node.exe --experimental-strip-types --test fe/scripts/api-source.test.mts fe/scripts/backend-integration-source.test.mts` | `15 passed, 0 failed` |
| `npm run typecheck` in `fe/` | passed |
| `npm run build` in `fe/` | passed |

### Verification notes

- `npm ci --no-audit --no-fund` was required in `fe/` because the isolated worktree did not have installed frontend dependencies yet.
- Temporary `fe/node_modules` and `fe/dist` artifacts were removed after verification so the worktree remains source-only.

## 6. Commit / Push Provenance

| Field | Value |
| --- | --- |
| Implementation commit | `87dfac66552f73120ae0acdeeceec1460f90c110` |
| Commit subject | `Expose the immutable public snapshot on report detail surfaces` |
| Push | completed |

## 7. Raw Evidence Summary

| Key | Value |
| --- | --- |
| Backend query surface | `app.analysis_result.public_snapshot_jsonb` now appears in reader-detail and email-detail queries. |
| Reader detail payload | `publicReportSnapshot` returned with archived evidence sections. |
| Email detail payload | `publicReportSnapshot` preserved through FE normalization. |
| Workspace report surface | unchanged. |
| Backend policy | unchanged. |
| FE type surface | `PublicReportSnapshot` added. |
| Dedicated snapshot schema | present. |
| Repo mutation beyond source/report | none. |
