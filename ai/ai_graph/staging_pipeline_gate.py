"""Run the real isolated-staging acceptance gate without exposing credentials.

The gate is deliberately an external client: it measures the actual browser contract
(``parse -> confirmed job -> terminal report``) and verifies immutable PostgreSQL
evidence through a small allow-listed operator projection.  It does not know a DSN,
read shell profiles, or target the public production host.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx


STAGING_API_BASE_URL_ENV = "AI_STAGING_AI_API_BASE_URL"
STAGING_BACKEND_API_BASE_URL_ENV = "AI_STAGING_BACKEND_API_BASE_URL"
STAGING_FE_ORIGIN_ENV = "AI_STAGING_FE_ORIGIN"
STAGING_ACCOUNT_TOKEN_ENV = "AI_STAGING_ACCOUNT_TOKEN"
STAGING_EVIDENCE_TOKEN_ENV = "AI_STAGING_EVIDENCE_PROBE_TOKEN"
STAGING_SESSION_COOKIE_ENV = "AI_STAGING_SESSION_COOKIE"
STAGING_CSRF_TOKEN_ENV = "AI_STAGING_CSRF_TOKEN"
STAGING_EXPECTED_REVISION_ENV = "AI_STAGING_EXPECTED_REVISION"
RUN_COUNT = 3
RUN_DEADLINE_SECONDS = 30.0
POLL_INTERVAL_SECONDS = 0.25
RSI_EXECUTION_SPEC_VERSION = "strategy-execution-spec.v1"
GENERIC_RSI_QUERY = (
    "KRX 일봉에서 RSI(14)가 30 이하이면 매수하고 70 이상이면 매도하는 전략을 "
    "최근 3년 구간에서 수수료와 슬리피지를 반영해 검증해줘."
)
PUBLIC_PRODUCTION_HOSTS = frozenset({"qt-agent.kro.kr"})


class StagingGateError(RuntimeError):
    """A bounded gate failure that never includes a secret value."""


@dataclass(frozen=True)
class StagingGateConfig:
    api_base_url: str
    backend_api_base_url: str
    fe_origin: str
    expected_revision: str
    account_token: str = field(repr=False)
    evidence_token: str = field(repr=False)
    session_cookie: str = field(repr=False)
    csrf_token: str = field(repr=False)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "StagingGateConfig":
        source = os.environ if env is None else env
        return cls(
            api_base_url=_https_base_url(_required(source, STAGING_API_BASE_URL_ENV), "AI API"),
            backend_api_base_url=_https_base_url(
                _required(source, STAGING_BACKEND_API_BASE_URL_ENV), "backend API"
            ),
            fe_origin=_https_base_url(_required(source, STAGING_FE_ORIGIN_ENV), "FE origin"),
            expected_revision=_required(source, STAGING_EXPECTED_REVISION_ENV),
            account_token=_required(source, STAGING_ACCOUNT_TOKEN_ENV),
            evidence_token=_required(source, STAGING_EVIDENCE_TOKEN_ENV),
            session_cookie=_required(source, STAGING_SESSION_COOKIE_ENV),
            csrf_token=_required(source, STAGING_CSRF_TOKEN_ENV),
        )


@dataclass(frozen=True)
class RunEvidence:
    job_id: str
    elapsed_seconds: float
    execution_spec_version: str
    execution_spec_hash: str
    as_of: str
    observations: int
    candidate_count: int
    total_return: float
    max_drawdown: float
    sharpe_ratio: float
    cost_model: str
    limitations_count: int
    successful_aoai_calls: int
    analysis_result_id: str
    manifest_hash: str


def run_gate(
    config: StagingGateConfig,
    *,
    client: httpx.Client | None = None,
    clock: Any = time.monotonic,
    sleep: Any = time.sleep,
) -> list[RunEvidence]:
    """Require three independent parse-to-immutable PostgreSQL reports."""

    owns_client = client is None
    transport = client or httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0))
    try:
        _verify_service_identity(transport, config)
        return [_run_once(transport, config, clock=clock, sleep=sleep) for _ in range(RUN_COUNT)]
    finally:
        if owns_client:
            transport.close()


def _verify_service_identity(client: httpx.Client, config: StagingGateConfig) -> None:
    api_status = _json_response(client.get(f"{config.api_base_url}/api-status"), "api status")
    if api_status.get("deployment_revision") != config.expected_revision:
        raise StagingGateError("staging deployment revision does not match the requested SHA")
    job_store = _object(api_status.get("job_store"), "job store")
    if (
        job_store.get("active_mode") != "persistent"
        or job_store.get("fallback") is not False
        or job_store.get("dsn_configured") is not True
    ):
        raise StagingGateError("staging job store is not a configured persistent PostgreSQL store")
    readiness = _json_response(client.get(f"{config.api_base_url}/readiness"), "AI readiness")
    checks = _object_list(readiness.get("checks"), "AI readiness checks")
    required_checks = {"durable_job_store", "migration_revision", "live_provider_configuration"}
    if (
        readiness.get("status") != "ready"
        or not required_checks.issubset({item.get("name") for item in checks})
        or any(item.get("ready") is not True for item in checks)
    ):
        raise StagingGateError("AI readiness is not ready or the /ai-api prefix is not preserved")


def _run_once(
    client: httpx.Client,
    config: StagingGateConfig,
    *,
    clock: Any,
    sleep: Any,
) -> RunEvidence:
    started = float(clock())
    auth_headers = {"Authorization": f"Bearer {config.account_token}"}
    draft = _json_response(
        client.post(
            f"{config.api_base_url}/api/strategies/parse",
            headers=auth_headers,
            json={"natural_language": GENERIC_RSI_QUERY},
        ),
        "RSI strategy parse",
    )
    payload = _confirmed_rsi_job_payload(draft)
    created = _json_response(
        client.post(f"{config.api_base_url}/analysis-jobs", headers=auth_headers, json=payload),
        "confirmed analysis job admission",
        expected_status=201,
    )
    job_id = _nonempty(created.get("job_id"), "analysis job id")
    terminal: Mapping[str, Any] | None = None
    while float(clock()) - started <= RUN_DEADLINE_SECONDS:
        job = _json_response(
            client.get(f"{config.api_base_url}/analysis-jobs/{job_id}", headers=auth_headers),
            "analysis job poll",
        )
        if isinstance(job.get("result"), Mapping):
            terminal = job
            break
        if job.get("status") in {"failed", "cancelled"}:
            raise StagingGateError("analysis job reached a failed terminal state")
        sleep(POLL_INTERVAL_SECONDS)
    if terminal is None:
        raise StagingGateError("analysis job did not reach a terminal result within 30 seconds")
    report = _validate_terminal_report(terminal)
    _seal_workspace_report(client, config, job_id)
    operator = _json_response(
        client.get(
            f"{config.api_base_url}/_operator/analysis-job-evidence/{job_id}",
            headers={"X-AI-Evidence-Probe": config.evidence_token},
        ),
        "immutable result evidence",
    )
    if operator.get("job_id") != job_id or operator.get("immutable_trigger_present") is not True:
        raise StagingGateError("completed job has no verified immutable result link")
    if operator.get("execution_spec_version") != RSI_EXECUTION_SPEC_VERSION:
        raise StagingGateError("analysis job was not admitted through the versioned RSI parse contract")
    execution_spec_hash = _sha256(operator.get("execution_spec_hash"), "execution spec hash")
    if operator.get("source") != "postgres" or operator.get("as_of") != report["as_of"]:
        raise StagingGateError("immutable result provenance does not match the terminal report")
    observations = _positive_int(operator.get("observations"), "observations")
    candidate_count = _positive_int(operator.get("candidate_count"), "candidate count")
    if candidate_count != report["candidate_count"]:
        raise StagingGateError("immutable result candidate count does not match the terminal report")
    successful_aoai_calls = _positive_int(operator.get("successful_aoai_calls"), "successful AOAI calls")
    elapsed = float(clock()) - started
    if elapsed > RUN_DEADLINE_SECONDS:
        raise StagingGateError("parse-to-immutable-report pipeline exceeded the 30-second acceptance budget")
    return RunEvidence(
        job_id=job_id,
        elapsed_seconds=round(elapsed, 3),
        execution_spec_version=RSI_EXECUTION_SPEC_VERSION,
        execution_spec_hash=execution_spec_hash,
        as_of=str(report["as_of"]),
        observations=observations,
        candidate_count=candidate_count,
        total_return=float(report["total_return"]),
        max_drawdown=float(report["max_drawdown"]),
        sharpe_ratio=float(report["sharpe_ratio"]),
        cost_model=str(report["cost_model"]),
        limitations_count=int(report["limitations_count"]),
        successful_aoai_calls=successful_aoai_calls,
        analysis_result_id=_nonempty(operator.get("analysis_result_id"), "analysis result id"),
        manifest_hash=_sha256(operator.get("manifest_hash"), "manifest hash"),
    )


def _confirmed_rsi_job_payload(draft: Mapping[str, Any]) -> dict[str, Any]:
    if draft.get("kind") != "rule_draft" or draft.get("is_executable") is not True:
        raise StagingGateError("RSI parse did not produce an executable strategy draft")
    if draft.get("clarification_required") is True or draft.get("unsupported_conditions"):
        raise StagingGateError("RSI parse requested clarification or omitted a condition")
    if draft.get("spec_version") != RSI_EXECUTION_SPEC_VERSION:
        raise StagingGateError("RSI parse did not produce the current execution spec version")
    spec = _object(draft.get("strategy_execution_spec"), "RSI execution spec")
    return {
        "parse_token": _nonempty(draft.get("parse_token"), "RSI parse token"),
        "client_idempotency_key": str(uuid.uuid4()),
        "spec_version": RSI_EXECUTION_SPEC_VERSION,
        "spec_hash": _sha256(draft.get("spec_hash"), "RSI execution spec hash"),
        "strategy_execution_spec": dict(spec),
    }


def _seal_workspace_report(client: httpx.Client, config: StagingGateConfig, job_id: str) -> None:
    headers = {
        "Cookie": config.session_cookie,
        "X-CSRF-Token": config.csrf_token,
        "Origin": config.fe_origin,
    }
    created = _json_response(
        client.post(
            f"{config.backend_api_base_url}/runs",
            headers=headers,
            json={
                "query": GENERIC_RSI_QUERY,
                "aiJobId": job_id,
                "requestPayload": {"aiJobId": job_id, "gate": "isolated-staging"},
            },
        ),
        "workspace report run admission",
        expected_status=201,
    )
    run_id = _nonempty(created.get("id") or created.get("runId"), "workspace run id")
    _json_response(
        client.post(
            f"{config.backend_api_base_url}/runs/{run_id}/complete",
            headers=headers,
            json={"aiJobId": job_id},
        ),
        "workspace report completion",
    )


def _validate_terminal_report(job: Mapping[str, Any]) -> dict[str, str | int | float]:
    result = _object(job.get("result"), "terminal result")
    if result.get("status") != "ready" or result.get("failure_cause") is not None:
        raise StagingGateError("analysis job ended without a ready terminal report")
    freshness = _object(result.get("freshness_evidence"), "freshness evidence")
    as_of = _nonempty(freshness.get("as_of"), "as-of date")
    if freshness.get("source") != "postgres" or freshness.get("no_recommendation") is not False:
        raise StagingGateError("terminal report is not eligible PostgreSQL research evidence")
    payload = _object(result.get("user_payload"), "report payload")
    performance = _object(payload.get("performance"), "performance")
    if performance.get("availability") != "available":
        raise StagingGateError("terminal report has no available measured performance")
    method = _object(performance.get("method_manifest"), "performance method manifest")
    if not _has_required_method_evidence(method):
        raise StagingGateError("terminal report omits method, sample, trade, or cost evidence")
    measured = _object(performance.get("performance"), "measured performance")
    _nonempty(measured.get("selected_candidate_id"), "selected candidate id")
    metrics = _object(measured.get("metrics"), "measured performance metrics")
    values = {name: _finite_number(metrics.get(name), f"measured {name}") for name in ("total_return", "max_drawdown", "sharpe_ratio")}
    candidate_count = _positive_int(metrics.get("candidates_evaluated"), "evaluated candidate count")
    limitations = performance.get("limitations")
    if not isinstance(limitations, list) or not all(isinstance(item, str) and item.strip() for item in limitations):
        raise StagingGateError("terminal report omits performance limitations contract")
    projection = _object(_object(payload.get("report"), "beginner report").get("web_projection"), "web report projection")
    _nonempty(projection.get("title"), "report title")
    _nonempty(projection.get("summary"), "report summary")
    section_ids = {section.get("id") for section in _object_list(projection.get("sections"), "report sections")}
    if not {"performance", "risk"}.issubset(section_ids):
        raise StagingGateError("report sections omit performance or risk limits")
    return {
        "as_of": as_of,
        "candidate_count": candidate_count,
        "total_return": values["total_return"],
        "max_drawdown": values["max_drawdown"],
        "sharpe_ratio": values["sharpe_ratio"],
        "cost_model": _nonempty(method.get("cost_tax_slippage_liquidity"), "cost model"),
        "limitations_count": len(limitations),
    }


def _has_required_method_evidence(method: Mapping[str, Any]) -> bool:
    required_text = ("start_date", "end_date", "cost_tax_slippage_liquidity", "historical_simulation_warning")
    if any(not isinstance(method.get(name), str) or not method[name].strip() for name in required_text):
        return False
    return all(isinstance(method.get(name), int) and not isinstance(method[name], bool) and method[name] >= 0 for name in ("observations", "trades")) and method["observations"] > 0


def _required(source: Mapping[str, str], key: str) -> str:
    value = (source.get(key) or "").strip()
    if not value:
        raise StagingGateError(f"required staging configuration is missing: {key}")
    return value


def _https_base_url(value: str, context: str) -> str:
    base_url = value.rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise StagingGateError(f"staging {context} base URL must be HTTPS without query data")
    if (parsed.hostname or "").lower() in PUBLIC_PRODUCTION_HOSTS:
        raise StagingGateError("isolated staging gate must not target the public production host")
    return base_url


def _json_response(response: httpx.Response, context: str, *, expected_status: int = 200) -> Mapping[str, Any]:
    if response.status_code != expected_status:
        reason = _safe_http_failure_reason(response)
        suffix = f" ({reason})" if reason else ""
        raise StagingGateError(f"{context} returned HTTP {response.status_code}{suffix}")
    try:
        return _object(response.json(), context)
    except ValueError as exc:
        raise StagingGateError(f"{context} did not return JSON") from exc


def _safe_http_failure_reason(response: httpx.Response) -> str | None:
    """Extract a route/code hint without echoing user input or upstream details."""

    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, Mapping):
        return None

    for key in ("reason_code", "code"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:96]

    detail = payload.get("detail")
    if not isinstance(detail, list):
        return None
    for item in detail:
        if not isinstance(item, Mapping):
            continue
        location = item.get("loc")
        if not isinstance(location, list):
            continue
        fields = [part for part in location if isinstance(part, str) and part != "body"]
        if fields:
            return f"request_validation:{'.'.join(fields[:3])}"
    return "request_validation"


def _object(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StagingGateError(f"{context} has an invalid shape")
    return value


def _object_list(value: Any, context: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise StagingGateError(f"{context} has an invalid shape")
    return value


def _nonempty(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StagingGateError(f"{context} is missing")
    return value


def _positive_int(value: Any, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise StagingGateError(f"{context} is missing or invalid")
    return value


def _sha256(value: Any, context: str) -> str:
    text = _nonempty(value, context)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise StagingGateError(f"{context} must be a SHA-256 hex digest")
    return text


def _finite_number(value: Any, context: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise StagingGateError(f"terminal report omits {context}")
    return float(value)


def main() -> int:
    evidence = run_gate(StagingGateConfig.from_env())
    print(json.dumps({"run_count": len(evidence), "runs": [item.__dict__ for item in evidence]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
