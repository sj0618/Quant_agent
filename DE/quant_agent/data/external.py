"""External non-OHLCV ingestion services: SEIBro, BOK ECOS, OpenDART, KIND, WICS."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
import hashlib
import json
from calendar import monthrange
from typing import Any

from quant_agent.data.config import BokConfig, DartConfig, KindConfig, SeibroConfig, WicsConfig
from quant_agent.data.db import sql_literal
from quant_agent.data.models import ApiRequestLog, LineageEvent, RawSourcePayload
from quant_agent.data.repository import DataRepository
from quant_agent.data.sources.bok import BokEcosClient, normalize_bok_observations
from quant_agent.data.sources.dart import OpenDartClient, normalize_corp_code_zip, normalize_financial_statement
from quant_agent.data.sources.kind import KindListedCompanyClient
from quant_agent.data.sources.wics import WicsCompanyGuideClient
from quant_agent.data.sources.seibro import (
    LexiconSentimentScorer,
    SeibroAnalystReportClient,
    SeibroReportClient,
    normalize_analyst_report_summaries,
    normalize_seibro_reports,
)


class ExternalDataIngestionService:
    def __init__(
        self,
        repository: DataRepository | None = None,
        bok_config: BokConfig | None = None,
        dart_config: DartConfig | None = None,
        kind_config: KindConfig | None = None,
        wics_config: WicsConfig | None = None,
        seibro_config: SeibroConfig | None = None,
    ) -> None:
        self.repository = repository or DataRepository()
        self.bok_client = BokEcosClient(bok_config or BokConfig.from_env())
        self.dart_client = OpenDartClient(dart_config or DartConfig.from_env())
        self.kind_client = KindListedCompanyClient(kind_config or KindConfig.from_env())
        self.wics_client = WicsCompanyGuideClient(wics_config or WicsConfig.from_env())
        resolved_seibro_config = seibro_config or SeibroConfig.from_env()
        self.seibro_client = SeibroReportClient(resolved_seibro_config)
        self.seibro_analyst_client = SeibroAnalystReportClient(resolved_seibro_config)
        self.sentiment_scorer = LexiconSentimentScorer()

    def ingest_bok_series(
        self,
        *,
        stat_code: str,
        cycle: str,
        start_period: str,
        end_period: str,
        item_code1: str = "?",
    ) -> int:
        run_id = self.repository.start_ingestion_run(
            dag_id="manual_bok_ingestion",
            task_id="ingest_bok_series",
            source_id="BOK",
            params={
                "stat_code": stat_code,
                "cycle": cycle,
                "start_period": start_period,
                "end_period": end_period,
                "item_code1": item_code1,
            },
        )
        try:
            raw_payload = self.bok_client.fetch_statistic_search(
                stat_code=stat_code,
                cycle=cycle,
                start_period=start_period,
                end_period=end_period,
                item_code1=item_code1,
            )
            self.repository.store_external_raw_payloads([raw_payload], run_id)
            rows = normalize_bok_observations(raw_payload)
            written = self.repository.upsert_bok_observations(rows, run_id)
            self.repository.finish_ingestion_run(run_id, status="success")
            return written
        except Exception as exc:
            self.repository.finish_ingestion_run(run_id, status="failed", error_message=str(exc))
            raise

    def ingest_dart_corp_codes(self) -> int:
        run_id = self.repository.start_ingestion_run(
            dag_id="manual_dart_ingestion",
            task_id="ingest_dart_corp_codes",
            source_id="DART",
            params={},
        )
        try:
            rows = normalize_corp_code_zip(self.dart_client.fetch_corp_codes())
            self.repository.store_external_raw_payloads(
                [
                    RawSourcePayload(
                        source="DART",
                        endpoint_key="corpCode",
                        request_date=date.today(),
                        request={"corp_code": "__all__", "reprt_code": "corpCode"},
                        payload={"rows": rows},
                    )
                ],
                run_id,
            )
            written = self.repository.upsert_dart_corp_map(rows, run_id)
            self.repository.finish_ingestion_run(run_id, status="success")
            return written
        except Exception as exc:
            self.repository.finish_ingestion_run(run_id, status="failed", error_message=str(exc))
            raise

    def ingest_dart_financial_statement(
        self,
        *,
        symbol: str,
        corp_code: str,
        business_year: int,
        report_code: str,
        fs_div: str = "CFS",
        period_end: date | None = None,
    ) -> int:
        run_id = self.repository.start_ingestion_run(
            dag_id="manual_dart_ingestion",
            task_id="ingest_dart_financial_statement",
            source_id="DART",
            params={
                "symbol": symbol,
                "corp_code": corp_code,
                "business_year": business_year,
                "report_code": report_code,
                "fs_div": fs_div,
                "period_end": period_end.isoformat() if period_end else None,
            },
        )
        try:
            raw_payload = self.dart_client.fetch_financial_statement(
                corp_code=corp_code,
                business_year=business_year,
                report_code=report_code,
                fs_div=fs_div,
            )
            self.repository.store_external_raw_payloads([raw_payload], run_id)
            rows = normalize_financial_statement(raw_payload, symbol=symbol, period_end=period_end)
            payload_hash = _stable_hash(raw_payload.payload)
            rows = [
                {
                    **row,
                    "source_payload_hash": payload_hash,
                    "filing_id": row.get("filing_id") or f"payload:{payload_hash}",
                }
                for row in rows
            ]
            written = self.repository.upsert_dart_financials(rows, run_id)
            self.repository.finish_ingestion_run(run_id, status="success")
            return written
        except Exception as exc:
            self.repository.finish_ingestion_run(run_id, status="failed", error_message=str(exc))
            raise

    def ingest_kind_sector_snapshot(self, *, as_of_date: date | None = None) -> int:
        snapshot_date = as_of_date or date.today()
        run_id = self.repository.start_ingestion_run(
            dag_id="manual_kind_ingestion",
            task_id="ingest_kind_sector_snapshot",
            source_id="KIND",
            params={
                "as_of_date": snapshot_date.isoformat(),
                "source": "listed_company_directory",
            },
        )
        try:
            rows = self.kind_client.fetch_listed_company_rows()
            for row in rows:
                row["sector_as_of"] = snapshot_date
            self.repository.upsert_kind_symbol_metadata(rows, run_id, as_of_date=snapshot_date)
            self.repository.upsert_kind_symbol_sectors(rows, run_id)
            matched_rows = self.repository.executor.fetch_json(
                f"""
                SELECT COUNT(*)::int AS matched_count
                  FROM core.symbol_master
                 WHERE sector_run_id = {sql_literal(run_id)}
                """
            )[0]["matched_count"]
            unmatched_rows = len(rows) - matched_rows
            null_sector_count = self.repository.executor.fetch_json(
                """
                SELECT COUNT(*)::int AS null_count
                  FROM core.symbol_master
                 WHERE listing_status = 'listed'
                   AND sector IS NULL
                """
            )[0]["null_count"]
            if unmatched_rows > 0 or null_sector_count > 0:
                # Keep the run successful so the matched universe stays fresh while the
                # uncovered symbols are investigated separately in the collection plan.
                print(
                    "KIND sector snapshot warnings: "
                    f"unmatched={unmatched_rows}/{len(rows)}, null_sector={null_sector_count}"
                )
            self.repository.finish_ingestion_run(run_id, status="success")
            return matched_rows
        except Exception as exc:
            self.repository.finish_ingestion_run(run_id, status="failed", error_message=str(exc))
            raise

    def ingest_wics_sector_snapshot(
        self,
        *,
        as_of_date: date | None = None,
        max_workers: int | None = None,
        symbol_limit: int | None = None,
    ) -> int:
        snapshot_date = as_of_date or date.today()
        run_id = self.repository.start_ingestion_run(
            dag_id="manual_wics_ingestion",
            task_id="ingest_wics_sector_snapshot",
            source_id="WICS",
            params={
                "as_of_date": snapshot_date.isoformat(),
                "max_workers": max_workers,
                "symbol_limit": symbol_limit,
                "source": "company_guide_information",
            },
        )
        try:
            target_rows = self.repository.executor.fetch_json(
                """
                SELECT symbol, name, market_segment
                  FROM core.symbol_master
                 WHERE listing_status = 'listed'
                   AND security_type = '보통주'
                   AND symbol ~ '^[0-9]{6}$'
                 ORDER BY symbol
                """
            )
            if symbol_limit is not None:
                target_rows = target_rows[:symbol_limit]
            if not target_rows:
                raise ValueError("No listed common-stock symbols were found for WICS ingestion.")

            worker_count = max(1, max_workers or self.wics_client.config.request_workers)
            sector_rows: list[dict[str, Any]] = []
            failed_symbols: list[tuple[str, str]] = []
            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=worker_count) as pool:
                future_to_symbol = {
                    pool.submit(
                        self.wics_client.fetch_sector_row,
                        symbol=row["symbol"],
                        company_name=row.get("name"),
                        market_segment=row.get("market_segment"),
                        as_of_date=snapshot_date,
                    ): row["symbol"]
                    for row in target_rows
                }
                for future in as_completed(future_to_symbol):
                    symbol = future_to_symbol[future]
                    try:
                        row = future.result()
                    except Exception as exc:  # noqa: BLE001 - collect failure summary for operator review
                        failed_symbols.append((symbol, str(exc)))
                        continue
                    if row.get("sector"):
                        sector_rows.append(row)

            if not sector_rows:
                raise ValueError("WICS ingestion did not normalize any sector rows.")

            matched_symbols = {str(row["symbol"]) for row in sector_rows if row.get("symbol")}
            matched_rows = len(matched_symbols)
            listed_common_null_sector_count = self.repository.executor.fetch_json(
                """
                SELECT COUNT(*)::int AS null_count
                  FROM core.symbol_master
                 WHERE listing_status = 'listed'
                   AND security_type = '보통주'
                   AND sector IS NULL
                """
            )[0]["null_count"]
            unmatched_rows = len(target_rows) - matched_rows
            if unmatched_rows > 0 or listed_common_null_sector_count > 0 or failed_symbols:
                sample_failures = ", ".join(f"{symbol}: {error}" for symbol, error in failed_symbols[:5])
                print(
                    "WICS sector snapshot warnings: "
                    f"matched={matched_rows}/{len(target_rows)}, "
                    f"unmatched={unmatched_rows}, "
                    f"common_null_sector={listed_common_null_sector_count}"
                    + (f", failed={len(failed_symbols)} [{sample_failures}]" if failed_symbols else "")
                )
            match_ratio = matched_rows / len(target_rows) if target_rows else 0.0
            if match_ratio < self.wics_client.config.min_match_ratio:
                raise ValueError(
                    "WICS sector coverage is below the configured threshold: "
                    f"{matched_rows}/{len(target_rows)} ({match_ratio:.4f}) < "
                    f"{self.wics_client.config.min_match_ratio:.4f}."
                )
            self.repository.store_wics_raw_payloads(sector_rows, run_id)
            self.repository.upsert_wics_symbol_sectors(sector_rows, run_id)
            self.repository.finish_ingestion_run(run_id, status="success")
            return matched_rows
        except Exception as exc:
            self.repository.finish_ingestion_run(run_id, status="failed", error_message=str(exc))
            raise

    def ingest_seibro_reports(
        self,
        *,
        endpoint_path: str,
        params: dict[str, Any],
        as_of_date: date,
        universe_min_score: float,
        universe_min_reports: int,
    ) -> int:
        run_id = self.repository.start_ingestion_run(
            dag_id="manual_seibro_ingestion",
            task_id="ingest_seibro_reports",
            source_id="SEIBRO",
            params={
                "endpoint_path": endpoint_path,
                "params": params,
                "as_of_date": as_of_date.isoformat(),
                "universe_min_score": universe_min_score,
                "universe_min_reports": universe_min_reports,
            },
        )
        try:
            raw_payload = self.seibro_client.fetch_report_payload(endpoint_path=endpoint_path, params=params)
            self.repository.store_external_raw_payloads([raw_payload], run_id)
            payload_hash = _stable_hash(raw_payload.payload)
            rows = []
            for report in normalize_seibro_reports(raw_payload.payload):
                score = self.sentiment_scorer.score(report.summary)
                rows.append(
                    {
                        **asdict(report),
                        "source_payload_hash": payload_hash,
                        "sentiment_score": score,
                        "model_version": self.sentiment_scorer.model_version,
                        "prompt_version": self.sentiment_scorer.prompt_version,
                    }
                )
            written = self.repository.upsert_seibro_reports_and_scores(rows, run_id)
            self.repository.refresh_seibro_universe(
                as_of_date=as_of_date,
                min_score=universe_min_score,
                min_reports=universe_min_reports,
                run_id=run_id,
            )
            self.repository.finish_ingestion_run(run_id, status="success")
            return written
        except Exception as exc:
            self.repository.finish_ingestion_run(run_id, status="failed", error_message=str(exc))
            raise

    def backfill_seibro_analyst_report_summaries(
        self,
        *,
        start_date: date,
        end_date: date,
        chunk_months: int | None = None,
        page_size: int | None = None,
        sleep_min_seconds: float | None = None,
        sleep_max_seconds: float | None = None,
        company_code: str = "",
    ) -> dict[str, Any]:
        config = self.seibro_analyst_client.config
        resolved_chunk_months = chunk_months or config.analyst_report_chunk_months
        resolved_page_size = page_size or config.analyst_report_page_size
        if resolved_chunk_months < 1:
            raise ValueError("chunk_months must be at least 1.")
        if resolved_page_size < 1:
            raise ValueError("page_size must be at least 1.")
        if end_date < start_date:
            raise ValueError("end_date must be greater than or equal to start_date.")

        run_id = self.repository.start_ingestion_run(
            dag_id="manual_seibro_analyst_report_backfill",
            task_id="backfill_seibro_analyst_report_summaries",
            source_id="SEIBRO",
            params={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "chunk_months": resolved_chunk_months,
                "page_size": resolved_page_size,
                "company_code": company_code,
            },
        )
        api_events: list[ApiRequestLog] = []
        self.seibro_analyst_client.set_request_observer(api_events.append)
        raw_payloads_written = 0
        rows_seen = 0
        upsert_attempts = 0
        chunks_processed = 0
        pages_processed = 0
        try:
            self.repository.ensure_analyst_report_summary_table()
            for chunk_start, chunk_end in month_chunks(start_date, end_date, resolved_chunk_months):
                chunks_processed += 1
                start_row = 1
                while True:
                    end_row = start_row + resolved_page_size - 1
                    raw_payload = self.seibro_analyst_client.fetch_summary_page(
                        start_date=chunk_start,
                        end_date=chunk_end,
                        start_row=start_row,
                        end_row=end_row,
                        company_code=company_code,
                    )
                    pages_processed += 1
                    raw_payloads_written += self.repository.store_external_raw_payloads([raw_payload], run_id)
                    if api_events:
                        self.repository.store_api_request_logs(api_events, run_id)
                        api_events.clear()
                    reports = normalize_analyst_report_summaries(raw_payload)
                    rows_seen += len(reports)
                    upsert_attempts += self.repository.upsert_analyst_report_summaries(reports, run_id)
                    self.repository.store_lineage_events(
                        [
                            LineageEvent(
                                target_table="raw.analyst_report_summary",
                                target_key=f"{chunk_start.isoformat()}:{chunk_end.isoformat()}:{start_row}:{end_row}",
                                source_table="raw.seibro_report_response",
                                source_key=_stable_hash(raw_payload.request),
                                transform_version="seibro-websquare-analyst-report-v1",
                                metadata={"row_count": len(reports)},
                            )
                        ],
                        run_id,
                    )
                    if len(reports) < resolved_page_size:
                        break
                    start_row += resolved_page_size
                    self.seibro_analyst_client.sleep_between_requests(sleep_min_seconds, sleep_max_seconds)
                self.seibro_analyst_client.sleep_between_requests(sleep_min_seconds, sleep_max_seconds)
            if api_events:
                self.repository.store_api_request_logs(api_events, run_id)
                api_events.clear()
            self.repository.finish_ingestion_run(run_id, status="success")
            unique_rows_in_table = self.repository.count_analyst_report_summaries(
                start_date=start_date,
                end_date=end_date,
                run_id=run_id,
            )
            return {
                "run_id": str(run_id),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "chunk_months": resolved_chunk_months,
                "page_size": resolved_page_size,
                "chunks_processed": chunks_processed,
                "pages_processed": pages_processed,
                "raw_payloads_written": raw_payloads_written,
                "rows_seen": rows_seen,
                "upsert_attempts": upsert_attempts,
                "unique_rows_in_table": unique_rows_in_table,
            }
        except Exception as exc:
            if api_events:
                self.repository.store_api_request_logs(api_events, run_id)
            self.repository.finish_ingestion_run(run_id, status="failed", error_message=str(exc))
            raise


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def month_chunks(start_date: date, end_date: date, months: int) -> list[tuple[date, date]]:
    if months < 1:
        raise ValueError("months must be at least 1.")
    chunks: list[tuple[date, date]] = []
    cursor = start_date
    while cursor <= end_date:
        next_start = _add_months(cursor, months)
        chunk_end = min(end_date, next_start - timedelta(days=1))
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, _last_day_of_month(year, month))
    return date(year, month, day)


def _last_day_of_month(year: int, month: int) -> int:
    return monthrange(year, month)[1]
