from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, NoReturn

from app.core.errors import AppError


class ContractImplementation(str, Enum):
    DB_BACKED = "db-backed"
    SCHEMA_ONLY_NOT_DB = "schema-only-not-db"


class ContractVisibility(str, Enum):
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"


@dataclass(frozen=True, slots=True)
class EndpointContract:
    method: str
    path: str
    implementation: ContractImplementation
    visibility: ContractVisibility
    production_ready: bool
    fe_live_allowed: bool
    auth_required: bool
    csrf_required_for_unsafe: bool
    summary: str
    required_dependency: str | None = None
    owner: str = "backend"

    @property
    def key(self) -> tuple[str, str]:
        return self.method, self.path


def contract(
    method: str,
    path: str,
    *,
    implementation: ContractImplementation,
    visibility: ContractVisibility,
    production_ready: bool,
    fe_live_allowed: bool,
    auth_required: bool,
    csrf_required_for_unsafe: bool,
    summary: str,
    required_dependency: str | None = None,
    owner: str = "backend",
) -> EndpointContract:
    return EndpointContract(
        method=method.upper(),
        path=path,
        implementation=implementation,
        visibility=visibility,
        production_ready=production_ready,
        fe_live_allowed=fe_live_allowed,
        auth_required=auth_required,
        csrf_required_for_unsafe=csrf_required_for_unsafe,
        summary=summary,
        required_dependency=required_dependency,
        owner=owner,
    )


TRACK_A_CONTRACT_POLICY: tuple[EndpointContract, ...] = (
    contract(
        "GET",
        "/health",
        implementation=ContractImplementation.SCHEMA_ONLY_NOT_DB,
        visibility=ContractVisibility.PUBLIC,
        production_ready=True,
        fe_live_allowed=True,
        auth_required=False,
        csrf_required_for_unsafe=False,
        summary="Backend health and config snapshot.",
    ),
    contract(
        "GET",
        "/auth/google/start",
        implementation=ContractImplementation.DB_BACKED,
        visibility=ContractVisibility.PUBLIC,
        production_ready=True,
        fe_live_allowed=True,
        auth_required=False,
        csrf_required_for_unsafe=False,
        summary="Start Google OAuth login.",
        required_dependency="auth session store",
    ),
    contract(
        "GET",
        "/auth/google/callback",
        implementation=ContractImplementation.DB_BACKED,
        visibility=ContractVisibility.PUBLIC,
        production_ready=True,
        fe_live_allowed=True,
        auth_required=False,
        csrf_required_for_unsafe=False,
        summary="Complete Google OAuth login.",
        required_dependency="auth session store",
    ),
    contract(
        "POST",
        "/auth/google/callback",
        implementation=ContractImplementation.DB_BACKED,
        visibility=ContractVisibility.PUBLIC,
        production_ready=True,
        fe_live_allowed=True,
        auth_required=False,
        csrf_required_for_unsafe=True,
        summary="Complete Google OAuth login via JSON callback.",
        required_dependency="auth session store",
    ),
    contract(
        "GET",
        "/auth/me",
        implementation=ContractImplementation.DB_BACKED,
        visibility=ContractVisibility.AUTHENTICATED,
        production_ready=True,
        fe_live_allowed=True,
        auth_required=True,
        csrf_required_for_unsafe=False,
        summary="Read the current authenticated user.",
        required_dependency="main DB engine",
    ),
    contract(
        "GET",
        "/auth/csrf",
        implementation=ContractImplementation.DB_BACKED,
        visibility=ContractVisibility.AUTHENTICATED,
        production_ready=True,
        fe_live_allowed=True,
        auth_required=True,
        csrf_required_for_unsafe=False,
        summary="Fetch the current CSRF token.",
        required_dependency="auth session store",
    ),
    contract(
        "POST",
        "/auth/logout",
        implementation=ContractImplementation.DB_BACKED,
        visibility=ContractVisibility.AUTHENTICATED,
        production_ready=True,
        fe_live_allowed=True,
        auth_required=True,
        csrf_required_for_unsafe=True,
        summary="Revoke the current session.",
        required_dependency="auth session store",
    ),
)

TRACK_C_CONTRACT_POLICY: tuple[EndpointContract, ...] = (
    contract(
        "GET",
        "/api/v1/api-status",
        implementation=ContractImplementation.SCHEMA_ONLY_NOT_DB,
        visibility=ContractVisibility.PUBLIC,
        production_ready=True,
        fe_live_allowed=True,
        auth_required=False,
        csrf_required_for_unsafe=False,
        summary="Track A and Track C contract status.",
    ),
    contract(
        "POST",
        "/api/v1/runs",
        implementation=ContractImplementation.DB_BACKED,
        visibility=ContractVisibility.AUTHENTICATED,
        production_ready=True,
        fe_live_allowed=True,
        auth_required=True,
        csrf_required_for_unsafe=True,
        summary="Create a Track C analysis run.",
        required_dependency="trading-data DB engine",
    ),
    contract(
        "GET",
        "/api/v1/runs/{run_id}",
        implementation=ContractImplementation.DB_BACKED,
        visibility=ContractVisibility.AUTHENTICATED,
        production_ready=True,
        fe_live_allowed=True,
        auth_required=True,
        csrf_required_for_unsafe=False,
        summary="Read a Track C analysis run.",
        required_dependency="trading-data DB engine",
    ),
    contract(
        "POST",
        "/api/v1/runs/{run_id}/complete",
        implementation=ContractImplementation.DB_BACKED,
        visibility=ContractVisibility.AUTHENTICATED,
        production_ready=True,
        fe_live_allowed=True,
        auth_required=True,
        csrf_required_for_unsafe=True,
        summary="Persist completion state and report content for a Track C run.",
        required_dependency="trading-data DB engine",
    ),
    contract(
        "GET",
        "/api/v1/me/notifications",
        implementation=ContractImplementation.DB_BACKED,
        visibility=ContractVisibility.AUTHENTICATED,
        production_ready=True,
        fe_live_allowed=True,
        auth_required=True,
        csrf_required_for_unsafe=False,
        summary="Read notification settings for the current owner.",
        required_dependency="main DB engine",
    ),
    contract(
        "PATCH",
        "/api/v1/me/notifications",
        implementation=ContractImplementation.DB_BACKED,
        visibility=ContractVisibility.AUTHENTICATED,
        production_ready=True,
        fe_live_allowed=True,
        auth_required=True,
        csrf_required_for_unsafe=True,
        summary="Persist notification settings for the current owner.",
        required_dependency="main DB engine",
    ),
    contract(
        "GET",
        "/api/v1/me/email-deliveries",
        implementation=ContractImplementation.DB_BACKED,
        visibility=ContractVisibility.AUTHENTICATED,
        production_ready=True,
        fe_live_allowed=True,
        auth_required=True,
        csrf_required_for_unsafe=False,
        summary="List owner-scoped email delivery history.",
        required_dependency="main DB engine",
    ),
    contract(
        "GET",
        "/api/v1/unsubscribe",
        implementation=ContractImplementation.DB_BACKED,
        visibility=ContractVisibility.PUBLIC,
        production_ready=True,
        fe_live_allowed=True,
        auth_required=False,
        csrf_required_for_unsafe=False,
        summary="Inspect an opaque signed unsubscribe token.",
        required_dependency="main DB engine",
    ),
    contract(
        "POST",
        "/api/v1/unsubscribe",
        implementation=ContractImplementation.DB_BACKED,
        visibility=ContractVisibility.PUBLIC,
        production_ready=True,
        fe_live_allowed=True,
        auth_required=False,
        csrf_required_for_unsafe=False,
        summary="Disable action emails using an opaque signed unsubscribe token.",
        required_dependency="main DB engine",
    ),
    contract(
        "GET",
        "/api/v1/reports",
        implementation=ContractImplementation.DB_BACKED,
        visibility=ContractVisibility.AUTHENTICATED,
        production_ready=True,
        fe_live_allowed=True,
        auth_required=True,
        csrf_required_for_unsafe=False,
        summary="List reader-safe archived-result metadata for the current owner.",
        required_dependency="trading-data DB engine",
    ),
    contract(
        "GET",
        "/api/v1/reports/{report_id}",
        implementation=ContractImplementation.DB_BACKED,
        visibility=ContractVisibility.AUTHENTICATED,
        production_ready=True,
        fe_live_allowed=True,
        auth_required=True,
        csrf_required_for_unsafe=False,
        summary="Read immutable identifiers and allow-listed verification evidence for the current owner.",
        required_dependency="trading-data DB engine",
    ),
)

CONTRACT_POLICY: tuple[EndpointContract, ...] = TRACK_A_CONTRACT_POLICY + TRACK_C_CONTRACT_POLICY

_POLICY_BY_METHOD_PATH = {item.key: item for item in CONTRACT_POLICY}


def get_contract(method: str, path: str) -> EndpointContract | None:
    contract = _POLICY_BY_METHOD_PATH.get((method.upper(), path))
    if contract is not None:
        return contract

    if path.startswith("/api/v1/"):
        legacy_path = path.removeprefix("/api/v1")
        return _POLICY_BY_METHOD_PATH.get((method.upper(), legacy_path))

    return None


def iter_contracts() -> tuple[EndpointContract, ...]:
    return CONTRACT_POLICY


def contract_metadata(contract: EndpointContract) -> dict[str, Any]:
    return {
        "x-quantagent-owner": contract.owner,
        "x-quantagent-implementation": contract.implementation.value,
        "x-quantagent-visibility": contract.visibility.value,
        "x-quantagent-production-ready": contract.production_ready,
        "x-quantagent-fe-live-allowed": contract.fe_live_allowed,
        "x-quantagent-auth-required": contract.auth_required,
        "x-quantagent-csrf-required-for-unsafe": contract.csrf_required_for_unsafe,
    }


def api_status_endpoints() -> list[dict[str, Any]]:
    return [
        {
            "method": contract.method,
            "path": contract.path,
            "implementation": contract.implementation.value,
            "visibility": contract.visibility.value,
            "productionReady": contract.production_ready,
            "feLiveAllowed": contract.fe_live_allowed,
            "authRequired": contract.auth_required,
            "csrfRequiredForUnsafe": contract.csrf_required_for_unsafe,
            "summary": contract.summary,
        }
        for contract in CONTRACT_POLICY
    ]


def fe_live_allowlist() -> set[tuple[str, str]]:
    return {contract.key for contract in CONTRACT_POLICY if contract.fe_live_allowed}


def apply_contract_openapi_metadata(schema: dict[str, Any]) -> dict[str, Any]:
    paths = schema.get("paths")
    if not isinstance(paths, dict):
        raise RuntimeError("OpenAPI schema is missing paths")

    allowed_methods = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method not in allowed_methods or not isinstance(operation, dict):
                continue
            contract = get_contract(method, path)
            if contract is None:
                continue
            operation.update(contract_metadata(contract))
    return schema


def raise_feature_not_implemented(*, feature: str, method: str, path: str) -> NoReturn:
    contract = get_contract(method, path)
    if contract is None:
        raise RuntimeError(f"Cannot raise 501 for unclassified contract: {method.upper()} {path}")
    raise AppError(
        status_code=501,
        component="contract",
        code="feature_not_implemented",
        message="This Backend contract is not production-ready",
        details={
            "feature": feature,
            "implementation": contract.implementation.value,
            "requiredDependency": contract.required_dependency or "",
        },
    )
