from __future__ import annotations

import base64
import json
from datetime import date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import AppError
from app.core.runtime_perf import measure_span
from app.db.session import fetch_all, fetch_one

REPORT_LIST_DEFAULT_LIMIT = 20
REPORT_LIST_MAX_LIMIT = 100
REPORT_STORE_COMPONENT = "reports"
RUN_STORE_COMPONENT = "analysis_runs"
REPORT_CONTENT_SCHEMA_VERSION = 1
_READER_EVIDENCE_SECTION_IDS = frozenset({"reproduction_contract", "metric_registry"})
_REPRODUCTION_CONTRACT_FIELDS = (
    ("contract_version", "재현 계약 버전"),
    ("input_hash", "입력 해시"),
    ("output_hash", "출력 해시"),
    ("data_fingerprint", "데이터 지문"),
    ("strategy_fingerprint", "전략 지문"),
    ("candidate_fingerprint", "후보 지문"),
    ("engine_version", "엔진 버전"),
    ("feature_version", "피처 버전"),
    ("metric_formula_version", "지표 수식 버전"),
    ("as_of_date", "기준일"),
    ("selected_candidate_id", "선정 후보 ID"),
)
KOREAN_WEEKDAY_LABELS = {
    "monday": "월요일",
    "tuesday": "화요일",
    "wednesday": "수요일",
    "thursday": "목요일",
    "friday": "금요일",
    "saturday": "토요일",
    "sunday": "일요일",
    "mon": "월요일",
    "tue": "화요일",
    "tues": "화요일",
    "wed": "수요일",
    "thu": "목요일",
    "thur": "목요일",
    "thurs": "목요일",
    "fri": "금요일",
    "sat": "토요일",
    "sun": "일요일",
}


def _coerce_bigint_user_id(user_id: str | int) -> int:
    normalized = str(user_id).strip()
    if not normalized:
        raise AppError(
            status_code=422,
            component=REPORT_STORE_COMPONENT,
            code="request_validation_failed",
            message="User id is required",
            details={"field": "user_id"},
        )
    try:
        return int(normalized)
    except ValueError as exc:
        raise AppError(
            status_code=422,
            component=REPORT_STORE_COMPONENT,
            code="request_validation_failed",
            message="User id must be an integer",
            details={"field": "user_id", "value": normalized},
        ) from exc


def _coerce_limit(limit: int) -> int:
    try:
        value = int(limit)
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            status_code=422,
            component=REPORT_STORE_COMPONENT,
            code="request_validation_failed",
            message="Report limit must be a positive integer",
            details={"limit": limit},
        ) from exc
    return max(1, min(value, REPORT_LIST_MAX_LIMIT))


def _normalize_search_pattern(query: str | None) -> str | None:
    if query is None:
        return None
    normalized = str(query).strip()
    if not normalized:
        return None
    return f"%{normalized}%"


def _cursor_payload(value: str | None, report_id: str | None) -> str | None:
    if value is None or report_id is None:
        return None
    payload = json.dumps({"sortAt": value, "id": report_id}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(raw_cursor: str | None) -> tuple[str, str] | None:
    if raw_cursor is None or not raw_cursor.strip():
        return None
    padded = raw_cursor.strip() + "=" * (-len(raw_cursor.strip()) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            status_code=400,
            component=REPORT_STORE_COMPONENT,
            code="invalid_report_cursor",
            message="Report cursor is invalid",
            details={"cursor": raw_cursor},
        ) from exc
    sort_at = payload.get("sortAt")
    report_id = payload.get("id")
    if not isinstance(sort_at, str) or not isinstance(report_id, str):
        raise AppError(
            status_code=400,
            component=REPORT_STORE_COMPONENT,
            code="invalid_report_cursor",
            message="Report cursor is invalid",
            details={"cursor": raw_cursor},
        )
    return sort_at, report_id


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def _optional_text(value: Any) -> str | None:
    text = _text(value).strip()
    return text or None


def _as_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _optional_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return text
    return parsed.isoformat().replace("+00:00", "Z")


def _json_object(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json", exclude_none=False)
        return dumped if isinstance(dumped, dict) else {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:  # noqa: BLE001
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _json_array(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item.model_dump(mode="json", exclude_none=False) if hasattr(item, "model_dump") else item for item in value]
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json", exclude_none=False)
        return dumped if isinstance(dumped, list) else []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:  # noqa: BLE001
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _config_value(config: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in config and config[key] is not None:
            return config[key]
    request_payload = _json_object(_first_non_empty(config.get("requestPayload"), config.get("request_payload")))
    for key in keys:
        if key in request_payload and request_payload[key] is not None:
            return request_payload[key]
    return None


def _strategy_id_from_config(config: dict[str, Any]) -> str | None:
    return _optional_text(_config_value(config, "strategyId", "strategy_id"))


def _instrument_id_from_config(config: dict[str, Any]) -> str | None:
    return _optional_text(_config_value(config, "instrumentId", "instrument_id"))


def _ticker_from_config(config: dict[str, Any]) -> str | None:
    return _optional_text(_config_value(config, "ticker"))


def _numeric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return None


def _normalize_status(value: Any) -> str:
    text = _optional_text(value)
    if not text:
        return "unknown"
    normalized = text.lower()
    if normalized in {"sent", "draft", "failed", "resent"}:
        return normalized
    if normalized in {"completed", "published"}:
        return "sent"
    if normalized == "completed":
        return "sent"
    return normalized


def _report_score_text(value: Any) -> str:
    numeric = _numeric(value)
    if numeric is None:
        return _text(_first_non_empty(value), "—")
    return f"{numeric:.1f}"




def _report_strategy_label(row: dict[str, Any], run_config: dict[str, Any]) -> str | None:
    strategy_name = _optional_text(_first_non_empty(row.get("strategy_name"), _config_value(run_config, "strategyName", "strategy_name")))
    if strategy_name is None:
        return None
    raw_query = _optional_text(_config_value(run_config, "query"))
    if raw_query is not None and strategy_name == raw_query:
        return None
    return strategy_name


def _report_int_value(value: Any) -> int:
    numeric = _numeric(value)
    if numeric is None:
        return 0
    return int(round(numeric))


def _report_date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y.%m.%d")
    if isinstance(value, date):
        return value.strftime("%Y.%m.%d")
    text = _optional_text(value)
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return text
    return parsed.strftime("%Y.%m.%d")


def _report_weekday_text(value: Any, fallback_date: Any = None) -> str:
    text = _optional_text(value)
    if text:
        normalized = text.strip().lower().replace(".", "")
        return KOREAN_WEEKDAY_LABELS.get(normalized, text)

    if fallback_date is not None:
        candidate = fallback_date
        if isinstance(candidate, str):
            try:
                candidate = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001
                return ""
        if isinstance(candidate, datetime):
            normalized = candidate.strftime("%A").lower()
        elif isinstance(candidate, date):
            normalized = candidate.strftime("%A").lower()
        else:
            return ""
        return KOREAN_WEEKDAY_LABELS.get(normalized, "")
    return ""


def _report_sent_at_text(value: Any) -> str:
    if isinstance(value, datetime):
        candidate = value
    else:
        text = _optional_text(value)
        if not text:
            return ""
        try:
            candidate = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            return text
    hour = candidate.hour
    minute = candidate.minute
    meridiem = "오전" if hour < 12 else "오후"
    display_hour = hour % 12 or 12
    return f"{meridiem} {display_hour}:{minute:02d} 발송"


def _report_market_snapshot(value: Any) -> list[dict[str, Any]]:
    items = _json_array(value)
    result: list[dict[str, Any]] = []
    for raw_item in items:
        item = _json_object(raw_item)
        label = _optional_text(_first_non_empty(item.get("label"), item.get("name")))
        raw_value = _optional_text(_first_non_empty(item.get("value"), item.get("text")))
        if label is None or raw_value is None:
            continue
        candidate: dict[str, Any] = {"label": label, "value": raw_value}
        tone = _optional_text(item.get("tone"))
        if tone:
            candidate["tone"] = tone
        result.append(candidate)
    return result


def _report_signal_axes(value: Any) -> list[dict[str, Any]]:
    items = _json_array(value)
    result: list[dict[str, Any]] = []
    for index, raw_item in enumerate(items, start=1):
        item = _json_object(raw_item)
        label = _optional_text(_first_non_empty(item.get("label"), item.get("name"), f"축 {index}")) or f"축 {index}"
        weight = _text(_first_non_empty(item.get("weight"), item.get("score"), item.get("ratio"), ""))
        title = _text(_first_non_empty(item.get("title"), item.get("name"), label))
        description = _text(_first_non_empty(item.get("description"), item.get("summary"), item.get("body"), ""))
        result.append(
            {
                "label": label,
                "weight": weight,
                "title": title,
                "description": description,
            }
        )
    return result


def _report_news_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed_tones = {"positive", "warning", "negative", "neutral", "info"}
    items: list[dict[str, Any]] = []
    for row in rows:
        tone = (_optional_text(row.get("tone")) or "neutral").lower()
        if tone not in allowed_tones:
            tone = "neutral"
        item = {
            "rank": _report_int_value(row.get("rank")),
            "title": _text(row.get("title")),
            "source": _text(_first_non_empty(row.get("source"), "")),
            "tone": tone,
        }
        if item["rank"] <= 0:
            continue
        items.append(item)
    return items


def _report_candidate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        signal = (_optional_text(row.get("signal")) or "").upper()
        if signal not in {"BUY", "HOLD", "DROP"}:
            continue
        evidence = _json_array(row.get("evidence_jsonb"))
        risk_reasons = [str(value) for value in _json_array(row.get("risk_reasons_jsonb")) if _optional_text(value)]
        confidence = _numeric(_first_non_empty(row.get("confidence"), row.get("score")))
        items.append(
            {
                "id": _text(_first_non_empty(row.get("ticker"), f"candidate-{index}")),
                "ticker": _text(_first_non_empty(row.get("ticker"), "")),
                "name": _text(_first_non_empty(row.get("name"), row.get("ticker"), "")),
                "sector": _text(_first_non_empty(row.get("sector"), "")),
                "signal": signal,
                "confidence": confidence if confidence is not None else 0.0,
                "price": _text(_first_non_empty(row.get("price"), "")),
                "changePercent": _text(_first_non_empty(row.get("change_percent"), "")),
                "rationale": _text(_first_non_empty(row.get("rationale"), "")),
                "evidence": [_json_object(entry) for entry in evidence if isinstance(entry, dict)],
                "riskReasons": risk_reasons,
            }
        )
        risk_manager_override = _optional_text(row.get("risk_manager_override"))
        if risk_manager_override is not None:
            items[-1]["risk_manager_override"] = risk_manager_override
        web_projection = _optional_text(row.get("web_projection"))
        if web_projection is not None:
            items[-1]["web_projection"] = web_projection
    return items


def _report_performance_metric(
    *,
    key: str,
    label: str,
    value: str,
    tone: str,
    caption: str,
    delta: str | None = None,
) -> dict[str, Any]:
    metric = {
        "key": key,
        "label": label,
        "value": value,
        "tone": tone,
        "caption": caption,
    }
    if delta:
        metric["delta"] = delta
    return metric


def _format_percent_value(value: Any, *, signed: bool = False) -> str | None:
    numeric = _numeric(value)
    if numeric is None:
        text = _optional_text(value)
        return text
    display = numeric * 100 if abs(numeric) <= 1.5 else numeric
    prefix = "+" if signed and display > 0 else ""
    return f"{prefix}{display:.1f}%"


def _format_ratio_value(value: Any) -> str | None:
    numeric = _numeric(value)
    if numeric is None:
        text = _optional_text(value)
        return text
    return f"{numeric:.2f}"


def _report_performance_payload(row: dict[str, Any]) -> dict[str, Any]:
    performance = _json_object(row.get("performance_jsonb"))
    metrics = _json_array(performance.get("metrics"))
    disclaimer = _optional_text(performance.get("disclaimer")) or ""
    if metrics:
        normalized_metrics: list[dict[str, Any]] = []
        for index, raw_metric in enumerate(metrics, start=1):
            metric = _json_object(raw_metric)
            key = _optional_text(_first_non_empty(metric.get("key"), metric.get("id"), f"metric-{index}")) or f"metric-{index}"
            label = _text(_first_non_empty(metric.get("label"), metric.get("title"), key))
            value = _text(_first_non_empty(metric.get("value"), metric.get("displayValue"), metric.get("amount"), ""))
            tone = _optional_text(metric.get("tone")) or "neutral"
            caption = _text(_first_non_empty(metric.get("caption"), ""))
            normalized_metric = {
                "key": key,
                "label": label,
                "value": value,
                "tone": tone,
                "caption": caption,
            }
            delta = _optional_text(metric.get("delta"))
            if delta is not None:
                normalized_metric["delta"] = delta
            normalized_metrics.append(normalized_metric)
        return {"metrics": normalized_metrics, "disclaimer": disclaimer}

    sharpe = _numeric(row.get("summary_sharpe_ratio"))
    max_drawdown = _format_percent_value(row.get("summary_max_drawdown"))
    win_rate = _format_percent_value(row.get("summary_win_rate"))
    period_return = _format_percent_value(row.get("summary_period_return"), signed=True)
    cagr = _format_percent_value(row.get("summary_cagr"))
    benchmark_return = _format_percent_value(row.get("summary_benchmark_return"))
    trade_count = _report_int_value(row.get("summary_trade_count"))
    metrics: list[dict[str, Any]] = []
    if sharpe is not None:
        metrics.append(
            _report_performance_metric(
                key="sharpe",
                label="Sharpe Ratio",
                value=f"{sharpe:.2f}",
                tone="positive" if sharpe >= 1 else ("warning" if sharpe >= 0.7 else "negative"),
                caption="backtest_summary.sharpe_ratio",
                delta=_text(_first_non_empty(benchmark_return, "")) if benchmark_return else None,
            )
        )
    if max_drawdown is not None:
        metrics.append(
            _report_performance_metric(
                key="mdd",
                label="Max Drawdown",
                value=max_drawdown,
                tone="negative",
                caption="backtest_summary.max_drawdown",
                delta=_text(_first_non_empty(benchmark_return, "")) if benchmark_return else None,
            )
        )
    if win_rate is not None:
        metrics.append(
            _report_performance_metric(
                key="winRate",
                label="Win Rate",
                value=win_rate,
                tone="positive" if (_numeric(row.get("summary_win_rate")) or 0) >= 0.5 else "warning",
                caption="backtest_summary.win_rate",
                delta=f"{trade_count}회 거래" if trade_count > 0 else None,
            )
        )
    if period_return is not None:
        metrics.append(
            _report_performance_metric(
                key="totalReturn",
                label="Total Return (10y)",
                value=period_return,
                tone="positive" if (_numeric(row.get("summary_period_return")) or 0) >= 0 else "negative",
                caption="backtest_summary.period_return",
                delta=f"CAGR {cagr}" if cagr else benchmark_return,
            )
        )
    return {"metrics": metrics, "disclaimer": disclaimer}


def _reader_safe_text(value: Any, *, limit: int = 512) -> str | None:
    """Return bounded, display-safe scalar text; never stringify nested payloads."""

    if not isinstance(value, (str, int, float, bool)):
        return None
    text = str(value).strip()
    if not text or len(text) > limit:
        return None
    return text


def _reader_safe_list(value: Any, *, limit: int = 12, item_limit: int = 120) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value[:limit]:
        text = _reader_safe_text(item, limit=item_limit)
        if text is not None:
            items.append(text)
    return items


def _reader_evidence_sections(value: Any) -> list[dict[str, Any]]:
    """Project only the two vetted, non-sensitive verification sections.

    The persisted report document also contains an execution snapshot and other
    AI-generated sections. Those are intentionally not part of the report
    detail API contract: this projection is an allowlist, not a JSON passthrough.
    """

    document = _json_object(value)
    published: list[dict[str, Any]] = []
    for raw_section in _json_array(document.get("sections")):
        section = _json_object(raw_section)
        section_id = _optional_text(section.get("id"))
        if section_id not in _READER_EVIDENCE_SECTION_IDS:
            continue
        items = _json_object(section.get("items"))

        if section_id == "reproduction_contract":
            entries = [
                {"label": label, "value": text, "depth": 1}
                for field, label in _REPRODUCTION_CONTRACT_FIELDS
                if (text := _reader_safe_text(items.get(field))) is not None
            ]
            if entries:
                published.append(
                    {
                        "id": section_id,
                        "title": "검증 재현 계약",
                        "entries": entries,
                    }
                )
            continue

        formula_version = _reader_safe_text(items.get("formula_version"), limit=128)
        metric_entries: list[dict[str, Any]] = []
        for raw_metric in _json_array(items.get("metrics"))[:30]:
            metric = _json_object(raw_metric)
            label = _reader_safe_text(metric.get("label"), limit=128)
            formula = _reader_safe_text(metric.get("formula"), limit=512)
            if label is None or formula is None:
                continue
            context: list[str] = []
            inputs = _reader_safe_list(metric.get("inputs"))
            if inputs:
                context.append(f"입력: {', '.join(inputs)}")
            for field, display_name in (
                ("input_window", "관찰 구간"),
                ("as_of_policy", "기준 시점"),
                ("null_policy", "결측 처리"),
                ("implementation_ref", "구현 기준"),
                ("implementation_hash", "구현 해시"),
            ):
                if (text := _reader_safe_text(metric.get(field))) is not None:
                    context.append(f"{display_name}: {text}")
            entry: dict[str, Any] = {"label": label, "value": formula, "depth": 1}
            if context:
                entry["description"] = " · ".join(context)
            metric_entries.append(entry)
        if metric_entries:
            projected: dict[str, Any] = {
                "id": section_id,
                "title": "퀀트 지표 산출 계약",
                "entries": metric_entries,
            }
            if formula_version is not None:
                projected["note"] = f"수식 레지스트리 버전: {formula_version}"
            published.append(projected)
    return published


def _report_summary_item(row: dict[str, Any]) -> dict[str, Any]:
    run_config = _json_object(row.get("run_config_jsonb"))
    sort_at = _first_non_empty(row.get("sort_at"), row.get("sent_at"), row.get("created_at"))
    report_date = _first_non_empty(row.get("report_date"), sort_at)
    strategy_name = _report_strategy_label(row, run_config)
    item = {
        "id": _text(_first_non_empty(row.get("report_id"))),
        "runId": _optional_text(row.get("backtest_run_id")),
        "date": _report_date_text(report_date),
        "weekday": _report_weekday_text(row.get("weekday"), report_date),
        "sentAt": _report_sent_at_text(_first_non_empty(row.get("sent_at"), row.get("created_at"))),
        "title": _text(_first_non_empty(row.get("title"), strategy_name, row.get("name"))),
        "summary": _text(_first_non_empty(row.get("summary"), row.get("description"), row.get("market_brief"), row.get("conclusion"))),
        "status": _normalize_status(_first_non_empty(row.get("status"), row.get("report_status"), row.get("run_status"))),
        "strategyName": strategy_name,
        "recommendationScore": _report_score_text(row.get("recommendation_score")),
        "signals": {
            "BUY": _report_int_value(row.get("buy_count")),
            "HOLD": _report_int_value(row.get("hold_count")),
            "DROP": _report_int_value(row.get("drop_count")),
        },
        "marketSnapshot": _report_market_snapshot(row.get("market_snapshot")),
        "_sortAt": _as_iso(sort_at),
    }
    strategy_id = _optional_text(_first_non_empty(row.get("strategy_id"), row.get("run_strategy_id"), _strategy_id_from_config(run_config)))
    if strategy_id is not None:
        item["strategyId"] = strategy_id
    instrument_id = _optional_text(_first_non_empty(row.get("instrument_id"), _instrument_id_from_config(run_config)))
    if instrument_id is not None:
        item["instrumentId"] = instrument_id
    instrument_name = _optional_text(_first_non_empty(row.get("instrument_name"), _config_value(run_config, "instrumentName", "instrument_name")))
    if instrument_name is not None:
        item["instrumentName"] = instrument_name
    ticker = _optional_text(_first_non_empty(row.get("ticker"), _ticker_from_config(run_config)))
    if ticker is not None:
        item["ticker"] = ticker
    published_at = _as_iso(sort_at)
    if published_at is not None:
        item["publishedAt"] = published_at
    created_at = _as_iso(row.get("created_at"))
    if created_at is not None:
        item["createdAt"] = created_at
    updated_at = _as_iso(row.get("updated_at"))
    if updated_at is not None:
        item["updatedAt"] = updated_at
    return item


async def list_reports(
    engine: AsyncEngine,
    *,
    limit: int = REPORT_LIST_DEFAULT_LIMIT,
    cursor: str | None = None,
    status: str | None = None,
    q: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    sanitized_limit = _coerce_limit(limit)
    cursor_payload = _decode_cursor(cursor)
    normalized_user_id = _coerce_bigint_user_id(user_id or "")
    filters: list[str] = ["run.user_id = CAST(:user_id AS bigint)"]
    params: dict[str, Any] = {"limit_plus_one": sanitized_limit + 1, "user_id": str(normalized_user_id)}
    if status is not None and str(status).strip():
        filters.append("report.status = :status")
        params["status"] = str(status).strip()
    search_pattern = _normalize_search_pattern(q)
    if search_pattern is not None:
        filters.append(
            "("
            "COALESCE(report.title, '') ILIKE :q "
            "OR COALESCE(report.summary, '') ILIKE :q "
            "OR COALESCE(report.content_md, '') ILIKE :q "
            "OR COALESCE(report.content_html, '') ILIKE :q "
            "OR COALESCE(report.market_brief, '') ILIKE :q "
            "OR COALESCE(report.market_context, '') ILIKE :q "
            "OR COALESCE(report.risk_manager_override, '') ILIKE :q "
            "OR COALESCE(report.conclusion, '') ILIKE :q "
            "OR COALESCE(report.warning_note, '') ILIKE :q "
            "OR COALESCE(profile.name, '') ILIKE :q "
            "OR COALESCE(profile.description, '') ILIKE :q "
            "OR COALESCE(profile.universe, '') ILIKE :q "
            "OR COALESCE(profile.entry_summary, '') ILIKE :q "
            "OR COALESCE(profile.exit_summary, '') ILIKE :q "
            "OR COALESCE(profile.risk_summary, '') ILIKE :q "
            "OR COALESCE(profile.tags::text, '') ILIKE :q "
            "OR COALESCE(run.strategy_id, '') ILIKE :q "
            "OR COALESCE(run.config_jsonb::text, '') ILIKE :q "
            "OR COALESCE(report.report_date::text, '') ILIKE :q "
            "OR COALESCE(report.weekday, '') ILIKE :q "
            "OR EXISTS ("
            "SELECT 1 "
            "FROM app.strategy_email_report_candidate AS candidate "
            "WHERE candidate.report_id = report.report_id "
            "AND ("
            "candidate.ticker ILIKE :q "
            "OR COALESCE(candidate.name, '') ILIKE :q "
            "OR COALESCE(candidate.sector, '') ILIKE :q "
            "OR candidate.signal ILIKE :q "
            "OR COALESCE(candidate.price, '') ILIKE :q "
            "OR COALESCE(candidate.change_percent, '') ILIKE :q "
            "OR COALESCE(candidate.rationale, '') ILIKE :q "
            "OR COALESCE(candidate.risk_manager_override, '') ILIKE :q "
            "OR COALESCE(candidate.web_projection, '') ILIKE :q "
            "OR COALESCE(candidate.evidence_jsonb::text, '') ILIKE :q "
            "OR COALESCE(candidate.risk_reasons_jsonb::text, '') ILIKE :q"
            ")"
            ")"
            ")"
        )
        params["q"] = search_pattern
    if cursor_payload is not None:
        filters.append(
            "(COALESCE(report.sent_at, report.created_at), report.report_id) "
            "< (CAST(:cursor_sort_at AS timestamptz), :cursor_id)"
        )
        params["cursor_sort_at"] = cursor_payload[0]
        params["cursor_id"] = cursor_payload[1]

    sql = f"""
        SELECT
            report.report_id::text AS report_id,
            report.backtest_run_id,
            report.strategy_id,
            profile.name AS strategy_name,
            report.title,
            report.summary,
            report.status,
            report.report_date,
            report.weekday,
            report.sent_at,
            report.created_at,
            report.updated_at,
            COALESCE(report.sent_at, report.created_at) AS sort_at,
            run.config_jsonb AS run_config_jsonb,
            run.strategy_id AS run_strategy_id,
            report.buy_count,
            report.hold_count,
            report.drop_count,
            report.recommendation_score,
            report.market_snapshot
        FROM app.strategy_email_report AS report
        INNER JOIN app.backtest_run AS run
          ON run.run_id = report.backtest_run_id
        LEFT JOIN app.strategy_report_profile AS profile
          ON profile.strategy_id = report.strategy_id
        WHERE {' AND '.join(filters)}
        ORDER BY COALESCE(report.sent_at, report.created_at) DESC, report.report_id DESC
        LIMIT :limit_plus_one
    """
    rows = await fetch_all(engine, sql, params)
    with measure_span("mapping"):
        items = [_report_summary_item(row) for row in rows[:sanitized_limit]]
        has_more = len(rows) > sanitized_limit
        next_cursor = None
        if has_more and items:
            last_item = items[-1]
            next_cursor = _cursor_payload(last_item["_sortAt"], last_item["id"])
        for item in items:
            item.pop("_sortAt", None)
    return {"items": items, "meta": {"limit": sanitized_limit, "hasMore": has_more, "nextCursor": next_cursor}}


async def get_report(engine: AsyncEngine, report_id: str, *, user_id: str | None = None) -> dict[str, Any] | None:
    filters = ["report.report_id = :report_id"]
    params: dict[str, Any] = {"report_id": report_id}
    if user_id is not None and str(user_id).strip():
        normalized_user_id = _coerce_bigint_user_id(user_id)
        filters.append("run.user_id = CAST(:user_id AS bigint)")
        params["user_id"] = str(normalized_user_id)
    row = await fetch_one(
        engine,
        f"""
        SELECT
            report.report_id,
            report.strategy_id,
            report.backtest_run_id,
            profile.name AS strategy_name,
            report.report_date,
            report.weekday,
            report.sent_at,
            report.title,
            report.summary,
            report.status,
            report.created_at,
            report.updated_at,
            report.recommendation_score,
            report.buy_count,
            report.hold_count,
            report.drop_count,
            report.market_snapshot,
            report.recipient,
            report.market_brief,
            report.market_context,
            report.risk_manager_override,
            report.conclusion,
            report.warning_note,
            report.signal_axes_jsonb,
            report.performance_jsonb,
            report.cost_notes,
            report.content_html,
            run.run_id AS run_id,
            run.strategy_id AS run_strategy_id,
            run.config_jsonb AS run_config_jsonb,
            summary.period_return AS summary_period_return,
            summary.cagr AS summary_cagr,
            summary.benchmark_return AS summary_benchmark_return,
            summary.max_drawdown AS summary_max_drawdown,
            summary.sharpe_ratio AS summary_sharpe_ratio,
            summary.win_rate AS summary_win_rate,
            summary.trade_count AS summary_trade_count,
            summary.metrics_version AS summary_metrics_version,
            detail.compare_json AS detail_compare_json,
            detail.composition_json AS detail_composition_json,
            detail.drawdown_detail_json AS detail_drawdown_detail_json,
            detail.drawdown_series_json AS detail_drawdown_series_json,
            detail.greeks_json AS detail_greeks_json,
            detail.rolling_returns_json AS detail_rolling_returns_json,
            detail.monthly_return_json AS detail_monthly_return_json,
            detail.montecarlo_json AS detail_montecarlo_json,
            detail.montecarlo_cagr_json AS detail_montecarlo_cagr_json,
            detail.montecarlo_drawdown_json AS detail_montecarlo_drawdown_json,
            detail.montecarlo_sharpe_json AS detail_montecarlo_sharpe_json,
            detail.outliers_json AS detail_outliers_json
        FROM app.strategy_email_report AS report
        LEFT JOIN app.backtest_run AS run
          ON run.run_id = report.backtest_run_id
        LEFT JOIN app.strategy_report_profile AS profile
          ON profile.strategy_id = report.strategy_id
        LEFT JOIN app.backtest_summary AS summary
          ON summary.run_id = report.backtest_run_id
        LEFT JOIN app.backtest_metric_detail AS detail
          ON detail.run_id = report.backtest_run_id
        WHERE {' AND '.join(filters)}
        LIMIT 1
        """,
        params,
    )
    if row is None:
        return None
    run_config = _json_object(row.get("run_config_jsonb"))
    strategy_name = _report_strategy_label(row, run_config)
    news_rows = await fetch_all(
        engine,
        """
        SELECT
            rank,
            title,
            source,
            tone,
            url,
            published_at,
            summary
        FROM app.strategy_email_report_news
        WHERE report_id = :report_id
        ORDER BY rank ASC
        """,
        {"report_id": report_id},
    )
    candidate_rows = await fetch_all(
        engine,
        """
        SELECT
            ticker,
            name,
            sector,
            signal,
            confidence,
            score,
            price,
            change_percent,
            rationale,
            evidence_jsonb,
            risk_reasons_jsonb,
            risk_manager_override,
            web_projection,
            sort_order
        FROM app.strategy_email_report_candidate
        WHERE report_id = :report_id
        ORDER BY sort_order ASC, ticker ASC
        """,
        {"report_id": report_id},
    )
    return {
        "id": _text(row.get("report_id")),
        "runId": _optional_text(row.get("backtest_run_id")) or _optional_text(row.get("run_id")) or "",
        "date": _report_date_text(row.get("report_date")),
        "weekday": _report_weekday_text(row.get("weekday"), row.get("report_date")),
        "sentAt": _report_sent_at_text(_first_non_empty(row.get("sent_at"), row.get("created_at"))),
        "title": _text(_first_non_empty(row.get("title"), strategy_name, row.get("strategy_id"))),
        "summary": _text(_first_non_empty(row.get("summary"), row.get("market_brief"), row.get("conclusion"))),
        "status": _normalize_status(_first_non_empty(row.get("status"))),
        "strategyId": _optional_text(
            _first_non_empty(
                row.get("strategy_id"),
                row.get("run_strategy_id"),
                _strategy_id_from_config(run_config),
            )
        ),
        "strategyName": strategy_name,
        "instrumentId": _optional_text(_first_non_empty(_instrument_id_from_config(run_config))),
        "instrumentName": _optional_text(_config_value(run_config, "instrumentName", "instrument_name")),
        "ticker": _optional_text(_first_non_empty(_ticker_from_config(run_config))),
        "recommendationScore": _report_score_text(row.get("recommendation_score")),
        "signals": {
            "BUY": _report_int_value(row.get("buy_count")),
            "HOLD": _report_int_value(row.get("hold_count")),
            "DROP": _report_int_value(row.get("drop_count")),
        },
        "marketSnapshot": _report_market_snapshot(row.get("market_snapshot")),
        "recipient": _optional_text(row.get("recipient")),
        "marketBrief": _text(_first_non_empty(row.get("market_brief"), row.get("summary"))),
        "marketContext": _optional_text(row.get("market_context")),
        "news": _report_news_rows(news_rows),
        "candidates": _report_candidate_rows(candidate_rows),
        "signalAxes": _report_signal_axes(row.get("signal_axes_jsonb")),
        "riskManagerOverride": _text(_first_non_empty(row.get("risk_manager_override"), "")),
        "conclusion": _text(_first_non_empty(row.get("conclusion"), row.get("summary"), row.get("market_brief"))),
        "warningNote": _optional_text(row.get("warning_note")),
        "performance": _report_performance_payload(row),
        "contentSections": _reader_evidence_sections(row.get("content_html")),
        "costNotes": [str(value) for value in _json_array(row.get("cost_notes")) if _optional_text(value)],
        "createdAt": _as_iso(row.get("created_at")),
        "updatedAt": _as_iso(row.get("updated_at")),
        "publishedAt": _as_iso(_first_non_empty(row.get("sent_at"), row.get("created_at"))),
        "_sortAt": _as_iso(_first_non_empty(row.get("sent_at"), row.get("created_at"))),
    }


async def get_analysis_run(engine: AsyncEngine, run_id: str, *, user_id: str | None = None) -> dict[str, Any] | None:
    filters = ["run.run_id = :run_id"]
    params: dict[str, Any] = {"run_id": run_id}
    if user_id is not None and str(user_id).strip():
        normalized_user_id = _coerce_bigint_user_id(user_id)
        filters.append("run.user_id = CAST(:user_id AS bigint)")
        params["user_id"] = str(normalized_user_id)

    row = await fetch_one(
        engine,
        f"""
        SELECT
            run.run_id,
            run.strategy_id,
            run.user_id,
            run.trace_id,
            run.execution_run_id,
            run.status,
            run.started_at,
            run.ended_at,
            run.error_message,
            run.benchmark_ticker,
            run.config_jsonb,
            run.created_at,
            report.report_id AS linked_report_id
        FROM app.backtest_run AS run
        LEFT JOIN app.strategy_email_report AS report
          ON report.backtest_run_id = run.run_id
        WHERE {' AND '.join(filters)}
        ORDER BY report.sent_at DESC NULLS LAST, report.created_at DESC NULLS LAST
        LIMIT 1
        """,
        params,
    )
    if row is None:
        return None

    error = None
    if _optional_text(row.get("error_message")):
        error = {
            "code": "run_failed",
            "message": _text(row.get("error_message")),
            "details": {"runId": _text(row.get("run_id"))},
        }

    config = _json_object(row.get("config_jsonb"))
    request_payload = _json_object(_first_non_empty(config.get("requestPayload"), config.get("request_payload")))
    strategy_id = _optional_text(
        _first_non_empty(
            row.get("strategy_id"),
            config.get("strategyId"),
            config.get("strategy_id"),
            request_payload.get("strategyId"),
            request_payload.get("strategy_id"),
        )
    )
    instrument_id = _optional_text(
        _first_non_empty(
            config.get("instrumentId"),
            config.get("instrument_id"),
            request_payload.get("instrumentId"),
            request_payload.get("instrument_id"),
        )
    )
    ticker = _optional_text(_first_non_empty(config.get("ticker"), request_payload.get("ticker")))
    ai_job_id = _optional_text(
        _first_non_empty(
            row.get("trace_id"),
            row.get("execution_run_id"),
            config.get("aiJobId"),
            config.get("ai_job_id"),
            config.get("traceId"),
            config.get("trace_id"),
            request_payload.get("aiJobId"),
            request_payload.get("ai_job_id"),
            request_payload.get("traceId"),
            request_payload.get("trace_id"),
        )
    )
    return {
        "id": _text(row.get("run_id")),
        "status": _text(_first_non_empty(row.get("status"), "unknown")),
        "reportId": _optional_text(row.get("linked_report_id")),
        "error": error,
        "createdAt": _as_iso(row.get("created_at")),
        "updatedAt": _as_iso(_first_non_empty(row.get("ended_at"), row.get("started_at"), row.get("created_at"))),
        "strategyId": strategy_id,
        "instrumentId": instrument_id,
        "ticker": ticker,
        "aiJobId": ai_job_id,
    }
