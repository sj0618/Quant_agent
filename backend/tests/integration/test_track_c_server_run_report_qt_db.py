from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.api.routes import fe_contract
from app.core.errors import AppError, register_exception_handlers
from app.db import user_queries
from app.db.session import create_db_engine, create_trading_data_db_engine, dispose_db_engine
from app.services import fe_contract_store
from app.services.google_oauth import GoogleIdentity
from app.services.session_store import AuthSessionStore
from tests.unit.test_auth_config import valid_settings
from tests.unit.test_auth_core import FakeRedis

OPT_IN_ENV = "TRACK_C_SERVER_WRITE_INTEGRATION"
API_ORIGIN = "https://api.example.co.kr"
FE_ORIGIN = "https://fe.example.co.kr"
SYNTHETIC_PREFIX = "track2-report-remediation"
TARGET_RELATIONS = (
    "app.users",
    "app.strategy",
    "app.strategy_report_profile",
    "app.backtest_run",
    "app.ai_backtest_report",
    "app.backtest_summary",
    "app.backtest_metric_detail",
    "app.strategy_email_report",
    "app.strategy_email_report_candidate",
    "app.strategy_email_report_news",
)


def _enabled() -> bool:
    return os.getenv(OPT_IN_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_url(name: str) -> str | None:
    env_value = os.getenv(name, "").strip()
    if env_value:
        return env_value
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'") or None
    return None


def _require_qt_db_server_url(raw: str | None, *, name: str) -> str:
    if not raw:
        pytest.skip(f"{name} is required for the controlled qt_db integration test")
    parsed = make_url(raw)
    database_name = (parsed.database or "").strip().lower()
    if database_name != "qt_db":
        pytest.skip(f"{name} must target qt_db, not {database_name or '<missing>'}")
    drivername = parsed.drivername.lower()
    if not drivername.startswith(("postgresql", "postgres")):
        pytest.skip(f"{name} must use PostgreSQL")
    host = (parsed.host or "").strip().lower()
    if host in {"", "localhost", "127.0.0.1", "::1"}:
        pytest.skip(f"{name} must use the configured non-local qt_db server endpoint")
    return raw


async def _fetch_one(engine: Any, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    async with engine.connect() as connection:
        result = await connection.execute(text(sql), params or {})
        row = result.mappings().first()
        return dict(row) if row is not None else None


async def _execute(engine: Any, sql: str, params: dict[str, Any] | None = None) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(sql), params or {})


async def _count(engine: Any, relation: str, predicate: str, params: dict[str, Any]) -> int:
    row = await _fetch_one(engine, f"SELECT COUNT(*) AS count FROM {relation} WHERE {predicate}", params)
    return int(row["count"] if row is not None else 0)


async def _identifier_counts(
    engine: Any,
    *,
    provider_user_id: str,
    strategy_id: str,
    run_id: str,
    report_id: str,
) -> dict[str, int]:
    return {
        "users": await _count(
            engine,
            "app.users",
            "auth_provider = 'google' AND provider_user_id = :value",
            {"value": provider_user_id},
        ),
        "strategy": await _count(engine, "app.strategy", "strategy_id = :value", {"value": strategy_id}),
        "strategy_report_profile": await _count(
            engine,
            "app.strategy_report_profile",
            "strategy_id = :value",
            {"value": strategy_id},
        ),
        "backtest_run": await _count(engine, "app.backtest_run", "run_id = :value", {"value": run_id}),
        "ai_backtest_report": await _count(
            engine,
            "app.ai_backtest_report",
            "report_id = CAST(:value AS uuid)",
            {"value": report_id},
        ),
        "backtest_summary": await _count(engine, "app.backtest_summary", "run_id = :value", {"value": run_id}),
        "backtest_metric_detail": await _count(
            engine,
            "app.backtest_metric_detail",
            "run_id = :value",
            {"value": run_id},
        ),
        "strategy_email_report": await _count(
            engine,
            "app.strategy_email_report",
            "report_id = :value",
            {"value": report_id},
        ),
        "strategy_email_report_candidate": await _count(
            engine,
            "app.strategy_email_report_candidate",
            "report_id = :value",
            {"value": report_id},
        ),
        "strategy_email_report_news": await _count(
            engine,
            "app.strategy_email_report_news",
            "report_id = :value",
            {"value": report_id},
        ),
    }


def _synthetic_identity(role: str, token: str) -> GoogleIdentity:
    return GoogleIdentity(
        sub=f"{SYNTHETIC_PREFIX}:{role}:{token}",
        email=f"{SYNTHETIC_PREFIX}-{role}-{token}@example.com",
        email_verified=True,
        name=f"Track 2 {role.title()}",
        picture=None,
    )


class _StoredAnalysisResult:
    """Shape ``fe_contract._completed_analysis_payload`` reads off a completed job."""

    def __init__(self, ai_job_id: str) -> None:
        self._ai_job_id = ai_job_id

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return {
            "status": "ready",
            "strategy_spec": {"strategy_id": f"{SYNTHETIC_PREFIX}:spec:{self._ai_job_id}"},
            "user_payload": {
                "recommendation_gate": {"validated": True, "source": SYNTHETIC_PREFIX},
                "performance": {"sharpe_ratio": 0.28, "total_return": 0.0123},
                "report": {
                    "web_projection": {
                        "title": f"{SYNTHETIC_PREFIX} report {self._ai_job_id}",
                        "summary": f"{SYNTHETIC_PREFIX} summary {self._ai_job_id}",
                        # Only allow-listed section ids survive into the reader projection.
                        "sections": [
                            {
                                "id": "reproduction_contract",
                                "title": "reproduction contract",
                                "items": {
                                    "contract_version": "integration-v1",
                                    "input_hash": self._ai_job_id,
                                },
                            }
                        ],
                    }
                },
            },
        }


class _FakeAnalysisJobStore:
    """Register ``jobs[ai_job_id] = owner_user_id``; unknown ids resolve to ``None`` (404)."""

    def __init__(self) -> None:
        self.jobs: dict[str, str] = {}

    def get_job(self, ai_job_id: str) -> SimpleNamespace | None:
        owner_id = self.jobs.get(ai_job_id)
        if owner_id is None:
            return None
        return SimpleNamespace(
            job_id=ai_job_id,
            user_id=owner_id,
            status="completed",
            result=_StoredAnalysisResult(ai_job_id),
            completed_at=datetime(2099, 1, 1, tzinfo=UTC),
        )


async def _database_identity(engine: Any) -> dict[str, Any]:
    row = await _fetch_one(
        engine,
        """
        SELECT current_database() AS database_name,
               current_schema() AS current_schema,
               inet_server_addr()::text AS server_address,
               inet_server_port() AS server_port
        """,
    )
    if row is None:
        raise AssertionError("qt_db identity query returned no row")
    return row


async def _prepare_context() -> dict[str, Any]:
    database_url = _require_qt_db_server_url(_resolve_url("DATABASE_URL"), name="DATABASE_URL")
    trading_url = _require_qt_db_server_url(
        _resolve_url("TRADING_DATA_DATABASE_URL"),
        name="TRADING_DATA_DATABASE_URL",
    )
    settings = valid_settings(
        include_raw_audit=False,
        APP_ENV="test",
        AUTH_PUBLIC_BACKEND_ORIGIN=API_ORIGIN,
        AUTH_ALLOWED_ORIGINS=FE_ORIGIN,
        AUTH_CSRF_REQUIRED=True,
        DATABASE_URL=database_url,
        TRADING_DATA_DATABASE_URL=trading_url,
    )
    auth_engine = create_db_engine(settings)
    trading_engine = create_trading_data_db_engine(settings)
    assert trading_engine is not None

    for engine in (auth_engine, trading_engine):
        identity = await _database_identity(engine)
        assert identity["database_name"] == "qt_db"
        assert identity["current_schema"] not in {"raw", "meta"}
    for relation in TARGET_RELATIONS:
        row = await _fetch_one(trading_engine, "SELECT to_regclass(:relation) AS relation", {"relation": relation})
        assert row is not None and row["relation"] == relation

    token = uuid4().hex
    owner_identity = _synthetic_identity("owner", token)
    intruder_identity = _synthetic_identity("intruder", token)
    owner = await user_queries.upsert_google_user(auth_engine, owner_identity)
    intruder = await user_queries.upsert_google_user(auth_engine, intruder_identity)

    fake_redis = FakeRedis()
    job_store = _FakeAnalysisJobStore()
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(fe_contract.router)
    app.state.settings = settings
    app.state.redis_client = fake_redis
    app.state.db_engine = auth_engine
    app.state.trading_data_db_engine = trading_engine
    app.state.analysis_job_store = job_store
    app.state.startup_config_error = None
    app.state.startup_redis_error = None
    return {
        "jobs": job_store.jobs,
        "settings": settings,
        "auth_engine": auth_engine,
        "trading_engine": trading_engine,
        "app": app,
        "store": AuthSessionStore(fake_redis, settings),
        "owner_id": str(owner["id"]),
        "intruder_id": str(intruder["id"]),
        "owner_provider_id": owner_identity.sub,
        "intruder_provider_id": intruder_identity.sub,
        "token": token,
    }


async def _cleanup(
    context: dict[str, Any],
    *,
    strategy_id: str,
    run_id: str,
    report_id: str,
) -> dict[str, int]:
    engine = context["trading_engine"]
    params = {"strategy_id": strategy_id, "run_id": run_id, "report_id": report_id}
    for sql in (
        "DELETE FROM app.strategy_email_report_candidate WHERE report_id = :report_id",
        "DELETE FROM app.strategy_email_report_news WHERE report_id = :report_id",
        "DELETE FROM app.strategy_email_report WHERE report_id = :report_id",
        "DELETE FROM app.backtest_summary WHERE run_id = :run_id",
        "DELETE FROM app.backtest_metric_detail WHERE run_id = :run_id",
        "DELETE FROM app.ai_backtest_report WHERE report_id = CAST(:report_id AS uuid)",
        "DELETE FROM app.backtest_run WHERE run_id = :run_id",
        "DELETE FROM app.strategy_report_profile WHERE strategy_id = :strategy_id",
        "DELETE FROM app.strategy WHERE strategy_id = :strategy_id",
    ):
        await _execute(engine, sql, params)

    for target_engine in (context["trading_engine"], context["auth_engine"]):
        await _execute(target_engine, _DELETE_UNPINNED_SYNTHETIC_USERS, {
            "owner": context["owner_provider_id"],
            "intruder": context["intruder_provider_id"],
        })
    return await _identifier_counts(
        engine,
        provider_user_id=context["owner_provider_id"],
        strategy_id=strategy_id,
        run_id=run_id,
        report_id=report_id,
    )


# Completion writes one app.analysis_result row, which carries a BEFORE DELETE/UPDATE
# "immutable" trigger and pins its owner through fk_analysis_result_user ON DELETE
# RESTRICT.  A synthetic user that completed a run therefore survives cleanup by design;
# every other synthetic row is removable.
_DELETE_UNPINNED_SYNTHETIC_USERS = """
    DELETE FROM app.users
    WHERE auth_provider = 'google'
      AND provider_user_id IN (:owner, :intruder)
      AND NOT EXISTS (
          SELECT 1 FROM app.analysis_result AS ar WHERE ar.user_id = users.user_id
      )
"""


def _completion_payload(*, ai_job_id: str) -> dict[str, Any]:
    """The completion body carries only the job reference; the result comes from the job store."""

    return {"aiJobId": ai_job_id}


@pytest.mark.skipif(not _enabled(), reason=f"{OPT_IN_ENV}=1 is required for controlled qt_db DML")
@pytest.mark.asyncio
async def test_track_c_server_run_report_qt_db() -> None:
    context = await _prepare_context()
    token = context["token"]
    owner_id = context["owner_id"]
    strategy_id = ""
    run_id = ""
    report_id = ""
    owner_session_id = intruder_session_id = None
    cleanup_counts: dict[str, int] | None = None
    try:
        create_payload = {
            "query": f"{SYNTHETIC_PREFIX} query {token}",
            "aiJobId": f"{SYNTHETIC_PREFIX}:job:{token}",
            "ticker": f"T2{token[:6]}",
            "timeframe": "daily",
            "requestPayload": {"seed": token, "source": SYNTHETIC_PREFIX},
        }
        ai_job_id = create_payload["aiJobId"]
        # A different job id carries a different stored result: the completion conflict path.
        conflict_ai_job_id = f"{SYNTHETIC_PREFIX}:job-conflict:{token}"
        context["jobs"][ai_job_id] = owner_id
        context["jobs"][conflict_ai_job_id] = owner_id
        run_id = fe_contract_store._analysis_run_uuid(owner_id, create_payload)  # type: ignore[attr-defined]
        strategy_id = fe_contract_store._analysis_run_strategy_uuid(owner_id, create_payload)  # type: ignore[attr-defined]
        report_id, _ = fe_contract_store._analysis_completion_report_id(run_id)  # type: ignore[attr-defined]
        before = await _identifier_counts(
            context["trading_engine"],
            provider_user_id=context["owner_provider_id"],
            strategy_id=strategy_id,
            run_id=run_id,
            report_id=report_id,
        )
        assert before == {
            "users": 1,
            "strategy": 0,
            "strategy_report_profile": 0,
            "backtest_run": 0,
            "ai_backtest_report": 0,
            "backtest_summary": 0,
            "backtest_metric_detail": 0,
            "strategy_email_report": 0,
            "strategy_email_report_candidate": 0,
            "strategy_email_report_news": 0,
        }

        owner_session_id, owner_csrf = await context["store"].create_session(user_id=owner_id)
        intruder_session_id, _ = await context["store"].create_session(user_id=context["intruder_id"])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=context["app"]), base_url=API_ORIGIN) as client:
            create = await client.post(
                "/api/v1/runs",
                cookies={context["settings"].auth_session_cookie_name: owner_session_id},
                headers={"Origin": API_ORIGIN, "X-CSRF-Token": owner_csrf},
                json=create_payload,
            )
            replay_create = await client.post(
                "/api/v1/runs",
                cookies={context["settings"].auth_session_cookie_name: owner_session_id},
                headers={"Origin": API_ORIGIN, "X-CSRF-Token": owner_csrf},
                json=create_payload,
            )
            assert create.status_code == 201, create.text
            assert replay_create.status_code == 201, replay_create.text
            assert create.json()["id"] == replay_create.json()["id"] == run_id
            assert create.json()["strategyId"] == replay_create.json()["strategyId"] == strategy_id
            assert strategy_id != run_id

            strategy_row = await _fetch_one(
                context["trading_engine"],
                """
                SELECT s.strategy_id, s.user_id, s.spec_jsonb, p.strategy_id AS profile_strategy_id,
                       r.strategy_id AS run_strategy_id
                FROM app.strategy AS s
                JOIN app.strategy_report_profile AS p ON p.strategy_id = s.strategy_id
                JOIN app.backtest_run AS r ON r.strategy_id = s.strategy_id
                WHERE s.strategy_id = :strategy_id AND r.run_id = :run_id
                """,
                {"strategy_id": strategy_id, "run_id": run_id},
            )
            assert strategy_row is not None
            assert str(strategy_row["user_id"]) == owner_id
            assert strategy_row["profile_strategy_id"] == strategy_id
            assert strategy_row["run_strategy_id"] == strategy_id
            spec = strategy_row["spec_jsonb"]
            if isinstance(spec, str):
                spec = json.loads(spec)
            assert spec["provenance"]["source"] == "track-c-run-request"

            completion = _completion_payload(ai_job_id=ai_job_id)
            completed = await client.post(
                f"/api/v1/runs/{run_id}/complete",
                cookies={context["settings"].auth_session_cookie_name: owner_session_id},
                headers={"Origin": API_ORIGIN, "X-CSRF-Token": owner_csrf},
                json=completion,
            )
            replay_completed = await client.post(
                f"/api/v1/runs/{run_id}/complete",
                cookies={context["settings"].auth_session_cookie_name: owner_session_id},
                headers={"Origin": API_ORIGIN, "X-CSRF-Token": owner_csrf},
                json=completion,
            )
            conflict = await client.post(
                f"/api/v1/runs/{run_id}/complete",
                cookies={context["settings"].auth_session_cookie_name: owner_session_id},
                headers={"Origin": API_ORIGIN, "X-CSRF-Token": owner_csrf},
                json=_completion_payload(ai_job_id=conflict_ai_job_id),
            )
            assert completed.status_code == 200, completed.text
            assert completed.json()["runId"] == run_id
            assert completed.json()["reportId"] == report_id
            assert completed.json()["status"] == "completed"
            assert completed.json()["created"] is True
            assert completed.json()["analysisResultId"]
            assert replay_completed.status_code == 200, replay_completed.text
            assert replay_completed.json() == {**completed.json(), "created": False}
            assert conflict.status_code == 409, conflict.text
            assert conflict.json()["error"]["code"] == "run_already_completed"

            peak = await _identifier_counts(
                context["trading_engine"],
                provider_user_id=context["owner_provider_id"],
                strategy_id=strategy_id,
                run_id=run_id,
                report_id=report_id,
            )
            # Candidates/news/backtest artifacts are no longer request-body derived: the
            # job-store payload carries only the web projection, gate and performance.
            assert peak == {
                "users": 1,
                "strategy": 1,
                "strategy_report_profile": 1,
                "backtest_run": 1,
                "ai_backtest_report": 1,
                "backtest_summary": 0,
                "backtest_metric_detail": 0,
                "strategy_email_report": 1,
                "strategy_email_report_candidate": 0,
                "strategy_email_report_news": 0,
            }

            owner_list = await client.get(
                "/api/v1/reports?limit=100",
                cookies={context["settings"].auth_session_cookie_name: owner_session_id},
            )
            owner_detail = await client.get(
                f"/api/v1/reports/{report_id}",
                cookies={context["settings"].auth_session_cookie_name: owner_session_id},
            )
            intruder_detail = await client.get(
                f"/api/v1/reports/{report_id}",
                cookies={context["settings"].auth_session_cookie_name: intruder_session_id},
            )
            assert owner_list.status_code == 200
            assert [item["id"] for item in owner_list.json()["items"]].count(report_id) == 1
            assert "content" not in next(item for item in owner_list.json()["items"] if item["id"] == report_id)
            assert owner_detail.status_code == 200
            assert owner_detail.json()["id"] == report_id
            assert owner_detail.json()["runId"] == run_id
            # ArchivedReportDetail is an allowlist: no marketBrief/performance/content leaks,
            # only the two vetted evidence sections carried by the stored web projection.
            assert "content" not in owner_detail.json()
            assert "marketBrief" not in owner_detail.json()
            assert "performance" not in owner_detail.json()
            assert [section["id"] for section in owner_detail.json()["contentSections"]] == [
                "reproduction_contract"
            ]
            assert intruder_detail.status_code == 404

            await _execute(
                context["trading_engine"],
                "DELETE FROM app.strategy_email_report WHERE report_id = :report_id",
                {"report_id": report_id},
            )
            ai_only_list = await client.get(
                "/api/v1/reports?limit=100",
                cookies={context["settings"].auth_session_cookie_name: owner_session_id},
            )
            ai_only_detail = await client.get(
                f"/api/v1/reports/{report_id}",
                cookies={context["settings"].auth_session_cookie_name: owner_session_id},
            )
            ai_only_intruder = await client.get(
                f"/api/v1/reports/{report_id}",
                cookies={context["settings"].auth_session_cookie_name: intruder_session_id},
            )
            assert ai_only_list.status_code == 200, ai_only_list.text
            assert [item["id"] for item in ai_only_list.json()["items"]].count(report_id) == 0
            assert ai_only_detail.status_code == 404, ai_only_detail.text
            assert ai_only_intruder.status_code == 404
    finally:
        if owner_session_id is not None:
            await context["store"].revoke_session(owner_session_id)
        if intruder_session_id is not None:
            await context["store"].revoke_session(intruder_session_id)
        if strategy_id and run_id and report_id:
            cleanup_counts = await _cleanup(context, strategy_id=strategy_id, run_id=run_id, report_id=report_id)
            # Only the owner row survives: it is pinned by the immutable analysis_result.
            assert cleanup_counts == {**{name: 0 for name in cleanup_counts}, "users": 1}
        await dispose_db_engine(context["auth_engine"])
        await dispose_db_engine(context["trading_engine"])
        print(
            "TRACK2_CONTROLLED_DML="
            + json.dumps(
                {
                    "prefix": SYNTHETIC_PREFIX,
                    "relations": list(TARGET_RELATIONS),
                    "identifiers": {"userId": owner_id, "strategyId": strategy_id, "runId": run_id, "reportId": report_id},
                    "cleanupCounts": cleanup_counts,
                },
                sort_keys=True,
            )
        )


@pytest.mark.skipif(not _enabled(), reason=f"{OPT_IN_ENV}=1 is required for controlled qt_db DML")
@pytest.mark.asyncio
async def test_track_c_server_completion_transaction_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    context = await _prepare_context()
    token = context["token"]
    owner_id = context["owner_id"]
    create_payload = {
        "query": f"{SYNTHETIC_PREFIX} rollback {token}",
        "aiJobId": f"{SYNTHETIC_PREFIX}:job-rollback:{token}",
        "requestPayload": {"seed": token},
    }
    context["jobs"][create_payload["aiJobId"]] = owner_id
    run_id = fe_contract_store._analysis_run_uuid(owner_id, create_payload)  # type: ignore[attr-defined]
    strategy_id = fe_contract_store._analysis_run_strategy_uuid(owner_id, create_payload)  # type: ignore[attr-defined]
    report_id, _ = fe_contract_store._analysis_completion_report_id(run_id)  # type: ignore[attr-defined]
    session_id = None
    cleanup_counts: dict[str, int] | None = None
    try:
        session_id, csrf = await context["store"].create_session(user_id=owner_id)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=context["app"]), base_url=API_ORIGIN) as client:
            created = await client.post(
                "/api/v1/runs",
                cookies={context["settings"].auth_session_cookie_name: session_id},
                headers={"Origin": API_ORIGIN, "X-CSRF-Token": csrf},
                json=create_payload,
            )
            assert created.status_code == 201, created.text
            before_run = await _fetch_one(
                context["trading_engine"],
                "SELECT strategy_id, status, ended_at FROM app.backtest_run WHERE run_id = :run_id",
                {"run_id": run_id},
            )

            async def _fail_mid_transaction(*_args: Any, **_kwargs: Any) -> dict[str, int]:
                raise AppError(
                    status_code=503,
                    component="reports",
                    code="controlled_failure",
                    message="controlled failure",
                )

            # Last write inside complete_analysis_run_from_db's single engine.begin() block.
            monkeypatch.setattr(
                fe_contract_store,
                "_persist_completion_report_children",
                _fail_mid_transaction,
            )
            failed = await client.post(
                f"/api/v1/runs/{run_id}/complete",
                cookies={context["settings"].auth_session_cookie_name: session_id},
                headers={"Origin": API_ORIGIN, "X-CSRF-Token": csrf},
                json=_completion_payload(ai_job_id=create_payload["aiJobId"]),
            )
            after_run = await _fetch_one(
                context["trading_engine"],
                "SELECT strategy_id, status, ended_at FROM app.backtest_run WHERE run_id = :run_id",
                {"run_id": run_id},
            )
            counts = await _identifier_counts(
                context["trading_engine"],
                provider_user_id=context["owner_provider_id"],
                strategy_id=strategy_id,
                run_id=run_id,
                report_id=report_id,
            )
            assert failed.status_code == 503, failed.text
            assert after_run == before_run
            assert counts["ai_backtest_report"] == 0
            assert counts["backtest_summary"] == 0
            assert counts["backtest_metric_detail"] == 0
            assert counts["strategy_email_report"] == 0
            assert counts["strategy_email_report_candidate"] == 0
            assert counts["strategy_email_report_news"] == 0
    finally:
        if session_id is not None:
            await context["store"].revoke_session(session_id)
        cleanup_counts = await _cleanup(context, strategy_id=strategy_id, run_id=run_id, report_id=report_id)
        assert cleanup_counts == {name: 0 for name in cleanup_counts}
        await dispose_db_engine(context["auth_engine"])
        await dispose_db_engine(context["trading_engine"])
        print(
            "TRACK2_ROLLBACK_DML="
            + json.dumps(
                {
                    "prefix": SYNTHETIC_PREFIX,
                    "identifiers": {"userId": owner_id, "strategyId": strategy_id, "runId": run_id, "reportId": report_id},
                    "cleanupCounts": cleanup_counts,
                },
                sort_keys=True,
            )
        )


@pytest.mark.skipif(not _enabled(), reason=f"{OPT_IN_ENV}=1 is required for controlled qt_db DML")
@pytest.mark.asyncio
async def test_track_c_server_legacy_null_strategy_completion() -> None:
    context = await _prepare_context()
    token = context["token"]
    owner_id = context["owner_id"]
    run_id = str(uuid4())
    run_config = {"query": f"{SYNTHETIC_PREFIX} legacy {token}", "requestPayload": {"seed": token}}
    strategy_id = fe_contract_store._analysis_run_strategy_uuid(owner_id, run_config)  # type: ignore[attr-defined]
    report_id, _ = fe_contract_store._analysis_completion_report_id(run_id)  # type: ignore[attr-defined]
    session_id = None
    cleanup_counts: dict[str, int] | None = None
    try:
        await _execute(
            context["trading_engine"],
            """
            INSERT INTO app.backtest_run (
                run_id, strategy_id, user_id, initial_capital, config_jsonb,
                strategy_snapshot_jsonb, status, created_at
            ) VALUES (
                :run_id, NULL, CAST(:user_id AS bigint), 1000000,
                CAST(:config AS jsonb), CAST(:snapshot AS jsonb), 'queued', now()
            )
            """,
            {
                "run_id": run_id,
                "user_id": int(owner_id),
                "config": json.dumps(run_config),
                "snapshot": json.dumps({"query": run_config["query"]}),
            },
        )
        # The legacy run config has no aiJobId, so the mismatch guard is skipped and the
        # completion still resolves its content from the job store.
        legacy_ai_job_id = f"{SYNTHETIC_PREFIX}:job-legacy:{token}"
        context["jobs"][legacy_ai_job_id] = owner_id
        session_id, csrf = await context["store"].create_session(user_id=owner_id)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=context["app"]), base_url=API_ORIGIN) as client:
            response = await client.post(
                f"/api/v1/runs/{run_id}/complete",
                cookies={context["settings"].auth_session_cookie_name: session_id},
                headers={"Origin": API_ORIGIN, "X-CSRF-Token": csrf},
                json=_completion_payload(ai_job_id=legacy_ai_job_id),
            )
            assert response.status_code == 200, response.text
            row = await _fetch_one(
                context["trading_engine"],
                """
                SELECT r.strategy_id, r.status, s.user_id, p.strategy_id AS profile_strategy_id
                FROM app.backtest_run AS r
                JOIN app.strategy AS s ON s.strategy_id = r.strategy_id
                JOIN app.strategy_report_profile AS p ON p.strategy_id = s.strategy_id
                WHERE r.run_id = :run_id
                """,
                {"run_id": run_id},
            )
            assert row is not None
            assert row["strategy_id"] == strategy_id
            assert row["strategy_id"] != run_id
            assert row["profile_strategy_id"] == strategy_id
            assert str(row["user_id"]) == owner_id
            assert row["status"] == "completed"
    finally:
        if session_id is not None:
            await context["store"].revoke_session(session_id)
        cleanup_counts = await _cleanup(context, strategy_id=strategy_id, run_id=run_id, report_id=report_id)
        # Only the owner row survives: it is pinned by the immutable analysis_result.
        assert cleanup_counts == {**{name: 0 for name in cleanup_counts}, "users": 1}
        await dispose_db_engine(context["auth_engine"])
        await dispose_db_engine(context["trading_engine"])
        print(
            "TRACK2_LEGACY_DML="
            + json.dumps(
                {
                    "prefix": SYNTHETIC_PREFIX,
                    "identifiers": {"userId": owner_id, "strategyId": strategy_id, "runId": run_id, "reportId": report_id},
                    "cleanupCounts": cleanup_counts,
                },
                sort_keys=True,
            )
        )
