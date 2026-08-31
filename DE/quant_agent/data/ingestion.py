"""OHLCV ingestion services for backfill and daily updates."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from quant_agent.data.config import KrxConfig, OhlcvIngestionConfig
from quant_agent.data.lineage_quality import LineageQualityReport
from quant_agent.data.models import OhlcvBar, OhlcvIngestionResult, RawSourcePayload
from quant_agent.data.repository import DataRepository
from quant_agent.data.sources.krx import KrxOhlcvClient

CANONICAL_OHLCV_SOURCE = "KRX"
KIS_ADJUSTED_INGESTION_SCRIPT = "scripts/ingest_kis_adjusted_ohlcv.py"


@dataclass(frozen=True)
class OhlcvIngestionRequest:
    source: str
    start_date: date
    end_date: date
    symbols: tuple[str, ...] = ()
    dag_id: str = "manual_ohlcv_ingestion"
    task_id: str = "ingest_ohlcv"


class OhlcvIngestionService:
    def __init__(
        self,
        repository: DataRepository | None = None,
        ingestion_config: OhlcvIngestionConfig | None = None,
        krx_config: KrxConfig | None = None,
    ) -> None:
        self.repository = repository or DataRepository()
        self.ingestion_config = ingestion_config or OhlcvIngestionConfig.from_env()
        self.krx_client = KrxOhlcvClient(krx_config or KrxConfig.from_env())

    def ingest_range(self, request: OhlcvIngestionRequest) -> OhlcvIngestionResult:
        source = request.source.upper()
        if source != CANONICAL_OHLCV_SOURCE:
            raise ValueError(
                f"Generic OHLCV ingestion only writes the canonical {CANONICAL_OHLCV_SOURCE} dataset. "
                f"Use {KIS_ADJUSTED_INGESTION_SCRIPT} for KIS adjusted data."
            )
        if request.end_date < request.start_date:
            raise ValueError("end_date must be greater than or equal to start_date.")
        run_id = self.repository.start_ingestion_run(
            dag_id=request.dag_id,
            task_id=request.task_id,
            source_id=source,
            params={
                "source": source,
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "symbols": list(request.symbols),
            },
        )
        total_fetched = 0
        total_written = 0
        total_raw_written = 0
        all_issues = []
        try:
            for chunk_start, chunk_end in chunk_date_range(
                request.start_date,
                request.end_date,
                self.ingestion_config.batch_days,
            ):
                raw_payloads, bars = self._fetch_chunk(source, chunk_start, chunk_end, request.symbols)
                total_fetched += len(bars)
                total_raw_written += self.repository.store_raw_payloads(raw_payloads, run_id)
                observed_open_dates = {
                    raw.request_date
                    for raw in raw_payloads
                    if isinstance(raw.payload.get("OutBlock_1"), list) and bool(raw.payload.get("OutBlock_1"))
                }
                self.repository.upsert_trading_calendar_observations(
                    start_date=chunk_start,
                    end_date=chunk_end,
                    observed_open_dates=observed_open_dates,
                    run_id=run_id,
                    source_id=source,
                )
                written, issues = self.repository.upsert_ohlcv_bars(bars, run_id, source)
                total_written += written
                all_issues.extend(issues)
                if bars:
                    self.repository.set_cursor(
                        source_id=source,
                        dataset="ohlcv_daily",
                        cursor_key="last_successful_trade_date",
                        cursor_value=max(bar.trade_date for bar in bars).isoformat(),
                    )

            self.repository.run_ohlcv_quality_framework(
                run_id=run_id,
                source_id=source,
                start_date=request.start_date,
                end_date=request.end_date,
                min_coverage=self.ingestion_config.min_symbol_coverage,
            )
            lineage_quality: LineageQualityReport = self.repository.enforce_lineage_quality_slo(
                run_id=run_id,
                source_id=source,
                start_date=request.start_date,
                end_date=request.end_date,
            )
            self.repository.finish_ingestion_run(run_id, status="success")
        except Exception as exc:
            self.repository.finish_ingestion_run(run_id, status="failed", error_message=str(exc))
            raise

        return OhlcvIngestionResult(
            run_id=run_id,
            source=source,
            start_date=request.start_date,
            end_date=request.end_date,
            rows_fetched=total_fetched,
            rows_written=total_written,
            raw_payloads_written=total_raw_written,
            quality_issues=all_issues,
            lineage_quality=lineage_quality.to_dict(),
        )

    def _fetch_chunk(
        self,
        source: str,
        start_date: date,
        end_date: date,
        symbols: tuple[str, ...],
    ) -> tuple[list[RawSourcePayload], list[OhlcvBar]]:
        if source == CANONICAL_OHLCV_SOURCE:
            raw_payloads: list[RawSourcePayload] = []
            bars: list[OhlcvBar] = []
            for trade_date in each_date(start_date, end_date):
                daily_payloads = self.krx_client.fetch_market_day_payloads(trade_date)
                raw_payloads.extend(daily_payloads)
                for raw_payload in daily_payloads:
                    from quant_agent.data.sources.krx import normalize_krx_market_day

                    bars.extend(self._filter_krx_bars(normalize_krx_market_day(raw_payload.payload), symbols))
            return raw_payloads, bars

        raise ValueError(f"Unsupported OHLCV source: {source}")

    @staticmethod
    def _filter_krx_bars(bars: list[OhlcvBar], symbols: tuple[str, ...]) -> list[OhlcvBar]:
        requested_symbols = {symbol.strip() for symbol in symbols if symbol.strip()}
        if not requested_symbols:
            return bars
        return [bar for bar in bars if bar.symbol in requested_symbols]


def each_date(start_date: date, end_date: date) -> Iterable[date]:
    if end_date < start_date:
        raise ValueError("end_date must be greater than or equal to start_date.")
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def chunk_date_range(start_date: date, end_date: date, chunk_days: int) -> Iterable[tuple[date, date]]:
    if chunk_days < 1:
        raise ValueError("chunk_days must be >= 1.")
    current = start_date
    while current <= end_date:
        chunk_end = min(current + timedelta(days=chunk_days - 1), end_date)
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)
