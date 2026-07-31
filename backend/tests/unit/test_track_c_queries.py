from __future__ import annotations

import pytest

from app.db import existing_report_queries


class FakeEngine:
    pass


@pytest.mark.asyncio
async def test_track_c_list_reports_clamps_limit_and_scopes_to_owner(monkeypatch):
    recorded: dict[str, object] = {}

    async def fake_fetch_all(engine, sql, params=None):
        recorded["engine"] = engine
        recorded["sql"] = sql
        recorded["params"] = params or {}
        return [
            {
                "report_id": "report-1",
                "backtest_run_id": "run-1",
                "strategy_id": "strategy-1",
                "strategy_name": "Track C Strategy",
                "title": "Track C report",
                "summary": "Summary",
                "status": "sent",
                "report_date": "2026-07-20",
                "weekday": "Monday",
                "sent_at": "2026-07-20T10:10:00Z",
                "created_at": "2026-07-20T10:00:00Z",
                "updated_at": "2026-07-20T10:05:00Z",
                "sort_at": "2026-07-20T10:10:00Z",
                "run_config_jsonb": {"strategyName": "Track C Strategy", "instrumentName": "Track C Instrument", "ticker": "005930"},
                "run_strategy_id": "strategy-1",
                "buy_count": 2,
                "hold_count": 1,
                "drop_count": 1,
                "recommendation_score": 7.4,
                "market_snapshot": [{"label": "KOSPI", "value": "2,654.21 (+0.84%)", "tone": "positive"}],
            }
        ]

    monkeypatch.setattr(existing_report_queries, "fetch_all", fake_fetch_all)

    result = await existing_report_queries.list_reports(
        FakeEngine(),
        user_id=" 42 ",
        limit=500,
        status="sent",
    )

    assert recorded["engine"] is not None
    assert "FROM app.strategy_email_report AS report" in str(recorded["sql"])
    assert "app.ai_backtest_report" not in str(recorded["sql"])
    assert "UNION ALL" not in str(recorded["sql"])
    assert recorded["params"]["user_id"] == "42"
    assert recorded["params"]["limit_plus_one"] == 101
    assert recorded["params"]["status"] == "sent"
    assert result["meta"]["limit"] == 100
    assert result["meta"]["hasMore"] is False
    assert result["items"][0]["id"] == "report-1"
    assert result["items"][0]["date"] == "2026.07.20"
    assert result["items"][0]["weekday"] == "월요일"
    assert result["items"][0]["sentAt"] == "오전 10:10 발송"
    assert result["items"][0]["strategyName"] == "Track C Strategy"
    assert result["items"][0]["recommendationScore"] == "7.4"
    assert result["items"][0]["signals"] == {"BUY": 2, "HOLD": 1, "DROP": 1}
    assert result["items"][0]["marketSnapshot"][0] == {
        "label": "KOSPI",
        "value": "2,654.21 (+0.84%)",
        "tone": "positive",
    }


@pytest.mark.asyncio
async def test_track_c_list_reports_applies_report_strategy_candidate_search(monkeypatch):
    recorded: dict[str, object] = {}

    async def fake_fetch_all(engine, sql, params=None):
        recorded["engine"] = engine
        recorded["sql"] = sql
        recorded["params"] = params or {}
        return [
            {
                "report_id": "report-1",
                "backtest_run_id": "run-1",
                "strategy_id": "strategy-1",
                "strategy_name": "Track C Strategy",
                "title": "Track C report",
                "summary": "Summary",
                "status": "sent",
                "report_date": "2026-07-20",
                "weekday": "Monday",
                "sent_at": "2026-07-20T10:10:00Z",
                "created_at": "2026-07-20T10:00:00Z",
                "updated_at": "2026-07-20T10:05:00Z",
                "sort_at": "2026-07-20T10:10:00Z",
                "run_config_jsonb": {"strategyName": "Track C Strategy", "instrumentName": "Track C Instrument", "ticker": "005930"},
                "run_strategy_id": "strategy-1",
                "buy_count": 2,
                "hold_count": 1,
                "drop_count": 1,
                "recommendation_score": 7.4,
                "market_snapshot": [],
            }
        ]

    monkeypatch.setattr(existing_report_queries, "fetch_all", fake_fetch_all)

    result = await existing_report_queries.list_reports(FakeEngine(), user_id="42", q="삼성전자")

    assert recorded["engine"] is not None
    assert recorded["params"]["user_id"] == "42"
    assert recorded["params"]["q"] == "%삼성전자%"
    assert "COALESCE(report.title, '') ILIKE :q" in str(recorded["sql"])
    assert "COALESCE(profile.name, '') ILIKE :q" in str(recorded["sql"])
    assert "EXISTS (SELECT 1 FROM app.strategy_email_report_candidate AS candidate" in str(recorded["sql"])
    assert "candidate.ticker ILIKE :q" in str(recorded["sql"])
    assert "candidate.web_projection" in str(recorded["sql"])
    assert result["items"][0]["id"] == "report-1"


@pytest.mark.asyncio
async def test_track_c_list_reports_paginates_with_cursor(monkeypatch):
    recorded: dict[str, object] = {}

    async def fake_fetch_all(engine, sql, params=None):
        recorded["params"] = params or {}
        return [
            {
                "report_id": "report-2",
                "backtest_run_id": "run-2",
                "title": "Report 2",
                "summary": "Summary 2",
                "status": "sent",
                "report_date": "2026-07-20",
                "weekday": "Monday",
                "created_at": "2026-07-20T10:00:00Z",
                "updated_at": "2026-07-20T10:05:00Z",
                "sent_at": "2026-07-20T10:10:00Z",
                "sort_at": "2026-07-20T10:10:00Z",
                "run_config_jsonb": {},
                "run_strategy_id": "strategy-2",
                "buy_count": 1,
                "hold_count": 0,
                "drop_count": 1,
                "recommendation_score": 6.8,
                "market_snapshot": [],
            },
            {
                "report_id": "report-1",
                "backtest_run_id": "run-1",
                "title": "Report 1",
                "summary": "Summary 1",
                "status": "sent",
                "report_date": "2026-07-19",
                "weekday": "Sunday",
                "created_at": "2026-07-19T09:00:00Z",
                "updated_at": "2026-07-19T09:05:00Z",
                "sent_at": "2026-07-19T09:10:00Z",
                "sort_at": "2026-07-19T09:10:00Z",
                "run_config_jsonb": {},
                "run_strategy_id": "strategy-1",
                "buy_count": 0,
                "hold_count": 2,
                "drop_count": 1,
                "recommendation_score": 5.9,
                "market_snapshot": [],
            },
        ]

    monkeypatch.setattr(existing_report_queries, "fetch_all", fake_fetch_all)

    cursor = existing_report_queries._cursor_payload("2026-07-20T11:00:00Z", "report-9")
    result = await existing_report_queries.list_reports(FakeEngine(), user_id="42", limit=1, cursor=cursor)

    assert recorded["params"]["cursor_sort_at"] == "2026-07-20T11:00:00Z"
    assert recorded["params"]["cursor_id"] == "report-9"
    assert result["meta"]["hasMore"] is True
    assert result["meta"]["nextCursor"] is not None
    assert existing_report_queries._decode_cursor(result["meta"]["nextCursor"]) == ("2026-07-20T10:10:00Z", "report-2")
    assert [item["id"] for item in result["items"]] == ["report-2"]


@pytest.mark.asyncio
async def test_track_c_get_report_parses_persisted_projection_and_scopes_to_owner(monkeypatch):
    recorded: dict[str, object] = {}

    async def fake_fetch_one(engine, sql, params=None):
        recorded["engine"] = engine
        recorded["sql"] = sql
        recorded["params"] = params or {}
        return {
            "report_id": "report-1",
            "strategy_id": "strategy-1",
            "backtest_run_id": "run-1",
            "strategy_name": "Track C Strategy",
            "report_date": "2026-07-20",
            "weekday": "Monday",
            "sent_at": "2026-07-20T10:10:00Z",
            "title": "Track C report",
            "summary": "Track C summary",
            "status": "sent",
            "created_at": "2026-07-20T10:00:00Z",
            "updated_at": "2026-07-20T10:05:00Z",
            "recommendation_score": 7.4,
            "buy_count": 2,
            "hold_count": 1,
            "drop_count": 1,
            "market_snapshot": [{"label": "KOSPI", "value": "2,654.21 (+0.84%)", "tone": "positive"}],
            "recipient": None,
            "market_brief": "Track C market brief",
            "market_context": None,
            "risk_manager_override": "Risk manager override",
            "conclusion": "Track C conclusion",
            "warning_note": None,
            "signal_axes_jsonb": [
                {"label": "축 1", "weight": "0.35", "title": "호재 (Bull)", "description": "기술적 패턴 · 모멘텀 · 거래량"}
            ],
            "performance_jsonb": {},
            "cost_notes": ["거래비용 반영: 수수료 0.015%, 거래세 0.23%, 슬리피지 0.1%."],
            "run_id": "run-1",
            "run_strategy_id": "strategy-1",
            "run_config_jsonb": {"strategyName": "Track C Strategy", "ticker": "005930"},
            "summary_period_return": 0.12,
            "summary_cagr": 0.14,
            "summary_benchmark_return": 0.08,
            "summary_max_drawdown": -0.05,
            "summary_sharpe_ratio": 1.23,
            "summary_win_rate": 0.67,
            "summary_trade_count": 12,
            "summary_metrics_version": "v1",
        }

    async def fake_fetch_all(engine, sql, params=None):
        recorded.setdefault("all_calls", []).append(sql)
        if "strategy_email_report_news" in sql:
            return [
                {
                    "rank": 1,
                    "title": "반도체 업황 회복",
                    "source": "Reuters",
                    "tone": "positive",
                    "url": "https://example.com/news-1",
                    "published_at": "2026-07-20T09:00:00Z",
                    "summary": "업황 회복과 수요 확대",
                }
            ]
        if "strategy_email_report_candidate" in sql:
            return [
                {
                    "ticker": "005930",
                    "name": "삼성전자",
                    "sector": "반도체",
                    "signal": "BUY",
                    "confidence": 0.82,
                    "score": 0.82,
                    "price": "76,000원",
                    "change_percent": "+1.2%",
                    "rationale": "수요 회복과 수급 개선",
                    "evidence_jsonb": [{"provider": "DART", "title": "실적 발표", "date": "2026-07-20", "summary": "실적 호조"}],
                    "risk_reasons_jsonb": ["실적 변동성"],
                    "risk_manager_override": "보류 없음",
                    "web_projection": "중립",
                    "sort_order": 1,
                }
            ]
        raise AssertionError(f"Unexpected SQL: {sql}")

    monkeypatch.setattr(existing_report_queries, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(existing_report_queries, "fetch_all", fake_fetch_all)

    result = await existing_report_queries.get_report(FakeEngine(), "report-1", user_id=" 42 ")

    assert recorded["params"]["user_id"] == "42"
    assert "FROM app.strategy_email_report AS report" in str(recorded["sql"])
    assert "app.ai_backtest_report" not in str(recorded["sql"])
    assert "content" not in result
    assert result["id"] == "report-1"
    assert result["runId"] == "run-1"
    assert result["date"] == "2026.07.20"
    assert result["weekday"] == "월요일"
    assert result["sentAt"] == "오전 10:10 발송"
    assert result["recipient"] is None
    assert result["marketBrief"] == "Track C market brief"
    assert result["news"][0]["title"] == "반도체 업황 회복"
    assert result["candidates"][0]["ticker"] == "005930"
    assert result["signalAxes"][0]["label"] == "축 1"
    assert result["riskManagerOverride"] == "Risk manager override"
    assert result["conclusion"] == "Track C conclusion"
    assert result["warningNote"] is None
    assert result["costNotes"] == ["거래비용 반영: 수수료 0.015%, 거래세 0.23%, 슬리피지 0.1%."]
    assert {metric["key"] for metric in result["performance"]["metrics"]} == {"sharpe", "mdd", "winRate", "totalReturn"}
    assert result["performance"]["disclaimer"] == ""


@pytest.mark.asyncio
async def test_track_c_get_report_returns_none_without_ai_fallback(monkeypatch):
    calls: list[str] = []

    async def fake_fetch_one(engine, sql, params=None):
        calls.append(sql)
        return None

    async def fake_fetch_all(*_args, **_kwargs):
        raise AssertionError("fetch_all must not be called when the persisted report row is missing")

    monkeypatch.setattr(existing_report_queries, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(existing_report_queries, "fetch_all", fake_fetch_all)

    result = await existing_report_queries.get_report(FakeEngine(), "report-ai-only", user_id="42")

    assert len(calls) == 1
    assert "FROM app.strategy_email_report AS report" in calls[0]
    assert "app.ai_backtest_report" not in calls[0]
    assert result is None


@pytest.mark.asyncio
async def test_track_c_get_analysis_run_parses_config_and_links_report(monkeypatch):
    recorded: dict[str, object] = {}

    async def fake_fetch_one(engine, sql, params=None):
        recorded["engine"] = engine
        recorded["sql"] = sql
        recorded["params"] = params or {}
        return {
            "run_id": "run-1",
            "strategy_id": "strategy-1",
            "user_id": 42,
            "trace_id": "trace-1",
            "execution_run_id": "job-1",
            "status": "completed",
            "started_at": "2026-07-20T10:00:00Z",
            "ended_at": "2026-07-20T10:10:00Z",
            "error_message": None,
            "benchmark_ticker": "005930",
            "config_jsonb": {"strategyId": "strategy-1", "instrumentId": "instrument-1", "ticker": "005930", "aiJobId": "job-1"},
            "created_at": "2026-07-20T09:55:00Z",
            "linked_report_id": "report-1",
        }

    monkeypatch.setattr(existing_report_queries, "fetch_one", fake_fetch_one)

    result = await existing_report_queries.get_analysis_run(FakeEngine(), "run-1", user_id="42")

    assert recorded["params"]["user_id"] == "42"
    assert "FROM app.backtest_run AS run" in str(recorded["sql"])
    assert result["id"] == "run-1"
    assert result["status"] == "completed"
    assert result["reportId"] == "report-1"
    assert result["strategyId"] == "strategy-1"
    assert result["instrumentId"] == "instrument-1"
    assert result["ticker"] == "005930"
    assert result["aiJobId"] == "trace-1"


@pytest.mark.asyncio
async def test_track_c_list_reports_omits_raw_prompt_strategy_name(monkeypatch):
    raw_strategy_name = "Run a new live analysis for Samsung Electronics (005930) using live data."

    async def fake_fetch_all(engine, sql, params=None):
        return [
            {
                "report_id": "report-raw-strategy",
                "backtest_run_id": "run-raw-strategy",
                "strategy_id": "strategy-raw",
                "strategy_name": raw_strategy_name,
                "title": "Track C report",
                "summary": "Summary",
                "status": "sent",
                "report_date": "2026-07-20",
                "weekday": "Monday",
                "sent_at": "2026-07-20T10:10:00Z",
                "created_at": "2026-07-20T10:00:00Z",
                "updated_at": "2026-07-20T10:05:00Z",
                "sort_at": "2026-07-20T10:10:00Z",
                "run_config_jsonb": {"query": raw_strategy_name},
                "run_strategy_id": "strategy-raw",
                "buy_count": 2,
                "hold_count": 1,
                "drop_count": 1,
                "recommendation_score": 7.4,
                "market_snapshot": [{"label": "KOSPI", "value": "2,654.21 (+0.84%)", "tone": "positive"}],
            }
        ]

    monkeypatch.setattr(existing_report_queries, "fetch_all", fake_fetch_all)

    result = await existing_report_queries.list_reports(FakeEngine(), user_id="42")

    assert result["items"][0]["id"] == "report-raw-strategy"
    assert result["items"][0]["strategyName"] is None
    assert result["items"][0]["title"] == "Track C report"


@pytest.mark.asyncio
async def test_track_c_get_report_omits_raw_prompt_strategy_name(monkeypatch):
    raw_strategy_name = "Run a new live analysis for Samsung Electronics (005930) using live data."
    observed: dict[str, object] = {}

    async def fake_fetch_one(engine, sql, params=None):
        observed["sql"] = sql
        return {
            "report_id": "report-raw-strategy",
            "strategy_id": "strategy-raw",
            "backtest_run_id": "run-raw-strategy",
            "strategy_name": raw_strategy_name,
            "report_date": "2026-07-20",
            "weekday": "Monday",
            "sent_at": "2026-07-20T10:10:00Z",
            "title": "Track C report",
            "summary": "Track C summary",
            "status": "sent",
            "created_at": "2026-07-20T10:00:00Z",
            "updated_at": "2026-07-20T10:05:00Z",
            "recommendation_score": 7.4,
            "buy_count": 2,
            "hold_count": 1,
            "drop_count": 1,
            "market_snapshot": [{"label": "KOSPI", "value": "2,654.21 (+0.84%)", "tone": "positive"}],
            "recipient": None,
            "market_brief": "Track C market brief",
            "market_context": None,
            "risk_manager_override": "Risk manager override",
            "conclusion": "Track C conclusion",
            "warning_note": None,
            "signal_axes_jsonb": [],
            "performance_jsonb": {},
            "cost_notes": [],
            "run_id": "run-raw-strategy",
            "run_strategy_id": "strategy-raw",
            "run_config_jsonb": {"query": raw_strategy_name},
            "summary_period_return": None,
            "summary_cagr": None,
            "summary_benchmark_return": None,
            "summary_max_drawdown": None,
            "summary_sharpe_ratio": None,
            "summary_win_rate": None,
            "summary_trade_count": None,
            "summary_metrics_version": None,
        }

    async def fake_fetch_all(engine, sql, params=None):
        if "strategy_email_report_news" in sql or "strategy_email_report_candidate" in sql:
            return []
        raise AssertionError(f"Unexpected SQL: {sql}")

    monkeypatch.setattr(existing_report_queries, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(existing_report_queries, "fetch_all", fake_fetch_all)

    result = await existing_report_queries.get_report(FakeEngine(), "report-raw-strategy", user_id="42")

    assert "FROM app.strategy_email_report AS report" in str(observed["sql"])
    assert result is not None
    assert result["id"] == "report-raw-strategy"
    assert result["strategyName"] is None
    assert result["title"] == "Track C report"
