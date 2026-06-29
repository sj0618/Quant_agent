from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Request

from app.core.errors import AppError

CONTRACT_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "fe_mock_contract.json"
RECENT_REPORT_LIMIT = 4
DEFAULT_NOTIFICATION_DELIVERY_HOUR = "08:00"
DEFAULT_NOTIFICATION_EMAIL = "user@example.co.kr"


@lru_cache(maxsize=1)
def load_contract_data() -> dict[str, Any]:
    return json.loads(CONTRACT_DATA_PATH.read_text(encoding="utf-8"))


def contract_value(key: str) -> Any:
    return copy.deepcopy(load_contract_data()[key])


def landing_sample() -> dict[str, Any]:
    return contract_value("landingSample")


def trading_candidates() -> list[dict[str, Any]]:
    return contract_value("tradingCandidates")


def performance_summary() -> dict[str, Any]:
    return contract_value("performanceSummary")


def report_summaries() -> list[dict[str, Any]]:
    return contract_value("reportSummaries")


def report_details() -> list[dict[str, Any]]:
    return contract_value("reportDetails")


def app_overview() -> dict[str, Any]:
    overview = contract_value("appOverview")
    overview["recentReports"] = report_summaries()[:RECENT_REPORT_LIMIT]
    return overview


def workspace_template() -> dict[str, Any]:
    overview = app_overview()
    overview["chatMessages"] = []
    overview["recentReports"] = []
    return overview


def report_detail_or_none(report_id: str) -> dict[str, Any] | None:
    for detail in report_details():
        if detail.get("id") == report_id:
            return detail

    summary = next((item for item in report_summaries() if item.get("id") == report_id), None)
    details = report_details()
    if summary is None or not details:
        return None

    merged = copy.deepcopy(details[0])
    merged.update(copy.deepcopy(summary))
    return merged


def notification_store(request: Request) -> dict[str, dict[str, Any]]:
    store = getattr(request.app.state, "notification_settings", None)
    if store is None:
        store = {}
        request.app.state.notification_settings = store
    return store


def default_notification_settings(email: str | None) -> dict[str, Any]:
    return {
        "dailyReportEmail": True,
        "actionEmails": True,
        "marketingEmail": False,
        "deliveryHour": DEFAULT_NOTIFICATION_DELIVERY_HOUR,
        "email": email or DEFAULT_NOTIFICATION_EMAIL,
    }


def get_notification_settings(request: Request, email: str | None) -> dict[str, Any]:
    normalized_email = (email or DEFAULT_NOTIFICATION_EMAIL).strip().lower()
    return copy.deepcopy(notification_store(request).get(normalized_email) or default_notification_settings(email))


def save_notification_settings(request: Request, settings: dict[str, Any]) -> dict[str, Any]:
    email = str(settings.get("email") or DEFAULT_NOTIFICATION_EMAIL).strip().lower()
    value = {**default_notification_settings(email), **copy.deepcopy(settings), "email": settings.get("email") or email}
    notification_store(request)[email] = value
    return copy.deepcopy(value)


def strategy_store(request: Request) -> dict[str, dict[str, Any]]:
    store = getattr(request.app.state, "strategies", None)
    if store is None:
        store = {}
        request.app.state.strategies = store
    return store


def create_strategy(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    strategy_id = f"strategy-{uuid4().hex[:12]}"
    base = contract_value("activeStrategySpec")
    if "natural_language_strategy" in payload or "natural_language" in payload or "query" in payload:
        base["natural_language_strategy"] = payload.get("natural_language_strategy") or payload.get("natural_language") or payload.get("query")
    base.update({key: value for key, value in payload.items() if value is not None})
    record = {
        "id": strategy_id,
        "strategy_id": strategy_id,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        **base,
    }
    strategy_store(request)[strategy_id] = record
    return copy.deepcopy(record)


def update_strategy(request: Request, strategy_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    store = strategy_store(request)
    current = store.get(strategy_id)
    if current is None:
        current = create_strategy(request, {})
        current["id"] = strategy_id
        current["strategy_id"] = strategy_id
    current.update({key: value for key, value in payload.items() if value is not None})
    current["updated_at"] = _now_iso()
    store[strategy_id] = current
    return copy.deepcopy(current)


def analysis_job_store(request: Request) -> dict[str, dict[str, Any]]:
    store = getattr(request.app.state, "analysis_jobs", None)
    if store is None:
        store = {}
        request.app.state.analysis_jobs = store
    return store


def create_analysis_job(request: Request, query: str, *, strategy_id: str | None = None) -> dict[str, Any]:
    job_id = f"job-{uuid4().hex[:12]}"
    job = build_analysis_job(job_id=job_id, query=query, strategy_id=strategy_id)
    analysis_job_store(request)[job_id] = job
    request.app.state.latest_analysis_job_id = job_id
    return copy.deepcopy(job)


def get_analysis_job(request: Request, job_id: str) -> dict[str, Any] | None:
    job = analysis_job_store(request).get(job_id)
    return copy.deepcopy(job) if job else None


def latest_analysis_job(request: Request) -> dict[str, Any] | None:
    latest_id = getattr(request.app.state, "latest_analysis_job_id", None)
    return get_analysis_job(request, latest_id) if latest_id else None


def latest_analysis_job_status(request: Request) -> dict[str, Any]:
    latest = latest_analysis_job(request)
    if not latest:
        return contract_value("analysisJobStatus")
    result = latest.get("result") or {}
    workspace_stages = [
        ("strategy_parse", "전략 해석", "done"),
        ("data_collect", "데이터 수집", "done"),
        ("signal_judge", "신호 판정", "done"),
        ("backtest", "백테스트", "done"),
        ("risk_review", "리스크 검토", "done"),
        ("report_ready", "리포트 준비 완료", "done"),
    ]
    return {
        "trace_id": latest["trace_id"],
        "status": result.get("status", "running"),
        "stages": [
            {"stage": stage, "status": status, "label": label, "updated_at": latest["updated_at"]}
            for stage, label, status in workspace_stages
        ],
    }


def build_analysis_job(*, job_id: str, query: str, strategy_id: str | None = None) -> dict[str, Any]:
    now = _now_iso()
    trace_id = f"qa-trace-{job_id}"
    strategy = _ai_strategy_spec(query=query, strategy_id=strategy_id or f"strategy-{job_id}")
    report = _ai_report_bundle()
    return {
        "job_id": job_id,
        "trace_id": trace_id,
        "query": query,
        "created_at": now,
        "updated_at": now,
        "stages": [
            {"stage": "interpreting", "status": "succeeded", "updated_at": now, "message": "전략 문장을 해석했습니다."},
            {"stage": "code_generation", "status": "succeeded", "updated_at": now, "message": "검증 후보를 구성했습니다."},
            {"stage": "backtest", "status": "succeeded", "updated_at": now, "message": "성과 요약을 생성했습니다."},
            {"stage": "debate", "status": "succeeded", "updated_at": now, "message": "리스크 검토를 완료했습니다."},
            {"stage": "finalizing", "status": "succeeded", "updated_at": now, "message": "리포트 초안을 준비했습니다."},
        ],
        "result": {
            "status": "ready",
            "trace_id": trace_id,
            "schema_version": "qa.ai_envelope.v1",
            "user_payload": {
                "headline": f"{strategy['name']} 분석 완료",
                "message": f"'{query}' 조건을 FE 계약용 API 응답으로 분석했습니다.",
                "next_actions": ["워크스페이스에서 후보 종목과 리포트를 확인하세요.", "조건을 수정해 새 분석을 실행할 수 있습니다."],
                "candidate_cards": [],
                "report": report,
                "performance": None,
                "question": None,
                "options": [],
                "recommended": None,
            },
            "strategy_spec": strategy,
            "debug_ref": f"backend_fe_contract:{job_id}",
            "retryable": True,
        },
    }


def _ai_strategy_spec(*, query: str, strategy_id: str) -> dict[str, Any]:
    active = contract_value("activeStrategySpec")
    constraints = active.get("constraints") or []
    return {
        "strategy_id": strategy_id,
        "name": active.get("name") or "QuantAgent 전략",
        "universe": active.get("universe") or "KOSPI200",
        "market": "KR",
        "timeframe": "daily",
        "entry_conditions": [
            {
                "left": "RSI",
                "operator": "lte",
                "right": 30,
                "description": active.get("buy_condition") or query,
            }
        ],
        "exit_conditions": [
            {
                "left": "RSI",
                "operator": "gte",
                "right": 70,
                "description": active.get("drop_condition") or "청산 조건",
            }
        ],
        "indicators": ["RSI", "Volume", active.get("sector") or "sector"],
        "risk_constraints": {"max_holding_days": 30, "fee_model_included": True},
        "assumptions": constraints if isinstance(constraints, list) else [str(constraints)],
        "source_refs": ["backend/app/data/fe_mock_contract.json"],
        "confidence": _recommendation_confidence(),
    }


def _ai_report_bundle() -> dict[str, Any]:
    summaries = report_summaries()
    summary = summaries[0] if summaries else {}
    candidates = trading_candidates()
    primary = next((item for item in candidates if item.get("signal") == "BUY"), candidates[0] if candidates else {})
    sections = [
        {"id": "summary", "title": summary.get("title", "QuantAgent 리포트"), "items": summary.get("marketSnapshot", [])},
        {
            "id": "signal",
            "title": "대표 신호",
            "items": {
                "action": primary.get("signal", "BUY"),
                "ticker": primary.get("ticker"),
                "name": primary.get("name"),
            },
        },
    ]
    projection = {
        "title": summary.get("title", "QuantAgent 분석 리포트"),
        "summary": summary.get("summary", "FE 계약용 백엔드 리포트입니다."),
        "sections": sections,
    }
    return {
        "web_projection": projection,
        "email_projection": projection,
        "risk_adjustments": [],
    }


def _recommendation_confidence() -> float:
    raw = str(app_overview().get("recommendationScore") or "7.6")
    try:
        return max(0.0, min(1.0, float(raw.split("/", maxsplit=1)[0].strip()) / 10))
    except ValueError:
        return 0.76


def require_analysis_job(job: dict[str, Any] | None) -> dict[str, Any]:
    if job is None:
        raise AppError(status_code=404, component="analysis_jobs", code="analysis_job_not_found", message="Analysis job was not found")
    return job


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
