from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai_graph.schemas import (
    APIEnvelope,
    ExecutionSpecV1OrV2,
    EnvelopeStatus,
    FailureDiagnostic,
    FreshnessEvidence,
    InternalPayload,
    StrategySpec,
    UserPayload,
)


@dataclass
class InMemoryDebugStore:
    """Stores raw internal payloads behind debug_ref for local QA and tests."""

    _records: dict[str, InternalPayload] = field(default_factory=dict)

    def put(self, debug_ref: str, payload: InternalPayload) -> None:
        self._records[debug_ref] = payload

    def get(self, debug_ref: str) -> InternalPayload | None:
        return self._records.get(debug_ref)


def build_envelope(
    *,
    status: EnvelopeStatus | str,
    trace_id: str,
    debug_ref: str,
    user_payload: UserPayload | dict[str, Any],
    strategy_spec: StrategySpec | dict[str, Any] | None,
    execution_spec: ExecutionSpecV1OrV2 | dict[str, Any] | None = None,
    execution_spec_version: str | None = None,
    execution_spec_hash: str | None = None,
    retryable: bool,
    semantic_slots: dict[str, Any] | None = None,
    data_requirements: list[dict[str, Any]] | None = None,
    source_usage: list[dict[str, Any]] | None = None,
    freshness_status: str | None = None,
    freshness_evidence: FreshnessEvidence | dict[str, Any] | None = None,
    proxy_disclosure: dict[str, str] | None = None,
    failure_cause: FailureDiagnostic | dict[str, Any] | None = None,
    evidence_refs: list[dict[str, Any]] | None = None,
    rule_provenance: dict[str, Any] | None = None,
) -> APIEnvelope:
    payload = (
        user_payload
        if isinstance(user_payload, UserPayload)
        else UserPayload.model_validate(user_payload)
    )
    return APIEnvelope(
        status=EnvelopeStatus(status),
        trace_id=trace_id,
        user_payload=payload,
        strategy_spec=strategy_spec,
        execution_spec=execution_spec,
        execution_spec_version=execution_spec_version,
        execution_spec_hash=execution_spec_hash,
        debug_ref=debug_ref,
        retryable=retryable,
        semantic_slots=semantic_slots,
        data_requirements=data_requirements or [],
        source_usage=source_usage or [],
        freshness_status=freshness_status,
        freshness_evidence=freshness_evidence,
        proxy_disclosure=proxy_disclosure,
        failure_cause=failure_cause,
        evidence_refs=evidence_refs or [],
        rule_provenance=rule_provenance,
    )
