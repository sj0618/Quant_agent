"""KIS OHLCV source pilot client."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from time import perf_counter
import time
from typing import Any

from quant_agent.data.config import KisConfig
from quant_agent.data.models import ApiRequestLog, OhlcvBar, RawSourcePayload
from quant_agent.data.sources.base import SourceConfigurationError, SourceResponseError, decimal_or_none


class KisOhlcvClient:
    source_name = "KIS"

    def __init__(self, config: KisConfig, request_observer: Callable[[ApiRequestLog], None] | None = None) -> None:
        self.config = config
        self._access_token: str | None = config.access_token
        self._request_observer = request_observer

    def set_request_observer(self, request_observer: Callable[[ApiRequestLog], None] | None) -> None:
        self._request_observer = request_observer

    def issue_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        if not self.config.is_configured:
            raise SourceConfigurationError("KIS_APP_KEY and KIS_APP_SECRET are required for KIS source pilot.")

        payload = self._request_json(
            method="POST",
            endpoint_key=self.config.token_path,
            request_fingerprint={"grant_type": "client_credentials"},
            json={
                "grant_type": "client_credentials",
                "appkey": self.config.app_key,
                "appsecret": self.config.app_secret,
            },
        )
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

        payload = self._request_json(
            method="GET",
            endpoint_key=self.config.daily_price_path,
            request_fingerprint={**params, "symbol": symbol, "adjusted": adjusted},
            headers={
                "Content-Type": "application/json",
                "authorization": f"Bearer {token}",
                "appkey": self.config.app_key or "",
                "appsecret": self.config.app_secret or "",
                "tr_id": "FHKST03010100",
            },
            params=params,
        )
        return RawSourcePayload(
            source=self.source_name,
            endpoint_key=self.config.daily_price_path,
            request_date=end_date,
            request={**params, "symbol": symbol, "adjusted": adjusted},
            payload=payload,
        )

    def _request_json(
        self,
        *,
        method: str,
        endpoint_key: str,
        request_fingerprint: dict[str, Any],
        **request_kwargs: Any,
    ) -> dict[str, Any]:
        import requests

        url = f"{self.config.base_url}{endpoint_key}"
        last_error: Exception | None = None
        for attempt in range(1, self.config.retry.attempts + 1):
            status_code: int | None = None
            response_payload: dict[str, Any] | None = None
            error_message: str | None = None
            success = False
            should_retry = False
            started_at = datetime.now(timezone.utc)
            started_perf = perf_counter()
            try:
                response = requests.request(
                    method,
                    url,
                    timeout=self.config.request_timeout_seconds,
                    **request_kwargs,
                )
                status_code = response.status_code
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise SourceResponseError("KIS response is not a JSON object.")
                response_payload = payload
                success = True
                return payload
            except Exception as exc:  # noqa: BLE001 - preserve final source error context
                last_error = exc
                error_message = str(exc)
                should_retry = attempt < self.config.retry.attempts
                if not should_retry:
                    raise
            finally:
                elapsed_ms = max(0, int((perf_counter() - started_perf) * 1000))
                self._record_api_request(
                    ApiRequestLog(
                        source_id=self.source_name,
                        endpoint_key=endpoint_key,
                        request={"method": method, "endpoint_key": endpoint_key, **request_fingerprint},
                        success=success,
                        status_code=status_code,
                        elapsed_ms=elapsed_ms,
                        retry_count=attempt - 1,
                        response=response_payload,
                        error_message=error_message,
                        metadata={"attempt": attempt, "max_attempts": self.config.retry.attempts},
                        request_started_at=started_at,
                    )
                )
            if should_retry:
                time.sleep(self.config.retry.backoff_seconds * attempt)
        assert last_error is not None
        raise last_error

    def _record_api_request(self, event: ApiRequestLog) -> None:
        if self._request_observer is None:
            return
        self._request_observer(event)


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
