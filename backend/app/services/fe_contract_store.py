from __future__ import annotations

import copy
import json
from datetime import UTC, date, datetime
from typing import Any, NoReturn
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import AppError
from app.db import existing_report_queries
from app.db.session import _sql_params_with_bigint_user_id, fetch_one
from app.db import user_queries

DEFAULT_INITIAL_CAPITAL = 1_000_000.0
REPORT_CONTENT_SCHEMA_VERSION = existing_report_queries.REPORT_CONTENT_SCHEMA_VERSION


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _mapping_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json", exclude_none=False)
        return dumped if isinstance(dumped, dict) else {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:  # noqa: BLE001
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _json_object(value: Any) -> dict[str, Any]:
    return _mapping_dict(value)


def _as_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    text = _non_empty_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return text
    return parsed.isoformat().replace("+00:00", "Z")


def _mapping_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        items: list[Any] = []
        for item in value:
            if hasattr(item, "model_dump"):
                items.append(item.model_dump(mode="json", exclude_none=False))
            else:
                items.append(copy.deepcopy(item))
        return items
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json", exclude_none=False)
        return dumped if isinstance(dumped, list) else []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:  # noqa: BLE001
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _non_empty_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text_value = value.strip()
        return text_value or None
    text_value = str(value).strip()
    return text_value or None


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _canonical_json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=_json_default)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _coerce_bigint_user_id(user_id: str | int) -> int:
    return existing_report_queries._coerce_bigint_user_id(user_id)  # type: ignore[attr-defined]


def _server_user_identity_profile_column(report: user_queries.UserSchemaReport) -> str | None:
    for column in ("profile_image_url", "avatar_url", "picture"):
        if column in report.columns:
            return column
    return None


def _server_user_identity_projection_sql(report: user_queries.UserSchemaReport) -> str:
    user_id_column = report.user_id_column
    if user_id_column is None:
        raise AppError(
            status_code=503,
            component="db",
            code="server_identity_schema_incompatible",
            message="Server identity schema is incompatible",
            details={
                "missing_columns": sorted(report.missing_required_columns),
                "present_columns": sorted(report.columns),
            },
        )

    insert_columns = [user_id_column, "email", "auth_provider", "provider_user_id"]
    values = [":user_id", ":email", ":auth_provider", ":provider_user_id"]

    if "name" in report.columns:
        insert_columns.append("name")
        values.append(":name")

    profile_column = _server_user_identity_profile_column(report)
    if profile_column is not None:
        insert_columns.append(profile_column)
        values.append(":profile_image_url")

    return f"""
        INSERT INTO app.users (
            {", ".join(insert_columns)}
        ) VALUES (
            {", ".join(values)}
        )
        ON CONFLICT DO NOTHING
    """


def _server_user_identity_projection_payload(source_user: dict[str, Any]) -> dict[str, Any]:
    profile_image_url = _non_empty_text(
        _first_non_empty(
            source_user.get("avatar_url"),
            source_user.get("profile_image_url"),
            source_user.get("picture"),
        )
    )
    return {
        "user_id": str(source_user["id"]),
        "email": _non_empty_text(source_user.get("email")),
        "name": _non_empty_text(source_user.get("name")),
        "auth_provider": _non_empty_text(source_user.get("auth_provider")),
        "provider_user_id": _non_empty_text(source_user.get("provider_user_id")),
        "profile_image_url": profile_image_url,
    }


def _server_user_identity_projection_matches(source_user: dict[str, Any], target_user: dict[str, Any], report: user_queries.UserSchemaReport) -> bool:
    desired = _server_user_identity_projection_payload(source_user)
    target_user_id_column = report.user_id_column or "user_id"
    target = {
        "user_id": _non_empty_text(target_user.get(target_user_id_column)),
        "email": _non_empty_text(target_user.get("email")),
        "auth_provider": _non_empty_text(target_user.get("auth_provider")),
        "provider_user_id": _non_empty_text(target_user.get("provider_user_id")),
    }
    return all(desired[key] == target[key] for key in ("user_id", "email", "auth_provider", "provider_user_id"))


async def ensure_server_user_projection(
    connection: Any,
    *,
    source_user: dict[str, Any],
    user_id: str,
) -> dict[str, Any]:
    report = await user_queries.inspect_user_schema(connection)
    if not report.supports_google_identity:
        raise AppError(
            status_code=503,
            component="db",
            code="server_identity_schema_incompatible",
            message="Server identity schema is incompatible",
            details={
                "missing_columns": sorted(report.missing_required_columns),
                "present_columns": sorted(report.columns),
            },
        )

    projection = _server_user_identity_projection_payload(source_user)
    projection["user_id"] = _coerce_bigint_user_id(user_id)

    insert_sql = _server_user_identity_projection_sql(report)
    await connection.execute(text(insert_sql), projection)

    user_id_column = report.user_id_column or "user_id"
    projected_user = await fetch_one(
        connection,
        f"SELECT * FROM app.users WHERE {user_id_column} = CAST(:user_id AS bigint) LIMIT 1",
        {"user_id": projection["user_id"]},
    )
    if projected_user is not None:
        if _server_user_identity_projection_matches(source_user, projected_user, report):
            return projected_user
        raise AppError(
            status_code=409,
            component="auth",
            code="server_identity_conflict",
            message="Server identity projection conflicts with an existing user row",
            details={"userId": projection["user_id"]},
        )

    projected_user = await fetch_one(
        connection,
        """
        SELECT *
        FROM app.users
        WHERE auth_provider = :auth_provider
          AND provider_user_id = :provider_user_id
        LIMIT 1
        """,
        {
            "auth_provider": projection["auth_provider"],
            "provider_user_id": projection["provider_user_id"],
        },
    )
    if projected_user is not None:
        raise AppError(
            status_code=409,
            component="auth",
            code="server_identity_conflict",
            message="Server identity projection conflicts with an existing provider binding",
            details={"userId": projection["user_id"]},
        )

    raise AppError(
        status_code=503,
        component="db",
        code="server_identity_store_unavailable",
        message="Server identity projection could not be persisted",
        details={"userId": projection["user_id"]},
    )


def _completion_payload_data(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return copy.deepcopy(payload)
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json", exclude_none=True)
    return copy.deepcopy(dict(payload))


def _analysis_run_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(payload)


def _analysis_run_seed(user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    request_payload = _mapping_dict(_first_non_empty(payload.get("requestPayload"), payload.get("request_payload")))
    stable_request_payload = {
        key: copy.deepcopy(value)
        for key, value in request_payload.items()
        if key not in {"createdAt", "updatedAt", "created_at", "updated_at"}
    }
    seed: dict[str, Any] = {"userId": user_id.strip()}
    ai_job_id = _non_empty_text(
        _first_non_empty(
            payload.get("aiJobId"),
            payload.get("ai_job_id"),
            request_payload.get("traceId"),
            request_payload.get("trace_id"),
            request_payload.get("aiJobId"),
            request_payload.get("ai_job_id"),
        )
    )
    if ai_job_id:
        seed["aiJobId"] = ai_job_id
    else:
        query = _non_empty_text(payload.get("query"))
        if query:
            seed["query"] = query
        strategy_id = _non_empty_text(_first_non_empty(payload.get("strategyId"), payload.get("strategy_id"), request_payload.get("strategyId"), request_payload.get("strategy_id")))
        if strategy_id:
            seed["strategyId"] = strategy_id
        instrument_id = _non_empty_text(_first_non_empty(payload.get("instrumentId"), payload.get("instrument_id"), request_payload.get("instrumentId"), request_payload.get("instrument_id")))
        if instrument_id:
            seed["instrumentId"] = instrument_id
        ticker = _non_empty_text(_first_non_empty(payload.get("ticker"), request_payload.get("ticker")))
        if ticker:
            seed["ticker"] = ticker
        if stable_request_payload:
            seed["requestPayload"] = stable_request_payload
    return seed


def _analysis_run_uuid(user_id: str, payload: dict[str, Any]) -> str:
    return str(uuid5(NAMESPACE_URL, _canonical_json_text(_analysis_run_seed(user_id, payload))))


def _analysis_run_strategy_uuid(user_id: str, payload: dict[str, Any]) -> str:
    seed = _canonical_json_text(_analysis_run_seed(user_id, payload))
    return str(uuid5(NAMESPACE_URL, f"quantagent:service-strategy:{seed}"))


def _generated_strategy_spec(payload: dict[str, Any]) -> dict[str, Any]:
    request_values: dict[str, Any] = {}
    for output_key, source_keys in (
        ("query", ("query",)),
        ("instrumentId", ("instrumentId", "instrument_id")),
        ("ticker", ("ticker",)),
        ("timeframe", ("timeframe", "interval")),
    ):
        value = _analysis_run_config_value(payload, *source_keys)
        if value is not None and (not isinstance(value, str) or value.strip()):
            request_values[output_key] = copy.deepcopy(value)
    return {
        "provenance": {
            "source": "track-c-run-request",
            "idPolicy": "uuid5-user-logical-request",
        },
        "request": request_values,
    }


def _strategy_not_available(*, strategy_id: str) -> NoReturn:
    raise AppError(
        status_code=404,
        component="analysis_runs",
        code="strategy_not_found",
        message="Strategy was not found",
        details={"strategyId": strategy_id},
    )


async def _resolve_run_strategy(
    connection: Any,
    *,
    user_id: str,
    run_id: str,
    request_data: dict[str, Any],
    requested_strategy_id: str | None = None,
) -> dict[str, Any]:
    normalized_user_id = _coerce_bigint_user_id(user_id)
    strategy_id = _non_empty_text(
        _first_non_empty(
            requested_strategy_id,
            _analysis_run_strategy_id_from_config(request_data),
        )
    )
    generated = strategy_id is None
    if generated:
        strategy_id = _analysis_run_strategy_uuid(str(normalized_user_id), request_data)
        if strategy_id == run_id:
            raise AppError(
                status_code=500,
                component="analysis_runs",
                code="strategy_resolution_failed",
                message="Generated strategy id conflicts with run id",
                details={"runId": run_id},
            )
        strategy_name = _non_empty_text(_analysis_run_config_value(request_data, "query"))
        if strategy_name is None:
            raise AppError(
                status_code=422,
                component="analysis_runs",
                code="request_validation_failed",
                message="A query is required when strategyId is not provided",
                details={"field": "query"},
            )
        await connection.execute(
            text(
                """
                INSERT INTO app.strategy (
                    strategy_id,
                    strategy_name,
                    user_id,
                    spec_jsonb,
                    created_at,
                    updated_at
                ) VALUES (
                    :strategy_id,
                    :strategy_name,
                    CAST(:user_id AS bigint),
                    CAST(:spec_jsonb AS jsonb),
                    :created_at,
                    :updated_at
                )
                ON CONFLICT (strategy_id) DO NOTHING
                """
            ),
            {
                "strategy_id": strategy_id,
                "strategy_name": strategy_name,
                "user_id": normalized_user_id,
                "spec_jsonb": _canonical_json_text(_generated_strategy_spec(request_data)),
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        )

    strategy = await _fetch_one_from_connection(
        connection,
        """
        SELECT strategy_id, strategy_name, description, user_id, spec_jsonb
        FROM app.strategy
        WHERE strategy_id = :strategy_id
        LIMIT 1
        """,
        {"strategy_id": strategy_id},
    )
    if strategy is None:
        _strategy_not_available(strategy_id=strategy_id)
    strategy_owner = strategy.get("user_id")
    if strategy_owner is not None and int(strategy_owner) != normalized_user_id:
        _strategy_not_available(strategy_id=strategy_id)

    timeframe = _non_empty_text(_analysis_run_config_value(request_data, "timeframe", "interval"))
    universe = _non_empty_text(
        _first_non_empty(
            _analysis_run_ticker_from_config(request_data),
            _analysis_run_instrument_id_from_config(request_data),
        )
    )
    profile_columns = ["strategy_id", "name", "description", "universe", "tags", "created_at", "updated_at"]
    profile_values = [
        ":strategy_id", ":name", ":description", ":universe", "CAST(:tags AS jsonb)", ":created_at", ":updated_at"
    ]
    profile_params: dict[str, Any] = {
        "strategy_id": strategy_id,
        "name": strategy["strategy_name"],
        "description": strategy.get("description"),
        "universe": universe,
        "tags": "[]",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    if timeframe is not None:
        profile_columns.insert(4, "timeframe")
        profile_values.insert(4, ":timeframe")
        profile_params["timeframe"] = timeframe
    await connection.execute(
        text(
            f"""
            INSERT INTO app.strategy_report_profile ({", ".join(profile_columns)})
            VALUES ({", ".join(profile_values)})
            ON CONFLICT (strategy_id) DO NOTHING
            """
        ),
        profile_params,
    )
    profile = await _fetch_one_from_connection(
        connection,
        """
        SELECT strategy_id, name, description, universe, timeframe, tags
        FROM app.strategy_report_profile
        WHERE strategy_id = :strategy_id
        LIMIT 1
        """,
        {"strategy_id": strategy_id},
    )
    if profile is None:
        raise AppError(
            status_code=503,
            component="reports",
            code="report_profile_unavailable",
            message="Strategy report profile could not be ensured",
            details={"strategyId": strategy_id},
        )
    return {
        "strategyId": strategy_id,
        "generated": generated,
        "strategy": strategy,
        "profile": profile,
    }


def _analysis_run_trace_uuid(user_id: str, payload: dict[str, Any]) -> UUID | None:
    request_payload = _mapping_dict(_first_non_empty(payload.get("requestPayload"), payload.get("request_payload")))
    candidate = _non_empty_text(
        _first_non_empty(
            payload.get("aiJobId"),
            payload.get("ai_job_id"),
            request_payload.get("traceId"),
            request_payload.get("trace_id"),
            request_payload.get("aiJobId"),
            request_payload.get("ai_job_id"),
        )
    )
    if not candidate:
        return None
    try:
        return UUID(candidate)
    except ValueError:
        return uuid5(NAMESPACE_URL, f"quantagent:analysis-run-trace:{user_id.strip()}:{candidate}")


def _analysis_run_config_value(config: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in config and config[key] is not None:
            return config[key]
    request_payload = _mapping_dict(_first_non_empty(config.get("requestPayload"), config.get("request_payload")))
    for key in keys:
        if key in request_payload and request_payload[key] is not None:
            return request_payload[key]
    return None


def _analysis_run_ai_job_id_from_config(config: dict[str, Any]) -> str | None:
    request_payload = _mapping_dict(_first_non_empty(config.get("requestPayload"), config.get("request_payload")))
    return _non_empty_text(
        _first_non_empty(
            config.get("aiJobId"),
            config.get("ai_job_id"),
            config.get("traceId"),
            config.get("trace_id"),
            request_payload.get("aiJobId"),
            request_payload.get("ai_job_id"),
            request_payload.get("traceId"),
            request_payload.get("trace_id"),
        )
    )


def _analysis_run_strategy_id_from_config(config: dict[str, Any]) -> str | None:
    return _non_empty_text(_analysis_run_config_value(config, "strategyId", "strategy_id"))


def _analysis_run_ticker_from_config(config: dict[str, Any]) -> str | None:
    return _non_empty_text(_analysis_run_config_value(config, "ticker"))


def _analysis_run_instrument_id_from_config(config: dict[str, Any]) -> str | None:
    return _non_empty_text(_analysis_run_config_value(config, "instrumentId", "instrument_id"))


def _analysis_completion_result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return _mapping_dict(_first_non_empty(payload.get("result"), payload.get("analysisResult")))


def _analysis_completion_result_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(_canonical_json_text(_analysis_completion_result_payload(payload)))


def _analysis_completion_ai_report_document(
    *,
    run_id: str,
    report_id: str,
    user_id: int,
    ai_job_id: str | None,
    status: str,
    completed_at: str,
    title: str,
    summary: str,
    result_snapshot: dict[str, Any],
    content_document: dict[str, Any],
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schemaVersion": REPORT_CONTENT_SCHEMA_VERSION,
        "reportId": report_id,
        "runId": run_id,
        "userId": user_id,
        "status": status,
        "completedAt": completed_at,
        "title": title,
        "summary": summary,
        "resultSnapshot": result_snapshot,
        "content": content_document,
    }
    if ai_job_id is not None:
        document["aiJobId"] = ai_job_id
    return json.loads(_canonical_json_text(document))


def _analysis_completion_title(*, result: dict[str, Any], config: dict[str, Any], run_id: str) -> str:
    user_payload = _mapping_dict(_first_non_empty(result.get("userPayload"), result.get("user_payload")))
    report_bundle = _mapping_dict(user_payload.get("report"))
    web_projection = _mapping_dict(_first_non_empty(report_bundle.get("webProjection"), report_bundle.get("web_projection")))
    title = _non_empty_text(
        _first_non_empty(
            result.get("title"),
            web_projection.get("title"),
            _analysis_run_config_value(config, "title"),
        )
    )
    if not title:
        raise AppError(
            status_code=422,
            component="reports",
            code="request_validation_failed",
            message="Report title is required",
            details={"field": "result.title"},
        )
    return title


def _analysis_completion_summary(*, result: dict[str, Any], config: dict[str, Any], run_id: str) -> str:
    user_payload = _mapping_dict(_first_non_empty(result.get("userPayload"), result.get("user_payload")))
    report_bundle = _mapping_dict(user_payload.get("report"))
    web_projection = _mapping_dict(_first_non_empty(report_bundle.get("webProjection"), report_bundle.get("web_projection")))
    summary = _non_empty_text(
        _first_non_empty(
            result.get("summary"),
            web_projection.get("summary"),
            _analysis_run_config_value(config, "summary"),
        )
    )
    if not summary:
        raise AppError(
            status_code=422,
            component="reports",
            code="request_validation_failed",
            message="Report summary is required",
            details={"field": "result.summary"},
        )
    return summary


def _analysis_completion_sections(result: dict[str, Any]) -> list[dict[str, Any]]:
    user_payload = _mapping_dict(_first_non_empty(result.get("userPayload"), result.get("user_payload")))
    report_bundle = _mapping_dict(user_payload.get("report"))
    web_projection = _mapping_dict(_first_non_empty(report_bundle.get("webProjection"), report_bundle.get("web_projection")))
    sections = _mapping_list(_first_non_empty(web_projection.get("sections"), result.get("sections")))
    return [section for section in sections if isinstance(section, dict)]


def _analysis_completion_content(
    *,
    title: str,
    summary: str,
    sections: list[dict[str, Any]],
    result_snapshot: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schemaVersion": REPORT_CONTENT_SCHEMA_VERSION,
        "title": title,
        "summary": summary,
        "sections": sections,
        "result": result_snapshot,
    }


def _analysis_completion_report_id(run_id: str) -> tuple[str, UUID]:
    report_uuid = uuid5(NAMESPACE_URL, f"quantagent:service-db:report:{run_id}")
    return str(report_uuid), report_uuid


def _analysis_run_invalid_transition(*, details: dict[str, Any], message: str) -> NoReturn:
    raise AppError(
        status_code=409,
        component="analysis_runs",
        code="run_already_completed",
        message=message,
        details=details,
    )


def _analysis_run_invalid_analysis_result(*, details: dict[str, Any], message: str) -> NoReturn:
    raise AppError(
        status_code=422,
        component="analysis_runs",
        code="request_validation_failed",
        message=message,
        details=details,
    )


def _analysis_run_ai_job_mismatch(*, run_id: str, expected_ai_job_id: str, received_ai_job_id: str) -> NoReturn:
    raise AppError(
        status_code=409,
        component="analysis_runs",
        code="run_already_completed",
        message="Analysis run completion payload references a different AI job",
        details={"runId": run_id, "expectedAiJobId": expected_ai_job_id, "receivedAiJobId": received_ai_job_id},
    )


def _analysis_run_already_completed(*, run_id: str, report_id: str, message: str) -> NoReturn:
    raise AppError(
        status_code=409,
        component="analysis_runs",
        code="run_already_completed",
        message=message,
        details={"runId": run_id, "reportId": report_id},
    )


def _analysis_completion_payload_conflict(*, run_id: str, report_id: str, message: str) -> NoReturn:
    raise AppError(
        status_code=409,
        component="analysis_runs",
        code="completion_payload_conflict",
        message=message,
        details={"runId": run_id, "reportId": report_id},
    )


def _report_store_unavailable(*, run_id: str, report_id: str, operation: str) -> NoReturn:
    raise AppError(
        status_code=503,
        component="reports",
        code="report_store_unavailable",
        message="Report store is unavailable",
        details={"runId": run_id, "reportId": report_id, "operation": operation},
    )


def _is_missing_relation_error(exc: DBAPIError) -> bool:
    message = f"{type(exc).__name__}: {exc}".lower()
    return (
        ("does not exist" in message and "relation" in message)
        or "undefined table" in message
        or "undefinedtable" in message
    )


def _report_status_for_server(status: str | None) -> str:
    normalized = _non_empty_text(status)
    if normalized is None:
        return "sent"
    normalized = normalized.lower()
    if normalized in {"completed", "published"}:
        return "sent"
    if normalized in {"sent", "draft", "failed", "resent"}:
        return normalized
    return normalized


async def _fetch_one_from_connection(connection: Any, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    result = await connection.execute(text(sql), _sql_params_with_bigint_user_id(sql, params))
    row = result.mappings().first()
    return dict(row) if row is not None else None


def _db_write_failed(*, component: str, feature: str, method: str, path: str, operation: str, exc: Exception) -> NoReturn:
    raise AppError(
        status_code=503,
        component=component,
        code=feature,
        message="Database write failed",
        details={
            "feature": feature,
            "method": method,
            "path": path,
            "operation": operation,
            "error": f"{type(exc).__name__}: {exc}",
        },
    ) from exc


async def create_analysis_run_from_db(
    engine: Any,
    *,
    user_id: str,
    payload: dict[str, Any] | None = None,
    identity_source_engine: Any | None = None,
) -> dict[str, Any]:
    request_data = _analysis_run_request_payload(payload or {})
    run_id = _analysis_run_uuid(user_id, request_data)
    user_id_param = str(_coerce_bigint_user_id(user_id))
    source_user = None
    if identity_source_engine is not None:
        source_user = await user_queries.load_user_by_id(identity_source_engine, user_id)
        if source_user is None:
            raise AppError(
                status_code=401,
                component="auth",
                code="user_session_invalid",
                message="Session user is unavailable",
                details={"userId": user_id},
            )

    requested_strategy_id = _analysis_run_strategy_id_from_config(request_data)
    instrument_id = _analysis_run_instrument_id_from_config(request_data)
    ticker = _analysis_run_ticker_from_config(request_data)
    ai_job_id = _analysis_run_ai_job_id_from_config(request_data)
    now = datetime.now(UTC)

    insert_sql = """
        INSERT INTO app.backtest_run (
            run_id,
            strategy_id,
            user_id,
            initial_capital,
            config_jsonb,
            strategy_snapshot_jsonb,
            status,
            created_at
        ) VALUES (
            :run_id,
            :strategy_id,
            CAST(:user_id AS bigint),
            :initial_capital,
            CAST(:config_jsonb AS jsonb),
            CAST(:strategy_snapshot_jsonb AS jsonb),
            :status,
            :created_at
        )
        ON CONFLICT (run_id) DO NOTHING
    """
    try:
        async with engine.begin() as connection:
            if source_user is not None:
                await ensure_server_user_projection(connection, source_user=source_user, user_id=user_id)
            existing_run = await existing_report_queries.get_analysis_run(connection, run_id, user_id=user_id_param)
            if existing_run is not None:
                resolved = await _resolve_run_strategy(
                    connection,
                    user_id=user_id_param,
                    run_id=run_id,
                    request_data=request_data,
                    requested_strategy_id=_non_empty_text(
                        _first_non_empty(existing_run.get("strategyId"), requested_strategy_id)
                    ),
                )
                strategy_id = resolved["strategyId"]
                if _non_empty_text(existing_run.get("strategyId")) is None:
                    await connection.execute(
                        text(
                            """
                            UPDATE app.backtest_run
                            SET strategy_id = :strategy_id,
                                strategy_snapshot_jsonb = CAST(:strategy_snapshot_jsonb AS jsonb)
                            WHERE run_id = :run_id
                              AND user_id = CAST(:user_id AS bigint)
                              AND strategy_id IS NULL
                            """
                        ),
                        {
                            "strategy_id": strategy_id,
                            "strategy_snapshot_jsonb": _canonical_json_text(
                                {
                                    "strategyId": strategy_id,
                                    "instrumentId": instrument_id,
                                    "ticker": ticker,
                                    "query": _non_empty_text(request_data.get("query")),
                                }
                            ),
                            "run_id": run_id,
                            "user_id": user_id_param,
                        },
                    )
                    existing_run = await existing_report_queries.get_analysis_run(
                        connection,
                        run_id,
                        user_id=user_id_param,
                    )
                    if existing_run is None:
                        raise AppError(
                            status_code=503,
                            component="analysis_runs",
                            code="run_not_found",
                            message="Analysis run could not be reloaded",
                            details={"runId": run_id},
                        )
                return existing_run

            resolved = await _resolve_run_strategy(
                connection,
                user_id=user_id_param,
                run_id=run_id,
                request_data=request_data,
                requested_strategy_id=requested_strategy_id,
            )
            strategy_id = resolved["strategyId"]
            insert_params = {
                "run_id": run_id,
                "user_id": user_id_param,
                "strategy_id": strategy_id,
                "initial_capital": DEFAULT_INITIAL_CAPITAL,
                "config_jsonb": _canonical_json_text(request_data),
                "strategy_snapshot_jsonb": _canonical_json_text(
                    {
                        "strategyId": strategy_id,
                        "instrumentId": instrument_id,
                        "ticker": ticker,
                        "query": _non_empty_text(request_data.get("query")),
                    }
                ),
                "status": "queued",
                "created_at": now,
            }

            await connection.execute(text(insert_sql), _sql_params_with_bigint_user_id(insert_sql, insert_params))

            created_run = await existing_report_queries.get_analysis_run(connection, run_id, user_id=user_id_param)
            if created_run is None:
                raise AppError(
                    status_code=503,
                    component="analysis_runs",
                    code="run_not_found",
                    message="Analysis run could not be created",
                    details={"runId": run_id},
                )
            if instrument_id is not None:
                created_run["instrumentId"] = instrument_id
            if ticker is not None:
                created_run["ticker"] = ticker
            if ai_job_id is not None:
                created_run["aiJobId"] = ai_job_id
            return created_run
    except DBAPIError as exc:
        _db_write_failed(
            component="analysis_runs",
            feature="analysis_creation",
            method="POST",
            path="/api/v1/runs",
            operation="create_analysis_run",
            exc=exc,
        )


async def get_analysis_run_from_db(engine: Any, run_id: str, *, user_id: str) -> dict[str, Any] | None:
    return await existing_report_queries.get_analysis_run(engine, run_id, user_id=user_id)


async def list_reports_from_db(
    engine: Any,
    *,
    user_id: str,
    limit: int = 20,
    cursor: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    return await existing_report_queries.list_reports(
        engine,
        user_id=user_id,
        limit=limit,
        cursor=cursor,
        status=status,
        q=q,
    )


async def list_reader_reports_from_db(
    engine: Any,
    *,
    user_id: str,
    limit: int = 20,
    cursor: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    """Browser archive projection; internal callers retain ``list_reports_from_db``."""

    return await existing_report_queries.list_reader_reports(
        engine,
        user_id=user_id,
        limit=limit,
        cursor=cursor,
        status=status,
        q=q,
    )


async def get_report_from_db(engine: Any, report_id: str, *, user_id: str) -> dict[str, Any] | None:
    return await existing_report_queries.get_report(engine, report_id, user_id=user_id)


async def get_reader_report_from_db(engine: Any, report_id: str, *, user_id: str) -> dict[str, Any] | None:
    """Browser archive projection; internal callers retain ``get_report_from_db``."""

    return await existing_report_queries.get_reader_report(engine, report_id, user_id=user_id)


async def _persist_server_report(
    engine: Any,
    *,
    user_id: str,
    run_id: str,
    title: str,
    summary: str,
    content: dict[str, Any] | None,
    status: str = "sent",
    strategy_id: str | None = None,
    published_at: str | None = None,
    report_id: str | None = None,
) -> dict[str, Any]:
    normalized_user_id = _coerce_bigint_user_id(user_id)
    if not title.strip():
        raise AppError(
            status_code=422,
            component="reports",
            code="request_validation_failed",
            message="Report title is required",
            details={"field": "title"},
        )
    if not summary.strip():
        raise AppError(
            status_code=422,
            component="reports",
            code="request_validation_failed",
            message="Report summary is required",
            details={"field": "summary"},
        )

    run = await existing_report_queries.get_analysis_run(engine, run_id, user_id=str(normalized_user_id))
    if run is None:
        raise AppError(
            status_code=404,
            component="analysis_runs",
            code="run_not_found",
            message="Analysis run was not found",
            details={"runId": run_id},
        )
    resolved_strategy_id = _non_empty_text(_first_non_empty(strategy_id, run.get("strategyId")))
    if resolved_strategy_id is None:
        raise AppError(
            status_code=422,
            component="analysis_runs",
            code="strategy_resolution_failed",
            message="A valid strategy is required before persisting a report",
            details={"runId": run_id},
        )

    normalized_status = _report_status_for_server(status)
    if normalized_status not in {"sent", "draft", "failed", "resent"}:
        raise AppError(
            status_code=422,
            component="reports",
            code="request_validation_failed",
            message="Report status is invalid",
            details={"status": status},
        )

    report_id = report_id or _analysis_completion_report_id(run_id)[0]
    completed_at_iso = _non_empty_text(published_at)
    completed_at_dt = datetime.fromisoformat(completed_at_iso.replace("Z", "+00:00")) if completed_at_iso else datetime.now(UTC)
    report_date = completed_at_dt.date()
    content_document = content or _analysis_completion_content(title=title, summary=summary, sections=[], result_snapshot={})
    serialized_content = _canonical_json_text(content_document)

    report_row_params = {
        "report_id": report_id,
        "strategy_id": resolved_strategy_id,
        "backtest_run_id": run_id,
        "ai_report_id": str(_analysis_completion_report_id(run_id)[1]),
        "report_date": report_date,
        "weekday": completed_at_dt.strftime("%A"),
        "sent_at": completed_at_dt,
        "title": title,
        "summary": summary,
        "status": normalized_status,
        "market_snapshot": json.dumps([], ensure_ascii=False),
        "market_brief": summary,
        "market_context": None,
        "conclusion": summary,
        "signal_axes_jsonb": json.dumps([], ensure_ascii=False),
        "performance_jsonb": json.dumps({}, ensure_ascii=False),
        "cost_notes": json.dumps([], ensure_ascii=False),
        "content_md": serialized_content,
        "content_html": serialized_content,
        "created_at": completed_at_dt,
        "updated_at": completed_at_dt,
    }

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                UPDATE app.backtest_run
                SET
                    strategy_id = COALESCE(strategy_id, :strategy_id),
                    status = 'completed',
                    ended_at = COALESCE(ended_at, :ended_at),
                    error_message = NULL
                WHERE run_id = :run_id
                  AND user_id = CAST(:user_id AS bigint)
                """
            ),
            {
                "strategy_id": report_row_params["strategy_id"],
                "ended_at": completed_at_dt,
                "run_id": run_id,
                "user_id": normalized_user_id,
            },
        )

        await connection.execute(
            text(
                """
                INSERT INTO app.strategy_email_report (
                    report_id,
                    strategy_id,
                    backtest_run_id,
                    ai_report_id,
                    report_date,
                    weekday,
                    sent_at,
                    title,
                    summary,
                    status,
                    market_snapshot,
                    market_brief,
                    market_context,
                    conclusion,
                    signal_axes_jsonb,
                    performance_jsonb,
                    cost_notes,
                    content_md,
                    content_html,
                    created_at,
                    updated_at
                ) VALUES (
                    :report_id,
                    :strategy_id,
                    :backtest_run_id,
                    :ai_report_id,
                    :report_date,
                    :weekday,
                    CAST(:sent_at AS timestamptz),
                    :title,
                    :summary,
                    :status,
                    CAST(:market_snapshot AS jsonb),
                    :market_brief,
                    :market_context,
                    :conclusion,
                    CAST(:signal_axes_jsonb AS jsonb),
                    CAST(:performance_jsonb AS jsonb),
                    CAST(:cost_notes AS jsonb),
                    :content_md,
                    :content_html,
                    :created_at,
                    :updated_at
                )
                ON CONFLICT (report_id) DO UPDATE SET
                    strategy_id = EXCLUDED.strategy_id,
                    backtest_run_id = EXCLUDED.backtest_run_id,
                    ai_report_id = EXCLUDED.ai_report_id,
                    report_date = EXCLUDED.report_date,
                    weekday = EXCLUDED.weekday,
                    sent_at = EXCLUDED.sent_at,
                    title = EXCLUDED.title,
                    summary = EXCLUDED.summary,
                    status = EXCLUDED.status,
                    market_snapshot = EXCLUDED.market_snapshot,
                    market_brief = EXCLUDED.market_brief,
                    market_context = EXCLUDED.market_context,
                    conclusion = EXCLUDED.conclusion,
                    signal_axes_jsonb = EXCLUDED.signal_axes_jsonb,
                    performance_jsonb = EXCLUDED.performance_jsonb,
                    cost_notes = EXCLUDED.cost_notes,
                    content_md = EXCLUDED.content_md,
                    content_html = EXCLUDED.content_html,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            report_row_params,
        )

    report = await existing_report_queries.get_report(engine, report_id, user_id=str(normalized_user_id))
    if report is None:
        raise AppError(
            status_code=503,
            component="reports",
            code="report_not_found",
            message="Report could not be created",
            details={"reportId": report_id},
        )
    return report


async def _persist_ai_backtest_report(
    connection: Any,
    *,
    user_id: str,
    run_id: str,
    report_id: str,
    ai_job_id: str | None,
    title: str,
    summary: str,
    result_snapshot: dict[str, Any],
    content_document: dict[str, Any],
    completed_at: str | datetime,
) -> tuple[dict[str, Any], bool]:
    normalized_user_id = _coerce_bigint_user_id(user_id)
    completed_at_iso = _as_iso(completed_at) or _now_iso()
    completed_at_dt = datetime.fromisoformat(completed_at_iso.replace("Z", "+00:00"))
    ai_document = _analysis_completion_ai_report_document(
        run_id=run_id,
        report_id=report_id,
        user_id=normalized_user_id,
        ai_job_id=ai_job_id,
        status="completed",
        completed_at=completed_at_iso,
        title=title,
        summary=summary,
        result_snapshot=result_snapshot,
        content_document=content_document,
    )
    ai_document_text = _canonical_json_text(ai_document)
    existing_report = await _fetch_one_from_connection(
        connection,
        """
        SELECT report_id, run_id, user_id, summary, report_jsonb
        FROM app.ai_backtest_report
        WHERE report_id = :report_id
        LIMIT 1
        """,
        {"report_id": report_id},
    )
    if existing_report is not None:
        existing_document_text = _canonical_json_text(_json_object(existing_report.get("report_jsonb")))
        if existing_document_text != ai_document_text:
            _analysis_completion_payload_conflict(
                run_id=run_id,
                report_id=report_id,
                message="AI backtest report already exists with different content",
            )
        return existing_report, False

    await connection.execute(
        text(
            """
            INSERT INTO app.ai_backtest_report (
                report_id,
                run_id,
                user_id,
                summary,
                report_jsonb,
                created_at
            ) VALUES (
                :report_id,
                :run_id,
                CAST(:user_id AS bigint),
                :summary,
                CAST(:report_jsonb AS jsonb),
                :created_at
            )
            ON CONFLICT (report_id) DO NOTHING
            """
        ),
        {
            "report_id": report_id,
            "run_id": run_id,
            "user_id": normalized_user_id,
            "summary": summary,
            "report_jsonb": ai_document_text,
            "created_at": completed_at_dt,
        },
    )

    persisted_report = await _fetch_one_from_connection(
        connection,
        """
        SELECT report_id, run_id, user_id, summary, report_jsonb
        FROM app.ai_backtest_report
        WHERE report_id = :report_id
        LIMIT 1
        """,
        {"report_id": report_id},
    )
    if persisted_report is None:
        _report_store_unavailable(run_id=run_id, report_id=report_id, operation="persist_ai_backtest_report")
    persisted_document_text = _canonical_json_text(_json_object(persisted_report.get("report_jsonb")))
    if persisted_document_text != ai_document_text:
        _analysis_completion_payload_conflict(
            run_id=run_id,
            report_id=report_id,
            message="AI backtest report already exists with different content",
        )
    return persisted_report, True


async def _persist_completion_report(
    connection: Any,
    *,
    user_id: str,
    run_id: str,
    title: str,
    summary: str,
    content: dict[str, Any] | None,
    status: str = "sent",
    strategy_id: str | None = None,
    published_at: str | None = None,
    report_id: str | None = None,
    ai_report_id: str | None = None,
) -> tuple[dict[str, Any], bool]:
    normalized_user_id = _coerce_bigint_user_id(user_id)
    normalized_strategy_id = _non_empty_text(strategy_id)
    if normalized_strategy_id is None:
        raise AppError(
            status_code=503,
            component="reports",
            code="strategy_resolution_failed",
            message="A valid strategy is required before persisting a report",
            details={"runId": run_id},
        )
    if not title.strip():
        raise AppError(
            status_code=422,
            component="reports",
            code="request_validation_failed",
            message="Report title is required",
            details={"field": "title"},
        )
    if not summary.strip():
        raise AppError(
            status_code=422,
            component="reports",
            code="request_validation_failed",
            message="Report summary is required",
            details={"field": "summary"},
        )

    normalized_status = _report_status_for_server(status)
    if normalized_status not in {"sent", "draft", "failed", "resent"}:
        raise AppError(
            status_code=422,
            component="reports",
            code="request_validation_failed",
            message="Report status is invalid",
            details={"status": status},
        )

    report_id = report_id or _analysis_completion_report_id(run_id)[0]
    ai_report_id_value = ai_report_id or str(_analysis_completion_report_id(run_id)[1])
    completed_at_iso = _non_empty_text(published_at) or _now_iso()
    completed_at_dt = datetime.fromisoformat(completed_at_iso.replace("Z", "+00:00"))
    report_date = completed_at_dt.date()
    content_document = content or _analysis_completion_content(title=title, summary=summary, sections=[], result_snapshot={})
    serialized_content = _canonical_json_text(content_document)
    desired_snapshot = _canonical_json_text(
        {
            "reportId": report_id,
            "runId": run_id,
            "userId": normalized_user_id,
            "strategyId": normalized_strategy_id,
            "backtestRunId": run_id,
            "aiReportId": ai_report_id_value,
            "reportDate": report_date.isoformat(),
            "weekday": completed_at_dt.strftime("%A"),
            "sentAt": _as_iso(completed_at_dt) or completed_at_iso,
            "title": title,
            "summary": summary,
            "status": normalized_status,
            "content": content_document,
        }
    )

    existing_report = await _fetch_one_from_connection(
        connection,
        """
        SELECT
            report_id,
            strategy_id,
            backtest_run_id,
            ai_report_id,
            report_date,
            weekday,
            sent_at,
            title,
            summary,
            status,
            content_md,
            content_html
        FROM app.strategy_email_report
        WHERE report_id = :report_id
        LIMIT 1
        """,
        {"report_id": report_id},
    )
    if existing_report is not None:
        existing_snapshot = _canonical_json_text(
            {
                "reportId": _non_empty_text(existing_report.get("report_id")) or report_id,
                "runId": _non_empty_text(existing_report.get("backtest_run_id")) or run_id,
                "userId": normalized_user_id,
                "strategyId": _non_empty_text(existing_report.get("strategy_id")) or normalized_strategy_id,
                "backtestRunId": _non_empty_text(existing_report.get("backtest_run_id")) or run_id,
                "aiReportId": _non_empty_text(existing_report.get("ai_report_id")) or ai_report_id_value,
                "reportDate": str(existing_report.get("report_date") or report_date),
                "weekday": _non_empty_text(existing_report.get("weekday")) or completed_at_dt.strftime("%A"),
                "sentAt": _as_iso(existing_report.get("sent_at")) or completed_at_iso,
                "title": _non_empty_text(existing_report.get("title")) or title,
                "summary": _non_empty_text(existing_report.get("summary")) or summary,
                "status": _non_empty_text(existing_report.get("status")) or normalized_status,
                "content": _json_object(_first_non_empty(existing_report.get("content_html"), existing_report.get("content_md"))),
            }
        )
        if existing_snapshot != desired_snapshot:
            _analysis_completion_payload_conflict(
                run_id=run_id,
                report_id=report_id,
                message="Analysis run is already completed with different content",
            )
        return existing_report, False

    await connection.execute(
        text(
            """
            INSERT INTO app.strategy_email_report (
                report_id,
                strategy_id,
                backtest_run_id,
                ai_report_id,
                report_date,
                weekday,
                sent_at,
                title,
                summary,
                status,
                market_snapshot,
                market_brief,
                market_context,
                conclusion,
                signal_axes_jsonb,
                performance_jsonb,
                cost_notes,
                content_md,
                content_html,
                created_at,
                updated_at
            ) VALUES (
                :report_id,
                :strategy_id,
                :backtest_run_id,
                :ai_report_id,
                :report_date,
                :weekday,
                CAST(:sent_at AS timestamptz),
                :title,
                :summary,
                :status,
                CAST(:market_snapshot AS jsonb),
                :market_brief,
                :market_context,
                :conclusion,
                CAST(:signal_axes_jsonb AS jsonb),
                CAST(:performance_jsonb AS jsonb),
                CAST(:cost_notes AS jsonb),
                :content_md,
                :content_html,
                :created_at,
                :updated_at
            )
            ON CONFLICT (report_id) DO NOTHING
            """
        ),
        {
            "report_id": report_id,
            "strategy_id": normalized_strategy_id,
            "backtest_run_id": run_id,
            "ai_report_id": ai_report_id_value,
            "report_date": report_date,
            "weekday": completed_at_dt.strftime("%A"),
            "sent_at": completed_at_dt,
            "title": title,
            "summary": summary,
            "status": normalized_status,
            "market_snapshot": json.dumps([], ensure_ascii=False),
            "market_brief": summary,
            "market_context": None,
            "conclusion": summary,
            "signal_axes_jsonb": json.dumps([], ensure_ascii=False),
            "performance_jsonb": json.dumps({}, ensure_ascii=False),
            "cost_notes": json.dumps([], ensure_ascii=False),
            "content_md": serialized_content,
            "content_html": serialized_content,
            "created_at": completed_at_dt,
            "updated_at": completed_at_dt,
        },
    )

    persisted_report = await _fetch_one_from_connection(
        connection,
        """
        SELECT
            report_id,
            strategy_id,
            backtest_run_id,
            ai_report_id,
            report_date,
            weekday,
            sent_at,
            title,
            summary,
            status,
            content_md,
            content_html
        FROM app.strategy_email_report
        WHERE report_id = :report_id
        LIMIT 1
        """,
        {"report_id": report_id},
    )
    if persisted_report is None:
        _report_store_unavailable(run_id=run_id, report_id=report_id, operation="persist_strategy_email_report")
    persisted_snapshot = _canonical_json_text(
        {
            "reportId": _non_empty_text(persisted_report.get("report_id")) or report_id,
            "runId": _non_empty_text(persisted_report.get("backtest_run_id")) or run_id,
            "userId": normalized_user_id,
            "strategyId": _non_empty_text(persisted_report.get("strategy_id")) or normalized_strategy_id,
            "backtestRunId": _non_empty_text(persisted_report.get("backtest_run_id")) or run_id,
            "aiReportId": _non_empty_text(persisted_report.get("ai_report_id")) or ai_report_id_value,
            "reportDate": str(persisted_report.get("report_date") or report_date),
            "weekday": _non_empty_text(persisted_report.get("weekday")) or completed_at_dt.strftime("%A"),
            "sentAt": _as_iso(persisted_report.get("sent_at")) or completed_at_iso,
            "title": _non_empty_text(persisted_report.get("title")) or title,
            "summary": _non_empty_text(persisted_report.get("summary")) or summary,
            "status": _non_empty_text(persisted_report.get("status")) or normalized_status,
            "content": _json_object(_first_non_empty(persisted_report.get("content_html"), persisted_report.get("content_md"))),
        }
    )
    if persisted_snapshot != desired_snapshot:
        _analysis_completion_payload_conflict(
            run_id=run_id,
            report_id=report_id,
            message="Analysis run is already completed with different content",
        )
    return persisted_report, True


async def _load_owned_run_for_completion(
    connection: Any,
    *,
    run_id: str,
    user_id: str,
) -> dict[str, Any] | None:
    return await _fetch_one_from_connection(
        connection,
        """
        SELECT
            run_id,
            strategy_id,
            user_id,
            status,
            config_jsonb,
            strategy_snapshot_jsonb,
            created_at,
            started_at,
            ended_at,
            error_message
        FROM app.backtest_run
        WHERE run_id = :run_id
          AND user_id = CAST(:user_id AS bigint)
        LIMIT 1
        FOR UPDATE
        """,
        {"run_id": run_id, "user_id": user_id},
    )


async def _validate_completion_replay(
    connection: Any,
    *,
    user_id: str,
    run_id: str,
    report_id: str,
    request_ai_job_id: str | None,
    result_snapshot: dict[str, Any],
    requested_completed_at: str | None,
) -> bool:
    existing = await _fetch_one_from_connection(
        connection,
        """
        SELECT report_id, run_id, user_id, summary, report_jsonb
        FROM app.ai_backtest_report
        WHERE report_id = :report_id
        LIMIT 1
        """,
        {"report_id": report_id},
    )
    if existing is None:
        return False

    document = _json_object(existing.get("report_jsonb"))
    existing_run_id = _non_empty_text(_first_non_empty(existing.get("run_id"), document.get("runId")))
    existing_user_id = _non_empty_text(_first_non_empty(existing.get("user_id"), document.get("userId")))
    existing_result = _json_object(
        _first_non_empty(document.get("resultSnapshot"), document.get("result_snapshot"))
    )
    existing_ai_job_id = _non_empty_text(
        _first_non_empty(document.get("aiJobId"), document.get("ai_job_id"))
    )
    existing_completed_at = _as_iso(
        _first_non_empty(document.get("completedAt"), document.get("completed_at"))
    )
    received_completed_at = _as_iso(requested_completed_at)
    conflicts = (
        existing_run_id != run_id
        or existing_user_id != str(_coerce_bigint_user_id(user_id))
        or _canonical_json_text(existing_result) != _canonical_json_text(result_snapshot)
        or (
            request_ai_job_id is not None
            and existing_ai_job_id is not None
            and request_ai_job_id != existing_ai_job_id
        )
        or (
            received_completed_at is not None
            and existing_completed_at is not None
            and received_completed_at != existing_completed_at
        )
    )
    if conflicts:
        _analysis_completion_payload_conflict(
            run_id=run_id,
            report_id=report_id,
            message="Analysis run is already completed with different content",
        )
    return True


def _completion_backtest_payload(result: dict[str, Any]) -> dict[str, Any]:
    return _mapping_dict(
        _first_non_empty(
            result.get("backtest"),
            result.get("backtestResult"),
            result.get("backtest_result"),
            result.get("executionResult"),
            result.get("execution_result"),
        )
    )


def _completion_backtest_summary(result: dict[str, Any]) -> dict[str, Any]:
    backtest = _completion_backtest_payload(result)
    return _mapping_dict(
        _first_non_empty(
            result.get("backtestSummary"),
            result.get("backtest_summary"),
            backtest.get("summary"),
        )
    )


def _completion_metric_detail(result: dict[str, Any]) -> dict[str, Any]:
    backtest = _completion_backtest_payload(result)
    return _mapping_dict(
        _first_non_empty(
            result.get("backtestMetricDetail"),
            result.get("backtest_metric_detail"),
            result.get("metricDetail"),
            result.get("metric_detail"),
            backtest.get("metricDetail"),
            backtest.get("metric_detail"),
        )
    )


def _payload_alias(payload: dict[str, Any], name: str) -> Any:
    camel_name = name.split("_")[0] + "".join(part.title() for part in name.split("_")[1:])
    return _first_non_empty(payload.get(name), payload.get(camel_name))


async def _persist_completion_backtest_artifacts(
    connection: Any,
    *,
    run_id: str,
    result: dict[str, Any],
) -> dict[str, bool]:
    persisted = {"summary": False, "metricDetail": False}
    summary = _completion_backtest_summary(result)
    summary_fields = (
        "final_equity", "final_cash", "open_positions", "period_return", "cagr",
        "benchmark_return", "alpha", "beta", "max_drawdown", "volatility",
        "sharpe_ratio", "sortino_ratio", "calmar_ratio", "win_rate", "profit_factor",
        "payoff_ratio", "avg_win", "avg_loss", "max_consecutive_wins",
        "max_consecutive_losses", "trade_count", "signal_count", "avg_holding_days",
        "turnover", "total_commission", "total_tax", "total_slippage",
        "excluded_ticker_count", "metrics_version",
    )
    summary_json_fields = (
        ("excluded_tickers_jsonb", []),
        ("indicator_report_jsonb", {}),
        ("cost_model_jsonb", {}),
        ("position_sizing_jsonb", {}),
    )
    if summary and any(_payload_alias(summary, name) is not None for name in summary_fields):
        params: dict[str, Any] = {
            "summary_id": str(uuid5(NAMESPACE_URL, f"quantagent:service-db:backtest-summary:{run_id}")),
            "run_id": run_id,
        }
        columns = ["summary_id", "run_id"]
        values = [":summary_id", ":run_id"]
        for name in summary_fields:
            columns.append(name)
            values.append(f":{name}")
            params[name] = _payload_alias(summary, name)
        for name, default in summary_json_fields:
            columns.append(name)
            values.append(f"CAST(:{name} AS jsonb)")
            params[name] = _canonical_json_text(
                _first_non_empty(_payload_alias(summary, name), copy.deepcopy(default))
            )
        await connection.execute(
            text(
                f"""
                INSERT INTO app.backtest_summary ({", ".join(columns)})
                VALUES ({", ".join(values)})
                ON CONFLICT (run_id) DO NOTHING
                """
            ),
            params,
        )
        persisted["summary"] = True

    detail = _completion_metric_detail(result)
    detail_fields = (
        "compare_json", "composition_json", "drawdown_detail_json", "drawdown_series_json",
        "greeks_json", "rolling_returns_json", "monthly_return_json", "montecarlo_json",
        "montecarlo_cagr_json", "montecarlo_drawdown_json", "montecarlo_sharpe_json",
        "outliers_json",
    )
    if detail and any(_payload_alias(detail, name) is not None for name in detail_fields):
        params = {"run_id": run_id}
        columns = ["run_id"]
        values = [":run_id"]
        array_fields = {
            "drawdown_detail_json", "drawdown_series_json", "rolling_returns_json", "monthly_return_json",
        }
        for name in detail_fields:
            default: Any = [] if name in array_fields else {}
            columns.append(name)
            values.append(f"CAST(:{name} AS jsonb)")
            params[name] = _canonical_json_text(
                _first_non_empty(_payload_alias(detail, name), copy.deepcopy(default))
            )
        await connection.execute(
            text(
                f"""
                INSERT INTO app.backtest_metric_detail ({", ".join(columns)})
                VALUES ({", ".join(values)})
                ON CONFLICT (run_id) DO NOTHING
                """
            ),
            params,
        )
        persisted["metricDetail"] = True
    return persisted


def _completion_web_projection(result: dict[str, Any]) -> dict[str, Any]:
    user_payload = _mapping_dict(_first_non_empty(result.get("userPayload"), result.get("user_payload")))
    report_bundle = _mapping_dict(user_payload.get("report"))
    return _mapping_dict(
        _first_non_empty(report_bundle.get("webProjection"), report_bundle.get("web_projection"))
    )


async def _persist_completion_report_children(
    connection: Any,
    *,
    report_id: str,
    result: dict[str, Any],
) -> dict[str, int]:
    web_projection = _completion_web_projection(result)
    candidate_values = _mapping_list(
        _first_non_empty(
            result.get("candidates"),
            web_projection.get("candidates"),
        )
    )
    news_values = _mapping_list(
        _first_non_empty(
            result.get("news"),
            web_projection.get("news"),
        )
    )
    persisted_candidates = 0
    seen_tickers: set[str] = set()
    for index, raw_candidate in enumerate(candidate_values):
        candidate = _mapping_dict(raw_candidate)
        ticker = _non_empty_text(candidate.get("ticker"))
        signal = (_non_empty_text(candidate.get("signal")) or "").upper()
        if ticker is None or ticker in seen_tickers or signal not in {"BUY", "HOLD", "DROP"}:
            continue
        seen_tickers.add(ticker)
        await connection.execute(
            text(
                """
                INSERT INTO app.strategy_email_report_candidate (
                    report_id, ticker, name, sector, signal, confidence, score,
                    price, change_percent, rationale, evidence_jsonb,
                    risk_reasons_jsonb, risk_manager_override, web_projection,
                    sort_order
                ) VALUES (
                    :report_id, :ticker, :name, :sector, :signal, :confidence, :score,
                    :price, :change_percent, :rationale, CAST(:evidence_jsonb AS jsonb),
                    CAST(:risk_reasons_jsonb AS jsonb), :risk_manager_override,
                    :web_projection, :sort_order
                )
                ON CONFLICT (report_id, ticker) DO NOTHING
                """
            ),
            {
                "report_id": report_id,
                "ticker": ticker,
                "name": _non_empty_text(candidate.get("name")),
                "sector": _non_empty_text(candidate.get("sector")),
                "signal": signal,
                "confidence": _first_non_empty(candidate.get("confidence")),
                "score": _first_non_empty(candidate.get("score")),
                "price": _non_empty_text(candidate.get("price")),
                "change_percent": _non_empty_text(
                    _first_non_empty(candidate.get("changePercent"), candidate.get("change_percent"))
                ),
                "rationale": _non_empty_text(candidate.get("rationale")),
                "evidence_jsonb": _canonical_json_text(_mapping_list(candidate.get("evidence"))),
                "risk_reasons_jsonb": _canonical_json_text(
                    _mapping_list(
                        _first_non_empty(candidate.get("riskReasons"), candidate.get("risk_reasons"))
                    )
                ),
                "risk_manager_override": _non_empty_text(
                    _first_non_empty(
                        candidate.get("riskManagerOverride"),
                        candidate.get("risk_manager_override"),
                    )
                ),
                "web_projection": _non_empty_text(
                    _first_non_empty(candidate.get("webProjection"), candidate.get("web_projection"))
                ),
                "sort_order": _first_non_empty(
                    candidate.get("sortOrder"),
                    candidate.get("sort_order"),
                    index,
                ),
            },
        )
        persisted_candidates += 1

    persisted_news = 0
    seen_ranks: set[int] = set()
    allowed_tones = {"positive", "warning", "negative", "neutral", "info"}
    for index, raw_news in enumerate(news_values, start=1):
        news = _mapping_dict(raw_news)
        title = _non_empty_text(news.get("title"))
        tone = (_non_empty_text(news.get("tone")) or "").lower()
        rank_value = _first_non_empty(news.get("rank"), index)
        try:
            rank = int(rank_value)
        except (TypeError, ValueError):
            continue
        if title is None or tone not in allowed_tones or rank <= 0 or rank in seen_ranks:
            continue
        seen_ranks.add(rank)
        await connection.execute(
            text(
                """
                INSERT INTO app.strategy_email_report_news (
                    report_id, rank, title, source, tone, url, published_at, summary
                ) VALUES (
                    :report_id, :rank, :title, :source, :tone, :url,
                    CAST(:published_at AS timestamptz), :summary
                )
                ON CONFLICT (report_id, rank) DO NOTHING
                """
            ),
            {
                "report_id": report_id,
                "rank": rank,
                "title": title,
                "source": _non_empty_text(news.get("source")),
                "tone": tone,
                "url": _non_empty_text(news.get("url")),
                "published_at": _non_empty_text(
                    _first_non_empty(news.get("publishedAt"), news.get("published_at"))
                ),
                "summary": _non_empty_text(news.get("summary")),
            },
        )
        persisted_news += 1
    return {"candidates": persisted_candidates, "news": persisted_news}


async def complete_analysis_run_from_db(
    engine: Any,
    *,
    user_id: str,
    run_id: str,
    payload: Any,
    identity_source_engine: Any | None = None,
    email_settings: Any | None = None,
) -> dict[str, Any]:
    user_id_param = str(_coerce_bigint_user_id(user_id))
    completion_data = _completion_payload_data(payload)
    source_user = None
    if identity_source_engine is not None:
        source_user = await user_queries.load_user_by_id(identity_source_engine, user_id)
        if source_user is None:
            raise AppError(
                status_code=401,
                component="auth",
                code="user_session_invalid",
                message="Session user is unavailable",
                details={"userId": user_id},
            )
    requested_status = _non_empty_text(completion_data.get("status"))
    if requested_status is not None and requested_status != "completed":
        _analysis_run_invalid_transition(
            details={"runId": run_id, "status": requested_status},
            message="Analysis run completion status is invalid",
        )

    result = _analysis_completion_result_payload(completion_data)
    result_snapshot = _analysis_completion_result_snapshot(completion_data)
    report_id, ai_report_uuid = _analysis_completion_report_id(run_id)
    ai_report_id = str(ai_report_uuid)
    report_created = False

    try:
        async with engine.begin() as connection:
            if source_user is not None:
                await ensure_server_user_projection(connection, source_user=source_user, user_id=user_id)

            run = await _load_owned_run_for_completion(
                connection,
                run_id=run_id,
                user_id=user_id_param,
            )
            if run is None:
                raise AppError(
                    status_code=404,
                    component="analysis_runs",
                    code="run_not_found",
                    message="Analysis run was not found",
                    details={"runId": run_id},
                )

            request_ai_job_id = _analysis_run_ai_job_id_from_config(completion_data)
            run_config = _mapping_dict(run.get("config_jsonb"))
            strategy_snapshot = _mapping_dict(run.get("strategy_snapshot_jsonb"))
            for key in ("query", "instrumentId", "ticker", "timeframe"):
                if _analysis_run_config_value(run_config, key) is None and strategy_snapshot.get(key) is not None:
                    run_config[key] = copy.deepcopy(strategy_snapshot[key])
            expected_ai_job_id = _analysis_run_ai_job_id_from_config(run_config)
            if request_ai_job_id and expected_ai_job_id and request_ai_job_id != expected_ai_job_id:
                _analysis_run_ai_job_mismatch(
                    run_id=run_id,
                    expected_ai_job_id=expected_ai_job_id,
                    received_ai_job_id=request_ai_job_id,
                )

            run_status = _non_empty_text(run.get("status")) or "unknown"
            if run_status in {"failed", "cancelled"}:
                _analysis_run_invalid_transition(
                    details={"runId": run_id, "status": run_status},
                    message="Analysis run cannot be completed from a terminal failure state",
                )

            requested_completed_at = _non_empty_text(
                _first_non_empty(completion_data.get("completedAt"), completion_data.get("completed_at"))
            )
            await _validate_completion_replay(
                connection,
                user_id=user_id_param,
                run_id=run_id,
                report_id=ai_report_id,
                request_ai_job_id=request_ai_job_id,
                result_snapshot=result_snapshot,
                requested_completed_at=requested_completed_at,
            )

            resolved = await _resolve_run_strategy(
                connection,
                user_id=user_id_param,
                run_id=run_id,
                request_data=run_config,
                requested_strategy_id=_non_empty_text(run.get("strategy_id")),
            )
            strategy_id = resolved["strategyId"]

            title = _analysis_completion_title(result=result, config=run_config, run_id=run_id)
            summary = _analysis_completion_summary(result=result, config=run_config, run_id=run_id)
            sections = _analysis_completion_sections(result)
            content_document = _analysis_completion_content(
                title=title,
                summary=summary,
                sections=sections,
                result_snapshot=result_snapshot,
            )

            persisted_completed_at = _as_iso(run.get("ended_at")) if run_status == "completed" else None
            completed_at_iso = requested_completed_at or persisted_completed_at or _now_iso()
            completed_at_dt = datetime.fromisoformat(completed_at_iso.replace("Z", "+00:00"))

            update_sql = """
                    UPDATE app.backtest_run
                    SET
                        strategy_id = COALESCE(strategy_id, :strategy_id),
                        status = 'completed',
                        ended_at = COALESCE(ended_at, :ended_at),
                        error_message = NULL
                    WHERE run_id = :run_id
                      AND user_id = CAST(:user_id AS bigint)
                    """
            await connection.execute(
                text(update_sql),
                _sql_params_with_bigint_user_id(
                    update_sql,
                    {
                        "strategy_id": strategy_id,
                        "ended_at": completed_at_dt,
                        "run_id": run_id,
                        "user_id": user_id_param,
                    },
                ),
            )

            _, _ = await _persist_ai_backtest_report(
                connection,
                user_id=user_id_param,
                run_id=run_id,
                report_id=ai_report_id,
                ai_job_id=request_ai_job_id or expected_ai_job_id,
                title=title,
                summary=summary,
                result_snapshot=result_snapshot,
                content_document=content_document,
                completed_at=completed_at_iso,
            )

            await _persist_completion_backtest_artifacts(
                connection,
                run_id=run_id,
                result=result,
            )

            _, report_created = await _persist_completion_report(
                connection,
                user_id=user_id_param,
                run_id=run_id,
                title=title,
                summary=summary,
                content=content_document,
                status="sent",
                strategy_id=strategy_id,
                published_at=completed_at_iso,
                report_id=report_id,
                ai_report_id=ai_report_id,
            )

            await _persist_completion_report_children(
                connection,
                report_id=report_id,
                result=result,
            )

            final_report = await existing_report_queries.get_report(connection, report_id, user_id=user_id_param)
            if final_report is None:
                raise AppError(
                    status_code=503,
                    component="reports",
                    code="report_not_found",
                    message="Report could not be created",
                    details={"reportId": report_id},
                )

            if email_settings is not None:
                from app.services import email_delivery

                await email_delivery.create_report_completed_delivery(
                    connection,
                    settings=email_settings,
                    user_id=user_id_param,
                    report_id=report_id,
                    correlation_id=f"report:{report_id}",
                )

            return {
                "runId": run_id,
                "reportId": _non_empty_text(final_report.get("id")) or report_id,
                "status": "completed",
                "created": report_created,
            }
    except DBAPIError as exc:
        if _is_missing_relation_error(exc):
            _report_store_unavailable(run_id=run_id, report_id=report_id, operation="complete_analysis_run")
        _db_write_failed(
            component="analysis_runs",
            feature="analysis_completion",
            method="POST",
            path=f"/api/v1/runs/{run_id}/complete",
            operation="complete_analysis_run",
            exc=exc,
        )
