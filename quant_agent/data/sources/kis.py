"""KIS OHLCV source pilot client."""

from __future__ import annotations

from datetime import date
from typing import Any

from quant_agent.data.config import KisConfig
from quant_agent.data.models import OhlcvBar, RawSourcePayload
from quant_agent.data.sources.base import SourceConfigurationError, SourceResponseError, decimal_or_none, retry_call


class KisOhlcvClient:
    source_name = "KIS"

    def __init__(self, config: KisConfig) -> None:
        self.config = config
        self._access_token: str | None = config.access_token

    def issue_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        if not self.config.is_configured:
            raise SourceConfigurationError("KIS_APP_KEY and KIS_APP_SECRET are required for KIS source pilot.")

        def request_payload() -> dict[str, Any]:
            import requests

            response = requests.post(
                f"{self.config.base_url}{self.config.token_path}",
                json={
                    "grant_type": "client_credentials",
                    "appkey": self.config.app_key,
                    "appsecret": self.config.app_secret,
                },
                timeout=self.config.request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceResponseError("KIS token response is not a JSON object.")
            return payload

        payload = retry_call(request_payload, self.config.retry)
        token = payload.get("access_token")
        if not token:
            raise SourceResponseError("KIS token response does not include access_token.")
        self._access_token = str(token)
        return self._access_token

    def fetch_daily_price(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        *,
        adjusted: bool = True,
    ) -> list[OhlcvBar]:
        raw_payload = self.fetch_daily_price_payload(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjusted=adjusted,
        )
        return normalize_kis_daily_price(raw_payload.payload, symbol=symbol)

    def fetch_daily_price_payload(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        *,
        adjusted: bool = True,
    ) -> RawSourcePayload:
        token = self.issue_access_token()
        price_flag = self.config.adjusted_price_flag if adjusted else self.config.original_price_flag
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_INPUT_DATE_1": start_date.strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": end_date.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": price_flag,
        }

        def request_payload() -> dict[str, Any]:
            import requests

            response = requests.get(
                f"{self.config.base_url}{self.config.daily_price_path}",
                headers={
                    "Content-Type": "application/json",
                    "authorization": f"Bearer {token}",
                    "appkey": self.config.app_key or "",
                    "appsecret": self.config.app_secret or "",
                    "tr_id": "FHKST03010100",
                },
                params=params,
                timeout=self.config.request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceResponseError("KIS daily price response is not a JSON object.")
            return payload

        payload = retry_call(request_payload, self.config.retry)
        return RawSourcePayload(
            source=self.source_name,
            endpoint_key=self.config.daily_price_path,
            request_date=end_date,
            request={**params, "symbol": symbol, "adjusted": adjusted},
            payload=payload,
        )


def normalize_kis_daily_price(payload: dict[str, Any], symbol: str) -> list[OhlcvBar]:
    rows = payload.get("output2")
    if not isinstance(rows, list):
        raise SourceResponseError("KIS response does not contain output2 list.")

    bars: list[OhlcvBar] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        date_text = str(row.get("stck_bsop_date", "")).strip()
        if not date_text:
            continue
        bars.append(
            OhlcvBar(
                source=KisOhlcvClient.source_name,
                symbol=symbol,
                trade_date=date.fromisoformat(f"{date_text[0:4]}-{date_text[4:6]}-{date_text[6:8]}"),
                open=decimal_or_none(row.get("stck_oprc")),
                high=decimal_or_none(row.get("stck_hgpr")),
                low=decimal_or_none(row.get("stck_lwpr")),
                close=decimal_or_none(row.get("stck_clpr")),
                volume=decimal_or_none(row.get("acml_vol")),
                raw=row,
            )
        )
    return bars
