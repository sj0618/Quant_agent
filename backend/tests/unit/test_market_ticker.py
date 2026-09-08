from __future__ import annotations

import asyncio

from fastapi import FastAPI
import httpx
import pytest

from app.api.routes import market_ticker


@pytest.mark.asyncio
async def test_public_market_ticker_partial_data_cache_and_failed_refresh(monkeypatch):
    """Local synthetic provider responses only, never evidence of live market prices."""
    calls = []
    failed = False

    def provider(request):
        calls.append(request)
        if failed:
            return httpx.Response(503)
        if request.url.host != "api.upbit.com":
            row = {
                "closePrice": "2,500.12", "compareToPreviousClosePrice": "-12.34", "fluctuationsRatio": "-0.49",
                "localTradedAt": "2026-01-02T16:00:00-04:00", "marketStatus": "CLOSE", "delayTime": 15,
            }
            if "KOSDAQ" in request.url.path:
                row["localTradedAt"] = "2026-01-02T16:00:00"  # Missing timezone must not become a local time.
            if "FX_USDKRW" in request.url.path:
                row["fluctuations"] = row.pop("compareToPreviousClosePrice")
                row["stockExchangeType"] = {"delayTime": row.pop("delayTime")}
                return httpx.Response(200, json={"exchangeInfo": row})
            return httpx.Response(200, json=row)
        return httpx.Response(200, json=[
            {"market": "KRW-BTC", "trade_price": 100000000, "signed_change_price": -1000000,
             "signed_change_rate": -0.01, "trade_timestamp": 1767321000000},
            {"market": "KRW-ETH", "trade_price": "NaN"},
            {"market": "KRW-UNKNOWN", "trade_price": 42},
        ])

    client_type = httpx.AsyncClient
    monkeypatch.setattr(market_ticker.httpx, "AsyncClient", lambda **kwargs: client_type(
        transport=httpx.MockTransport(provider), **kwargs,
    ))
    app = FastAPI()
    app.include_router(market_ticker.router)
    async with client_type(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first, cached = await asyncio.gather(client.get("/api/v1/market-ticker"), client.get("/api/v1/market-ticker"))
        assert first.status_code == 200
        payload = first.json()
        assert payload == cached.json()
        assert len(calls) == 6
        assert str(calls[0].url) == "https://api.upbit.com/v1/ticker?markets=KRW-BTC%2CKRW-ETH"
        assert payload["metadata"]["count"] == 5
        assert payload["metadata"]["source"] == "upstream_api"
        assert payload["metadata"]["sources"] == ["naver_finance", "upbit"]
        quotes = {row["symbol"]: row for row in payload["quotes"]}
        assert len(quotes) == 7
        assert quotes["BTC"]["price"] == 100000000
        assert quotes["BTC"]["change"] == -1000000
        assert quotes["BTC"]["changePercent"] == -1
        assert quotes["BTC"]["asOf"] == "2026-01-02T02:30:00+00:00"
        assert "UTC 00:00" in quotes["BTC"]["changeBasis"]
        assert quotes["ETH"]["price"] is None
        assert quotes["KOSDAQ"]["status"] == "unavailable"
        assert quotes["KOSPI"]["price"] == 2500.12
        assert quotes["KOSPI"]["change"] == -12.34
        assert quotes["KOSPI"]["changePercent"] == -0.49
        assert quotes["KOSPI"]["asOf"] == "2026-01-02T16:00:00-04:00"
        assert quotes["KOSPI"]["marketStatus"] == "CLOSE"
        assert quotes["USDKRW"]["delayMinutes"] == 15
        assert "하나은행" in quotes["USDKRW"]["changeBasis"]

        failed = True
        app.state.market_ticker_expires = 0
        refresh = (await client.get("/api/v1/market-ticker")).json()
        assert len(calls) == 12
        assert refresh["metadata"]["count"] == 0
        assert all(row["price"] is None and row["asOf"] is None for row in refresh["quotes"])
