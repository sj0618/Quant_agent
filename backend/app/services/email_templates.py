from __future__ import annotations

from html import escape
from urllib.parse import quote, urlsplit

from app.schemas.email_delivery import (
    DEFAULT_EMAIL_TEMPLATE_NAME,
    DEFAULT_EMAIL_TEMPLATE_VERSION,
    EmailTemplateRenderResult,
)


def _normalize_inline_text(value: str | None, fallback: str) -> str:
    normalized = " ".join((value or fallback).split()).strip()
    return normalized or fallback


def _public_report_url(public_base_url: str, report_id: str) -> str:
    base = public_base_url.strip().rstrip("/")
    if not base:
        raise ValueError("public_base_url is required")
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("public_base_url must be an absolute http(s) URL without credentials")
    # /reports/:id is the FE archive route that resolves AI job ids; the emailed report
    # lives on the owner-scoped email report screen.
    return f"{base}/me/email-reports/{quote(report_id, safe='')}"


def render_report_completed_template(
    *,
    public_base_url: str,
    report_id: str,
    report_title: str | None,
    report_summary: str | None,
    recipient_email: str,
    recipient_name: str | None = None,
    unsubscribe_url: str | None = None,
) -> EmailTemplateRenderResult:
    title = _normalize_inline_text(report_title, "Your report is ready")
    summary = _normalize_inline_text(report_summary, "QuantAgent has prepared your report.")
    recipient_label = _normalize_inline_text(recipient_name, recipient_email)
    report_url = _public_report_url(public_base_url, report_id)
    subject = f"QuantAgent report ready: {title}"

    html_body = "\n".join(
        [
            "<!doctype html>",
            "<html>",
            "  <body>",
            f"    <p>Hi {escape(recipient_label)},</p>",
            "    <p>Your report is ready.</p>",
            f"    <p><strong>{escape(title)}</strong></p>",
            f"    <p>{escape(summary)}</p>",
            f"    <p><a href=\"{escape(report_url)}\">Open report</a></p>",
            *(
                [f"    <p><a href=\"{escape(unsubscribe_url)}\">Unsubscribe from action emails</a></p>"]
                if unsubscribe_url
                else []
            ),
            "  </body>",
            "</html>",
        ]
    )
    text_body = "\n".join(
        [
            f"Hi {recipient_label},",
            "",
            "Your report is ready.",
            f"Title: {title}",
            f"Summary: {summary}",
            f"Open report: {report_url}",
            *([f"Unsubscribe from action emails: {unsubscribe_url}"] if unsubscribe_url else []),
        ]
    )

    return EmailTemplateRenderResult(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        template_name=DEFAULT_EMAIL_TEMPLATE_NAME,
        template_version=DEFAULT_EMAIL_TEMPLATE_VERSION,
    )
