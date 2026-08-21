"""Freshness evidence and recommendation gating derived from source metadata."""

from __future__ import annotations

from collections.abc import Mapping
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
    as_of = _parse_as_of(manifest.get("as_of"))
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


def freshness_status_from_metadata(pipeline_metadata: Mapping[str, Any]) -> FreshnessStatus:
    """Expose the same status used by the API/report evidence."""

    return build_freshness_evidence(pipeline_metadata).status
