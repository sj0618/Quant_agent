"""Airflow DAGs for Quant-Agent data engineering.

The module is import-safe outside Airflow so local unit tests can inspect it
without installing Apache Airflow.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys

try:  # pragma: no cover - Airflow is an orchestration runtime dependency.
    from airflow.decorators import dag, task
except ImportError:  # pragma: no cover
    dag = None
    task = None


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_airflow_dotenv() -> None:
    if os.getenv("QUANT_AIRFLOW_LOAD_DOTENV", "true").lower() in {"0", "false", "no", "off"}:
        return
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv is a runtime dependency in this repo.
        return
    dotenv_path = Path(os.getenv("QUANT_AIRFLOW_DOTENV_PATH", str(REPO_ROOT / ".env")))
    load_dotenv(dotenv_path=dotenv_path, override=False)


_load_airflow_dotenv()

DEFAULT_DAILY_SCHEDULE = os.getenv("QUANT_AIRFLOW_DAILY_SCHEDULE", "0 4 * * *")
DEFAULT_BACKFILL_SCHEDULE = os.getenv("QUANT_AIRFLOW_BACKFILL_SCHEDULE", None)
DEFAULT_START_DATE = datetime.fromisoformat(os.getenv("QUANT_AIRFLOW_START_DATE", "2026-01-01T00:00:00"))
DEFAULT_TA_WARMUP_DAYS = int(os.getenv("QUANT_AIRFLOW_TA_WARMUP_DAYS", "365"))
DEFAULT_EXTERNAL_LOOKBACK_DAYS = int(os.getenv("QUANT_AIRFLOW_EXTERNAL_LOOKBACK_DAYS", "7"))
KIS_ADJUSTED_INGEST_SCRIPT = Path(
    os.getenv("QUANT_AIRFLOW_KIS_ADJUSTED_INGEST_SCRIPT", str(REPO_ROOT / "scripts" / "ingest_kis_adjusted_ohlcv.py"))
)
DART_BOK_INGEST_SCRIPT = Path(
    os.getenv("QUANT_AIRFLOW_DART_BOK_INGEST_SCRIPT", str(REPO_ROOT / "scripts" / "ingest_dart_bok_history.py"))
)
EXTERNAL_INGEST_SCRIPT = Path(
    os.getenv("QUANT_AIRFLOW_EXTERNAL_INGEST_SCRIPT", str(REPO_ROOT / "scripts" / "ingest_external_data.py"))
)
TA_PIPELINE_SCRIPT = Path(
    os.getenv("QUANT_AIRFLOW_TA_PIPELINE_SCRIPT", str(REPO_ROOT / "scripts" / "compute_technical_indicators_pipeline.py"))
)
QA_CHECK_SCRIPT = Path(
    os.getenv("QUANT_AIRFLOW_QA_CHECK_SCRIPT", str(REPO_ROOT / "scripts" / "run_data_quality_checks.py"))
)
SYMBOL_METADATA_SCRIPT = Path(
    os.getenv("QUANT_AIRFLOW_SYMBOL_METADATA_SCRIPT", str(REPO_ROOT / "scripts" / "refresh_symbol_metadata.py"))
)
PYTHON_EXECUTABLE = os.getenv("QUANT_AIRFLOW_PYTHON", sys.executable)

DEFAULT_BOK_RATE_FX_SERIES = (
    {"stat_code": "722Y001", "cycle": "D", "item_code1": "0101000"},  # 한국은행 기준금리
    {"stat_code": "817Y002", "cycle": "D", "item_code1": "010101000"},  # 콜금리(1일, 전체거래)
    {"stat_code": "817Y002", "cycle": "D", "item_code1": "010901000"},  # KOFR
    {"stat_code": "817Y002", "cycle": "D", "item_code1": "010502000"},  # CD(91일)
    {"stat_code": "817Y002", "cycle": "D", "item_code1": "010190000"},  # 국고채(1년)
    {"stat_code": "817Y002", "cycle": "D", "item_code1": "010200000"},  # 국고채(3년)
    {"stat_code": "817Y002", "cycle": "D", "item_code1": "010210000"},  # 국고채(10년)
    {"stat_code": "817Y002", "cycle": "D", "item_code1": "010300000"},  # 회사채(3년, AA-)
    {"stat_code": "817Y002", "cycle": "D", "item_code1": "010320000"},  # 회사채(3년, BBB-)
    {"stat_code": "731Y003", "cycle": "D", "item_code1": "0000003"},  # 원/달러 종가 15:30
    {"stat_code": "731Y003", "cycle": "D", "item_code1": "0000006"},  # 원/100엔
    {"stat_code": "731Y003", "cycle": "D", "item_code1": "0000010"},  # 원/위안 종가
)
DEFAULT_BOK_MONTHLY_OIL_SERIES = (
    {"stat_code": "902Y003", "cycle": "M", "item_code1": "010101", "language": "en"},  # WTI
    {"stat_code": "902Y003", "cycle": "M", "item_code1": "010102", "language": "en"},  # Dubai Fateh
    {"stat_code": "902Y003", "cycle": "M", "item_code1": "010103", "language": "en"},  # Brent
)
DEFAULT_BOK_SERIES_JSON = json.dumps(
    [*DEFAULT_BOK_RATE_FX_SERIES, *DEFAULT_BOK_MONTHLY_OIL_SERIES],
    ensure_ascii=False,
    separators=(",", ":"),
)


def _symbols_from_env() -> tuple[str, ...]:
    return tuple(symbol.strip() for symbol in os.getenv("OHLCV_SYMBOLS", "").split(",") if symbol.strip())


def _bok_series_json() -> str:
    return os.getenv("BOK_SERIES_JSON") or os.getenv("BOK_DAILY_SERIES_JSON") or DEFAULT_BOK_SERIES_JSON


if dag and task:  # pragma: no branch

    @dag(
        dag_id="quant_agent_daily_data_engineering",
        description="Daily OHLCV ingestion, TA-Lib precompute, and external data refresh.",
        schedule=DEFAULT_DAILY_SCHEDULE,
        start_date=DEFAULT_START_DATE,
        catchup=False,
        max_active_runs=1,
        default_args={"retries": int(os.getenv("QUANT_AIRFLOW_RETRIES", "3")), "retry_delay": timedelta(minutes=5)},
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
            target_date = _target_date(logical_date)
            start_date = _warmup_start_date(target_date)
            return _run_python_script(
                TA_PIPELINE_SCRIPT,
                _technical_indicator_args(start_date=start_date, end_date=target_date),
            )

        @task(task_id="ingest_kis_adjusted_ohlcv_daily")
        def ingest_kis_adjusted_ohlcv_daily(logical_date: str | None = None) -> dict:
            target_date = _target_date(logical_date)
            return _run_python_script(
                KIS_ADJUSTED_INGEST_SCRIPT,
                _kis_adjusted_ingest_args(start_date=target_date, end_date=target_date),
            )

        @task(task_id="refresh_symbol_metadata_daily")
        def refresh_symbol_metadata_daily(logical_date: str | None = None) -> dict:
            target_date = _target_date(logical_date)
            return _run_python_script(
                SYMBOL_METADATA_SCRIPT,
                _symbol_metadata_args(as_of_date=target_date),
            )

        @task(task_id="refresh_symbol_sector_daily")
        def refresh_symbol_sector_daily(logical_date: str | None = None) -> dict:
            target_date = _target_date(logical_date)
            return _run_python_script(
                EXTERNAL_INGEST_SCRIPT,
                _kind_sector_args(as_of_date=target_date),
            )

        @task(task_id="run_data_quality_checks_daily")
        def run_data_quality_checks_daily(logical_date: str | None = None) -> dict:
            target_date = _target_date(logical_date)
            start_date = _warmup_start_date(target_date)
            return _run_python_script(
                QA_CHECK_SCRIPT,
                _data_quality_args(start_date=start_date, end_date=target_date),
            )

        @task(task_id="ingest_bok_daily")
        def ingest_bok_daily(logical_date: str | None = None) -> dict:
            from quant_agent.data.config import BokConfig

            if not BokConfig.from_env().is_configured:
                _skip("BOK_API_KEY is not configured.")
            target_date = _target_date(logical_date)
            return _run_python_script(
                DART_BOK_INGEST_SCRIPT,
                _dart_bok_ingest_args(
                    source="bok",
                    start_date=_external_ingest_start_date(target_date),
                    end_date=target_date,
                    bok_series_json=_bok_series_json(),
                ),
            )

        @task(task_id="ingest_dart_financials_daily")
        def ingest_dart_financials_daily(logical_date: str | None = None) -> dict:
            target_date = _target_date(logical_date)
            return _run_python_script(
                DART_BOK_INGEST_SCRIPT,
                _dart_bok_ingest_args(
                    source="dart",
                    start_date=_external_ingest_start_date(target_date),
                    end_date=target_date,
                ),
            )

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
        symbol_metadata = refresh_symbol_metadata_daily()
        sector_metadata = refresh_symbol_sector_daily()
        kis_adjusted = ingest_kis_adjusted_ohlcv_daily()
        computed = compute_ta_indicators_daily()
        qa = run_data_quality_checks_daily()
        bok = ingest_bok_daily()
        dart = ingest_dart_financials_daily()
        seibro = ingest_seibro_reports_daily()
        ingested >> [symbol_metadata, kis_adjusted, bok, seibro]
        symbol_metadata >> sector_metadata >> qa
        symbol_metadata >> dart
        kis_adjusted >> computed
        computed >> qa

    @dag(
        dag_id="quant_agent_backfill_ohlcv_10y",
        description="10-year OHLCV backfill using the configured primary source.",
        schedule=DEFAULT_BACKFILL_SCHEDULE,
        start_date=DEFAULT_START_DATE,
        catchup=False,
        max_active_runs=1,
        default_args={"retries": int(os.getenv("QUANT_AIRFLOW_RETRIES", "3")), "retry_delay": timedelta(minutes=10)},
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


def _warmup_start_date(target_date: date) -> date:
    return target_date - timedelta(days=DEFAULT_TA_WARMUP_DAYS)


def _external_ingest_start_date(target_date: date) -> date:
    return target_date - timedelta(days=DEFAULT_EXTERNAL_LOOKBACK_DAYS)


def _kis_adjusted_ingest_args(*, start_date: date, end_date: date) -> list[str]:
    args = [
        "--start-date",
        start_date.isoformat(),
        "--end-date",
        end_date.isoformat(),
    ]
    symbols = _symbols_from_env()
    if symbols:
        args.extend(["--tickers", ",".join(symbols)])
    return args


def _technical_indicator_args(*, start_date: date, end_date: date) -> list[str]:
    args = [
        "--start-date",
        start_date.isoformat(),
        "--end-date",
        end_date.isoformat(),
        "--input-price-source",
        "kis-adjusted",
    ]
    symbols = _symbols_from_env()
    if symbols:
        args.extend(["--tickers", ",".join(symbols)])
    return args


def _data_quality_args(*, start_date: date, end_date: date) -> list[str]:
    return [
        "--start-date",
        start_date.isoformat(),
        "--end-date",
        end_date.isoformat(),
        "--checks",
        "all",
    ]


def _symbol_metadata_args(*, as_of_date: date) -> list[str]:
    return [
        "--as-of-date",
        as_of_date.isoformat(),
    ]


def _kind_sector_args(*, as_of_date: date) -> list[str]:
    return [
        "--job",
        "kind-sector",
        "--as-of-date",
        as_of_date.isoformat(),
    ]


def _dart_bok_ingest_args(
    *, source: str, start_date: date, end_date: date, bok_series_json: str | None = None
) -> list[str]:
    args = [
        "--scope",
        "custom",
        "--sources",
        source,
        "--start-date",
        start_date.isoformat(),
        "--end-date",
        end_date.isoformat(),
        "--dag-id",
        "quant_agent_daily_data_engineering",
    ]
    if source == "dart":
        args.extend(["--dart-period-mode", os.getenv("DART_DAILY_PERIOD_MODE", "filing-window")])
        if os.getenv("DART_REFRESH_CORP_CODES", "true").lower() not in {"0", "false", "no", "off"}:
            args.append("--dart-refresh-corp-codes")
    elif source == "bok" and bok_series_json:
        args.extend(["--bok-series-json", bok_series_json])
    return args


def _run_python_script(script_path: Path, args: list[str]) -> dict:
    command = [PYTHON_EXECUTABLE, str(script_path), *args]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"{script_path.name} failed with exit code {completed.returncode}: "
            f"{_tail(completed.stderr or completed.stdout)}"
        )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": _tail(completed.stdout),
        "stderr": _tail(completed.stderr),
    }


def _tail(text: str, limit: int = 4000) -> str:
    return text[-limit:] if len(text) > limit else text


def _skip(message: str) -> None:
    try:  # pragma: no cover - Airflow runtime only.
        from airflow.exceptions import AirflowSkipException

        raise AirflowSkipException(message)
    except ImportError:
        raise RuntimeError(message)
