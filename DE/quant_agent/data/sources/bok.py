"""Bank of Korea ECOS source client."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from quant_agent.data.config import BokConfig
from quant_agent.data.models import RawSourcePayload
from quant_agent.data.sources.base import SourceConfigurationError, SourceResponseError, retry_call


class BokEcosClient:
    source_name = "BOK"

    def __init__(self, config: BokConfig) -> None:
        self.config = config

    def fetch_statistic_search(
        self,
        *,
        stat_code: str,
        cycle: str,
        start_period: str,
        end_period: str,
        item_code1: str = "?",
        language: str = "kr",
        limit: int = 10000,
    ) -> RawSourcePayload:
        if not self.config.is_configured:
            raise SourceConfigurationError("BOK_API_KEY is required for BOK ECOS ingestion.")

        path = (
            f"{self.config.base_url}/StatisticSearch/{self.config.api_key}/json/{language}/1/{limit}/"
            f"{stat_code}/{cycle}/{start_period}/{end_period}/{item_code1}"
        )

        def request_payload() -> dict[str, Any]:
            import requests

            response = requests.get(path, timeout=self.config.request_timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceResponseError("BOK response is not a JSON object.")
            return payload

        payload = retry_call(request_payload, self.config.retry)
        return RawSourcePayload(
            source=self.source_name,
            endpoint_key="StatisticSearch",
            request_date=date.today(),
            request={
                "stat_code": stat_code,
                "cycle": cycle,
                "start_period": start_period,
                "end_period": end_period,
                "item_code1": item_code1,
                "language": language,
                "limit": limit,
            },
            payload=payload,
        )


def normalize_bok_observations(raw_payload: RawSourcePayload, *, published_at_policy: str = "fetch_time") -> list[dict[str, Any]]:
    rows = raw_payload.payload.get("StatisticSearch", {}).get("row")
    if rows is None:
        error = raw_payload.payload.get("RESULT") or raw_payload.payload.get("StatisticSearch", {}).get("RESULT")
        if error:
            if error.get("CODE") == "INFO-200":
                return []
            raise SourceResponseError(f"BOK API returned error metadata: {error}")
        return []
    if not isinstance(rows, list):
        raise SourceResponseError("BOK StatisticSearch.row is not a list.")

    fetch_time = datetime.now(timezone.utc)
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        time_text = str(row.get("TIME", "")).strip()
        stat_code = str(row.get("STAT_CODE") or raw_payload.request.get("stat_code") or "").strip()
        item_code = str(row.get("ITEM_CODE1") or raw_payload.request.get("item_code1") or "").strip()
        value = _decimal_or_none(row.get("DATA_VALUE"))
        effective_date = _period_to_effective_date(time_text, str(raw_payload.request.get("cycle", "")))
        normalized.append(
            {
                "series_id": f"{stat_code}:{item_code}",
                "effective_date": effective_date,
                "published_at": fetch_time.isoformat() if published_at_policy == "fetch_time" else None,
                "value": value,
                "metadata": row,
            }
        )
    return normalized


def _period_to_effective_date(period: str, cycle: str) -> date:
    text = period.strip()
    if len(text) == 8:
        return date.fromisoformat(f"{text[0:4]}-{text[4:6]}-{text[6:8]}")
    if len(text) == 6:
        return date.fromisoformat(f"{text[0:4]}-{text[4:6]}-01")
    if "Q" in text.upper():
        year = int(text[:4])
        quarter = int(text[-1])
        month = {1: 3, 2: 6, 3: 9, 4: 12}[quarter]
        return date(year, month, 1)
    if len(text) == 4:
        return date(int(text), 1, 1)
    raise SourceResponseError(f"Unsupported BOK period format: {period} ({cycle})")


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or str(value).strip() in {"", "-"}:
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None
