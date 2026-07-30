from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from app.core.config import redact_secrets

EMAIL_ADDRESS_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")

EMAIL_EVENT_ALLOWED_FIELDS = {
    "attempt_count",
    "available_at",
    "body_bytes",
    "batch_size",
    "claim_ttl_seconds",
    "count",
    "delivery_status",
    "created",
    "duplicate",
    "event_created_at",
    "event_type",
    "dry_run",
    "error_code",
    "error_message",
    "event",
    "matched",
    "provider",
    "provider_message_id_present",
    "provider_delivery_status",
    "provider_last_event_type",
    "provider_last_event_at",
    "provider_status_class",
    "processing_status",
    "reason_code",
    "reason",
    "result",
    "retention_days",
    "shutdown_grace_seconds",
    "status_code",
    "status",
    "submission_status",
    "tolerance_seconds",
    "reused",
    "trigger_type",
    "worker_id",
    "worker_state",
    "projection_updated",
    "projection_ignored_stale",
}


def _normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {key: _normalize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_value(item) for item in value]
    normalized = redact_secrets(value)
    if isinstance(normalized, str):
        return EMAIL_ADDRESS_PATTERN.sub("<redacted-email>", normalized)
    return normalized


def emit_email_event(logger: logging.Logger, event: str, **fields: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"event": event}
    for key, value in fields.items():
        if key not in EMAIL_EVENT_ALLOWED_FIELDS:
            continue
        if value is None:
            continue
        payload[key] = _normalize_value(value)
    logger.info("%s", json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
    return payload
