"""Freshness evidence and recommendation gating derived from source metadata."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from ai_graph.schemas import FreshnessEvidence, FreshnessStatus

KNOWN_FRESHNESS_STATUSES = frozenset({"fresh", "stale", "unknown", "not_time_sensitive"})
NO_RECOMMENDATION_STATUSES = frozenset({"stale", "unknown"})


def _parse_as_of(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def classify_source_freshness(
    *,
    data_as_of: date | None,
    settled_session: date | None,
) -> tuple[FreshnessStatus, str]:
    """Decide freshness against the last trading session that has already closed.

    The reference is the previous session rather than today's, because KRX EOD rows
    only land after the close: a run started while the market is still open is not
    stale merely because today's bar does not exist yet. Anything at or past that
    session is fresh, so a load that already carries today's bar stays fresh too.
    """

    if settled_session is None:
        return "unknown", "직전 개장일을 확인할 수 없어 freshness를 판정하지 못했습니다."
    if data_as_of is None:
        return "unknown", "적재된 가격 데이터의 기준일을 확인할 수 없습니다."
    if data_as_of >= settled_session:
        return (
            "fresh",
            f"가격 데이터가 직전 개장일({settled_session.isoformat()})까지 적재돼 있습니다.",
        )
    return (
        "stale",
        (
            f"가격 데이터가 {data_as_of.isoformat()}까지만 적재돼 직전 개장일"
            f"({settled_session.isoformat()})에 {(settled_session - data_as_of).days}일 뒤처져 있습니다."
        ),
    )


def build_freshness_evidence(
    pipeline_metadata: Mapping[str, Any] | None,
) -> FreshnessEvidence:
    """Create one honest freshness decision from the release source manifest."""

    if not isinstance(pipeline_metadata, Mapping):
        return FreshnessEvidence(
            status="unknown",
            reason="source manifest가 없어 freshness 한계를 확인할 수 없습니다.",
            source="unknown",
            no_recommendation=True,
        )

    manifest = pipeline_metadata.get("source_manifest")
    if not isinstance(manifest, Mapping):
        return FreshnessEvidence(
            status="unknown",
            reason="source manifest가 없어 freshness 한계를 확인할 수 없습니다.",
            source=str(pipeline_metadata.get("source") or "unknown"),
            no_recommendation=True,
        )

    raw_status = str(manifest.get("freshness") or "unknown")
    status: FreshnessStatus = (
        raw_status if raw_status in KNOWN_FRESHNESS_STATUSES else "unknown"
    )  # type: ignore[assignment]
    source = str(manifest.get("source") or "unknown")
    as_of = _parse_as_of(
        pipeline_metadata.get("freshness_as_of")
        if pipeline_metadata.get("freshness_as_of") is not None
        else manifest.get("as_of")
    )
    configured_reason = pipeline_metadata.get("freshness_reason")
    if isinstance(configured_reason, str) and configured_reason.strip():
        reason = configured_reason.strip()
    elif status == "stale":
        reason = "source as-of가 freshness 한계를 넘어 stale로 판정되었습니다."
    elif status == "unknown":
        reason = "source freshness 한계를 확인할 수 없어 추천을 생성하지 않습니다."
    elif status == "not_time_sensitive":
        reason = "이 입력은 시간 민감도가 없어 freshness 제한을 적용하지 않습니다."
    else:
        reason = "source as-of가 설정된 freshness 한계 안에 있습니다."

    no_recommendation = status in NO_RECOMMENDATION_STATUSES or source in {
        "fixture",
        "unknown",
    }
    return FreshnessEvidence(
        status=status,
        as_of=as_of,
        reason=reason,
        source=source,
        no_recommendation=no_recommendation,
    )


def withhold_recommendations_without_l4_evidence(
    evidence: FreshnessEvidence,
    *,
    l4_evidence: Sequence[Mapping[str, Any]] | None,
) -> FreshnessEvidence:
    """Keep a fresh source honest when it has no L4 support for a recommendation."""

    if l4_evidence:
        return evidence
    return evidence.model_copy(
        update={
            "no_recommendation": True,
            "reason": "L4 근거가 없어 추천을 생성하지 않습니다.",
        }
    )


def freshness_status_from_metadata(pipeline_metadata: Mapping[str, Any]) -> FreshnessStatus:
    """Expose the same status used by the API/report evidence."""

    return build_freshness_evidence(pipeline_metadata).status
