from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

EmailDeliveryStatus = Literal["PENDING", "PROCESSING", "RETRY_PENDING", "SENT", "FAILED", "CANCELLED"]
EmailDeliveryTriggerType = Literal["report_completed", "daily_digest"]
EmailDeliveryTemplateName = Literal["report_completed", "daily_digest"]
EmailDeliveryTemplateVersion = Literal["v1"]
EmailDeliverySendStatus = Literal["accepted", "retryable_error", "permanent_error"]

DEFAULT_EMAIL_DELIVERY_TRIGGER_TYPE: EmailDeliveryTriggerType = "report_completed"
DEFAULT_EMAIL_TEMPLATE_NAME: EmailDeliveryTemplateName = "report_completed"
DEFAULT_EMAIL_TEMPLATE_VERSION: EmailDeliveryTemplateVersion = "v1"
DEFAULT_DAILY_DIGEST_TRIGGER_TYPE: EmailDeliveryTriggerType = "daily_digest"
DEFAULT_DAILY_DIGEST_TEMPLATE_NAME: EmailDeliveryTemplateName = "daily_digest"
DEFAULT_EMAIL_PROVIDER = "brevo"


@dataclass(frozen=True, slots=True)
class EmailDeliveryCreateRequest:
    user_id: str
    report_id: str
    trigger_type: EmailDeliveryTriggerType
    template_name: EmailDeliveryTemplateName
    template_version: EmailDeliveryTemplateVersion
    recipient_email: str
    idempotency_key: str
    payload_json: dict[str, Any] = field(default_factory=dict)
    provider: str = DEFAULT_EMAIL_PROVIDER
    max_attempts: int = 5
    available_at: datetime | None = None
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class EmailDeliveryMessage:
    recipient_email: str
    sender_email: str
    sender_name: str
    subject: str
    html_body: str
    text_body: str
    correlation_id: str | None
    idempotency_key: str
    template_name: EmailDeliveryTemplateName
    template_version: EmailDeliveryTemplateVersion


@dataclass(frozen=True, slots=True)
class EmailTemplateRenderResult:
    subject: str
    html_body: str
    text_body: str
    template_name: EmailDeliveryTemplateName = DEFAULT_EMAIL_TEMPLATE_NAME
    template_version: EmailDeliveryTemplateVersion = DEFAULT_EMAIL_TEMPLATE_VERSION


@dataclass(frozen=True, slots=True)
class EmailDeliverySendResult:
    provider: str = DEFAULT_EMAIL_PROVIDER
    provider_message_id: str | None = None
    accepted_at: str | None = None
    status: EmailDeliverySendStatus = "permanent_error"
    retryable: bool = False
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class EmailDeliveryEligibilityDecision:
    allowed: bool
    reason_code: str
    reason_message: str
    user_id: str | None = None
    report_id: str | None = None
    recipient_email: str | None = None
    trigger_type: EmailDeliveryTriggerType = DEFAULT_EMAIL_DELIVERY_TRIGGER_TYPE
    template_name: EmailDeliveryTemplateName = DEFAULT_EMAIL_TEMPLATE_NAME
    template_version: EmailDeliveryTemplateVersion = DEFAULT_EMAIL_TEMPLATE_VERSION
    correlation_id: str | None = None
    payload_json: dict[str, Any] = field(default_factory=dict)
