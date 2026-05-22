"""Airflow DAGs for Quant-Agent data engineering.

The module is import-safe outside Airflow so local unit tests can inspect it
without installing Apache Airflow.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import os

try:  # pragma: no cover - Airflow is an orchestration runtime dependency.
    from airflow.decorators import dag, task
except ImportError:  # pragma: no cover
    dag = None
    task = None


DEFAULT_DAILY_SCHEDULE = os.getenv("QUANT_AIRFLOW_DAILY_SCHEDULE", "30 18 * * 1-5")
DEFAULT_BACKFILL_SCHEDULE = os.getenv("QUANT_AIRFLOW_BACKFILL_SCHEDULE", None)
DEFAULT_START_DATE = datetime.fromisoformat(os.getenv("QUANT_AIRFLOW_START_DATE", "2026-01-01T00:00:00"))


def _symbols_from_env() -> tuple[str, ...]:
    return tuple(symbol.strip() for symbol in os.getenv("OHLCV_SYMBOLS", "").split(",") if symbol.strip())


if dag and task:  # pragma: no branch

    @dag(
        dag_id="quant_agent_daily_data_engineering",
        description="Daily OHLCV ingestion, TA-Lib precompute, and external data refresh.",
        schedule=DEFAULT_DAILY_SCHEDULE,
        start_date=DEFAULT_START_DATE,
        catchup=False,
        max_active_runs=1,
        default_args={"retries": int(os.getenv("QUANT_AIRFLOW_RETRIES", "2")), "retry_delay": timedelta(minutes=5)},
        tags=["quant-agent", "data-engineering"],
    )
    def daily_data_engineering():
        @task(task_id="ingest_ohlcv_daily")
        def ingest_ohlcv_daily(logical_date: str | None = None) -> dict:
            from quant_agent.data.config import OhlcvIngestionConfig
            from quant_agent.data.ingestion import OhlcvIngestionRequest, OhlcvIngestionService

            target_date = _target_date(logical_date)
            config = OhlcvIngestionConfig.from_env()
            result = OhlcvIngestionService().ingest_range(
                OhlcvIngestionRequest(
                    source=config.primary_source,
                    start_date=target_date,
                    end_date=target_date,
                    symbols=_symbols_from_env(),
                    dag_id="quant_agent_daily_data_engineering",
                    task_id="ingest_ohlcv_daily",
                )
            )
            return {"run_id": str(result.run_id), "rows_written": result.rows_written}

        @task(task_id="compute_ta_indicators_daily")
        def compute_ta_indicators_daily(logical_date: str | None = None) -> dict:
            from quant_agent.data.indicators.service import TechnicalIndicatorService

            target_date = _target_date(logical_date)
            counts = TechnicalIndicatorService().compute_and_store(
                start_date=target_date,
                end_date=target_date,
                symbols=list(_symbols_from_env()) or None,
            )
            return {"stored_rows": counts}

        @task(task_id="ingest_bok_daily")
        def ingest_bok_daily(logical_date: str | None = None) -> dict:
            from quant_agent.data.external import ExternalDataIngestionService

            series_configs = _json_env("BOK_DAILY_SERIES_JSON", [])
            if not series_configs:
                _skip("BOK_DAILY_SERIES_JSON is not configured.")
            target_date = _target_date(logical_date)
            period = target_date.strftime("%Y%m%d")
            service = ExternalDataIngestionService()
            written = 0
            for config in series_configs:
                written += service.ingest_bok_series(
                    stat_code=config["stat_code"],
                    cycle=config.get("cycle", "D"),
                    start_period=config.get("start_period", period),
                    end_period=config.get("end_period", period),
                    item_code1=config.get("item_code1", "?"),
                )
            return {"written": written}

        @task(task_id="ingest_dart_corp_codes_daily")
        def ingest_dart_corp_codes_daily() -> dict:
            from quant_agent.data.external import ExternalDataIngestionService

            if os.getenv("DART_REFRESH_CORP_CODES", "false").lower() != "true":
                _skip("DART_REFRESH_CORP_CODES is not true.")
            return {"written": ExternalDataIngestionService().ingest_dart_corp_codes()}

        @task(task_id="ingest_seibro_reports_daily")
        def ingest_seibro_reports_daily(logical_date: str | None = None) -> dict:
            from quant_agent.data.external import ExternalDataIngestionService

            endpoint = os.getenv("SEIBRO_REPORT_ENDPOINT")
            if not endpoint:
                _skip("SEIBRO_REPORT_ENDPOINT is not configured.")
            target_date = _target_date(logical_date)
            params = _json_env("SEIBRO_REPORT_PARAMS_JSON", {})
            written = ExternalDataIngestionService().ingest_seibro_reports(
                endpoint_path=endpoint,
                params=params,
                as_of_date=target_date,
                universe_min_score=float(os.getenv("SEIBRO_UNIVERSE_MIN_SCORE", "0.0")),
                universe_min_reports=int(os.getenv("SEIBRO_UNIVERSE_MIN_REPORTS", "1")),
            )
            return {"written": written}

        ingested = ingest_ohlcv_daily()
        computed = compute_ta_indicators_daily()
        bok = ingest_bok_daily()
        dart = ingest_dart_corp_codes_daily()
        seibro = ingest_seibro_reports_daily()
        ingested >> [computed, bok, seibro]
        # DART corp-code refresh is independent and intentionally has no upstream dependency.

    @dag(
        dag_id="quant_agent_backfill_ohlcv_10y",
        description="10-year OHLCV backfill using the configured primary source.",
        schedule=DEFAULT_BACKFILL_SCHEDULE,
        start_date=DEFAULT_START_DATE,
        catchup=False,
        max_active_runs=1,
        default_args={"retries": int(os.getenv("QUANT_AIRFLOW_RETRIES", "2")), "retry_delay": timedelta(minutes=10)},
        tags=["quant-agent", "data-engineering", "backfill"],
    )
    def backfill_ohlcv_10y():
        @task(task_id="backfill_ohlcv_10y")
        def backfill_ohlcv() -> dict:
            from quant_agent.data.config import OhlcvIngestionConfig
            from quant_agent.data.ingestion import OhlcvIngestionRequest, OhlcvIngestionService

            config = OhlcvIngestionConfig.from_env()
            end_date = date.today()
            start_date = end_date.replace(year=end_date.year - config.backfill_years)
            result = OhlcvIngestionService().ingest_range(
                OhlcvIngestionRequest(
                    source=config.primary_source,
                    start_date=start_date,
                    end_date=end_date,
                    symbols=_symbols_from_env(),
                    dag_id="quant_agent_backfill_ohlcv_10y",
                    task_id="backfill_ohlcv_10y",
                )
            )
            return {"run_id": str(result.run_id), "rows_written": result.rows_written}

        backfill_ohlcv()

    quant_agent_daily_data_engineering = daily_data_engineering()
    quant_agent_backfill_ohlcv_10y = backfill_ohlcv_10y()


def _target_date(logical_date: str | None) -> date:
    if logical_date:
        return date.fromisoformat(logical_date[:10])
    try:  # pragma: no cover - Airflow context only exists inside task runtime.
        from airflow.operators.python import get_current_context

        return get_current_context()["logical_date"].date()
    except (ImportError, KeyError, RuntimeError):
        return date.today()


def _json_env(name: str, default):
    raw = os.getenv(name)
    if not raw:
        return default
    return json.loads(raw)


def _skip(message: str) -> None:
    try:  # pragma: no cover - Airflow runtime only.
        from airflow.exceptions import AirflowSkipException

        raise AirflowSkipException(message)
    except ImportError:
        raise RuntimeError(message)
