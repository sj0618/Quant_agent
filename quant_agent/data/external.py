"""External non-OHLCV ingestion services: SEIBro, BOK ECOS, OpenDART."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
import hashlib
import json
from typing import Any

from quant_agent.data.config import BokConfig, DartConfig, SeibroConfig
from quant_agent.data.models import RawSourcePayload
from quant_agent.data.repository import DataRepository
from quant_agent.data.sources.bok import BokEcosClient, normalize_bok_observations
from quant_agent.data.sources.dart import OpenDartClient, normalize_corp_code_zip, normalize_financial_statement
from quant_agent.data.sources.seibro import LexiconSentimentScorer, SeibroReportClient, normalize_seibro_reports


class ExternalDataIngestionService:
    def __init__(
        self,
        repository: DataRepository | None = None,
        bok_config: BokConfig | None = None,
        dart_config: DartConfig | None = None,
        seibro_config: SeibroConfig | None = None,
    ) -> None:
        self.repository = repository or DataRepository()
        self.bok_client = BokEcosClient(bok_config or BokConfig.from_env())
        self.dart_client = OpenDartClient(dart_config or DartConfig.from_env())
        self.seibro_client = SeibroReportClient(seibro_config or SeibroConfig.from_env())
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
            written = self.repository.upsert_dart_financials(rows, run_id)
            self.repository.finish_ingestion_run(run_id, status="success")
            return written
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


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
