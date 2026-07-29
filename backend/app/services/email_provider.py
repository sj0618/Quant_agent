from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import Settings, redact_secrets, validate_sender_mailbox
from app.core.errors import AppError
from app.schemas.email_delivery import EmailDeliveryMessage, EmailDeliverySendResult

BREVO_API_BASE_URL = "https://api.brevo.com"
BREVO_PROVIDER_NAME = "brevo"
BREVO_REQUEST_USER_AGENT = "QuantAgentBackend/0.1"
BREVO_REQUEST_PATH = "/v3/smtp/email"
BREVO_SANDBOX_HEADER = "X-Sib-Sandbox"
BREVO_SANDBOX_VALUE = "drop"
RESEND_API_BASE_URL = "https://api.resend.com"
RESEND_PROVIDER_NAME = "resend"
RESEND_REQUEST_PATH = "/emails"
RETRYABLE_HTTP_STATUSES = {429}
EMAIL_ADDRESS_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _safe_text(value: Any, *, limit: int = 500) -> str:
    text = str(redact_secrets(str(value if value is not None else ""))).strip()
    text = EMAIL_ADDRESS_PATTERN.sub("<redacted-email>", text)
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _normalize_message_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _safe_code(value: Any, *, fallback: str) -> str:
    normalized = "".join(
        character for character in str(value or "").strip().lower() if character.isalnum() or character in "_-"
    )
    return normalized[:80] or fallback


def _extract_response_code(response: httpx.Response) -> str | None:
    code: str | None = None
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        payload = None

    if isinstance(payload, dict):
        inner = payload.get("error") if isinstance(payload.get("error"), dict) else payload
        if isinstance(inner, dict):
            code_value = inner.get("code") or inner.get("name") or inner.get("type")
            if code_value is not None:
                code = str(code_value)
    return code


class BrevoEmailProvider:
    def __init__(self, settings: Settings, *, api_base_url: str | None = None) -> None:
        self.settings = settings
        self.api_base_url = (api_base_url or settings.email_brevo_api_base_url or BREVO_API_BASE_URL).rstrip("/")

    def _runtime_provider_name(self) -> str:
        return str(self.settings.email_provider or BREVO_PROVIDER_NAME).strip().lower()

    def validate_configuration(self) -> None:
        if self.settings.email_effective_rollout_mode == "disabled":
            raise AppError(
                status_code=503,
                component="email_provider",
                code="email_rollout_disabled",
                message="Email rollout is disabled",
            )
        if self.settings.email_provider not in {BREVO_PROVIDER_NAME, RESEND_PROVIDER_NAME}:
            raise AppError(
                status_code=503,
                component="email_provider",
                code="email_provider_invalid",
                message="Email provider is not configured for Brevo or Resend compatibility",
                details={"provider": self.settings.email_provider},
            )
        if not self.settings.email_delivery_enabled:
            raise AppError(
                status_code=503,
                component="email_provider",
                code="email_delivery_disabled",
                message="Email delivery is disabled",
            )
        if self.settings.email_api_key is None:
            raise AppError(
                status_code=503,
                component="email_provider",
                code="email_api_key_missing",
                message="Brevo API key is required for explicit provider calls",
            )
        if not self.settings.email_from_address:
            raise AppError(
                status_code=503,
                component="email_provider",
                code="email_from_address_missing",
                message="Email sender address is required",
            )
        try:
            validate_sender_mailbox(
                self.settings.email_from_address,
                require_authenticated_domain=True,
            )
        except ValueError:
            raise AppError(
                status_code=503,
                component="email_provider",
                code="email_from_address_invalid",
                message="Email sender address is invalid",
            ) from None
        if not self.settings.email_from_name:
            raise AppError(
                status_code=503,
                component="email_provider",
                code="email_from_name_missing",
                message="Email sender name is required",
            )

    def _assert_rollout_recipient_allowed(self, recipient_email: str) -> None:
        rollout_mode = self.settings.email_effective_rollout_mode
        if rollout_mode == "disabled":
            raise AppError(
                status_code=403,
                component="email_provider",
                code="email_rollout_disabled",
                message="Email rollout is disabled",
            )
        if rollout_mode == "production":
            return
        allowed = {item.lower() for item in self.settings.email_local_recipient_allowlist_values}
        normalized_recipient = recipient_email.strip().lower()
        if not allowed or normalized_recipient not in allowed:
            raise AppError(
                status_code=403,
                component="email_provider",
                code="email_recipient_not_allowlisted",
                message="Recipient is not in the local development allowlist",
                details={"allowlist_size": len(allowed)},
            )

    def _assert_local_live_send_allowed(self, recipient_email: str) -> None:
        self._assert_rollout_recipient_allowed(recipient_email)

    def _request_headers(self, message: EmailDeliveryMessage, *, provider_name: str) -> dict[str, str]:
        headers: dict[str, str] = {
            "accept": "application/json",
            "content-type": "application/json",
            "Idempotency-Key": message.idempotency_key,
            "User-Agent": BREVO_REQUEST_USER_AGENT,
        }
        api_key = self.settings.email_api_key_value or ""
        if provider_name == RESEND_PROVIDER_NAME:
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            headers["api-key"] = api_key
        if message.correlation_id:
            headers["X-QuantAgent-Correlation-Id"] = message.correlation_id
        headers["X-QuantAgent-Template"] = f"{message.template_name}/{message.template_version}"
        return headers

    def _request_payload(self, message: EmailDeliveryMessage, *, provider_name: str) -> dict[str, Any]:
        headers: dict[str, str] = {
            "X-QuantAgent-Template": f"{message.template_name}/{message.template_version}",
        }
        if message.correlation_id:
            headers["X-QuantAgent-Correlation-Id"] = message.correlation_id
        if provider_name == BREVO_PROVIDER_NAME:
            if self.settings.email_brevo_sandbox_mode:
                headers[BREVO_SANDBOX_HEADER] = BREVO_SANDBOX_VALUE
            return {
                "sender": {
                    "name": self.settings.email_from_name,
                    "email": self.settings.email_from_address,
                },
                "to": [
                    {
                        "email": message.recipient_email,
                    }
                ],
                "subject": message.subject,
                "htmlContent": message.html_body,
                "textContent": message.text_body,
                "headers": headers,
            }

        return {
            "from": f"{self.settings.email_from_name} <{self.settings.email_from_address}>",
            "to": [message.recipient_email],
            "subject": message.subject,
            "html": message.html_body,
            "text": message.text_body,
            "headers": headers,
        }

    def normalize_error(self, error: Exception | httpx.Response) -> EmailDeliverySendResult:
        provider_name = self._runtime_provider_name()
        if isinstance(error, httpx.Response):
            code = _extract_response_code(error)
            status_code = error.status_code
            retryable = status_code in RETRYABLE_HTTP_STATUSES or status_code >= 500
            normalized_status = "retryable_error" if retryable else "permanent_error"
            return EmailDeliverySendResult(
                provider=provider_name,
                provider_message_id=None,
                accepted_at=None,
                status=normalized_status,
                retryable=retryable,
                error_code=_safe_code(code, fallback=f"{provider_name}_http_{status_code}"),
                error_message=f"Email provider request failed with HTTP {status_code}",
            )

        if isinstance(error, (httpx.TimeoutException, httpx.RequestError)):
            return EmailDeliverySendResult(
                provider=provider_name,
                provider_message_id=None,
                accepted_at=None,
                status="retryable_error",
                retryable=True,
                error_code=f"{provider_name}_request_error",
                error_message=_safe_text(f"{type(error).__name__}: {error}"),
            )

        return EmailDeliverySendResult(
            provider=provider_name,
            provider_message_id=None,
            accepted_at=None,
            status="permanent_error",
            retryable=False,
            error_code=f"{provider_name}_unexpected_error",
            error_message=_safe_text(f"{type(error).__name__}: {error}"),
        )

    async def send(self, message: EmailDeliveryMessage) -> EmailDeliverySendResult:
        self.validate_configuration()
        self._assert_rollout_recipient_allowed(message.recipient_email)

        timeout = httpx.Timeout(self.settings.email_request_timeout_seconds)
        provider_name = self._runtime_provider_name()
        headers = self._request_headers(message, provider_name=provider_name)
        payload = self._request_payload(message, provider_name=provider_name)
        base_url = self.api_base_url if provider_name == BREVO_PROVIDER_NAME else RESEND_API_BASE_URL
        request_path = BREVO_REQUEST_PATH if provider_name == BREVO_PROVIDER_NAME else RESEND_REQUEST_PATH

        try:
            async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
                response = await client.post(request_path, headers=headers, json=payload)
        except Exception as exc:  # noqa: BLE001
            return self.normalize_error(exc)

        if 200 <= response.status_code < 300:
            response_payload: dict[str, Any] = {}
            try:
                parsed = response.json()
                if isinstance(parsed, dict):
                    response_payload = parsed
            except Exception:  # noqa: BLE001
                response_payload = {}
            if provider_name == BREVO_PROVIDER_NAME:
                provider_message_id = _normalize_message_id(
                    response_payload.get("messageId") or response_payload.get("message_id") or response_payload.get("messageID")
                )
            else:
                provider_message_id = _normalize_message_id(
                    response_payload.get("id") or response_payload.get("messageId") or response_payload.get("message_id")
                )
            return EmailDeliverySendResult(
                provider=provider_name,
                provider_message_id=provider_message_id,
                accepted_at=_utc_now_iso(),
                status="accepted",
                retryable=False,
            )

        return self.normalize_error(response)


# Backward-compatible alias for older imports/tests.
ResendEmailProvider = BrevoEmailProvider
