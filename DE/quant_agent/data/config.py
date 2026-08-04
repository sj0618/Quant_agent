"""Configuration for Quant-Agent data engineering.

This module intentionally does not call ``load_dotenv``. Secrets must be
provided by the runtime environment, Airflow Connections, or a secret backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import os


DEFAULT_KRX_DAILY_MARKET_ENDPOINTS = (
    "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd",
    "https://data-dbg.krx.co.kr/svc/apis/sto/ksq_bydd_trd",
)
DEFAULT_KIS_REAL_BASE_URL = "https://openapi.koreainvestment.com:9443"
DEFAULT_KIS_VIRTUAL_BASE_URL = "https://openapivts.koreainvestment.com:29443"
DEFAULT_KIS_DAILY_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
DEFAULT_KIS_TOKEN_PATH = "/oauth2/tokenP"
DEFAULT_KIS_ADJUSTED_PRICE_FLAG = "0"
DEFAULT_KIS_ORIGINAL_PRICE_FLAG = "1"

DEFAULT_PILOT_SYMBOL = "005930"
DEFAULT_PILOT_LOOKBACK_DAYS = 30
DEFAULT_MIN_SYMBOL_COVERAGE = 0.70
DEFAULT_PILOT_MAX_PRICE_ISSUE_RATIO = 0.05
DEFAULT_REQUEST_TIMEOUT_SECONDS = 20
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 1.0
DEFAULT_DB_HOST = "127.0.0.1"
DEFAULT_DB_PORT = 5432
DEFAULT_DB_NAME = "quant_agent"
DEFAULT_DB_USER = "quant_agent"
DEFAULT_DB_CONTAINER = "quant-agent-db"
DEFAULT_DB_EXECUTION_MODE = "psycopg"
DEFAULT_OHLCV_BATCH_DAYS = 1
DEFAULT_OHLCV_BACKFILL_YEARS = 10
DEFAULT_TA_TRANSFORM_VERSION = "ta-lib-0.6.8"
DEFAULT_SEIBRO_BASE_URL = "https://openplatform.seibro.or.kr"
DEFAULT_SEIBRO_WEB_BASE_URL = "https://seibro.or.kr"
DEFAULT_SEIBRO_ANALYST_REPORT_PAGE_PATH = (
    "/websquare/control.jsp?w2xPath=/IPORTAL/user/company/BIP_CNTS01019V.xml&menuNo=16"
)
DEFAULT_SEIBRO_ANALYST_REPORT_API_PATH = "/websquare/engine/proworks/callServletService.jsp"
DEFAULT_SEIBRO_ANALYST_REPORT_ACTION = "entrAnalysisSummaryReportPList"
DEFAULT_SEIBRO_ANALYST_REPORT_TASK = "ksd.safe.bip.cnts.Company.process.EntrAnalysisPTask"
DEFAULT_SEIBRO_ANALYST_REPORT_PAGE_SIZE = 500
DEFAULT_SEIBRO_ANALYST_REPORT_CHUNK_MONTHS = 1
DEFAULT_SEIBRO_REQUEST_SLEEP_MIN_SECONDS = 1.0
DEFAULT_SEIBRO_REQUEST_SLEEP_MAX_SECONDS = 3.0
DEFAULT_BOK_BASE_URL = "https://ecos.bok.or.kr/api"
DEFAULT_DART_BASE_URL = "https://opendart.fss.or.kr/api"
DEFAULT_KIND_CORP_LIST_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do"
DEFAULT_WICS_COMPANY_INFO_URL = "https://wcomp.fnguide.com/CompanyInfo/Information"
DEFAULT_WICS_REQUEST_WORKERS = 4


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _env_values(*names: str) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for name in names:
        value = _env(name)
        if value is None:
            continue
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        values.append(normalized)
    return tuple(values)


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    return default if raw is None else float(raw)


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    return default if raw is None else int(raw)


@dataclass(frozen=True)
class RetryConfig:
    attempts: int = DEFAULT_RETRY_ATTEMPTS
    backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS

    @classmethod
    def from_env(cls) -> "RetryConfig":
        return cls(
            attempts=_env_int("API_RETRY_MAX_ATTEMPTS", DEFAULT_RETRY_ATTEMPTS),
            backoff_seconds=_env_float("API_RETRY_BACKOFF_SECONDS", DEFAULT_RETRY_BACKOFF_SECONDS),
        )


@dataclass(frozen=True)
class KrxConfig:
    api_key: str | None
    daily_market_endpoints: tuple[str, ...]
    request_timeout_seconds: int
    retry: RetryConfig

    @classmethod
    def from_env(cls) -> "KrxConfig":
        endpoints = _env("KRX_DAILY_MARKET_ENDPOINTS")
        return cls(
            api_key=_env("KRX_API_KEY"),
            daily_market_endpoints=_parse_endpoint_list(endpoints, DEFAULT_KRX_DAILY_MARKET_ENDPOINTS),
            request_timeout_seconds=_env_int("API_REQUEST_TIMEOUT_SECONDS", DEFAULT_REQUEST_TIMEOUT_SECONDS),
            retry=RetryConfig.from_env(),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class KisConfig:
    app_key: str | None
    app_secret: str | None
    access_token: str | None
    base_url: str
    daily_price_path: str
    token_path: str
    adjusted_price_flag: str
    original_price_flag: str
    request_timeout_seconds: int
    retry: RetryConfig

    @classmethod
    def from_env(cls) -> "KisConfig":
        trading_env = (_env("KIS_TRADING_ENV", "virtual") or "virtual").lower()
        default_base_url = DEFAULT_KIS_REAL_BASE_URL if trading_env == "real" else DEFAULT_KIS_VIRTUAL_BASE_URL
        return cls(
            app_key=_env("KIS_APP_KEY"),
            app_secret=_env("KIS_APP_SECRET"),
            access_token=_env("KIS_ACCESS_TOKEN"),
            base_url=(_env("KIS_BASE_URL", default_base_url) or default_base_url).rstrip("/"),
            daily_price_path=_env("KIS_DAILY_PRICE_PATH", DEFAULT_KIS_DAILY_PRICE_PATH) or DEFAULT_KIS_DAILY_PRICE_PATH,
            token_path=_env("KIS_TOKEN_PATH", DEFAULT_KIS_TOKEN_PATH) or DEFAULT_KIS_TOKEN_PATH,
            adjusted_price_flag=_env("KIS_ADJUSTED_PRICE_FLAG", DEFAULT_KIS_ADJUSTED_PRICE_FLAG)
            or DEFAULT_KIS_ADJUSTED_PRICE_FLAG,
            original_price_flag=_env("KIS_ORIGINAL_PRICE_FLAG", DEFAULT_KIS_ORIGINAL_PRICE_FLAG)
            or DEFAULT_KIS_ORIGINAL_PRICE_FLAG,
            request_timeout_seconds=_env_int("API_REQUEST_TIMEOUT_SECONDS", DEFAULT_REQUEST_TIMEOUT_SECONDS),
            retry=RetryConfig.from_env(),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.app_key and self.app_secret)


@dataclass(frozen=True)
class PilotConfig:
    sample_symbol: str
    start_date: date
    end_date: date
    krx_trade_date: date
    min_symbol_coverage: float
    max_price_issue_ratio: float

    @classmethod
    def from_env(cls) -> "PilotConfig":
        today = date.today()
        end_date = _parse_date(_env("SOURCE_PILOT_END_DATE"), today)
        start_date = _parse_date(
            _env("SOURCE_PILOT_START_DATE"),
            end_date - timedelta(days=DEFAULT_PILOT_LOOKBACK_DAYS),
        )
        krx_trade_date = _parse_date(_env("SOURCE_PILOT_KRX_TRADE_DATE"), end_date)
        return cls(
            sample_symbol=_env("SOURCE_PILOT_SYMBOL", DEFAULT_PILOT_SYMBOL) or DEFAULT_PILOT_SYMBOL,
            start_date=start_date,
            end_date=end_date,
            krx_trade_date=krx_trade_date,
            min_symbol_coverage=_env_float("OHLCV_MIN_SYMBOL_COVERAGE", DEFAULT_MIN_SYMBOL_COVERAGE),
            max_price_issue_ratio=_env_float("SOURCE_PILOT_MAX_PRICE_ISSUE_RATIO", DEFAULT_PILOT_MAX_PRICE_ISSUE_RATIO),
        )


@dataclass(frozen=True)
class DatabaseConfig:
    """Database connection settings.

    ``password`` and ``dsn`` are intentionally read only from process
    environment. The application never loads ``.env`` files.
    """

    dsn: str | None
    host: str
    port: int
    database: str
    user: str
    password: str | None
    execution_mode: str
    docker_container: str

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        return cls(
            dsn=_env("QUANT_DB_DSN") or _env("DATABASE_URL"),
            host=_env("QUANT_DB_HOST", DEFAULT_DB_HOST) or DEFAULT_DB_HOST,
            port=_env_int("QUANT_DB_PORT", DEFAULT_DB_PORT),
            database=_env("QUANT_DB_NAME", DEFAULT_DB_NAME) or DEFAULT_DB_NAME,
            user=_env("QUANT_DB_USER", DEFAULT_DB_USER) or DEFAULT_DB_USER,
            password=_env("QUANT_DB_PASSWORD"),
            execution_mode=(_env("QUANT_DB_EXECUTION_MODE", DEFAULT_DB_EXECUTION_MODE) or DEFAULT_DB_EXECUTION_MODE).lower(),
            docker_container=_env("QUANT_DB_CONTAINER", DEFAULT_DB_CONTAINER) or DEFAULT_DB_CONTAINER,
        )

    def psycopg_conninfo(self) -> str:
        if self.dsn:
            return self.dsn
        if not self.password:
            raise ValueError("QUANT_DB_PASSWORD or QUANT_DB_DSN is required for psycopg DB access.")
        return (
            f"host={self.host} port={self.port} dbname={self.database} "
            f"user={self.user} password={self.password}"
        )


@dataclass(frozen=True)
class OhlcvIngestionConfig:
    primary_source: str
    batch_days: int
    backfill_years: int
    min_symbol_coverage: float

    @classmethod
    def from_env(cls) -> "OhlcvIngestionConfig":
        return cls(
            primary_source=(_env("OHLCV_PRIMARY_SOURCE", "KRX") or "KRX").upper(),
            batch_days=_env_int("OHLCV_BATCH_DAYS", DEFAULT_OHLCV_BATCH_DAYS),
            backfill_years=_env_int("OHLCV_BACKFILL_YEARS", DEFAULT_OHLCV_BACKFILL_YEARS),
            min_symbol_coverage=_env_float("OHLCV_MIN_SYMBOL_COVERAGE", DEFAULT_MIN_SYMBOL_COVERAGE),
        )


@dataclass(frozen=True)
class TaConfig:
    transform_version: str

    @classmethod
    def from_env(cls) -> "TaConfig":
        return cls(transform_version=_env("TA_TRANSFORM_VERSION", DEFAULT_TA_TRANSFORM_VERSION) or DEFAULT_TA_TRANSFORM_VERSION)


@dataclass(frozen=True)
class SeibroConfig:
    base_url: str
    web_base_url: str
    analyst_report_page_path: str
    analyst_report_api_path: str
    analyst_report_action: str
    analyst_report_task: str
    analyst_report_page_size: int
    analyst_report_chunk_months: int
    request_sleep_min_seconds: float
    request_sleep_max_seconds: float
    api_key: str | None
    collection_approved: bool
    request_timeout_seconds: int
    retry: RetryConfig

    @classmethod
    def from_env(cls) -> "SeibroConfig":
        return cls(
            base_url=(_env("SEIBRO_BASE_URL", DEFAULT_SEIBRO_BASE_URL) or DEFAULT_SEIBRO_BASE_URL).rstrip("/"),
            web_base_url=(
                _env("SEIBRO_WEB_BASE_URL", DEFAULT_SEIBRO_WEB_BASE_URL) or DEFAULT_SEIBRO_WEB_BASE_URL
            ).rstrip("/"),
            analyst_report_page_path=_env(
                "SEIBRO_ANALYST_REPORT_PAGE_PATH", DEFAULT_SEIBRO_ANALYST_REPORT_PAGE_PATH
            )
            or DEFAULT_SEIBRO_ANALYST_REPORT_PAGE_PATH,
            analyst_report_api_path=_env(
                "SEIBRO_ANALYST_REPORT_API_PATH", DEFAULT_SEIBRO_ANALYST_REPORT_API_PATH
            )
            or DEFAULT_SEIBRO_ANALYST_REPORT_API_PATH,
            analyst_report_action=_env(
                "SEIBRO_ANALYST_REPORT_ACTION", DEFAULT_SEIBRO_ANALYST_REPORT_ACTION
            )
            or DEFAULT_SEIBRO_ANALYST_REPORT_ACTION,
            analyst_report_task=_env("SEIBRO_ANALYST_REPORT_TASK", DEFAULT_SEIBRO_ANALYST_REPORT_TASK)
            or DEFAULT_SEIBRO_ANALYST_REPORT_TASK,
            analyst_report_page_size=_env_int(
                "SEIBRO_ANALYST_REPORT_PAGE_SIZE", DEFAULT_SEIBRO_ANALYST_REPORT_PAGE_SIZE
            ),
            analyst_report_chunk_months=_env_int(
                "SEIBRO_ANALYST_REPORT_CHUNK_MONTHS", DEFAULT_SEIBRO_ANALYST_REPORT_CHUNK_MONTHS
            ),
            request_sleep_min_seconds=_env_float(
                "SEIBRO_REQUEST_SLEEP_MIN_SECONDS", DEFAULT_SEIBRO_REQUEST_SLEEP_MIN_SECONDS
            ),
            request_sleep_max_seconds=_env_float(
                "SEIBRO_REQUEST_SLEEP_MAX_SECONDS", DEFAULT_SEIBRO_REQUEST_SLEEP_MAX_SECONDS
            ),
            api_key=_env("SEIBRO_API_KEY"),
            collection_approved=(_env("SEIBRO_COLLECTION_APPROVED", "false") or "false").lower() == "true",
            request_timeout_seconds=_env_int("API_REQUEST_TIMEOUT_SECONDS", DEFAULT_REQUEST_TIMEOUT_SECONDS),
            retry=RetryConfig.from_env(),
        )


@dataclass(frozen=True)
class BokConfig:
    base_url: str
    api_key: str | None
    request_timeout_seconds: int
    retry: RetryConfig

    @classmethod
    def from_env(cls) -> "BokConfig":
        return cls(
            base_url=(_env("BOK_BASE_URL", DEFAULT_BOK_BASE_URL) or DEFAULT_BOK_BASE_URL).rstrip("/"),
            api_key=_env("BOK_API_KEY"),
            request_timeout_seconds=_env_int("API_REQUEST_TIMEOUT_SECONDS", DEFAULT_REQUEST_TIMEOUT_SECONDS),
            retry=RetryConfig.from_env(),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class DartConfig:
    base_url: str
    api_keys: tuple[str, ...]
    request_timeout_seconds: int
    retry: RetryConfig

    @classmethod
    def from_env(cls) -> "DartConfig":
        return cls(
            base_url=(_env("DART_BASE_URL", DEFAULT_DART_BASE_URL) or DEFAULT_DART_BASE_URL).rstrip("/"),
            api_keys=_env_values(
                "FSS_API_KEY",
                "FSS_API_KEY_2",
                "FSS_API_KEY_3",
                "DART_API_KEY",
                "OPENDART_API_KEY",
            ),
            request_timeout_seconds=_env_int("API_REQUEST_TIMEOUT_SECONDS", DEFAULT_REQUEST_TIMEOUT_SECONDS),
            retry=RetryConfig.from_env(),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_keys)

    @property
    def api_key(self) -> str | None:
        return self.api_keys[0] if self.api_keys else None


@dataclass(frozen=True)
class KindConfig:
    corp_list_url: str
    request_timeout_seconds: int
    retry: RetryConfig

    @classmethod
    def from_env(cls) -> "KindConfig":
        return cls(
            corp_list_url=(_env("KIND_CORP_LIST_URL", DEFAULT_KIND_CORP_LIST_URL) or DEFAULT_KIND_CORP_LIST_URL).rstrip("/"),
            request_timeout_seconds=_env_int("API_REQUEST_TIMEOUT_SECONDS", DEFAULT_REQUEST_TIMEOUT_SECONDS),
            retry=RetryConfig.from_env(),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.corp_list_url)


@dataclass(frozen=True)
class WicsConfig:
    company_info_url: str
    request_workers: int
    request_timeout_seconds: int
    retry: RetryConfig

    @classmethod
    def from_env(cls) -> "WicsConfig":
        return cls(
            company_info_url=(
                _env("WICS_COMPANY_INFO_URL", DEFAULT_WICS_COMPANY_INFO_URL) or DEFAULT_WICS_COMPANY_INFO_URL
            ).rstrip("/"),
            request_workers=_env_int("WICS_REQUEST_WORKERS", DEFAULT_WICS_REQUEST_WORKERS),
            request_timeout_seconds=_env_int("API_REQUEST_TIMEOUT_SECONDS", DEFAULT_REQUEST_TIMEOUT_SECONDS),
            retry=RetryConfig.from_env(),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.company_info_url)


def _parse_date(raw: str | None, default: date) -> date:
    if raw is None:
        return default
    return date.fromisoformat(raw)


def _parse_endpoint_list(raw: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if raw is None:
        return default
    delimiter = ";" if ";" in raw else ","
    endpoints = tuple(item.strip() for item in raw.split(delimiter) if item.strip())
    return endpoints or default
