from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import DBAPIError

from app.core.errors import AppError
from app.db import existing_report_queries
from app.services import fe_contract_store
from app.db import user_queries

# Component integration coverage for Track C store orchestration.
# These tests use a fake engine plus monkeypatched query-layer readers; they
# are intentionally not live qt_db(server) coverage.


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


class _FakeMappingsResult:
    def __init__(self, rows: list[dict[str, object]] | None = None):
        self._rows = rows or []

    def all(self):
        return [dict(row) for row in self._rows]

    def first(self):
        return dict(self._rows[0]) if self._rows else None


class _FakeResult:
    def __init__(self, rows: list[dict[str, object]] | None = None):
        self._rows = rows or []

    def mappings(self):
        return _FakeMappingsResult(self._rows)


class _FakeConnection:
    def __init__(self, engine):
        self.engine = engine

    async def execute(self, statement, params=None):
        sql = getattr(statement, "text", str(statement))
        params = dict(params or {})
        self.engine.write_log.append({"sql": sql, "params": params})
        normalized = " ".join(sql.split()).lower()
        if self.engine.fail_sql_contains and self.engine.fail_sql_contains in normalized:
            raise DBAPIError(sql, params, RuntimeError("synthetic transaction failure"), False)

        if normalized.startswith("insert into app.strategy ("):
            strategy_id = str(params["strategy_id"])
            if strategy_id not in self.engine.strategies:
                self.engine.strategies[strategy_id] = {
                    "strategy_id": strategy_id,
                    "strategy_name": params["strategy_name"],
                    "description": None,
                    "user_id": int(params["user_id"]),
                    "spec_jsonb": params["spec_jsonb"],
                }
            return _FakeResult()

        if normalized.startswith("select strategy_id, strategy_name, description, user_id, spec_jsonb from app.strategy"):
            strategy = self.engine.strategies.get(str(params["strategy_id"]))
            return _FakeResult([strategy] if strategy is not None else [])

        if normalized.startswith("insert into app.strategy_report_profile"):
            strategy_id = str(params["strategy_id"])
            if strategy_id not in self.engine.strategy_profiles:
                self.engine.strategy_profiles[strategy_id] = {
                    "strategy_id": strategy_id,
                    "name": params["name"],
                    "description": params.get("description"),
                    "universe": params.get("universe"),
                    "timeframe": params.get("timeframe") or "daily",
                    "tags": [],
                }
            return _FakeResult()

        if normalized.startswith("select strategy_id, name, description, universe, timeframe, tags from app.strategy_report_profile"):
            profile = self.engine.strategy_profiles.get(str(params["strategy_id"]))
            return _FakeResult([profile] if profile is not None else [])

        if (
            normalized.startswith("select run_id, strategy_id, user_id")
            and "from app.backtest_run" in normalized
            and "for update" in normalized
        ):
            run = self.engine.backtest_runs.get(str(params["run_id"]))
            if run is None or str(run.get("user_id")) != str(params.get("user_id")):
                return _FakeResult()
            return _FakeResult([run])

        if normalized.startswith("insert into app.backtest_run"):
            run_id = params["run_id"]
            if run_id not in self.engine.backtest_runs:
                self.engine.backtest_runs[run_id] = {
                    "run_id": run_id,
                    "strategy_id": params.get("strategy_id"),
                    "user_id": str(params.get("user_id")),
                    "initial_capital": params.get("initial_capital"),
                    "config_jsonb": params.get("config_jsonb"),
                    "strategy_snapshot_jsonb": params.get("strategy_snapshot_jsonb"),
                    "status": params.get("status"),
                    "created_at": params.get("created_at"),
                    "ended_at": None,
                    "error_message": None,
                    "trace_id": params.get("trace_id"),
                    "execution_run_id": params.get("execution_run_id"),
                    "benchmark_ticker": None,
                    "analysis_result_id": None,
                }
            return _FakeResult()

        if normalized.startswith("update app.backtest_run"):
            run_id = params["run_id"]
            row = self.engine.backtest_runs[run_id]
            row["strategy_id"] = params.get("strategy_id") or row.get("strategy_id")
            row["analysis_result_id"] = params.get("analysis_result_id") or row.get("analysis_result_id")
            row["status"] = "completed"
            row["ended_at"] = params.get("ended_at")
            row["error_message"] = None
            return _FakeResult()

        if normalized.startswith("select job_id, user_id, job_jsonb from app.ai_analysis_job"):
            job = self.engine.analysis_jobs.get(str(params["job_id"]))
            job_document = job.get("job_jsonb") if job is not None else None
            persisted_owner = job.get("user_id") if job is not None else None
            document_owner = job_document.get("user_id") if isinstance(job_document, dict) else None
            if job is not None and str(persisted_owner or document_owner) != str(params.get("user_id")):
                job = None
            return _FakeResult([job] if job is not None else [])

        if normalized.startswith("select analysis_result_id from app.ai_analysis_job"):
            job = self.engine.analysis_jobs.get(str(params["job_id"]))
            job_document = job.get("job_jsonb") if job is not None else None
            persisted_owner = job.get("user_id") if job is not None else None
            document_owner = job_document.get("user_id") if isinstance(job_document, dict) else None
            if job is None or str(persisted_owner or document_owner) != str(params["user_id"]):
                return _FakeResult()
            return _FakeResult([{"analysis_result_id": job.get("analysis_result_id")}])

        if normalized.startswith("update app.ai_analysis_job"):
            job = self.engine.analysis_jobs.get(str(params["job_id"]))
            job_document = job.get("job_jsonb") if job is not None else None
            persisted_owner = job.get("user_id") if job is not None else None
            document_owner = job_document.get("user_id") if isinstance(job_document, dict) else None
            if job is not None and str(persisted_owner or document_owner) == str(params["user_id"]):
                job["analysis_result_id"] = params["analysis_result_id"]
            return _FakeResult()

        if normalized.startswith("insert into app.analysis_result"):
            key = (str(params["user_id"]), str(params["manifest_hash"]))
            if key not in self.engine.analysis_results:
                self.engine.analysis_results[key] = dict(params)
            return _FakeResult()

        if normalized.startswith("select analysis_result_id, user_id, manifest_schema_version, manifest_hash"):
            key = (str(params["user_id"]), str(params["manifest_hash"]))
            row = self.engine.analysis_results.get(key)
            return _FakeResult([row] if row is not None else [])

        if normalized.startswith("select analysis_result_id from app.backtest_run"):
            row = self.engine.backtest_runs.get(str(params["run_id"]))
            if row is None or str(row.get("user_id")) != str(params.get("user_id")):
                return _FakeResult()
            return _FakeResult([{"analysis_result_id": row.get("analysis_result_id")}])

        if normalized.startswith("select report.analysis_result_id from app.strategy_email_report as report"):
            report = self.engine.strategy_email_reports.get(str(params["report_id"]))
            run = self.engine.backtest_runs.get(str(report.get("backtest_run_id"))) if report else None
            if report is None or run is None or str(run.get("user_id")) != str(params.get("user_id")):
                return _FakeResult()
            return _FakeResult([{"analysis_result_id": report.get("analysis_result_id")}])

        if normalized.startswith("select report.report_id, report.analysis_result_id from app.strategy_email_report as report"):
            rows = []
            for report_id in params["report_ids"]:
                report = self.engine.strategy_email_reports.get(str(report_id))
                run = self.engine.backtest_runs.get(str(report.get("backtest_run_id"))) if report else None
                if report is not None and run is not None and str(run.get("user_id")) == str(params.get("user_id")):
                    rows.append({"report_id": report_id, "analysis_result_id": report.get("analysis_result_id")})
            return _FakeResult(rows)

        # Both the replay guard and _validate_completion_replay read this row, with and
        # without analysis_result_id in the column list. Matching only one of the two
        # shapes silently starves the other of rows and disarms its conflict check.
        if normalized.startswith("select report_id, run_id, user_id,") and "from app.ai_backtest_report" in normalized:
            report_id = params["report_id"]
            row = self.engine.ai_backtest_reports.get(report_id)
            return _FakeResult([row] if row is not None else [])

        if normalized.startswith("update app.ai_backtest_report"):
            row = self.engine.ai_backtest_reports.get(params["report_id"])
            if (
                row is not None
                and str(row.get("run_id")) == str(params["run_id"])
                and (row.get("user_id") is None or str(row.get("user_id")) == str(params["user_id"]))
                and row.get("analysis_result_id") is None
            ):
                row["analysis_result_id"] = params["analysis_result_id"]
            return _FakeResult()

        if normalized.startswith("insert into app.ai_backtest_report"):
            report_id = params["report_id"]
            if report_id not in self.engine.ai_backtest_reports:
                self.engine.ai_backtest_reports[report_id] = dict(params)
            return _FakeResult()

        if normalized.startswith("insert into app.strategy_email_report"):
            report_id = params["report_id"]
            if report_id not in self.engine.strategy_email_reports:
                self.engine.strategy_email_reports[report_id] = dict(params)
            return _FakeResult()

        if normalized.startswith("update app.strategy_email_report"):
            row = self.engine.strategy_email_reports.get(params["report_id"])
            if (
                row is not None
                and str(row.get("backtest_run_id")) == str(params["run_id"])
                and row.get("analysis_result_id") is None
            ):
                row["analysis_result_id"] = params["analysis_result_id"]
            return _FakeResult()

        if normalized.startswith("select report_id, strategy_id, backtest_run_id, ai_report_id, analysis_result_id, report_date"):
            report_id = params["report_id"]
            row = self.engine.strategy_email_reports.get(report_id)
            return _FakeResult([row] if row is not None else [])

        return _FakeResult()


class _FakeTransaction:
    def __init__(self, engine):
        self.engine = engine

    async def __aenter__(self):
        self.snapshot = {
            "strategies": copy.deepcopy(self.engine.strategies),
            "strategy_profiles": copy.deepcopy(self.engine.strategy_profiles),
            "backtest_runs": copy.deepcopy(self.engine.backtest_runs),
            "ai_backtest_reports": copy.deepcopy(self.engine.ai_backtest_reports),
            "strategy_email_reports": copy.deepcopy(self.engine.strategy_email_reports),
            "analysis_results": copy.deepcopy(self.engine.analysis_results),
            "analysis_jobs": copy.deepcopy(self.engine.analysis_jobs),
        }
        return _FakeConnection(self.engine)

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.engine.strategies = self.snapshot["strategies"]
            self.engine.strategy_profiles = self.snapshot["strategy_profiles"]
            self.engine.backtest_runs = self.snapshot["backtest_runs"]
            self.engine.ai_backtest_reports = self.snapshot["ai_backtest_reports"]
            self.engine.strategy_email_reports = self.snapshot["strategy_email_reports"]
            self.engine.analysis_results = self.snapshot["analysis_results"]
            self.engine.analysis_jobs = self.snapshot["analysis_jobs"]
        return False


class TrackCFakeEngine:
    def __init__(self):
        self.strategies: dict[str, dict[str, object]] = {
            "strategy-1": {
                "strategy_id": "strategy-1",
                "strategy_name": "RSI 30",
                "description": None,
                "user_id": 42,
                "spec_jsonb": {},
            }
        }
        self.strategy_profiles: dict[str, dict[str, object]] = {}
        self.backtest_runs: dict[str, dict[str, object]] = {}
        self.ai_backtest_reports: dict[str, dict[str, object]] = {}
        self.strategy_email_reports: dict[str, dict[str, object]] = {}
        self.analysis_results: dict[tuple[str, str], dict[str, object]] = {}
        self.analysis_jobs: dict[str, dict[str, object]] = {}
        self.write_log: list[dict[str, object]] = []
        self.fail_sql_contains: str | None = None

    def begin(self):
        return _FakeTransaction(self)

    def connect(self):
        return _FakeTransaction(self)


def _track_c_run_view(engine: TrackCFakeEngine, run_id: str, user_id: str) -> dict[str, object] | None:
    row = engine.backtest_runs.get(run_id)
    if row is None or str(row.get("user_id")) != str(user_id):
        return None
    config = json.loads(str(row.get("config_jsonb") or "{}"))
    request_payload = config.get("requestPayload") or config.get("request_payload") or {}
    linked_report_id = next(
        (
            report_id
            for report_id, report in engine.strategy_email_reports.items()
            if str(report.get("backtest_run_id")) == run_id and str(row.get("user_id")) == str(user_id)
        ),
        None,
    )
    return {
        "id": run_id,
        "status": row.get("status"),
        "reportId": linked_report_id,
        "error": None,
        "createdAt": _iso(row.get("created_at")),
        "updatedAt": _iso(row.get("ended_at") or row.get("created_at")),
        "strategyId": config.get("strategyId") or config.get("strategy_id") or row.get("strategy_id"),
        "instrumentId": config.get("instrumentId") or config.get("instrument_id") or request_payload.get("instrumentId"),
        "ticker": config.get("ticker") or request_payload.get("ticker"),
        "aiJobId": config.get("aiJobId") or config.get("ai_job_id") or request_payload.get("aiJobId") or request_payload.get("ai_job_id"),
    }


def _track_c_report_view(engine: TrackCFakeEngine, report_id: str, user_id: str) -> dict[str, object] | None:
    row = engine.strategy_email_reports.get(report_id)
    if row is None:
        return None
    run = engine.backtest_runs.get(str(row.get("backtest_run_id")))
    if run is None or str(run.get("user_id")) != str(user_id):
        return None
    content_text = row.get("content_html") or row.get("content_md") or "{}"
    content = json.loads(str(content_text))
    return {
        "id": report_id,
        "runId": str(row.get("backtest_run_id")),
        "title": row.get("title"),
        "summary": row.get("summary"),
        "status": row.get("status"),
        "createdAt": _iso(row.get("created_at") or row.get("sent_at")),
        "updatedAt": _iso(row.get("updated_at") or row.get("sent_at") or row.get("created_at")),
        "strategyId": row.get("strategy_id"),
        "strategyName": None,
        "instrumentId": None,
        "instrumentName": None,
        "ticker": None,
        "publishedAt": _iso(row.get("sent_at") or row.get("created_at")),
        "content": content,
    }


def _iso(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return str(value)


def _handle_engine(handle):
    return getattr(handle, "engine", handle)


def _install_state_readers(monkeypatch, engine: TrackCFakeEngine):
    async def fake_get_analysis_run(_engine, run_id: str, *, user_id: str | None = None):
        assert _handle_engine(_engine) is engine
        return _track_c_run_view(engine, run_id, user_id or "")

    async def fake_get_report(_engine, report_id: str, *, user_id: str | None = None):
        assert _handle_engine(_engine) is engine
        return _track_c_report_view(engine, report_id, user_id or "")

    monkeypatch.setattr(existing_report_queries, "get_analysis_run", fake_get_analysis_run)
    monkeypatch.setattr(existing_report_queries, "get_report", fake_get_report)


@pytest.mark.asyncio
async def test_track_c_projection_helper_uses_one_active_connection_without_nested_begin(monkeypatch):
    source_user = {
        "id": "42",
        "email": "user@example.co.kr",
        "auth_provider": "google",
        "provider_user_id": "google-sub-1",
        "name": "Track C User",
        "picture": "https://example.co.kr/avatar.png",
    }
    fake_connection = SimpleNamespace(executed=[], begin_called=False)

    class FakeUserSchemaReport:
        columns = {"id", "email", "auth_provider", "provider_user_id", "name", "picture"}
        missing_required_columns: set[str] = set()
        supports_google_identity = True
        user_id_column = "id"

    async def fake_inspect_user_schema(connection):
        assert connection is fake_connection
        return FakeUserSchemaReport()

    async def fake_fetch_one(connection, sql, params=None):
        assert connection is fake_connection
        fake_connection.executed.append({"sql": sql, "params": dict(params or {})})
        return {
            "id": 42,
            "email": source_user["email"],
            "auth_provider": source_user["auth_provider"],
            "provider_user_id": source_user["provider_user_id"],
            "name": source_user["name"],
            "picture": source_user["picture"],
        }

    async def fake_execute(statement, params=None):
        fake_connection.executed.append({"sql": str(statement), "params": dict(params or {})})

        class _Result:
            def mappings(self):
                return self

            def first(self):
                return None

        return _Result()

    fake_connection.execute = fake_execute

    def fail_begin():
        fake_connection.begin_called = True
        raise AssertionError("ensure_server_user_projection must not open a nested transaction")

    fake_connection.begin = fail_begin

    monkeypatch.setattr(user_queries, "inspect_user_schema", fake_inspect_user_schema)
    monkeypatch.setattr(fe_contract_store, "fetch_one", fake_fetch_one)

    projected = await fe_contract_store.ensure_server_user_projection(
        fake_connection,
        source_user=source_user,
        user_id="42",
    )

    assert fake_connection.begin_called is False
    assert projected["email"] == source_user["email"]
    assert projected["auth_provider"] == "google"
    assert projected["provider_user_id"] == "google-sub-1"
    assert len(fake_connection.executed) == 2
    assert "INSERT INTO app.users" in fake_connection.executed[0]["sql"]
    assert "SELECT * FROM app.users" in fake_connection.executed[1]["sql"]


@pytest.mark.asyncio
async def test_track_c_component_integration_create_analysis_run_replays_idempotently(monkeypatch):
    engine = TrackCFakeEngine()
    _install_state_readers(monkeypatch, engine)

    payload = {"query": "RSI 30", "strategyId": "strategy-1", "requestPayload": {"seed": "alpha"}}

    created = await fe_contract_store.create_analysis_run_from_db(engine, user_id="42", payload=payload)
    replayed = await fe_contract_store.create_analysis_run_from_db(engine, user_id="42", payload=payload)

    assert created["id"] == replayed["id"]
    assert created["strategyId"] == "strategy-1"
    assert created["ticker"] is None
    assert sum(1 for entry in engine.write_log if "insert into app.backtest_run" in str(entry["sql"]).lower()) == 1


@pytest.mark.asyncio
async def test_track_c_component_integration_complete_analysis_run_replays_and_conflicts(monkeypatch):
    engine = TrackCFakeEngine()
    _install_state_readers(monkeypatch, engine)

    payload = {"query": "RSI 30", "strategyId": "strategy-1", "requestPayload": {"seed": "alpha"}}
    run = await fe_contract_store.create_analysis_run_from_db(engine, user_id="42", payload=payload)

    completion = {
        "status": "completed",
        "result": {
            "title": "Track C report",
            "summary": "Track C summary",
            "userPayload": {
                "report": {
                    "webProjection": {
                        "title": "Track C report",
                        "summary": "Track C summary",
                        "sections": [{"title": "Section", "summary": "Body"}],
                    }
                }
            },
        },
    }

    created = await fe_contract_store.complete_analysis_run_from_db(engine, user_id="42", run_id=run["id"], payload=completion)
    replayed = await fe_contract_store.complete_analysis_run_from_db(engine, user_id="42", run_id=run["id"], payload=completion)

    conflict = dict(completion)
    conflict["result"] = {
        "title": "Track C report",
        "summary": "Different summary",
        "userPayload": {
            "report": {
                "webProjection": {
                    "title": "Track C report",
                    "summary": "Different summary",
                    "sections": [{"title": "Section", "summary": "Body"}],
                }
            }
        },
    }

    assert created == {
        "runId": run["id"],
        "reportId": created["reportId"],
        "analysisResultId": created["analysisResultId"],
        "status": "completed",
        "created": True,
    }
    assert replayed == {
        "runId": run["id"],
        "reportId": created["reportId"],
        "analysisResultId": created["analysisResultId"],
        "status": "completed",
        "created": False,
    }
    assert engine.backtest_runs[run["id"]]["analysis_result_id"] == created["analysisResultId"]
    assert engine.ai_backtest_reports[created["reportId"]]["analysis_result_id"] == created["analysisResultId"]
    assert engine.strategy_email_reports[created["reportId"]]["analysis_result_id"] == created["analysisResultId"]
    assert len(engine.analysis_results) == 1
    with pytest.raises(AppError) as exc:
        await fe_contract_store.complete_analysis_run_from_db(engine, user_id="42", run_id=run["id"], payload=conflict)
    assert exc.value.status_code == 409
    assert sum(1 for entry in engine.write_log if "insert into app.backtest_run" in str(entry["sql"]).lower()) == 1
    assert sum(1 for entry in engine.write_log if "insert into app.ai_backtest_report" in str(entry["sql"]).lower()) == 1
    assert sum(1 for entry in engine.write_log if "insert into app.strategy_email_report" in str(entry["sql"]).lower()) == 1


def _ai_job_run_payload(seed: str, ai_job_id: str) -> dict[str, object]:
    return {
        "query": "RSI 30",
        "strategyId": "strategy-1",
        "aiJobId": ai_job_id,
        "requestPayload": {"aiJobId": ai_job_id, "query": "RSI 30", "seed": seed},
    }


def _ai_job_completion(ai_job_id: str, result: dict[str, object]) -> dict[str, object]:
    return {"status": "completed", "aiJobId": ai_job_id, "result": {**result, "aiJobId": ai_job_id}}


@pytest.mark.asyncio
async def test_track_c_completion_replay_for_same_ai_job_survives_result_schema_drift(monkeypatch):
    # The AI result schema gains fields between deploys, so the snapshot the server
    # re-derives on a replay no longer matches the one persisted at first save. Completion
    # is idempotent per (user, aiJobId): that drift must not 409 and must not rewrite the
    # immutable analysis_result / report rows.
    engine = TrackCFakeEngine()
    _install_state_readers(monkeypatch, engine)

    run = await fe_contract_store.create_analysis_run_from_db(
        engine, user_id="42", payload=_ai_job_run_payload("drift", "ai-job-1")
    )
    created = await fe_contract_store.complete_analysis_run_from_db(
        engine,
        user_id="42",
        run_id=run["id"],
        payload=_ai_job_completion("ai-job-1", {"title": "Report", "summary": "Summary"}),
    )
    report_id = created["reportId"]
    before = copy.deepcopy(
        {
            "run": engine.backtest_runs[run["id"]],
            "ai_report": engine.ai_backtest_reports[report_id],
            "email_report": engine.strategy_email_reports[report_id],
            "analysis_results": engine.analysis_results,
        }
    )
    writes_before = len(engine.write_log)

    replayed = await fe_contract_store.complete_analysis_run_from_db(
        engine,
        user_id="42",
        run_id=run["id"],
        payload=_ai_job_completion(
            "ai-job-1",
            {
                "title": "Report",
                "summary": "Summary",
                "strategySpec": {"holdingDays": 5, "rebalanceIntervalDays": 20},
                "performance": {"outSampleMaxDrawdown": -0.12},
            },
        ),
    )

    assert created["created"] is True
    assert replayed == {
        "runId": run["id"],
        "reportId": report_id,
        "analysisResultId": created["analysisResultId"],
        "status": "completed",
        "created": False,
    }
    assert engine.backtest_runs[run["id"]] == before["run"]
    assert engine.ai_backtest_reports[report_id] == before["ai_report"]
    assert engine.strategy_email_reports[report_id] == before["email_report"]
    assert engine.analysis_results == before["analysis_results"]
    replay_writes = [
        entry for entry in engine.write_log[writes_before:]
        if not " ".join(str(entry["sql"]).split()).lower().startswith("select")
    ]
    assert replay_writes == []


@pytest.mark.asyncio
async def test_track_c_completion_replay_still_backfills_a_partially_linked_run(monkeypatch):
    # The replay short-circuit must not skip the idempotent analysis_result_id backfills
    # while any of the three rows is still unlinked - a run left half-linked by a partial
    # migration would otherwise take the short-circuit forever and never heal.
    engine = TrackCFakeEngine()
    _install_state_readers(monkeypatch, engine)

    run = await fe_contract_store.create_analysis_run_from_db(
        engine, user_id="42", payload=_ai_job_run_payload("partial", "ai-job-1")
    )
    completion = _ai_job_completion("ai-job-1", {"title": "Report", "summary": "Summary"})
    created = await fe_contract_store.complete_analysis_run_from_db(
        engine, user_id="42", run_id=run["id"], payload=completion
    )
    report_id = created["reportId"]
    engine.ai_backtest_reports[report_id]["analysis_result_id"] = None
    engine.strategy_email_reports[report_id]["analysis_result_id"] = None

    replayed = await fe_contract_store.complete_analysis_run_from_db(
        engine, user_id="42", run_id=run["id"], payload=completion
    )

    assert replayed["created"] is False
    assert engine.ai_backtest_reports[report_id]["analysis_result_id"] == created["analysisResultId"]
    assert engine.strategy_email_reports[report_id]["analysis_result_id"] == created["analysisResultId"]
    assert len(engine.analysis_results) == 1


@pytest.mark.asyncio
async def test_track_c_completion_for_a_different_ai_job_still_conflicts(monkeypatch):
    engine = TrackCFakeEngine()
    _install_state_readers(monkeypatch, engine)

    run = await fe_contract_store.create_analysis_run_from_db(
        engine, user_id="42", payload=_ai_job_run_payload("conflict", "ai-job-1")
    )
    await fe_contract_store.complete_analysis_run_from_db(
        engine,
        user_id="42",
        run_id=run["id"],
        payload=_ai_job_completion("ai-job-1", {"title": "Report", "summary": "Summary"}),
    )

    with pytest.raises(AppError) as exc:
        await fe_contract_store.complete_analysis_run_from_db(
            engine,
            user_id="42",
            run_id=run["id"],
            payload=_ai_job_completion("ai-job-2", {"title": "Report", "summary": "Summary"}),
        )

    assert exc.value.status_code == 409
    assert len(engine.analysis_results) == 1


@pytest.mark.asyncio
async def test_track_c_completion_replay_stays_scoped_to_the_owning_user(monkeypatch):
    engine = TrackCFakeEngine()
    _install_state_readers(monkeypatch, engine)

    run = await fe_contract_store.create_analysis_run_from_db(
        engine, user_id="42", payload=_ai_job_run_payload("scope", "ai-job-1")
    )
    await fe_contract_store.complete_analysis_run_from_db(
        engine,
        user_id="42",
        run_id=run["id"],
        payload=_ai_job_completion("ai-job-1", {"title": "Report", "summary": "Summary"}),
    )

    with pytest.raises(AppError) as exc:
        await fe_contract_store.complete_analysis_run_from_db(
            engine,
            user_id="43",
            run_id=run["id"],
            payload=_ai_job_completion("ai-job-1", {"title": "Report", "summary": "Summary"}),
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_track_c_legacy_completed_rows_with_null_result_id_replay_and_backfill(monkeypatch):
    engine = TrackCFakeEngine()
    _install_state_readers(monkeypatch, engine)
    run = await fe_contract_store.create_analysis_run_from_db(
        engine,
        user_id="42",
        payload={"query": "RSI 30", "strategyId": "strategy-1", "requestPayload": {"seed": "legacy"}},
    )
    completion = {
        "status": "completed",
        "result": {
            "title": "Legacy report",
            "summary": "Legacy summary",
            "sections": [{"title": "Section", "summary": "Body"}],
        },
    }
    created = await fe_contract_store.complete_analysis_run_from_db(
        engine, user_id="42", run_id=run["id"], payload=completion
    )
    report_id = created["reportId"]
    expected_result_id = created["analysisResultId"]
    engine.backtest_runs[run["id"]]["analysis_result_id"] = None
    engine.ai_backtest_reports[report_id]["analysis_result_id"] = None
    engine.strategy_email_reports[report_id]["analysis_result_id"] = None

    replayed = await fe_contract_store.complete_analysis_run_from_db(
        engine, user_id="42", run_id=run["id"], payload=completion
    )

    assert replayed["analysisResultId"] == expected_result_id
    assert replayed["created"] is False
    assert engine.backtest_runs[run["id"]]["analysis_result_id"] == expected_result_id
    assert engine.ai_backtest_reports[report_id]["analysis_result_id"] == expected_result_id
    assert engine.strategy_email_reports[report_id]["analysis_result_id"] == expected_result_id
    assert len(engine.analysis_results) == 1


@pytest.mark.asyncio
async def test_track_c_legacy_completed_rows_with_null_result_id_reject_changed_replay(monkeypatch):
    engine = TrackCFakeEngine()
    _install_state_readers(monkeypatch, engine)
    run = await fe_contract_store.create_analysis_run_from_db(
        engine,
        user_id="42",
        payload={"query": "RSI 30", "strategyId": "strategy-1", "requestPayload": {"seed": "legacy-conflict"}},
    )
    completion = {
        "status": "completed",
        "result": {"title": "Legacy report", "summary": "Legacy summary"},
    }
    created = await fe_contract_store.complete_analysis_run_from_db(
        engine, user_id="42", run_id=run["id"], payload=completion
    )
    report_id = created["reportId"]
    engine.backtest_runs[run["id"]]["analysis_result_id"] = None
    engine.ai_backtest_reports[report_id]["analysis_result_id"] = None
    engine.strategy_email_reports[report_id]["analysis_result_id"] = None
    changed = {
        "status": "completed",
        "result": {"title": "Legacy report", "summary": "Changed summary"},
    }

    with pytest.raises(AppError) as exc:
        await fe_contract_store.complete_analysis_run_from_db(
            engine, user_id="42", run_id=run["id"], payload=changed
        )

    assert exc.value.status_code == 409
    # Pins the conflict to _validate_completion_replay rather than a later site: that is
    # the check the replay short-circuit must sit in front of, not behind.
    assert exc.value.message == "Analysis run is already completed with different content"
    assert engine.backtest_runs[run["id"]]["analysis_result_id"] is None
    assert engine.ai_backtest_reports[report_id]["analysis_result_id"] is None
    assert engine.strategy_email_reports[report_id]["analysis_result_id"] is None
    assert len(engine.analysis_results) == 1


@pytest.mark.asyncio
async def test_track_c_component_integration_store_wrappers_forward_to_query_layer(monkeypatch):
    engine = TrackCFakeEngine()
    observed: dict[str, object] = {}

    async def fake_get_analysis_run(_engine, run_id: str, *, user_id: str | None = None):
        observed["analysis_run"] = (_engine, run_id, user_id)
        return {"id": run_id}

    async def fake_list_reports(
        _engine,
        *,
        user_id: str,
        limit: int = 20,
        cursor: str | None = None,
        status: str | None = None,
        q: str | None = None,
    ):
        observed["list_reports"] = (_engine, user_id, limit, cursor, status, q)
        return {"items": [], "meta": {"limit": limit, "hasMore": False, "nextCursor": None}}

    async def fake_get_report(_engine, report_id: str, *, user_id: str | None = None):
        observed["report"] = (_engine, report_id, user_id)
        return {"id": report_id}

    async def fake_list_reader_reports(
        _engine,
        *,
        user_id: str,
        limit: int = 20,
        cursor: str | None = None,
        status: str | None = None,
        q: str | None = None,
    ):
        observed["reader_list_reports"] = (_engine, user_id, limit, cursor, status, q)
        return {"items": [], "meta": {"limit": limit, "hasMore": False, "nextCursor": None}}

    async def fake_get_reader_report(_engine, report_id: str, *, user_id: str | None = None):
        observed["reader_report"] = (_engine, report_id, user_id)
        return {"id": report_id}

    monkeypatch.setattr(existing_report_queries, "get_analysis_run", fake_get_analysis_run)
    monkeypatch.setattr(existing_report_queries, "list_reports", fake_list_reports)
    monkeypatch.setattr(existing_report_queries, "get_report", fake_get_report)
    monkeypatch.setattr(existing_report_queries, "list_reader_reports", fake_list_reader_reports)
    monkeypatch.setattr(existing_report_queries, "get_reader_report", fake_get_reader_report)

    assert await fe_contract_store.get_analysis_run_from_db(engine, "run-1", user_id="42") == {"id": "run-1"}
    assert await fe_contract_store.list_reports_from_db(engine, user_id="42", limit=5, cursor="cursor", status="sent", q="삼성전자") == {
        "items": [],
        "meta": {"limit": 5, "hasMore": False, "nextCursor": None},
    }
    assert await fe_contract_store.get_report_from_db(engine, "report-1", user_id="42") == {"id": "report-1"}
    assert await fe_contract_store.list_reader_reports_from_db(engine, user_id="42", limit=5, cursor="cursor", status="sent", q="report-1") == {
        "items": [],
        "meta": {"limit": 5, "hasMore": False, "nextCursor": None},
    }
    assert await fe_contract_store.get_reader_report_from_db(engine, "report-1", user_id="42") == {"id": "report-1"}
    assert observed["analysis_run"] == (engine, "run-1", "42")
    assert observed["list_reports"] == (engine, "42", 5, "cursor", "sent", "삼성전자")
    assert observed["report"] == (engine, "report-1", "42")
    assert observed["reader_list_reports"] == (engine, "42", 5, "cursor", "sent", "report-1")
    assert observed["reader_report"] == (engine, "report-1", "42")


def test_track_c_generated_strategy_id_is_stable_user_scoped_and_not_run_id():
    payload = {
        "query": "RSI 30",
        "aiJobId": "job-1",
        "requestPayload": {"query": "RSI 30", "timeframe": "daily"},
    }
    run_id = fe_contract_store._analysis_run_uuid("42", payload)

    first = fe_contract_store._analysis_run_strategy_uuid("42", payload)
    replay = fe_contract_store._analysis_run_strategy_uuid("42", payload)
    other_user = fe_contract_store._analysis_run_strategy_uuid("43", payload)

    assert first == replay
    assert first != other_user
    assert first != run_id


def test_analysis_result_identity_is_canonical_owner_scoped_and_changes_with_manifest():
    result = {
        "summary": "Summary",
        "title": "Report",
        "recommendationGate": {"status": "PASS"},
        "strategySpec": {
            "entry": ["rsi < 30"],
            "exit": ["rsi > 70"],
            "risk_constraints": {"private_market_limit": 0.2},
        },
        "performance": {"dataQuality": ["postgres"], "reliability": {"status": "sufficient"}},
    }
    execution = {
        "schema_version": "1",
        "run_identity": {"job_id": "job-1", "run_id": "run-1"},
        "policy_hashes": {"strategy": "a" * 64},
    }
    first = fe_contract_store._analysis_result_manifest_bundle(result=result, execution_manifest=execution)
    reordered = fe_contract_store._analysis_result_manifest_bundle(
        result={
            "performance": result["performance"],
            "strategy_spec": result["strategySpec"],
            "recommendation_gate": result["recommendationGate"],
            "title": "Report",
            "summary": "Summary",
        },
        execution_manifest={"policy_hashes": execution["policy_hashes"], "run_identity": execution["run_identity"], "schema_version": "1"},
    )
    changed_result = copy.deepcopy(result)
    changed_result["strategySpec"]["risk_constraints"]["private_market_limit"] = 0.3
    changed = fe_contract_store._analysis_result_manifest_bundle(
        result=changed_result,
        execution_manifest=execution,
    )

    assert fe_contract_store._analysis_result_uuid("42", first) == fe_contract_store._analysis_result_uuid("42", reordered)
    assert fe_contract_store._analysis_result_uuid("42", first) != fe_contract_store._analysis_result_uuid("42", changed)
    assert fe_contract_store._analysis_result_uuid("42", first) != fe_contract_store._analysis_result_uuid("43", first)
    assert first["report"]["result"]["strategySpec"]["risk_constraints"]["private_market_limit"] == 0.2


def test_analysis_result_identity_normalizes_numbers_and_preserves_null_string_semantics():
    execution = {"schema_version": "1", "run_identity": {"run_id": "run-1"}}
    numeric_float = fe_contract_store._analysis_result_manifest_bundle(
        result={"title": "Report", "sections": [{"value": 1.0, "optional": None}]},
        execution_manifest=execution,
    )
    numeric_int = fe_contract_store._analysis_result_manifest_bundle(
        result={"title": "Report", "sections": [{"optional": None, "value": 1}]},
        execution_manifest=execution,
    )
    numeric_string = fe_contract_store._analysis_result_manifest_bundle(
        result={"title": "Report", "sections": [{"value": "1", "optional": None}]},
        execution_manifest=execution,
    )
    missing_null = fe_contract_store._analysis_result_manifest_bundle(
        result={"title": "Report", "sections": [{"value": 1}]},
        execution_manifest=execution,
    )

    assert fe_contract_store._analysis_result_manifest_hash(numeric_float) == fe_contract_store._analysis_result_manifest_hash(numeric_int)
    assert fe_contract_store._analysis_result_manifest_hash(numeric_int) != fe_contract_store._analysis_result_manifest_hash(numeric_string)
    assert fe_contract_store._analysis_result_manifest_hash(numeric_int) != fe_contract_store._analysis_result_manifest_hash(missing_null)


def test_analysis_result_public_snapshot_filters_nested_fields_without_changing_identity_manifest():
    result = {
        "title": "Public report",
        "summary": "Public summary",
        "sections": [{"title": "Visible", "privateNote": "remove me"}],
        "performance": {"reliability": {"status": "sufficient"}, "apiKey": "remove me"},
        "internalPayload": {"node_outputs": {"secret": "remove me"}},
        "debugRef": "remove me",
    }
    execution = {
        "schema_version": "1",
        "run_identity": {"job_id": "job-1"},
        "events": {"fills": [{"document": {"token_count": 10}}]},
    }

    public_result = fe_contract_store._public_analysis_result_payload(result)
    manifests = fe_contract_store._analysis_result_manifest_bundle(result=result, execution_manifest=execution)
    public_serialized = json.dumps(public_result, sort_keys=True).lower()
    identity_serialized = json.dumps(manifests, sort_keys=True).lower()

    assert "internalpayload" not in public_serialized
    assert "debugref" not in public_serialized
    assert "privatenote" not in public_serialized
    assert "apikey" not in public_serialized
    assert "privatenote" in identity_serialized
    assert "apikey" in identity_serialized
    assert "token_count" in identity_serialized


@pytest.mark.asyncio
async def test_analysis_result_links_persisted_job_run_report_and_owner_projection(monkeypatch):
    engine = TrackCFakeEngine()
    _install_state_readers(monkeypatch, engine)
    engine.analysis_jobs["job-1"] = {
        "job_id": "job-1",
        "user_id": None,
        "job_jsonb": {
            "user_id": "42",
            "execution_manifest": {
                "schema_version": "1",
                "run_identity": {"job_id": "job-1", "run_id": "run-1"},
                "policy_hashes": {"strategy": "a" * 64},
            }
        },
        "analysis_result_id": None,
    }
    run = await fe_contract_store.create_analysis_run_from_db(
        engine,
        user_id="42",
        payload={"query": "RSI 30", "strategyId": "strategy-1", "aiJobId": "job-1"},
    )
    completed = await fe_contract_store.complete_analysis_run_from_db(
        engine,
        user_id="42",
        run_id=run["id"],
        payload={
            "status": "completed",
            "aiJobId": "job-1",
            "result": {"title": "Report", "summary": "Summary"},
        },
    )

    result_id = completed["analysisResultId"]
    assert engine.analysis_jobs["job-1"]["analysis_result_id"] == result_id
    assert engine.backtest_runs[run["id"]]["analysis_result_id"] == result_id
    assert engine.ai_backtest_reports[completed["reportId"]]["analysis_result_id"] == result_id
    assert engine.strategy_email_reports[completed["reportId"]]["analysis_result_id"] == result_id
    assert (await fe_contract_store.get_analysis_run_from_db(engine, run["id"], user_id="42"))["analysisResultId"] == result_id
    assert (await fe_contract_store.get_report_from_db(engine, completed["reportId"], user_id="42"))["analysisResultId"] == result_id

    async def fake_list_reports(_engine, **_kwargs):
        return {
            "items": [{"id": completed["reportId"], "runId": run["id"]}],
            "meta": {"limit": 20, "hasMore": False, "nextCursor": None},
        }

    monkeypatch.setattr(existing_report_queries, "list_reports", fake_list_reports)
    listed = await fe_contract_store.list_reports_from_db(engine, user_id="42")
    assert listed["items"][0]["analysisResultId"] == result_id
    assert await fe_contract_store.get_analysis_run_from_db(engine, run["id"], user_id="99") is None
    assert await fe_contract_store.get_report_from_db(engine, completed["reportId"], user_id="99") is None


@pytest.mark.asyncio
async def test_track_c_create_without_strategy_id_returns_real_distinct_strategy(monkeypatch):
    engine = TrackCFakeEngine()
    _install_state_readers(monkeypatch, engine)
    payload = {"query": "RSI 30", "aiJobId": "job-1", "requestPayload": {"seed": "alpha"}}

    created = await fe_contract_store.create_analysis_run_from_db(engine, user_id="42", payload=payload)
    replayed = await fe_contract_store.create_analysis_run_from_db(engine, user_id="42", payload=payload)

    assert created["strategyId"]
    assert created["strategyId"] == replayed["strategyId"]
    assert created["strategyId"] != created["id"]
    assert created["strategyId"] in engine.strategies
    assert created["strategyId"] in engine.strategy_profiles
    assert json.loads(str(engine.strategies[created["strategyId"]]["spec_jsonb"]))["provenance"]["source"] == "track-c-run-request"


@pytest.mark.asyncio
async def test_track_c_create_rejects_strategy_owned_by_another_user(monkeypatch):
    engine = TrackCFakeEngine()
    engine.strategies["foreign-strategy"] = {
        "strategy_id": "foreign-strategy",
        "strategy_name": "Foreign",
        "description": None,
        "user_id": 99,
        "spec_jsonb": {},
    }
    _install_state_readers(monkeypatch, engine)

    with pytest.raises(AppError) as exc:
        await fe_contract_store.create_analysis_run_from_db(
            engine,
            user_id="42",
            payload={"query": "RSI 30", "strategyId": "foreign-strategy"},
        )

    assert exc.value.status_code == 404
    assert engine.backtest_runs == {}


@pytest.mark.asyncio
async def test_track_c_completion_repairs_legacy_null_strategy_and_missing_profile(monkeypatch):
    engine = TrackCFakeEngine()
    _install_state_readers(monkeypatch, engine)
    payload = {"query": "Legacy RSI", "aiJobId": "legacy-job", "requestPayload": {"seed": "legacy"}}
    run_id = fe_contract_store._analysis_run_uuid("42", payload)
    created_at = datetime(2026, 7, 20, tzinfo=UTC)
    engine.backtest_runs[run_id] = {
        "run_id": run_id,
        "strategy_id": None,
        "user_id": "42",
        "initial_capital": 1_000_000,
        "config_jsonb": _json_text(payload),
        "strategy_snapshot_jsonb": _json_text({"query": "Legacy RSI"}),
        "status": "queued",
        "created_at": created_at,
        "ended_at": None,
        "error_message": None,
        "trace_id": None,
        "execution_run_id": None,
        "benchmark_ticker": None,
    }
    completion = {
        "status": "completed",
        "completedAt": "2026-07-20T12:00:00Z",
        "result": {"title": "Legacy report", "summary": "Legacy summary"},
    }

    result = await fe_contract_store.complete_analysis_run_from_db(
        engine,
        user_id="42",
        run_id=run_id,
        payload=completion,
    )

    strategy_id = str(engine.backtest_runs[run_id]["strategy_id"])
    assert result["status"] == "completed"
    assert strategy_id
    assert strategy_id != run_id
    assert strategy_id in engine.strategies
    assert strategy_id in engine.strategy_profiles


@pytest.mark.asyncio
async def test_track_c_completion_recreates_missing_profile_without_overwriting_strategy(monkeypatch):
    engine = TrackCFakeEngine()
    _install_state_readers(monkeypatch, engine)
    payload = {"query": "RSI 30", "strategyId": "strategy-1"}
    run = await fe_contract_store.create_analysis_run_from_db(engine, user_id="42", payload=payload)
    engine.strategy_profiles.clear()

    await fe_contract_store.complete_analysis_run_from_db(
        engine,
        user_id="42",
        run_id=run["id"],
        payload={
            "status": "completed",
            "completedAt": "2026-07-20T12:00:00Z",
            "result": {"title": "Report", "summary": "Summary"},
        },
    )

    assert engine.strategies["strategy-1"]["strategy_name"] == "RSI 30"
    assert engine.strategy_profiles["strategy-1"]["name"] == "RSI 30"


@pytest.mark.asyncio
async def test_track_c_completion_rolls_back_run_and_reports_when_child_persist_fails(monkeypatch):
    engine = TrackCFakeEngine()
    _install_state_readers(monkeypatch, engine)
    run = await fe_contract_store.create_analysis_run_from_db(
        engine,
        user_id="42",
        payload={"query": "RSI 30", "strategyId": "strategy-1"},
    )
    engine.fail_sql_contains = "insert into app.strategy_email_report_candidate"

    with pytest.raises(AppError) as exc:
        await fe_contract_store.complete_analysis_run_from_db(
            engine,
            user_id="42",
            run_id=run["id"],
            payload={
                "status": "completed",
                "completedAt": "2026-07-20T12:00:00Z",
                "result": {
                    "title": "Report",
                    "summary": "Summary",
                    "candidates": [{"ticker": "005930", "signal": "BUY"}],
                },
            },
        )

    assert exc.value.status_code == 503
    assert engine.backtest_runs[run["id"]]["status"] == "queued"
    assert engine.backtest_runs[run["id"]]["ended_at"] is None
    assert engine.ai_backtest_reports == {}
    assert engine.strategy_email_reports == {}
