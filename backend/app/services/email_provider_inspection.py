from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import AppError
from app.services.email_provider import BREVO_API_BASE_URL, BREVO_REQUEST_USER_AGENT

TRANSACTIONAL_EMAILS_PATH = "/v3/smtp/emails"
TRANSACTIONAL_EVENTS_PATH = "/v3/smtp/statistics/events"
BLOCKED_CONTACTS_PATH = "/v3/smtp/blockedContacts"


@dataclass(frozen=True, slots=True)
class BrevoTransactionalEmailReference:
    message_id: str = field(repr=False)
    uuid: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class BrevoEmailEvent:
    event: str
    delivery_status: str
    occurred_at: str | None = None
    message_id: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class BrevoBlockedContactStatus:
    matched: bool
    reason_category: str = "unknown"
    sender_specific_match: bool = False


def map_brevo_delivery_event(value: Any) -> str:
    normalized = "".join(character for character in str(value or "").strip().lower() if character.isalnum())
    return {
        "request": "pending",
        "requests": "pending",
        "sent": "pending",
        "delivered": "delivered",
        "deferred": "deferred",
        "softbounce": "soft_bounce",
        "softbounces": "soft_bounce",
        "hardbounce": "hard_bounce",
        "hardbounces": "hard_bounce",
        "blocked": "blocked",
        "invalid": "invalid",
        "invalidemail": "invalid",
        "spam": "complaint",
        "complaint": "complaint",
        "unsubscribed": "unsubscribed",
        "error": "error",
    }.get(normalized, "unknown")


def _blocked_reason_category(value: Any) -> str:
    normalized = "".join(character for character in str(value or "").strip().lower() if character.isalnum())
    return {
        "unsubscribedviama": "unsubscribed",
        "unsubscribedviaemail": "unsubscribed",
        "unsubscribedviaapi": "unsubscribed",
        "adminblocked": "blocked",
        "hardbounce": "hard_bounce",
        "contactflaggedasspam": "complaint",
    }.get(normalized, "unknown")


def _dict_items(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _event_from_payload(payload: dict[str, Any]) -> BrevoEmailEvent:
    event_name = str(payload.get("event") or payload.get("name") or payload.get("type") or "unknown")
    occurred_at = payload.get("date") or payload.get("time") or payload.get("ts_event") or payload.get("ts")
    return BrevoEmailEvent(
        event=event_name,
        delivery_status=map_brevo_delivery_event(event_name),
        occurred_at=str(occurred_at) if occurred_at is not None else None,
        message_id=str(payload.get("messageId")) if payload.get("messageId") else None,
    )


class BrevoEmailInspector:
    """Read-only Brevo inspection client; it has no send or mutation methods."""

    def __init__(
        self,
        settings: Settings,
        *,
        api_base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.api_base_url = (api_base_url or settings.email_brevo_api_base_url or BREVO_API_BASE_URL).rstrip("/")
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        api_key = self.settings.email_api_key_value
        if not api_key:
            raise AppError(
                status_code=503,
                component="email_provider_inspection",
                code="email_api_key_missing",
                message="Brevo API key is required for provider inspection",
            )
        return {
            "accept": "application/json",
            "api-key": api_key,
            "User-Agent": BREVO_REQUEST_USER_AGENT,
        }

    async def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        timeout = httpx.Timeout(self.settings.email_request_timeout_seconds)
        async with httpx.AsyncClient(
            base_url=self.api_base_url,
            headers=self._headers(),
            timeout=timeout,
            transport=self.transport,
        ) as client:
            response = await client.get(path, params=params)
        if not 200 <= response.status_code < 300:
            raise AppError(
                status_code=502,
                component="email_provider_inspection",
                code="email_provider_read_failed",
                message=f"Brevo read-only inspection failed with HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                status_code=502,
                component="email_provider_inspection",
                code="email_provider_read_invalid_json",
                message="Brevo read-only inspection returned invalid JSON",
            ) from exc
        return payload if isinstance(payload, dict) else {}

    async def get_transactional_email_by_message_id(
        self, message_id: str
    ) -> BrevoTransactionalEmailReference | None:
        payload = await self._get_json(TRANSACTIONAL_EMAILS_PATH, params={"messageId": message_id})
        for item in _dict_items(payload, "transactionalEmails", "emails", "items"):
            candidate = str(item.get("messageId") or "")
            if candidate == message_id:
                return BrevoTransactionalEmailReference(
                    message_id=candidate,
                    uuid=str(item.get("uuid")) if item.get("uuid") else None,
                )
        return None

    async def get_transactional_emails_by_recipient_window(
        self,
        recipient_email: str,
        *,
        start_date: date,
        end_date: date,
    ) -> list[BrevoTransactionalEmailReference]:
        payload = await self._get_json(
            TRANSACTIONAL_EMAILS_PATH,
            params={
                "email": recipient_email,
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "limit": 500,
                "offset": 0,
                "sort": "desc",
            },
        )
        return [
            BrevoTransactionalEmailReference(
                message_id=str(item.get("messageId") or ""),
                uuid=str(item.get("uuid")) if item.get("uuid") else None,
            )
            for item in _dict_items(payload, "transactionalEmails", "emails", "items")
            if item.get("messageId")
        ]

    async def get_transactional_email_history_by_uuid(self, uuid: str) -> list[BrevoEmailEvent]:
        payload = await self._get_json(f"{TRANSACTIONAL_EMAILS_PATH}/{uuid}")
        return [_event_from_payload(item) for item in _dict_items(payload, "events")]

    async def get_email_events_by_message_id(self, message_id: str) -> list[BrevoEmailEvent]:
        payload = await self._get_json(
            TRANSACTIONAL_EVENTS_PATH,
            params={"messageId": message_id, "limit": 2500, "offset": 0, "sort": "desc"},
        )
        return [_event_from_payload(item) for item in _dict_items(payload, "events")]

    async def get_email_events_by_recipient_window(
        self,
        recipient_email: str,
        *,
        start_date: date,
        end_date: date,
    ) -> list[BrevoEmailEvent]:
        payload = await self._get_json(
            TRANSACTIONAL_EVENTS_PATH,
            params={
                "email": recipient_email,
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "limit": 2500,
                "offset": 0,
                "sort": "desc",
            },
        )
        return [_event_from_payload(item) for item in _dict_items(payload, "events")]

    async def get_blocked_contact_status(
        self,
        recipient_email: str,
        *,
        sender_email: str | None = None,
        max_contacts: int = 1000,
    ) -> BrevoBlockedContactStatus:
        offset = 0
        while offset < max_contacts:
            payload = await self._get_json(
                BLOCKED_CONTACTS_PATH,
                params={"limit": 100, "offset": offset, "sort": "desc"},
            )
            contacts = _dict_items(payload, "contacts", "items")
            for contact in contacts:
                if str(contact.get("email") or "").casefold() != recipient_email.casefold():
                    continue
                reason = contact.get("reason") if isinstance(contact.get("reason"), dict) else {}
                contact_sender = str(contact.get("senderEmail") or contact.get("sender") or "")
                return BrevoBlockedContactStatus(
                    matched=True,
                    reason_category=_blocked_reason_category(reason.get("code")),
                    sender_specific_match=bool(
                        sender_email and contact_sender and contact_sender.casefold() == sender_email.casefold()
                    ),
                )
            declared_count = payload.get("count")
            if len(contacts) < 100 or (
                isinstance(declared_count, int) and offset + len(contacts) >= declared_count
            ):
                break
            offset += 100
        return BrevoBlockedContactStatus(matched=False)
