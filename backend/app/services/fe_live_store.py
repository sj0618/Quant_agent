from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import fetch_all, fetch_one


def _iso(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value or "")


def _date_label(value: Any) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%Y.%m.%d")
    return str(value or "")


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _json(value: Any, default: Any) -> Any:
    return value if value is not None else default


def _summary(row: dict[str, Any]) -> dict[str, Any]:
    signals = _json(row.get("signals"), {})
    if not isinstance(signals, dict):
        signals = {}
    return {
        "id": str(row["id"]),
        "strategyId": str(row.get("strategy_id") or row["id"]),
        "date": _date_label(row.get("latest_report_date")),
        "weekday": _iso(row.get("latest_report_date")),
        "sentAt": _iso(row.get("latest_sent_at")),
        "title": row.get("title") or row.get("name") or "전략 리포트",
        "summary": row.get("summary") or "",
        "status": row.get("latest_status") or "draft",
        "strategyName": row.get("name") or "",
        "recommendationScore": f"{_number(row.get('recommendation_score')):.1f}",
        "signals": {
            "BUY": int(signals.get("BUY", 0)),
            "HOLD": int(signals.get("HOLD", 0)),
            "DROP": int(signals.get("DROP", 0)),
        },
        "marketSnapshot": _json(row.get("market_snapshot"), []),
    }


def _candidate(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("ticker") or ""),
        "ticker": str(row.get("ticker") or ""),
        "name": row.get("name") or "",
        "sector": row.get("sector") or "",
        "signal": row.get("signal") or "HOLD",
        "confidence": _number(row.get("confidence")),
        "score": _number(row.get("score")),
        "price": str(row.get("price") or ""),
        "changePercent": str(row.get("change_percent") or ""),
        "rationale": row.get("rationale") or "",
        "evidence": _json(row.get("evidence_jsonb"), []),
        "riskReasons": _json(row.get("risk_reasons_jsonb"), []),
        "risk_manager_override": row.get("risk_manager_override"),
        "web_projection": row.get("web_projection"),
    }


async def report_summaries(engine: AsyncEngine) -> list[dict[str, Any]]:
    rows = await fetch_all(
        engine,
        """
        SELECT v.*, r.title, r.market_snapshot
        FROM app.strategy_report_summary_v v
        LEFT JOIN app.strategy_email_report r ON r.report_id = v.latest_email_report_id
        ORDER BY v.latest_report_date DESC NULLS LAST, v.latest_sent_at DESC NULLS LAST
        """,
    )
    return [_summary(row) for row in rows]


async def report_detail(engine: AsyncEngine, report_id: str) -> dict[str, Any] | None:
    row = await fetch_one(
        engine,
        """
        SELECT r.*, p.name AS strategy_name, p.universe, p.timeframe
        FROM app.strategy_email_report r
        LEFT JOIN app.strategy_report_profile p ON p.strategy_id = r.strategy_id
        WHERE r.report_id = :report_id
        """,
        {"report_id": report_id},
    )
    if row is None:
        return None

    news = await fetch_all(
        engine,
        """
        SELECT rank, title, source, tone
        FROM app.strategy_email_report_news
        WHERE report_id = :report_id
        ORDER BY rank
        """,
        {"report_id": report_id},
    )
    candidates = await fetch_all(
        engine,
        """
        SELECT ticker, name, sector, signal, confidence, score, price, change_percent,
               rationale, evidence_jsonb, risk_reasons_jsonb, risk_manager_override, web_projection
        FROM app.strategy_email_report_candidate
        WHERE report_id = :report_id
        ORDER BY sort_order, ticker
        """,
        {"report_id": report_id},
    )
    summary = _summary({**row, "id": row["report_id"], "latest_report_date": row["report_date"], "latest_sent_at": row["sent_at"], "latest_status": row["status"], "recommendation_score": row["recommendation_score"], "signals": {"BUY": row.get("buy_count", 0), "HOLD": row.get("hold_count", 0), "DROP": row.get("drop_count", 0)}})
    performance = _json(row.get("performance_jsonb"), {})
    if not isinstance(performance, dict):
        performance = {}
    return {
        **summary,
        "recipient": row.get("recipient") or "",
        "strategyUniverse": row.get("universe"),
        "marketBrief": row.get("market_brief") or "",
        "marketContext": row.get("market_context"),
        "news": [
            {"rank": item["rank"], "title": item["title"], "source": item.get("source") or "", "tone": item.get("tone") or "neutral"}
            for item in news
        ],
        "candidates": [_candidate(item) for item in candidates],
        "signalAxes": _json(row.get("signal_axes_jsonb"), []),
        "riskManagerOverride": row.get("risk_manager_override") or "",
        "conclusion": row.get("conclusion") or row.get("summary") or "",
        "warningNote": row.get("warning_note"),
        "performance": {"metrics": performance.get("metrics", []), "disclaimer": performance.get("disclaimer", "")},
        "costNotes": _json(row.get("cost_notes"), []),
    }


async def trading_candidates(engine: AsyncEngine) -> list[dict[str, Any]]:
    row = await fetch_one(
        engine,
        """
        SELECT report_id
        FROM app.strategy_email_report
        ORDER BY report_date DESC, sent_at DESC NULLS LAST
        LIMIT 1
        """,
    )
    if row is None:
        return []
    candidates = await fetch_all(
        engine,
        """
        SELECT ticker, name, sector, signal, confidence, score, price, change_percent,
               rationale, evidence_jsonb, risk_reasons_jsonb, risk_manager_override, web_projection
        FROM app.strategy_email_report_candidate
        WHERE report_id = :report_id
        ORDER BY sort_order, ticker
        """,
        {"report_id": row["report_id"]},
    )
    return [_candidate(item) for item in candidates]


async def performance_summary(engine: AsyncEngine) -> dict[str, Any]:
    row = await fetch_one(
        engine,
        """
        SELECT s.*, r.backtest_start_date, r.backtest_end_date, r.created_at, r.run_id
        FROM app.backtest_summary s
        JOIN app.backtest_run r ON r.run_id = s.run_id
        WHERE r.status = 'completed'
        ORDER BY r.created_at DESC
        LIMIT 1
        """,
    )
    if row is None:
        return _empty_performance()

    metrics = [
        {"key": "sharpe", "label": "Sharpe Ratio", "value": f"{_number(row.get('sharpe_ratio')):.2f}", "tone": "positive", "caption": "실제 백테스트 결과"},
        {"key": "mdd", "label": "Max Drawdown", "value": f"{_number(row.get('max_drawdown')) * 100:.2f}%", "tone": "negative", "caption": "실제 백테스트 결과"},
        {"key": "winRate", "label": "Win Rate", "value": f"{_number(row.get('win_rate')) * 100:.2f}%", "tone": "neutral", "caption": "실제 백테스트 결과"},
        {"key": "totalReturn", "label": "Total Return", "value": f"{_number(row.get('period_return')) * 100:.2f}%", "tone": "neutral", "caption": "실제 백테스트 결과"},
    ]
    points = await fetch_all(
        engine,
        """
        SELECT trade_date, total_equity
        FROM app.backtest_equity_point
        WHERE run_id = :run_id
        ORDER BY trade_date
        """,
        {"run_id": row["run_id"]},
    )
    initial = _number(points[0].get("total_equity"), 1) if points else 1
    equity = [
        {"date": _iso(point.get("trade_date")), "strategy": (_number(point.get("total_equity")) / initial - 1) * 100, "original": 0, "benchmark": 0}
        for point in points
    ]
    return {
        "headline": "실제 백테스트 결과",
        "period": f"{_date_label(row.get('backtest_start_date'))} ~ {_date_label(row.get('backtest_end_date'))}",
        "benchmarkLabel": "실제 데이터 기준",
        "metrics": metrics,
        "equityCurve": equity,
        "comparison": [],
        "macroEvents": [],
        "disclaimer": "공용 DB에 저장된 백테스트 결과입니다.",
    }


def _empty_performance() -> dict[str, Any]:
    return {"headline": "백테스트 결과 없음", "period": "", "metrics": [], "equityCurve": [], "comparison": [], "macroEvents": [], "disclaimer": "완료된 백테스트가 없습니다."}


async def app_overview(engine: AsyncEngine) -> dict[str, Any]:
    reports = await report_summaries(engine)
    latest_id = await fetch_one(
        engine,
        """
        SELECT report_id
        FROM app.strategy_email_report
        ORDER BY report_date DESC, sent_at DESC NULLS LAST
        LIMIT 1
        """,
    )
    latest = await report_detail(engine, latest_id["report_id"]) if latest_id else None
    candidates = await trading_candidates(engine)
    performance = await performance_summary(engine)
    strategy = {
        "name": latest.get("strategyName", "") if latest else "",
        "natural_language_strategy": latest.get("summary", "") if latest else "",
        "universe": latest.get("strategyUniverse", "") if latest else "",
        "sector": "",
        "buy_condition": "",
        "hold_condition": "",
        "drop_condition": "",
        "rebalance": "",
        "constraints": [],
    }
    signals = latest.get("signals", {}) if latest else {}
    return {
        "strategy": strategy,
        "recommendationScore": latest.get("recommendationScore", "") if latest else "",
        "recommendationDelta": "",
        "passCount": sum(signals.values()),
        "buyCount": signals.get("BUY", 0),
        "holdCount": signals.get("HOLD", 0),
        "dropCount": signals.get("DROP", 0),
        "nextRunLabel": "실제 데이터 기준",
        "latestRunLabel": latest.get("date", "") if latest else "실행 기록 없음",
        "chatMessages": [],
        "candidates": candidates,
        "performance": performance,
        "recentReports": reports[:4],
        "envelope": None,
        "jobStatus": {"trace_id": "", "status": "failed", "stages": []},
    }


async def workspace_template(engine: AsyncEngine) -> dict[str, Any]:
    overview = await app_overview(engine)
    overview["chatMessages"] = []
    overview["recentReports"] = []
    return overview
