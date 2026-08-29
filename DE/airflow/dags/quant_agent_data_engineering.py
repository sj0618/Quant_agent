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


if Path("/opt/airflow/DE").exists():
    DE_ROOT = Path("/opt/airflow/DE")        # 도커 컨테이너 내부 경로
    REPO_ROOT = Path("/opt/airflow/DE")
else:
    DE_ROOT = Path(__file__).resolve().parents[2]  # 로컬의 Quant-agent/DE 폴더
    REPO_ROOT = DE_ROOT.parent                     # 로컬의 Quant-agent 최상위 폴더

if str(DE_ROOT) not in sys.path:
    sys.path.insert(0, str(DE_ROOT))

from quant_agent.data.catalogs import BOK_SERIES_PRESETS  # noqa: E402


try:  # pragma: no cover - installed with Airflow in production.
    import pendulum
except ImportError:  # Local import-safe fallback.
    pendulum = None
    from zoneinfo import ZoneInfo

# 2. 한국 타임존 세팅 및 크론식에서 CRON_TZ 문구 제거 (순수 시간만 남김)
LOCAL_TZ = pendulum.timezone("Asia/Seoul") if pendulum else ZoneInfo("Asia/Seoul")
DEFAULT_DAILY_SCHEDULE = "0 10 * * *"
DEFAULT_OHLCV_REPAIR_SCHEDULE = "0 7 * * *"
DEFAULT_WICS_SCHEDULE = os.getenv("QUANT_AIRFLOW_WICS_SCHEDULE", "0 6 * * 1")
DEFAULT_PROMPT_RETENTION_SCHEDULE = "0 5 * * *"
PROMPT_RETENTION_DAG_ID = "quant_agent_ai_prompt_retention"
PROMPT_RETENTION_RETRIES = 3
PROMPT_RETENTION_RETRY_DELAY = timedelta(minutes=5)

DEFAULT_BACKFILL_SCHEDULE = os.getenv("QUANT_AIRFLOW_BACKFILL_SCHEDULE", None)

# 3. 뒤에 .replace(tzinfo=LOCAL_TZ)를 붙여 시작 날짜에 한국 타임존 주입
DEFAULT_START_DATE = datetime.fromisoformat(os.getenv("QUANT_AIRFLOW_START_DATE", "2026-01-01T00:00:00")).replace(tzinfo=LOCAL_TZ)
DEFAULT_TA_WARMUP_DAYS = int(os.getenv("QUANT_AIRFLOW_TA_WARMUP_DAYS", "365"))
DEFAULT_EXTERNAL_LOOKBACK_DAYS = int(os.getenv("QUANT_AIRFLOW_EXTERNAL_LOOKBACK_DAYS", "7"))
DEFAULT_OHLCV_REPAIR_LOOKBACK_DAYS = int(os.getenv("QUANT_AIRFLOW_OHLCV_REPAIR_LOOKBACK_DAYS", "7"))
DEFAULT_TRADING_CALENDAR_LOOKBACK_DAYS = int(os.getenv("QUANT_AIRFLOW_TRADING_CALENDAR_LOOKBACK_DAYS", "7"))
TRADING_CALENDAR_SCRIPT = Path(
    os.getenv("QUANT_AIRFLOW_TRADING_CALENDAR_SCRIPT", str(DE_ROOT / "scripts" / "refresh_krx_trading_calendar.py"))
)
WICS_SECTOR_SCRIPT = Path(
    os.getenv("QUANT_AIRFLOW_WICS_SECTOR_SCRIPT", str(DE_ROOT / "scripts" / "ingest_wics_sectors.py"))
)
EXTERNAL_DATA_SCRIPT = Path(
    os.getenv("QUANT_AIRFLOW_EXTERNAL_DATA_SCRIPT", str(DE_ROOT / "scripts" / "ingest_external_data.py"))
)
KIS_ADJUSTED_INGEST_SCRIPT = Path(
    os.getenv("QUANT_AIRFLOW_KIS_ADJUSTED_INGEST_SCRIPT", str(DE_ROOT / "scripts" / "ingest_kis_adjusted_ohlcv.py"))
)
DART_BOK_INGEST_SCRIPT = Path(
    os.getenv("QUANT_AIRFLOW_DART_BOK_INGEST_SCRIPT", str(DE_ROOT / "scripts" / "ingest_dart_bok_history.py"))
)
TA_PIPELINE_SCRIPT = Path(
    os.getenv("QUANT_AIRFLOW_TA_PIPELINE_SCRIPT", str(DE_ROOT / "scripts" / "compute_technical_indicators_pipeline.py"))
)
QA_CHECK_SCRIPT = Path(
    os.getenv("QUANT_AIRFLOW_QA_CHECK_SCRIPT", str(DE_ROOT / "scripts" / "run_data_quality_checks.py"))
)
SYMBOL_METADATA_SCRIPT = Path(
    os.getenv("QUANT_AIRFLOW_SYMBOL_METADATA_SCRIPT", str(DE_ROOT / "scripts" / "refresh_symbol_metadata.py"))
)
PROMPT_RETENTION_SCRIPT = DE_ROOT / "scripts" / "purge_ai_prompt_logs.py"
PYTHON_EXECUTABLE = os.getenv("QUANT_AIRFLOW_PYTHON", sys.executable)

DEFAULT_BOK_RATE_FX_SERIES = BOK_SERIES_PRESETS["rate-fx"]
DEFAULT_BOK_MONTHLY_OIL_SERIES = tuple(
    item for item in BOK_SERIES_PRESETS["all-macro"] if item not in DEFAULT_BOK_RATE_FX_SERIES
)
DEFAULT_BOK_SERIES_JSON = json.dumps(
    list(BOK_SERIES_PRESETS["all-macro"]),
    ensure_ascii=False,
    separators=(",", ":"),
)


def _symbols_from_env() -> tuple[str, ...]:
    return tuple(symbol.strip() for symbol in os.getenv("OHLCV_SYMBOLS", "").split(",") if symbol.strip())


def _bok_series_json() -> str:
    return os.getenv("BOK_SERIES_JSON") or os.getenv("BOK_DAILY_SERIES_JSON") or DEFAULT_BOK_SERIES_JSON


def _ta_worker_count() -> int | None:
    raw = os.getenv("QUANT_TA_MAX_WORKERS")
    if raw is None or raw.strip() == "":
        return None
    workers = int(raw)
    if workers < 1:
        raise ValueError("QUANT_TA_MAX_WORKERS must be >= 1.")
    return workers


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
        @task(task_id="refresh_krx_trading_calendar_daily")
        def refresh_krx_trading_calendar_daily(logical_date: str | None = None, data_interval_end: str | None = None) -> dict:
            run_date = _run_reference_date(logical_date, data_interval_end)
            return _run_python_script(
                TRADING_CALENDAR_SCRIPT,
                _trading_calendar_args(
                    start_date=run_date - timedelta(days=DEFAULT_TRADING_CALENDAR_LOOKBACK_DAYS),
                    end_date=run_date,
                ),
            )

        @task(task_id="ingest_ohlcv_daily")
        def ingest_ohlcv_daily(logical_date: str | None = None, data_interval_end: str | None = None) -> dict:
            from quant_agent.data.config import OhlcvIngestionConfig
            from quant_agent.data.ingestion import OhlcvIngestionRequest, OhlcvIngestionService

            target_date = _previous_run_trade_date(logical_date, data_interval_end)
            start_date, end_date = _daily_ohlcv_ingest_window(target_date)
            config = OhlcvIngestionConfig.from_env()
            result = OhlcvIngestionService().ingest_range(
                OhlcvIngestionRequest(
                    source=config.primary_source,
                    start_date=start_date,
                    end_date=end_date,
                    symbols=_symbols_from_env(),
                    dag_id="quant_agent_daily_data_engineering",
                    task_id="ingest_ohlcv_daily",
                )
            )
            return {"run_id": str(result.run_id), "rows_written": result.rows_written}

        @task(task_id="compute_ta_indicators_daily")
        def compute_ta_indicators_daily(logical_date: str | None = None, data_interval_end: str | None = None) -> dict:
            target_date = _previous_run_trade_date(logical_date, data_interval_end)
            start_date = _warmup_start_date(target_date)
            return _run_python_script(
                TA_PIPELINE_SCRIPT,
                _technical_indicator_args(start_date=start_date, end_date=target_date),
            )

        @task(task_id="ingest_kis_adjusted_ohlcv_daily")
        def ingest_kis_adjusted_ohlcv_daily(logical_date: str | None = None, data_interval_end: str | None = None) -> dict:
            target_date = _previous_run_trade_date(logical_date, data_interval_end)
            return _run_python_script(
                KIS_ADJUSTED_INGEST_SCRIPT,
                _kis_adjusted_ingest_args(start_date=target_date, end_date=target_date),
            )

        @task(task_id="refresh_symbol_metadata_daily")
        def refresh_symbol_metadata_daily(logical_date: str | None = None, data_interval_end: str | None = None) -> dict:
            target_date = _previous_run_trade_date(logical_date, data_interval_end)
            return _run_python_script(
                SYMBOL_METADATA_SCRIPT,
                _symbol_metadata_args(as_of_date=target_date),
            )

        @task(task_id="run_data_quality_checks_daily")
        def run_data_quality_checks_daily(logical_date: str | None = None, data_interval_end: str | None = None) -> dict:
            target_date = _previous_run_trade_date(logical_date, data_interval_end)
            start_date = _warmup_start_date(target_date)
            return _run_python_script(
                QA_CHECK_SCRIPT,
                _data_quality_args(start_date=start_date, end_date=target_date),
            )

        @task(task_id="ingest_bok_daily")
        def ingest_bok_daily(logical_date: str | None = None, data_interval_end: str | None = None) -> dict:
            from quant_agent.data.config import BokConfig

            if not BokConfig.from_env().is_configured:
                _skip("BOK_API_KEY is not configured.")
            target_date = _previous_run_trade_date(logical_date, data_interval_end)
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
        def ingest_dart_financials_daily(logical_date: str | None = None, data_interval_end: str | None = None) -> dict:
            target_date = _previous_run_trade_date(logical_date, data_interval_end)
            return _run_python_script(
                DART_BOK_INGEST_SCRIPT,
                _dart_bok_ingest_args(
                    source="dart",
                    start_date=_external_ingest_start_date(target_date),
                    end_date=target_date,
                ),
            )

        calendar = refresh_krx_trading_calendar_daily()
        ingested = ingest_ohlcv_daily()
        symbol_metadata = refresh_symbol_metadata_daily()
        kis_adjusted = ingest_kis_adjusted_ohlcv_daily()
        computed = compute_ta_indicators_daily()
        qa = run_data_quality_checks_daily()
        bok = ingest_bok_daily()
        dart = ingest_dart_financials_daily()
        calendar >> ingested
        ingested >> [symbol_metadata, kis_adjusted, bok]
        symbol_metadata >> qa
        symbol_metadata >> dart
        kis_adjusted >> computed
        computed >> qa
        bok >> qa
        dart >> qa

    @dag(
        dag_id="quant_agent_ohlcv_repair",
        description="Morning OHLCV repair run for late KRX publication.",
        schedule=DEFAULT_OHLCV_REPAIR_SCHEDULE,
        start_date=DEFAULT_START_DATE,
        catchup=False,
        max_active_runs=1,
        default_args={"retries": int(os.getenv("QUANT_AIRFLOW_RETRIES", "3")), "retry_delay": timedelta(minutes=5)},
        tags=["quant-agent", "data-engineering", "repair"],
    )
    def ohlcv_repair():
        @task(task_id="ingest_ohlcv_daily")
        def ingest_ohlcv_daily(logical_date: str | None = None, data_interval_end: str | None = None) -> dict:
            from quant_agent.data.config import OhlcvIngestionConfig
            from quant_agent.data.ingestion import OhlcvIngestionRequest, OhlcvIngestionService

            run_date = _run_reference_date(logical_date, data_interval_end)
            start_date, end_date = _repair_ohlcv_ingest_window(run_date)
            config = OhlcvIngestionConfig.from_env()
            result = OhlcvIngestionService().ingest_range(
                OhlcvIngestionRequest(
                    source=config.primary_source,
                    start_date=start_date,
                    end_date=end_date,
                    symbols=_symbols_from_env(),
                    dag_id="quant_agent_ohlcv_repair",
                    task_id="ingest_ohlcv_daily",
                )
            )
            return {"run_id": str(result.run_id), "rows_written": result.rows_written}

        @task(task_id="refresh_symbol_metadata_daily")
        def refresh_symbol_metadata_daily(logical_date: str | None = None, data_interval_end: str | None = None) -> dict:
            target_date = _target_date(
                logical_date,
                data_interval_end,
                include_same_day_trade_date=False,
            )
            return _run_python_script(
                SYMBOL_METADATA_SCRIPT,
                _symbol_metadata_args(as_of_date=target_date),
            )

        @task(task_id="run_data_quality_checks_daily")
        def run_data_quality_checks_daily(logical_date: str | None = None, data_interval_end: str | None = None) -> dict:
            target_date = _target_date(
                logical_date,
                data_interval_end,
                include_same_day_trade_date=False,
            )
            start_date = _warmup_start_date(target_date)
            return _run_python_script(
                QA_CHECK_SCRIPT,
                _data_quality_args(start_date=start_date, end_date=target_date),
            )

        ingested = ingest_ohlcv_daily()
        symbol_metadata = refresh_symbol_metadata_daily()
        qa = run_data_quality_checks_daily()
        ingested >> symbol_metadata >> qa

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

    @dag(
        dag_id=PROMPT_RETENTION_DAG_ID,
        description="Delete AI prompt and response content older than 90 days.",
        schedule=DEFAULT_PROMPT_RETENTION_SCHEDULE,
        start_date=DEFAULT_START_DATE,
        catchup=False,
        max_active_runs=1,
        default_args={"retries": PROMPT_RETENTION_RETRIES, "retry_delay": PROMPT_RETENTION_RETRY_DELAY},
        tags=["quant-agent", "ai", "retention"],
    )
    def ai_prompt_retention():
        @task(task_id="purge_ai_prompt_logs")
        def purge_ai_prompt_logs() -> dict:
            return _run_python_script(PROMPT_RETENTION_SCRIPT, [])

        purge_ai_prompt_logs()

    quant_agent_daily_data_engineering = daily_data_engineering()

    @dag(
        dag_id="quant_agent_wics_sector_snapshot",
        description="Periodic FnGuide WICS sector membership snapshot with history tracking.",
        schedule=DEFAULT_WICS_SCHEDULE,
        start_date=DEFAULT_START_DATE,
        catchup=False,
        max_active_runs=1,
        default_args={"retries": int(os.getenv("QUANT_AIRFLOW_RETRIES", "3")), "retry_delay": timedelta(minutes=10)},
        tags=["quant-agent", "data-engineering", "wics"],
    )
    def wics_sector_snapshot():
        @task(task_id="refresh_kind_symbol_metadata")
        def refresh_kind_symbol_metadata(logical_date: str | None = None, data_interval_end: str | None = None) -> dict:
            run_date = _run_reference_date(logical_date, data_interval_end)
            return _run_python_script(
                EXTERNAL_DATA_SCRIPT,
                ["--job", "kind-sector", "--as-of-date", run_date.isoformat()],
            )

        @task(task_id="ingest_wics_sector_snapshot")
        def ingest_wics_sector_snapshot(logical_date: str | None = None, data_interval_end: str | None = None) -> dict:
            run_date = _run_reference_date(logical_date, data_interval_end)
            return _run_python_script(WICS_SECTOR_SCRIPT, ["--as-of-date", run_date.isoformat()])

        kind_metadata = refresh_kind_symbol_metadata()
        wics = ingest_wics_sector_snapshot()
        kind_metadata >> wics

    quant_agent_wics_sector_snapshot = wics_sector_snapshot()
    quant_agent_ohlcv_repair = ohlcv_repair()
    quant_agent_backfill_ohlcv_10y = backfill_ohlcv_10y()
    quant_agent_ai_prompt_retention = ai_prompt_retention()


def _target_date(logical_date, data_interval_end=None, *, include_same_day_trade_date: bool) -> date:
    reference = data_interval_end or logical_date
    if reference:
        # Airflow context는 UTC 또는 tz-aware datetime일 수 있으므로, 먼저 한국시간 기준 날짜로 맞춘다.
        if isinstance(reference, datetime):
            run_date = reference.astimezone(LOCAL_TZ).date() if reference.tzinfo else reference.replace(tzinfo=LOCAL_TZ).date()
        elif isinstance(reference, date):
            run_date = reference
        elif isinstance(reference, str):
            parsed = datetime.fromisoformat(reference)
            run_date = parsed.astimezone(LOCAL_TZ).date() if parsed.tzinfo else parsed.date()
        elif hasattr(reference, "date"):
            candidate = reference.date()
            run_date = candidate.astimezone(LOCAL_TZ).date() if isinstance(candidate, datetime) else candidate
        else:
            run_date = date.today()

        from quant_agent.data.repository import DataRepository

        rows = DataRepository().executor.fetch_json(
            _krx_trade_date_query(
                run_date,
                include_same_day_trade_date=include_same_day_trade_date,
            )
        )
        raw_trade_date = rows[0].get("trade_date") if rows else None
        if not raw_trade_date:
            operator = "<=" if include_same_day_trade_date else "<"
            raise ValueError(f"No KRX open trade date found {operator} {run_date.isoformat()}.")
        return date.fromisoformat(str(raw_trade_date))

    try:  # pragma: no cover - Airflow context only exists inside task runtime.
        from airflow.operators.python import get_current_context

        context = get_current_context()
        return _target_date(
            context.get("logical_date"),
            context.get("data_interval_end"),
            include_same_day_trade_date=include_same_day_trade_date,
        )
    except (ImportError, KeyError, RuntimeError):
        return date.today()


def _krx_trade_date_query(run_date: date, *, include_same_day_trade_date: bool) -> str:
    operator = "<=" if include_same_day_trade_date else "<"
    return f"""
            SELECT MAX(trade_date)::text AS trade_date
              FROM core.trading_calendar
             WHERE market = 'KRX'
               AND is_open = TRUE
               AND trade_date {operator} DATE '{run_date.isoformat()}'
            """


def _run_reference_date(logical_date, data_interval_end=None) -> date:
    """Resolve the run's calendar date (KST) from the Airflow context.

    Unlike ``_target_date`` this never consults ``core.trading_calendar``, so it is
    safe to use as the *end* anchor of an ingestion window: the OHLCV ingest date must
    advance with the wall-clock schedule, not with what the pipeline has already
    stored. (Deriving the ingest date from the calendar - which is written only from
    bars this pipeline ingested - is what made daily ingestion re-fetch the last
    backfilled day forever and never reach new KRX sessions.)
    """

    reference = data_interval_end or logical_date
    if reference:
        if isinstance(reference, datetime):
            return reference.astimezone(LOCAL_TZ).date() if reference.tzinfo else reference.replace(tzinfo=LOCAL_TZ).date()
        if isinstance(reference, date):
            return reference
        if isinstance(reference, str):
            parsed = datetime.fromisoformat(reference)
            return parsed.astimezone(LOCAL_TZ).date() if parsed.tzinfo else parsed.date()
        if hasattr(reference, "date"):
            candidate = reference.date()
            return candidate.astimezone(LOCAL_TZ).date() if isinstance(candidate, datetime) else candidate
        return date.today()

    try:  # pragma: no cover - Airflow context only exists inside task runtime.
        from airflow.operators.python import get_current_context

        context = get_current_context()
        return _run_reference_date(context.get("logical_date"), context.get("data_interval_end"))
    except (ImportError, KeyError, RuntimeError):
        return date.today()


def _previous_run_trade_date(logical_date=None, data_interval_end=None) -> date:
    """Use the prior wall-clock date without depending on a self-written calendar.

    The daily 10:00 KST run must request the previous date even when KRX has not
    published rows yet.  KRX holidays and weekends remain harmless empty requests,
    while a stale ``core.trading_calendar`` cannot pin the ingestion high-water mark.
    """

    return _run_reference_date(logical_date, data_interval_end) - timedelta(days=1)


def _latest_ingested_krx_trade_date() -> date | None:
    """Most recent KRX open day already stored, or None on a cold warehouse."""

    from quant_agent.data.repository import DataRepository

    rows = DataRepository().executor.fetch_json(
        """
        SELECT MAX(trade_date)::text AS trade_date
          FROM core.trading_calendar
         WHERE market = 'KRX'
           AND is_open = TRUE
        """
    )
    raw_latest = rows[0].get("trade_date") if rows else None
    return date.fromisoformat(str(raw_latest)) if raw_latest else None


def _daily_ohlcv_ingest_window(run_date: date) -> tuple[date, date]:
    """Daily OHLCV ingest window: resume from the high-water mark, end at run_date.

    The window's end is the schedule's own date rather than ``MAX(trading_calendar)``,
    which is what lets ingestion advance and self-heal any gap since the last
    successful run. KRX itself decides which days in the window are trading days, so
    non-trading days in the span are harmless no-ops. A cold warehouse ingests only
    run_date; large historical loads are the backfill DAG's job.
    """

    latest = _latest_ingested_krx_trade_date()
    if latest is None:
        return run_date, run_date
    start = min(latest + timedelta(days=1), run_date)
    return start, run_date


def _repair_ohlcv_ingest_window(run_date: date) -> tuple[date, date]:
    """Morning repair window: re-fetch a trailing span ending at run_date.

    Repair exists to pick up KRX's late-published or corrected sessions, so it
    re-requests recent days unconditionally (the upsert is idempotent) instead of only
    filling forward. Anchoring the end to run_date - not ``MAX(trading_calendar)`` -
    also keeps repair from wedging on the last stored day.
    """

    start = run_date - timedelta(days=DEFAULT_OHLCV_REPAIR_LOOKBACK_DAYS)
    return start, run_date


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
    ]
    workers = _ta_worker_count()
    if workers is not None:
        args.extend(["--workers", str(workers)])
    args.extend([
        "--input-price-source",
        "kis-adjusted",
    ])
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


def _trading_calendar_args(*, start_date: date, end_date: date) -> list[str]:
    return [
        "--start-date",
        start_date.isoformat(),
        "--end-date",
        end_date.isoformat(),
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
