from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import math
from time import monotonic

from fastapi import APIRouter, Request
import httpx

router = APIRouter(tags=["market"])
INSTRUMENTS = (
    ("KOSPI", "코스피", "INDEX"),
    ("KOSDAQ", "코스닥", "INDEX"),
    ("NASDAQ", "나스닥", "INDEX"),
    ("SP500", "S&P 500", "INDEX"),
    ("BTC", "비트코인", "KRW"),
    ("ETH", "이더리움", "KRW"),
    ("USDKRW", "달러/원", "KRW"),
)
NAVER_URLS = {
    "KOSPI": "https://m.stock.naver.com/api/index/KOSPI/basic",
    "KOSDAQ": "https://m.stock.naver.com/api/index/KOSDAQ/basic",
    "NASDAQ": "https://api.stock.naver.com/index/.IXIC/basic",
    "SP500": "https://api.stock.naver.com/index/.INX/basic",
    "USDKRW": "https://api.stock.naver.com/marketindex/exchange/FX_USDKRW",
}


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("Missing market value")
    result = float(str(value).replace(",", ""))
    if not math.isfinite(result):
        raise ValueError("Non-finite market value")
    return result


def _upbit_quote(row: dict) -> dict:
    # Upbit signed changes are against the previous day's close (UTC 00:00),
    # not a rolling 24-hour return. trade_timestamp is the last actual trade.
    price = _number(row["trade_price"])
    if price <= 0:
        raise ValueError("Invalid market price")
    return {
        "price": price,
        "change": _number(row["signed_change_price"]),
        "changePercent": _number(row["signed_change_rate"]) * 100,
        "asOf": datetime.fromtimestamp(_number(row["trade_timestamp"]) / 1000, timezone.utc).isoformat(),
        "source": "upbit",
        "changeBasis": "전일 종가 대비 (UTC 00:00)",
        "status": "available",
    }


def _naver_quote(payload: dict, *, exchange: bool = False) -> dict:
    row = payload["exchangeInfo"] if exchange else payload
    as_of = datetime.fromisoformat(row["localTradedAt"])
    price = _number(row["closePrice"])
    if as_of.utcoffset() is None or price <= 0:
        raise ValueError("Missing quote timezone or invalid price")
    delay = row.get("stockExchangeType", {}).get("delayTime") if exchange else row.get("delayTime")
    return {
        "price": price,
        "change": _number(row["fluctuations" if exchange else "compareToPreviousClosePrice"]),
        "changePercent": _number(row["fluctuationsRatio"]),
        "asOf": as_of.isoformat(),
        "source": "naver_finance",
        "changeBasis": "전일 대비 · 하나은행 고시환율" if exchange else "전일 종가 대비",
        "status": "available",
        "marketStatus": row.get("marketStatus"),
        "delayMinutes": _number(delay) if delay is not None else None,
    }


async def _load_quotes() -> dict:
    quotes = {
        symbol: {
            "symbol": symbol, "name": name, "currency": currency,
            "price": None, "change": None, "changePercent": None, "asOf": None,
            "source": "unavailable", "changeBasis": "전일 종가 대비", "status": "unavailable",
        }
        for symbol, name, currency in INSTRUMENTS
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        async def load_naver(symbol: str, url: str) -> None:
            try:
                response = await client.get(url)
                response.raise_for_status()
                quotes[symbol].update(_naver_quote(response.json(), exchange=symbol == "USDKRW"))
            except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError):
                pass

        async def load_upbit() -> None:
            try:
                response = await client.get("https://api.upbit.com/v1/ticker", params={"markets": "KRW-BTC,KRW-ETH"})
                response.raise_for_status()
                rows = response.json()
                if isinstance(rows, list):
                    for row in rows:
                        if not isinstance(row, dict) or row.get("market") not in {"KRW-BTC", "KRW-ETH"}:
                            continue
                        try:
                            quotes[row["market"].removeprefix("KRW-")].update(_upbit_quote(row))
                        except (KeyError, TypeError, ValueError, OverflowError, OSError):
                            continue
            except (httpx.HTTPError, ValueError):
                pass

        await asyncio.gather(load_upbit(), *(load_naver(symbol, url) for symbol, url in NAVER_URLS.items()))
    available = [quote for quote in quotes.values() if quote["status"] == "available"]
    return {
        "quotes": list(quotes.values()),
        "metadata": {
            "source": "upstream_api", "asOf": datetime.now(timezone.utc).isoformat(),
            "count": len(available), "sources": sorted({quote["source"] for quote in available}),
        },
    }


@router.get("/api/v1/market-ticker")
async def market_ticker(request: Request) -> dict:
    # ponytail: process-local cache; share it if multiple backend workers need one provider quota.
    state = request.app.state
    if not hasattr(state, "market_ticker_lock"):
        state.market_ticker_lock = asyncio.Lock()
        state.market_ticker_expires = 0.0
    async with state.market_ticker_lock:
        if monotonic() >= state.market_ticker_expires:
            # Replace even a failed refresh: old prices must not look freshly fetched.
            state.market_ticker_result = await _load_quotes()
            state.market_ticker_expires = monotonic() + 60
        return state.market_ticker_result
