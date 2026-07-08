"""KRX OHLCV source pilot client."""

from __future__ import annotations

from datetime import date
from typing import Any

from quant_agent.data.config import KrxConfig
from quant_agent.data.models import OhlcvBar, RawSourcePayload
from quant_agent.data.sources.base import SourceConfigurationError, SourceResponseError, decimal_or_none, retry_call


class KrxOhlcvClient:
    source_name = "KRX"

    def __init__(self, config: KrxConfig) -> None:
        self.config = config

    def fetch_market_day(self, trade_date: date) -> list[OhlcvBar]:
        return [bar for raw_payload in self.fetch_market_day_payloads(trade_date) for bar in normalize_krx_market_day(raw_payload.payload)]

    def fetch_market_day_payloads(self, trade_date: date) -> list[RawSourcePayload]:
        if not self.config.is_configured:
            raise SourceConfigurationError("KRX_API_KEY is required for KRX source pilot.")

        payloads: list[RawSourcePayload] = []
        for endpoint in self.config.daily_market_endpoints:
            request = {"basDd": trade_date.strftime("%Y%m%d")}
            payloads.append(
                RawSourcePayload(
                    source=self.source_name,
                    endpoint_key=endpoint,
                    request_date=trade_date,
                    request=request,
                    payload=self._fetch_market_day_endpoint(trade_date, endpoint, request),
                )
            )
        return payloads

    def _fetch_market_day_endpoint(self, trade_date: date, endpoint: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        def request_payload() -> dict[str, Any]:
            import requests
            response = requests.get(
                endpoint,
                params=params or {"basDd": trade_date.strftime("%Y%m%d")},
                headers={"AUTH_KEY": self.config.api_key or ""},
                timeout=self.config.request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceResponseError("KRX response is not a JSON object.")
            return payload

        return retry_call(request_payload, self.config.retry)


def normalize_krx_market_day(payload: dict[str, Any]) -> list[OhlcvBar]:
    rows = payload.get("OutBlock_1")
    if not isinstance(rows, list):
        raise SourceResponseError("KRX response does not contain OutBlock_1 list.")

    bars: list[OhlcvBar] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        date_text = str(row.get("BAS_DD", "")).strip()
        symbol = str(row.get("ISU_CD", "")).strip()
        if not date_text or not symbol:
            continue
        bars.append(
            OhlcvBar(
                source=KrxOhlcvClient.source_name,
                symbol=symbol,
                name=str(row.get("ISU_NM", "")).strip() or None,
                trade_date=date.fromisoformat(f"{date_text[0:4]}-{date_text[4:6]}-{date_text[6:8]}"),
                open=decimal_or_none(row.get("TDD_OPNPRC")),
                high=decimal_or_none(row.get("TDD_HGPRC")),
                low=decimal_or_none(row.get("TDD_LWPRC")),
                close=decimal_or_none(row.get("TDD_CLSPRC")),
                volume=decimal_or_none(row.get("ACC_TRDVOL")),
                raw=row,
            )
        )
    return bars
