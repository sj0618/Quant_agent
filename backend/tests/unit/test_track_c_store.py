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

        if normalized.startswith("select run_id, strategy_id, user_id, status, config_jsonb, strategy_snapshot_jsonb"):
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
                }
            return _FakeResult()

        if normalized.startswith("update app.backtest_run"):
            run_id = params["run_id"]
            row = self.engine.backtest_runs[run_id]
            row["strategy_id"] = params.get("strategy_id") or row.get("strategy_id")
            row["status"] = "completed"
            row["ended_at"] = params.get("ended_at")
            row["error_message"] = None
            return _FakeResult()

        if normalized.startswith("select report_id, run_id, user_id, summary, report_jsonb from app.ai_backtest_report"):
            report_id = params["report_id"]
            row = self.engine.ai_backtest_reports.get(report_id)
            return _FakeResult([row] if row is not None else [])

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

        if normalized.startswith("select report_id, strategy_id, backtest_run_id, ai_report_id, report_date, weekday, sent_at, title, summary, status, content_md, content_html from app.strategy_email_report"):
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
        }
        return _FakeConnection(self.engine)

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.engine.strategies = self.snapshot["strategies"]
            self.engine.strategy_profiles = self.snapshot["strategy_profiles"]
            self.engine.backtest_runs = self.snapshot["backtest_runs"]
            self.engine.ai_backtest_reports = self.snapshot["ai_backtest_reports"]
            self.engine.strategy_email_reports = self.snapshot["strategy_email_reports"]
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

    assert created == {"runId": run["id"], "reportId": created["reportId"], "status": "completed", "created": True}
    assert replayed == {"runId": run["id"], "reportId": created["reportId"], "status": "completed", "created": False}
    with pytest.raises(AppError) as exc:
        await fe_contract_store.complete_analysis_run_from_db(engine, user_id="42", run_id=run["id"], payload=conflict)
    assert exc.value.status_code == 409
    assert sum(1 for entry in engine.write_log if "insert into app.backtest_run" in str(entry["sql"]).lower()) == 1
    assert sum(1 for entry in engine.write_log if "insert into app.ai_backtest_report" in str(entry["sql"]).lower()) == 1
    assert sum(1 for entry in engine.write_log if "insert into app.strategy_email_report" in str(entry["sql"]).lower()) == 1


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
