"""Repository layer for raw/core/feature/mart data engineering writes."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

from quant_agent.data.config import DEFAULT_BOK_STALENESS_DAYS, DatabaseConfig
from quant_agent.data.catalogs import BOK_SERIES_PRESETS, DART_REPORT_CODE_PERIOD_END, bok_series_id
from quant_agent.data.db import SqlExecutor, jsonb_literal, make_executor, sql_literal
from quant_agent.data.lineage_quality import (
    DEFAULT_MIN_LINEAGE_COVERAGE,
    LineageQualityReport,
    assess_lineage_quality,
    require_lineage_quality,
)
from quant_agent.data.models import (
    AnalystReportSummary,
    ApiRequestLog,
    DataQualityIssue,
    LineageEvent,
    OhlcvBar,
    RawSourcePayload,
)
from quant_agent.data.quality import OhlcvQualityConfig, duplicate_keys, is_tradable_ohlcv, ohlcv_quality_flags
from quant_agent.data.security_types import classify_security_type


DATA_SOURCES = {
    "KRX": ("Korea Exchange", "KRX_DAILY_MARKET_ENDPOINTS", True),
    "KIS": ("Korea Investment Securities", "KIS_BASE_URL", False),
    "KIND": ("Korea Exchange KIND listed-company directory", "KIND_CORP_LIST_URL", False),
    "WICS": ("FnGuide Company Guide WICS classification", "WICS_COMPANY_INFO_URL", False),
    "SEIBRO": ("KSD SEIBro Open Platform", "SEIBRO_BASE_URL", False),
    "BOK": ("Bank of Korea ECOS", "BOK_BASE_URL", False),
    "DART": ("OpenDART Financial Supervisory Service", "DART_BASE_URL", False),
    "TA": ("TA-Lib technical indicator transform", "TA_TRANSFORM_VERSION", False),
    "QA": ("Quant-Agent data quality checks", "QA_RULE_VERSION", False),
}


ANALYST_REPORT_SUMMARY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS raw.analyst_report_summary (
    report_date DATE NOT NULL,
    ticker TEXT NOT NULL,
    company_name TEXT NOT NULL,
    summary TEXT NOT NULL,
    opinion TEXT,
    target_price NUMERIC(20, 6),
    close_price NUMERIC(20, 6),
    institution TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    source_payload_hash TEXT NOT NULL,
    raw_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_id UUID REFERENCES meta.ingestion_run(run_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (report_date, ticker, institution, author)
);

CREATE INDEX IF NOT EXISTS idx_raw_analyst_report_summary_ticker_date
    ON raw.analyst_report_summary (ticker, report_date DESC);
CREATE INDEX IF NOT EXISTS idx_raw_analyst_report_summary_payload
    ON raw.analyst_report_summary USING GIN (raw_jsonb);
"""


class DataRepository:
    def __init__(self, executor: SqlExecutor | None = None, db_config: DatabaseConfig | None = None) -> None:
        self.executor = executor or make_executor(db_config)

    def ensure_data_sources(self) -> None:
        values = []
        for source_id, (name, base_url_key, is_primary) in DATA_SOURCES.items():
            values.append(
                "("
                f"{sql_literal(source_id)}, {sql_literal(name)}, {sql_literal(base_url_key)}, "
                f"{sql_literal('v1')}, {sql_literal(is_primary)}"
                ")"
            )
        self.executor.execute_script(
            f"""
            INSERT INTO meta.data_source (source_id, name, base_url_key, version, is_primary)
            VALUES {", ".join(values)}
            ON CONFLICT (source_id) DO UPDATE SET
              name = EXCLUDED.name,
              base_url_key = EXCLUDED.base_url_key,
              is_primary = EXCLUDED.is_primary,
              updated_at = now();
            """
        )

    def start_ingestion_run(
        self,
        *,
        dag_id: str,
        task_id: str,
        source_id: str,
        params: dict[str, Any],
    ) -> UUID:
        run_id = uuid4()
        self.ensure_data_sources()
        self.executor.execute_script(
            f"""
            INSERT INTO meta.ingestion_run
              (run_id, dag_id, task_id, source_id, started_at, status, params_jsonb)
            VALUES (
              {sql_literal(run_id)}, {sql_literal(dag_id)}, {sql_literal(task_id)},
              {sql_literal(source_id)}, {sql_literal(datetime.now(timezone.utc).isoformat())},
              'running', {jsonb_literal(params)}
            );
            """
        )
        return run_id

    def finish_ingestion_run(self, run_id: UUID, *, status: str, error_message: str | None = None) -> None:
        self.executor.execute_script(
            f"""
            UPDATE meta.ingestion_run
               SET ended_at = now(),
                   status = {sql_literal(status)},
                   error_message = {sql_literal(error_message)}
             WHERE run_id = {sql_literal(run_id)};
            """
        )

    def store_api_request_log(self, event: ApiRequestLog, run_id: UUID) -> None:
        self.store_api_request_logs([event], run_id)

    def store_api_request_logs(self, events: list[ApiRequestLog], run_id: UUID) -> None:
        if not events:
            return
        rows = ", ".join(_api_request_log_row(event, run_id) for event in events)
        self.executor.execute_script(
            f"""
            INSERT INTO meta.api_request_log
              (run_id, source_id, endpoint_key, request_hash, success, status_code,
               elapsed_ms, retry_count, response_hash, error_message, metadata_jsonb, request_started_at)
            VALUES {rows};
            """
        )

    def store_lineage_events(self, events: list[LineageEvent], run_id: UUID) -> None:
        if not events:
            return
        rows = ", ".join(_lineage_event_row(event, run_id) for event in events)
        self.executor.execute_script(
            f"""
            INSERT INTO meta.lineage_event
              (target_table, target_key, source_table, source_key, run_id, transform_version, metadata_jsonb)
            VALUES {rows};
            """
        )

    def ensure_analyst_report_summary_table(self) -> None:
        self.executor.execute_script(ANALYST_REPORT_SUMMARY_TABLE_SQL)

    def store_raw_payloads(self, raw_payloads: list[RawSourcePayload], run_id: UUID) -> int:
        if not raw_payloads:
            return 0
        rows = []
        for raw_payload in raw_payloads:
            request_hash = _stable_hash(raw_payload.request)
            payload_hash = _stable_hash(raw_payload.payload)
            request_date = raw_payload.request_date or date.today()
            rows.append(
                "("
                f"{sql_literal(raw_payload.source)}, {sql_literal(request_date)}, "
                f"{sql_literal(request_hash)}, {sql_literal(payload_hash)}, "
                f"{jsonb_literal(raw_payload.payload)}, {sql_literal(run_id)}"
                ")"
            )
        self.executor.execute_script(
            f"""
            INSERT INTO raw.ohlcv_response
              (source_id, request_date, request_hash, payload_hash, payload_jsonb, run_id)
            VALUES {", ".join(rows)}
            ON CONFLICT (source_id, request_hash, payload_hash) DO NOTHING;
            """
        )
        return len(rows)

    def store_external_raw_payloads(self, raw_payloads: list[RawSourcePayload], run_id: UUID) -> int:
        written = 0
        for raw_payload in raw_payloads:
            payload_hash = _stable_hash(raw_payload.payload)
            source = raw_payload.source.upper()
            if source == "SEIBRO":
                query_window = json.dumps(raw_payload.request, ensure_ascii=False, sort_keys=True, default=str)
                self.executor.execute_script(
                    f"""
                    INSERT INTO raw.seibro_report_response (query_window, payload_hash, payload_jsonb, run_id)
                    VALUES ({sql_literal(query_window)}, {sql_literal(payload_hash)}, {jsonb_literal(raw_payload.payload)}, {sql_literal(run_id)})
                    ON CONFLICT (query_window, payload_hash) DO NOTHING;
                    """
                )
                written += 1
            elif source == "BOK":
                self.executor.execute_script(
                    f"""
                    INSERT INTO raw.bok_response (stat_code, item_code, payload_hash, payload_jsonb, run_id)
                    VALUES (
                      {sql_literal(raw_payload.request.get('stat_code'))},
                      {sql_literal(raw_payload.request.get('item_code1'))},
                      {sql_literal(payload_hash)},
                      {jsonb_literal(raw_payload.payload)},
                      {sql_literal(run_id)}
                    )
                    ON CONFLICT (stat_code, item_code, payload_hash) DO NOTHING;
                    """
                )
                written += 1
            elif source == "DART":
                self.executor.execute_script(
                    f"""
                    INSERT INTO raw.dart_response (corp_code, report_code, payload_hash, payload_jsonb, run_id)
                    VALUES (
                      {sql_literal(raw_payload.request.get('corp_code'))},
                      {sql_literal(raw_payload.request.get('reprt_code'))},
                      {sql_literal(payload_hash)},
                      {jsonb_literal(raw_payload.payload)},
                      {sql_literal(run_id)}
                    )
                    ON CONFLICT (corp_code, report_code, payload_hash) DO NOTHING;
                    """
                )
                written += 1
        return written

    def upsert_ohlcv_bars(self, bars: list[OhlcvBar], run_id: UUID, source_id: str) -> tuple[int, list[DataQualityIssue]]:
        if not bars:
            return 0, []

        issues: list[DataQualityIssue] = []
        duplicate_key_set = duplicate_keys(bars)
        if duplicate_key_set:
            counts = Counter((bar.symbol, bar.trade_date) for bar in bars)
            for symbol, trade_date in sorted(duplicate_key_set):
                issues.append(
                    DataQualityIssue(
                        dataset="core.ohlcv_daily",
                        severity="warning",
                        rule_code="DUPLICATE_SYMBOL_DATE",
                        message=f"Observed {counts[(symbol, trade_date)]} rows for one symbol/date; last upsert wins.",
                        symbol=symbol,
                        trade_date=trade_date,
                    )
                )

        deduped_bars = list({(bar.symbol, bar.trade_date): bar for bar in bars}.values())
        symbol_by_code: dict[str, OhlcvBar] = {}
        for bar in deduped_bars:
            symbol_by_code[bar.symbol] = bar

        symbol_rows = []
        lifecycle_rows = []
        security_type_history_rows = []
        name_history_rows = []
        calendar_dates: set[date] = set()
        ohlcv_rows = []
        lineage_rows = []
        issue_rows = []

        for bar in symbol_by_code.values():
            market_segment = _infer_market_segment(bar.raw)
            security_type = _infer_security_type(bar.raw)
            symbol_rows.append(
                "("
                f"{sql_literal(bar.symbol)}, {sql_literal(bar.name or bar.symbol)}, "
                f"{sql_literal(market_segment)}, {sql_literal(market_segment)}, "
                f"{sql_literal(security_type)}, {sql_literal('listed')}, "
                f"{sql_literal(bar.trade_date)}, NULL, {jsonb_literal(_symbol_metadata(bar.raw))}"
                ")"
            )
            lifecycle_rows.append(
                "("
                f"{sql_literal(bar.symbol)}, {sql_literal(bar.trade_date)}, {sql_literal(market_segment)}, "
                f"{sql_literal('listed')}, {sql_literal('listed')}, {sql_literal(source_id)}, "
                f"{sql_literal(run_id)}, {jsonb_literal(_symbol_metadata(bar.raw))}"
                ")"
            )
            name_history_rows.append(
                "("
                f"{sql_literal(bar.symbol)}, {sql_literal(bar.trade_date)}, {sql_literal(bar.name or bar.symbol)}, "
                f"{sql_literal(source_id)}, {sql_literal(run_id)}, {jsonb_literal(_symbol_metadata(bar.raw))}"
                ")"
            )
        for bar in deduped_bars:
            calendar_dates.add(bar.trade_date)
            flags = ohlcv_quality_flags(bar)
            if flags:
                for rule_code in flags:
                    issue = DataQualityIssue(
                        dataset="core.ohlcv_daily",
                        severity="warning",
                        rule_code=rule_code.upper(),
                        message=f"OHLCV quality flag {rule_code} detected.",
                        symbol=bar.symbol,
                        trade_date=bar.trade_date,
                    )
                    issues.append(issue)
                    issue_rows.append(_dq_issue_row(issue, run_id))

            source_key = f"{source_id}:{bar.symbol}:{bar.trade_date.isoformat()}"
            ohlcv_rows.append(
                "("
                "(SELECT symbol_id FROM core.symbol_master WHERE symbol = "
                f"{sql_literal(bar.symbol)}), "
                f"{sql_literal(bar.trade_date)}, {sql_literal(bar.open)}, {sql_literal(bar.high)}, "
                f"{sql_literal(bar.low)}, {sql_literal(bar.close)}, {sql_literal(bar.volume)}, "
                f"{sql_literal(source_id)}, {sql_literal(run_id)}, {sql_literal(is_tradable_ohlcv(bar))}, "
                f"{jsonb_literal(flags)}"
                ")"
            )
            lineage_rows.append(
                "("
                f"{sql_literal('core.ohlcv_daily')}, "
                f"{sql_literal(f'{bar.symbol}:{bar.trade_date.isoformat()}')}, "
                f"{sql_literal('raw.ohlcv_response')}, {sql_literal(source_key)}, "
                f"{sql_literal(run_id)}, {sql_literal('ohlcv-normalize-v1')}"
                ")"
            )

        for bar in sorted(deduped_bars, key=lambda candidate: (candidate.symbol, candidate.trade_date)):
            security_type = _infer_security_type(bar.raw)
            security_type_metadata = _security_type_history_metadata(bar.raw)
            if security_type is not None and security_type_metadata is not None:
                security_type_history_rows.append(
                    "("
                    f"{sql_literal(bar.symbol)}, {sql_literal(bar.trade_date)}, "
                    f"{sql_literal(security_type)}, {sql_literal(source_id)}, "
                    f"{sql_literal(run_id)}, {sql_literal('security-type-source-payload-v1')}, "
                    f"{jsonb_literal(security_type_metadata)}"
                    ")"
                )

        calendar_rows = [
            "("
            f"{sql_literal('KRX')}, {sql_literal(trade_date)}, TRUE, {sql_literal('OPEN_OBSERVED')}, "
            f"{sql_literal(source_id)}, {sql_literal(run_id)}, {sql_literal('observed')}"
            ")"
            for trade_date in sorted(calendar_dates)
        ]

        duplicate_issue_rows = [_dq_issue_row(issue, run_id) for issue in issues if issue.rule_code == "DUPLICATE_SYMBOL_DATE"]
        all_issue_rows = issue_rows + duplicate_issue_rows

        script_parts = [
            "BEGIN;",
            f"""
            INSERT INTO core.symbol_master
              (symbol, name, market, market_segment, security_type, listing_status, listed_at, delisted_at, metadata_jsonb)
            VALUES {", ".join(symbol_rows)}
            ON CONFLICT (symbol) DO UPDATE SET
              name = COALESCE(NULLIF(EXCLUDED.name, ''), core.symbol_master.name),
              market = COALESCE(EXCLUDED.market, core.symbol_master.market),
              market_segment = COALESCE(EXCLUDED.market_segment, core.symbol_master.market_segment),
              security_type = COALESCE(EXCLUDED.security_type, core.symbol_master.security_type),
              listing_status = EXCLUDED.listing_status,
              listed_at = COALESCE(LEAST(core.symbol_master.listed_at, EXCLUDED.listed_at), EXCLUDED.listed_at, core.symbol_master.listed_at),
              delisted_at = NULL,
              metadata_jsonb = core.symbol_master.metadata_jsonb || EXCLUDED.metadata_jsonb,
              updated_at = now();
            """,
            _symbol_lifecycle_sql(lifecycle_rows),
            _symbol_security_type_history_sql(security_type_history_rows),
            _symbol_name_history_sql(name_history_rows),
            f"""
            INSERT INTO core.trading_calendar
              (market, trade_date, is_open, reason, source_id, run_id, evidence_status)
            VALUES {", ".join(calendar_rows)}
            ON CONFLICT (market, trade_date) DO UPDATE SET
              is_open = EXCLUDED.is_open,
              reason = EXCLUDED.reason,
              source_id = EXCLUDED.source_id,
              run_id = EXCLUDED.run_id,
              evidence_status = EXCLUDED.evidence_status;
            """,
            f"""
            INSERT INTO core.ohlcv_daily
              (symbol_id, trade_date, open, high, low, close, volume, source_id, run_id, is_tradable, quality_flags)
            VALUES {", ".join(ohlcv_rows)}
            ON CONFLICT (trade_date, symbol_id) DO UPDATE SET
              open = EXCLUDED.open,
              high = EXCLUDED.high,
              low = EXCLUDED.low,
              close = EXCLUDED.close,
              volume = EXCLUDED.volume,
              source_id = EXCLUDED.source_id,
              run_id = EXCLUDED.run_id,
              is_tradable = EXCLUDED.is_tradable,
              quality_flags = EXCLUDED.quality_flags,
              updated_at = now();
            """,
            f"""
            INSERT INTO meta.lineage_event
              (target_table, target_key, source_table, source_key, run_id, transform_version)
            VALUES {", ".join(lineage_rows)};
            """,
        ]
        if all_issue_rows:
            script_parts.append(
                f"""
                INSERT INTO meta.data_quality_issue
                  (run_id, dataset, symbol, trade_date, severity, rule_code, message)
                VALUES {", ".join(all_issue_rows)};
                """
            )
        script_parts.append("COMMIT;")
        self.executor.execute_script("\n".join(script_parts))
        return len(deduped_bars), issues

    def upsert_trading_calendar_observations(
        self,
        *,
        start_date: date,
        end_date: date,
        observed_open_dates: set[date],
        run_id: UUID,
        source_id: str = "KRX",
    ) -> int:
        """Persist calendar evidence without treating missing weekday data as closed."""

        if end_date < start_date:
            raise ValueError("end_date must be greater than or equal to start_date.")
        rows = []
        current = start_date
        while current <= end_date:
            if current.weekday() >= 5:
                is_open, reason, evidence = False, "WEEKEND", "weekend"
            elif current in observed_open_dates:
                is_open, reason, evidence = True, "OPEN_OBSERVED", "observed"
            else:
                is_open, reason, evidence = None, "UNCONFIRMED_NO_DATA", "unconfirmed"
            rows.append(
                "("
                f"{sql_literal('KRX')}, {sql_literal(current)}, {sql_literal(is_open)}, {sql_literal(reason)}, "
                f"{sql_literal(source_id)}, {sql_literal(run_id)}, {sql_literal(evidence)}"
                ")"
            )
            current += timedelta(days=1)
        self.executor.execute_script(
            f"""
            INSERT INTO core.trading_calendar
              (market, trade_date, is_open, reason, source_id, run_id, evidence_status)
            VALUES {", ".join(rows)}
            ON CONFLICT (market, trade_date) DO UPDATE SET
                is_open = CASE
                    WHEN EXCLUDED.is_open IS TRUE THEN TRUE
                    WHEN core.trading_calendar.is_open IS TRUE THEN TRUE
                    ELSE EXCLUDED.is_open
                END,
                reason = CASE
                    WHEN EXCLUDED.is_open IS TRUE THEN EXCLUDED.reason
                    WHEN core.trading_calendar.is_open IS TRUE THEN core.trading_calendar.reason
                    ELSE EXCLUDED.reason
                END,
                source_id = EXCLUDED.source_id,
                run_id = EXCLUDED.run_id,
                evidence_status = CASE
                    WHEN EXCLUDED.is_open IS TRUE THEN EXCLUDED.evidence_status
                    WHEN core.trading_calendar.is_open IS TRUE THEN core.trading_calendar.evidence_status
                    ELSE EXCLUDED.evidence_status
                END;
            """
        )
        return len(rows)

    def refresh_symbol_lifecycle(self, *, run_id: UUID, as_of_date: date, source_id: str = "KRX") -> None:
        confirmed_calendar = self.executor.fetch_json(
            f"""
            SELECT 1
              FROM core.trading_calendar
             WHERE market = 'KRX'
               AND trade_date = {sql_literal(as_of_date)}
               AND is_open IS TRUE
               AND evidence_status = 'observed'
             LIMIT 1;
            """
        )
        if not confirmed_calendar:
            return
        self.executor.execute_script(
            f"""
            WITH observations AS (
                SELECT o.symbol_id,
                       o.trade_date,
                       sm.market_segment,
                       sm.name
                  FROM core.ohlcv_daily o
                  JOIN core.symbol_master sm ON sm.symbol_id = o.symbol_id
                 WHERE o.source_id = {sql_literal(source_id)}
                   AND o.trade_date <= {sql_literal(as_of_date)}
            ),
            first_seen AS (
                SELECT symbol_id,
                       MIN(trade_date) AS listed_at,
                       MAX(trade_date) AS last_seen_at
                  FROM observations
                 GROUP BY symbol_id
            )
            UPDATE core.symbol_master sm
               SET listed_at = COALESCE(sm.listed_at, f.listed_at),
                   delisted_at = CASE WHEN f.last_seen_at = {sql_literal(as_of_date)} THEN NULL ELSE sm.delisted_at END,
                   updated_at = now()
              FROM first_seen f
             WHERE sm.symbol_id = f.symbol_id;

            WITH observations AS (
                SELECT o.symbol_id,
                       o.trade_date,
                       sm.market_segment,
                       LAG(o.trade_date) OVER (PARTITION BY o.symbol_id ORDER BY o.trade_date) AS previous_trade_date
                  FROM core.ohlcv_daily o
                  JOIN core.symbol_master sm ON sm.symbol_id = o.symbol_id
                 WHERE o.source_id = {sql_literal(source_id)}
                   AND o.trade_date <= {sql_literal(as_of_date)}
            ),
            segmented AS (
                SELECT *,
                       SUM(
                           CASE
                             WHEN previous_trade_date IS NULL OR trade_date - previous_trade_date > 30 THEN 1
                             ELSE 0
                           END
                       ) OVER (PARTITION BY symbol_id ORDER BY trade_date) AS segment_id
                  FROM observations
            ),
            listing_segments AS (
                SELECT symbol_id,
                       MIN(trade_date) AS valid_from,
                       CASE WHEN MAX(trade_date) < {sql_literal(as_of_date)} THEN MAX(trade_date) ELSE NULL::date END AS valid_to,
                       MAX(market_segment) AS market,
                       segment_id
                  FROM segmented
                 GROUP BY symbol_id, segment_id
            )
            INSERT INTO core.symbol_listing_history
              (symbol_id, valid_from, valid_to, market, listing_status, event_type, source_id, run_id, metadata_jsonb)
            SELECT symbol_id,
                   valid_from,
                   valid_to,
                   market,
                   'listed',
                   CASE WHEN segment_id = 1 THEN 'listed' ELSE 'relisted' END,
                   {sql_literal(source_id)},
                   {sql_literal(run_id)},
                   jsonb_build_object('derived_from', 'core.ohlcv_daily', 'segment_id', segment_id)
              FROM listing_segments
            ON CONFLICT (symbol_id, valid_from) DO UPDATE SET
              valid_to = EXCLUDED.valid_to,
              market = COALESCE(EXCLUDED.market, core.symbol_listing_history.market),
              listing_status = EXCLUDED.listing_status,
              event_type = EXCLUDED.event_type,
              source_id = EXCLUDED.source_id,
              run_id = EXCLUDED.run_id,
              metadata_jsonb = core.symbol_listing_history.metadata_jsonb || EXCLUDED.metadata_jsonb;

            WITH first_seen AS (
                SELECT o.symbol_id,
                       MIN(o.trade_date) AS valid_from
                  FROM core.ohlcv_daily o
                 WHERE o.source_id = {sql_literal(source_id)}
                   AND o.trade_date <= {sql_literal(as_of_date)}
                 GROUP BY o.symbol_id
            )
            INSERT INTO core.symbol_name_history
              (symbol_id, valid_from, valid_to, name, source_id, run_id, metadata_jsonb)
            SELECT sm.symbol_id,
                   f.valid_from,
                   NULL,
                   sm.name,
                   {sql_literal(source_id)},
                   {sql_literal(run_id)},
                   jsonb_build_object('derived_from', 'core.symbol_master')
              FROM core.symbol_master sm
              JOIN first_seen f ON f.symbol_id = sm.symbol_id
            ON CONFLICT (symbol_id, valid_from, name) DO UPDATE SET
              source_id = EXCLUDED.source_id,
              run_id = EXCLUDED.run_id,
              metadata_jsonb = core.symbol_name_history.metadata_jsonb || EXCLUDED.metadata_jsonb;

            WITH observed AS (
                SELECT DISTINCT symbol_id
                  FROM core.ohlcv_daily
                 WHERE source_id = {sql_literal(source_id)}
                   AND trade_date = {sql_literal(as_of_date)}
            ),
            delisted AS (
                SELECT sm.symbol_id
                  FROM core.symbol_master sm
                 WHERE sm.listing_status = 'listed'
                   AND sm.symbol_id NOT IN (SELECT symbol_id FROM observed)
                   AND EXISTS (
                       SELECT 1
                         FROM core.ohlcv_daily o
                        WHERE o.symbol_id = sm.symbol_id
                          AND o.source_id = {sql_literal(source_id)}
                          AND o.trade_date < {sql_literal(as_of_date)}
                   )
            )
            UPDATE core.symbol_master sm
               SET listing_status = 'delisted',
                   delisted_at = {sql_literal(as_of_date)},
                   updated_at = now()
              FROM delisted d
             WHERE sm.symbol_id = d.symbol_id;

            WITH observed AS (
                SELECT DISTINCT symbol_id
                  FROM core.ohlcv_daily
                 WHERE source_id = {sql_literal(source_id)}
                   AND trade_date = {sql_literal(as_of_date)}
            )
            UPDATE core.symbol_master sm
               SET listing_status = 'listed',
                   delisted_at = NULL,
                   listed_at = COALESCE(sm.listed_at, {sql_literal(as_of_date)}),
                   updated_at = now()
              FROM observed o
             WHERE sm.symbol_id = o.symbol_id
               AND sm.listing_status <> 'listed';

            WITH observed AS (
                SELECT DISTINCT symbol_id
                  FROM core.ohlcv_daily
                 WHERE source_id = {sql_literal(source_id)}
                   AND trade_date = {sql_literal(as_of_date)}
            )
            UPDATE core.symbol_listing_history h
               SET valid_to = {sql_literal(as_of_date)}
             WHERE h.valid_to IS NULL
               AND h.listing_status = 'listed'
               AND h.symbol_id NOT IN (SELECT symbol_id FROM observed);

            WITH delisted AS (
                SELECT sm.symbol_id, sm.market_segment
                  FROM core.symbol_master sm
                 WHERE sm.listing_status = 'delisted'
                   AND sm.delisted_at = {sql_literal(as_of_date)}
            )
            INSERT INTO core.symbol_listing_history
              (symbol_id, valid_from, valid_to, market, listing_status, event_type, source_id, run_id, metadata_jsonb)
            SELECT symbol_id, {sql_literal(as_of_date)}, NULL, market_segment, 'delisted', 'delisted',
                   {sql_literal(source_id)}, {sql_literal(run_id)}, '{{}}'::jsonb
              FROM delisted
            ON CONFLICT (symbol_id, valid_from) DO UPDATE SET
              listing_status = EXCLUDED.listing_status,
              event_type = EXCLUDED.event_type,
              source_id = EXCLUDED.source_id,
              run_id = EXCLUDED.run_id,
              metadata_jsonb = core.symbol_listing_history.metadata_jsonb || EXCLUDED.metadata_jsonb;
            """
        )

    def refresh_ohlcv_quality(
        self,
        *,
        run_id: UUID,
        source_id: str,
        start_date: date,
        end_date: date,
        min_coverage: float,
    ) -> None:
        self.executor.execute_script(
            f"""
            WITH expected AS (
                SELECT COUNT(DISTINCT trade_date)::int AS days
                  FROM core.ohlcv_daily
                 WHERE trade_date BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
                   AND source_id = {sql_literal(source_id)}
            ),
            observed AS (
                SELECT symbol_id,
                       COUNT(DISTINCT trade_date)::int AS observed_days,
                       SUM(CASE WHEN quality_flags <> '{{}}'::jsonb THEN 1 ELSE 0 END)::int AS issue_count
                  FROM core.ohlcv_daily
                 WHERE trade_date BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
                   AND source_id = {sql_literal(source_id)}
                 GROUP BY symbol_id
            )
            INSERT INTO core.ohlcv_quality_daily
              (symbol_id, as_of_date, expected_days, observed_days, coverage_ratio, missing_days, issue_count, run_id)
            SELECT o.symbol_id,
                   {sql_literal(end_date)}::date,
                   e.days,
                   o.observed_days,
                   CASE WHEN e.days = 0 THEN 0 ELSE o.observed_days::numeric / e.days END,
                   GREATEST(e.days - o.observed_days, 0),
                   o.issue_count,
                   {sql_literal(run_id)}
              FROM observed o
             CROSS JOIN expected e
            ON CONFLICT (symbol_id, as_of_date) DO UPDATE SET
              expected_days = EXCLUDED.expected_days,
              observed_days = EXCLUDED.observed_days,
              coverage_ratio = EXCLUDED.coverage_ratio,
              missing_days = EXCLUDED.missing_days,
              issue_count = EXCLUDED.issue_count,
              run_id = EXCLUDED.run_id;

            INSERT INTO meta.data_quality_issue
              (run_id, dataset, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'core.ohlcv_quality_daily', 'warning', 'LOW_COVERAGE',
                   'Symbol coverage below configured threshold ' || {sql_literal(min_coverage)}
              WHERE EXISTS (
                SELECT 1
                  FROM core.ohlcv_quality_daily
                 WHERE as_of_date = {sql_literal(end_date)}
                   AND coverage_ratio < {sql_literal(min_coverage)}
              );
            """
        )

    def run_ohlcv_quality_framework(
        self,
        *,
        run_id: UUID,
        source_id: str,
        start_date: date,
        end_date: date,
        min_coverage: float,
        config: OhlcvQualityConfig | None = None,
    ) -> None:
        quality_config = config or OhlcvQualityConfig()
        self.refresh_ohlcv_quality(
            run_id=run_id,
            source_id=source_id,
            start_date=start_date,
            end_date=end_date,
            min_coverage=min_coverage,
        )
        self.executor.execute_script(
            f"""
            WITH expected_dates AS (
                SELECT trade_date
                  FROM core.trading_calendar
                 WHERE market = 'KRX'
                   AND is_open = TRUE
                   AND trade_date BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
                UNION
                SELECT DISTINCT trade_date
                  FROM core.ohlcv_daily
                 WHERE source_id = {sql_literal(source_id)}
                   AND trade_date BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
            ),
            scoped_symbols AS (
                SELECT DISTINCT o.symbol_id, sm.symbol
                  FROM core.ohlcv_daily o
                  JOIN core.symbol_master sm ON sm.symbol_id = o.symbol_id
                 WHERE o.source_id = {sql_literal(source_id)}
                   AND o.trade_date BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
            ),
            missing_symbol_dates AS (
                SELECT s.symbol, e.trade_date
                  FROM scoped_symbols s
                 CROSS JOIN expected_dates e
                  LEFT JOIN core.ohlcv_daily o
                    ON o.symbol_id = s.symbol_id
                   AND o.trade_date = e.trade_date
                   AND o.source_id = {sql_literal(source_id)}
                 WHERE o.symbol_id IS NULL
            )
            INSERT INTO meta.data_quality_issue
              (run_id, dataset, symbol, trade_date, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'core.ohlcv_daily', symbol, trade_date,
                   'warning', 'MISSING_SYMBOL_DATE',
                   'Expected trading date is missing for symbol.'
              FROM missing_symbol_dates;

            WITH ordered AS (
                SELECT sm.symbol,
                       o.symbol_id,
                       o.trade_date,
                       o.close,
                       CASE
                         WHEN o.close IS NOT NULL
                          AND o.close = LAG(o.close) OVER (PARTITION BY o.symbol_id ORDER BY o.trade_date)
                         THEN 0
                         ELSE 1
                       END AS break_flag
                  FROM core.ohlcv_daily o
                  JOIN core.symbol_master sm ON sm.symbol_id = o.symbol_id
                 WHERE o.source_id = {sql_literal(source_id)}
                   AND o.trade_date BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
            ),
            grouped AS (
                SELECT *,
                       SUM(break_flag) OVER (PARTITION BY symbol_id ORDER BY trade_date) AS stale_group
                  FROM ordered
            ),
            stale AS (
                SELECT symbol,
                       trade_date,
                       COUNT(*) OVER (PARTITION BY symbol_id, stale_group) AS stale_days
                  FROM grouped
                 WHERE close IS NOT NULL
            )
            INSERT INTO meta.data_quality_issue
              (run_id, dataset, symbol, trade_date, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'core.ohlcv_daily', symbol, trade_date,
                   'warning', 'STALE_PRICE',
                   'Close price unchanged for at least '
                   || {sql_literal(quality_config.stale_price_days)}
                   || ' consecutive observations.'
              FROM stale
             WHERE stale_days >= {sql_literal(quality_config.stale_price_days)};

            WITH volume_baseline AS (
                SELECT symbol_id,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY volume) AS median_volume,
                       COUNT(*)::int AS sample_count
                  FROM core.ohlcv_daily
                 WHERE source_id = {sql_literal(source_id)}
                   AND trade_date BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
                   AND volume > 0
                 GROUP BY symbol_id
            ),
            anomalous AS (
                SELECT sm.symbol,
                       o.trade_date,
                       o.volume,
                       b.median_volume,
                       CASE
                         WHEN o.volume >= b.median_volume * {sql_literal(quality_config.volume_anomaly_multiplier)}
                         THEN 'HIGH_VOLUME_ANOMALY'
                         ELSE 'LOW_VOLUME_ANOMALY'
                       END AS rule_code
                  FROM core.ohlcv_daily o
                  JOIN core.symbol_master sm ON sm.symbol_id = o.symbol_id
                  JOIN volume_baseline b ON b.symbol_id = o.symbol_id
                 WHERE o.source_id = {sql_literal(source_id)}
                   AND o.trade_date BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
                   AND b.sample_count >= {sql_literal(quality_config.min_volume_sample_count)}
                   AND b.median_volume > 0
                   AND o.volume > 0
                   AND (
                        o.volume >= b.median_volume * {sql_literal(quality_config.volume_anomaly_multiplier)}
                     OR o.volume <= b.median_volume / {sql_literal(quality_config.volume_anomaly_multiplier)}
                   )
            )
            INSERT INTO meta.data_quality_issue
              (run_id, dataset, symbol, trade_date, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'core.ohlcv_daily', symbol, trade_date,
                   'warning', rule_code,
                   'Volume differs materially from the symbol median baseline.'
              FROM anomalous;
            """
        )

    def enforce_lineage_quality_slo(
        self,
        *,
        run_id: UUID,
        source_id: str,
        start_date: date,
        end_date: date,
        min_coverage: float = DEFAULT_MIN_LINEAGE_COVERAGE,
    ) -> LineageQualityReport:
        rows = self.executor.fetch_json(
            f"""
            SELECT
              (
                SELECT COUNT(*)::int
                  FROM core.ohlcv_daily
                 WHERE run_id = {sql_literal(run_id)}
                   AND source_id = {sql_literal(source_id)}
                   AND trade_date BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
              ) AS target_rows,
              (
                SELECT COUNT(*)::int
                  FROM meta.lineage_event
                 WHERE run_id = {sql_literal(run_id)}
                   AND target_table = 'core.ohlcv_daily'
              ) AS lineage_rows
            """
        )
        counts = rows[0] if rows else {}
        report = assess_lineage_quality(
            target_rows=int(counts.get("target_rows") or 0),
            lineage_rows=int(counts.get("lineage_rows") or 0),
            min_coverage=min_coverage,
        )
        return require_lineage_quality(report)

    def run_kis_krx_consistency_checks(
        self,
        *,
        run_id: UUID,
        start_date: date,
        end_date: date,
        config: OhlcvQualityConfig | None = None,
    ) -> None:
        quality_config = config or OhlcvQualityConfig()
        self.executor.execute_script(
            f"""
            WITH krx AS (
                SELECT sm.symbol,
                       o.trade_date,
                       o.close AS krx_close
                  FROM core.ohlcv_daily o
                  JOIN core.symbol_master sm ON sm.symbol_id = o.symbol_id
                 WHERE o.source_id = 'KRX'
                   AND o.trade_date BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
            ),
            kis AS (
                SELECT ticker AS symbol,
                       "time" AS trade_date,
                       adj_close AS kis_adj_close
                  FROM feature.kis_adjusted_ohlcv_daily
                 WHERE "time" BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
            ),
            compared AS (
                SELECT COALESCE(kis.symbol, krx.symbol) AS symbol,
                       COALESCE(kis.trade_date, krx.trade_date) AS trade_date,
                       kis.kis_adj_close,
                       krx.krx_close
                  FROM kis
                  FULL OUTER JOIN krx
                    ON krx.symbol = kis.symbol
                   AND krx.trade_date = kis.trade_date
            ),
            issues AS (
                SELECT symbol,
                       trade_date,
                       CASE
                         WHEN kis_adj_close IS NULL THEN 'KRX_MISSING_KIS_ADJUSTED'
                         WHEN krx_close IS NULL THEN 'KIS_MISSING_KRX_REFERENCE'
                         ELSE 'KIS_KRX_CLOSE_MISMATCH'
                       END AS rule_code
                  FROM compared
                 WHERE kis_adj_close IS NULL
                    OR krx_close IS NULL
                    OR (
                        krx_close <> 0
                    AND ABS(kis_adj_close - krx_close) / ABS(krx_close)
                        > {sql_literal(quality_config.price_mismatch_tolerance_ratio)}
                    )
            )
            INSERT INTO meta.data_quality_issue
              (run_id, dataset, symbol, trade_date, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'feature.kis_adjusted_ohlcv_daily', symbol, trade_date,
                   'warning', rule_code,
                   'KIS adjusted data and KRX source data consistency check failed.'
              FROM issues;
            """
        )

    def run_backtest_readiness_checks(
        self,
        *,
        run_id: UUID,
        start_date: date,
        end_date: date,
        bok_staleness_days: int = DEFAULT_BOK_STALENESS_DAYS,
    ) -> None:
        """Record PIT contract violations and coverage gaps for backtest inputs."""

        if bok_staleness_days < 0:
            raise ValueError("bok_staleness_days must be non-negative.")
        expected_bok_values = ", ".join(
            f"({sql_literal(bok_series_id(item))}, {sql_literal(item['cycle'])})"
            for item in BOK_SERIES_PRESETS["all-macro"]
        )
        expected_dart_values = _expected_dart_period_values(start_date, end_date)
        bok_stale_before = end_date - timedelta(days=bok_staleness_days)

        self.executor.execute_script(
            f"""
            INSERT INTO meta.data_quality_issue
              (run_id, dataset, trade_date, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'core.trading_calendar', c.trade_date,
                   'warning', 'KRX_CALENDAR_UNCONFIRMED',
                   'Weekday has no confirmed KRX open/holiday evidence.'
              FROM core.trading_calendar c
             WHERE c.market = 'KRX'
               AND c.trade_date BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
               AND EXTRACT(ISODOW FROM c.trade_date) NOT IN (6, 7)
               AND c.is_open IS NULL;

            INSERT INTO meta.data_quality_issue
              (run_id, dataset, trade_date, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'feature.wics_symbol_sector_history',
                   {sql_literal(end_date)}, 'warning', 'WICS_PIT_COVERAGE_GAP',
                   'WICS sector membership history does not cover all listed common stocks at the requested as-of date.'
              WHERE EXISTS (
                  SELECT 1
                    FROM core.symbol_master sm
                   WHERE sm.listing_status = 'listed'
                     AND sm.security_type = '보통주'
                     AND sm.market_segment IN ('KOSPI', 'KOSDAQ')
                     AND NOT EXISTS (
                         SELECT 1
                           FROM feature.wics_symbol_sector_history h
                          WHERE h.symbol_id = sm.symbol_id
                            AND h.valid_from <= {sql_literal(end_date)}
                            AND (h.valid_to IS NULL OR h.valid_to >= {sql_literal(end_date)})
                     )
              );

            INSERT INTO meta.data_quality_issue
              (run_id, dataset, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'feature.wics_symbol_sector_history',
                   'error', 'WICS_INTERVAL_OVERLAP',
                   'WICS sector membership intervals overlap for a symbol.'
              WHERE EXISTS (
                  SELECT 1
                    FROM feature.wics_symbol_sector_history a
                    JOIN feature.wics_symbol_sector_history b
                      ON a.symbol_id = b.symbol_id
                     AND (a.wics_code, a.valid_from) < (b.wics_code, b.valid_from)
                     AND a.valid_from <= COALESCE(b.valid_to, DATE '9999-12-31')
                     AND b.valid_from <= COALESCE(a.valid_to, DATE '9999-12-31')
              );

            INSERT INTO meta.data_quality_issue
              (run_id, dataset, symbol, trade_date, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'feature.dart_financial_filing', sm.symbol,
                   f.period_end, 'error', 'DART_AVAILABILITY_BEFORE_PERIOD',
                   'DART filing availability date precedes its reporting period end.'
              FROM feature.dart_financial_filing f
              JOIN core.symbol_master sm ON sm.symbol_id = f.symbol_id
             WHERE f.period_end BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
               AND f.available_from < f.period_end;

            INSERT INTO meta.data_quality_issue
              (run_id, dataset, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'feature.bok_macro_daily', 'error',
                   'BOK_AVAILABILITY_BEFORE_EFFECTIVE',
                   'BOK available_from precedes effective_date.'
              WHERE EXISTS (
                  SELECT 1
                    FROM feature.bok_macro_daily
                   WHERE available_from < effective_date
              );

            INSERT INTO meta.data_quality_issue
              (run_id, dataset, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'feature.ta_indicator_definition', 'error',
                   'TA_DEFINITION_COUNT_INVALID',
                   'TA indicator definition catalog count is not 158.'
              WHERE (SELECT COUNT(*) FROM feature.ta_indicator_definition) <> 158;

            WITH expected(series_id, cycle) AS (
                VALUES {expected_bok_values}
            ), observed AS (
                SELECT series_id,
                       MAX(available_from) AS latest_available_from,
                       COUNT(*)::int AS observation_count
                 FROM feature.bok_macro_daily
                 WHERE effective_date BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
                   AND available_from <= {sql_literal(end_date)}
                 GROUP BY series_id
            )
            INSERT INTO meta.data_quality_issue
              (run_id, dataset, trade_date, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'feature.bok_macro_daily', {sql_literal(end_date)},
                   'warning', 'BOK_EXPECTED_SERIES_MISSING',
                   'Expected BOK macro series has no observation in the requested range: ' || e.series_id
              FROM expected e
              LEFT JOIN observed o ON o.series_id = e.series_id
             WHERE o.series_id IS NULL;

            WITH expected(series_id, cycle) AS (
                VALUES {expected_bok_values}
            ), expected_trade_days AS (
                SELECT COUNT(*)::int AS day_count
                  FROM core.trading_calendar
                 WHERE market = 'KRX'
                   AND is_open IS TRUE
                   AND trade_date BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
            ), observed AS (
                SELECT series_id, COUNT(*)::int AS observation_count
                 FROM feature.bok_macro_daily
                 WHERE effective_date BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
                   AND available_from <= {sql_literal(end_date)}
                 GROUP BY series_id
            )
            INSERT INTO meta.data_quality_issue
              (run_id, dataset, trade_date, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'feature.bok_macro_daily', {sql_literal(end_date)},
                   'warning', 'BOK_DAILY_FREQUENCY_GAP',
                   'Daily BOK series has fewer observations than confirmed KRX open days: ' || e.series_id
              FROM expected e
              CROSS JOIN expected_trade_days d
              LEFT JOIN observed o ON o.series_id = e.series_id
             WHERE e.cycle = 'D'
               AND d.day_count > 0
               AND COALESCE(o.observation_count, 0) < d.day_count;

            INSERT INTO meta.data_quality_issue
              (run_id, dataset, trade_date, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'feature.bok_macro_daily', {sql_literal(end_date)},
                   'warning', 'BOK_SERIES_STALE',
                   'BOK series latest available_from is older than the configured staleness threshold: ' || series_id
              FROM feature.bok_macro_daily
             WHERE available_from <= {sql_literal(end_date)}
             GROUP BY series_id
            HAVING MAX(available_from) < {sql_literal(bok_stale_before)};

            WITH expected(report_code, period_end) AS (
                VALUES {expected_dart_values}
            ), observed AS (
                SELECT report_code, period_end, COUNT(*)::int AS cfs_count
                 FROM feature.dart_financial_filing
                 WHERE fs_div = 'CFS'
                   AND available_from <= {sql_literal(end_date)}
                 GROUP BY report_code, period_end
            )
            INSERT INTO meta.data_quality_issue
              (run_id, dataset, trade_date, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'feature.dart_financial_filing', e.period_end,
                   'warning', 'DART_CFS_REPORT_MISSING',
                   'No CFS filing was found for report ' || e.report_code || ' at ' || e.period_end
              FROM expected e
              LEFT JOIN observed o
                ON o.report_code = e.report_code
               AND o.period_end = e.period_end
             WHERE e.period_end IS NOT NULL
               AND o.period_end IS NULL;

            INSERT INTO meta.data_quality_issue
              (run_id, dataset, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'feature.dart_financial_filing', 'warning',
                   'DART_NON_CFS_ONLY',
                   'Financial filing coverage contains periods without a CFS version.'
              WHERE EXISTS (
                  SELECT 1
                   FROM feature.dart_financial_filing f
                   WHERE f.period_end BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
                     AND f.available_from <= {sql_literal(end_date)}
                   GROUP BY f.period_end, f.report_code
                  HAVING BOOL_OR(f.fs_div = 'CFS') IS FALSE
              );

            INSERT INTO meta.data_quality_issue
              (run_id, dataset, symbol, trade_date, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'feature.dart_financial_account_value', sm.symbol,
                   f.period_end, 'warning', 'DART_ACCOUNT_VALUES_MISSING',
                   'CFS filing has no normalized account values.'
              FROM feature.dart_financial_filing f
              JOIN core.symbol_master sm ON sm.symbol_id = f.symbol_id
             WHERE f.fs_div = 'CFS'
               AND f.period_end BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
               AND f.available_from <= {sql_literal(end_date)}
               AND NOT EXISTS (
                   SELECT 1
                     FROM feature.dart_financial_account_value a
                    WHERE a.filing_version_id = f.filing_version_id
               );

            WITH expected_dates AS (
                SELECT trade_date
                  FROM core.trading_calendar
                 WHERE market = 'KRX'
                   AND is_open IS TRUE
                   AND trade_date BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
            ), observed_dates AS (
                SELECT DISTINCT "time" AS trade_date
                  FROM feature.kis_adjusted_ohlcv_daily
                 WHERE "time" BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
            )
            INSERT INTO meta.data_quality_issue
              (run_id, dataset, trade_date, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'feature.kis_adjusted_ohlcv_daily', e.trade_date,
                   'warning', 'KIS_ADJUSTED_DATE_MISSING',
                   'Confirmed KRX open date has no KIS adjusted OHLCV rows.'
              FROM expected_dates e
              LEFT JOIN observed_dates o ON o.trade_date = e.trade_date
             WHERE o.trade_date IS NULL;

            INSERT INTO meta.data_quality_issue
              (run_id, dataset, trade_date, severity, rule_code, message)
            SELECT {sql_literal(run_id)}, 'feature.kis_corporate_action_event', a."time",
                   'error', 'KIS_REVISION_EVENT_NOT_RETAINED',
                   'KIS adjustment metadata was present without a retained corporate-action event.'
              FROM feature.kis_adjusted_ohlcv_daily a
             WHERE a."time" BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
               AND (NULLIF(BTRIM(a.mod_yn), '') IS NOT NULL
                    OR NULLIF(BTRIM(a.revision_reason), '') IS NOT NULL)
               AND NOT EXISTS (
                   SELECT 1
                     FROM feature.kis_corporate_action_event e
                    WHERE e.ticker = a.ticker
                      AND e.effective_date = a."time"
                      AND COALESCE(e.mod_yn, '') IS NOT DISTINCT FROM COALESCE(a.mod_yn, '')
                      AND COALESCE(e.revision_reason, '') IS NOT DISTINCT FROM COALESCE(a.revision_reason, '')
               );
            """
        )

    def count_data_quality_errors(self, *, run_id: UUID) -> int:
        rows = self.executor.fetch_json(
            f"""
            SELECT COUNT(*)::int AS error_count
              FROM meta.data_quality_issue
             WHERE run_id = {sql_literal(run_id)}
               AND severity = 'error';
            """
        )
        return int(rows[0]["error_count"]) if rows else 0

    def set_cursor(self, *, source_id: str, dataset: str, cursor_key: str, cursor_value: str) -> None:
        self.executor.execute_script(
            f"""
            INSERT INTO meta.ingestion_cursor (source_id, dataset, cursor_key, cursor_value)
            VALUES ({sql_literal(source_id)}, {sql_literal(dataset)}, {sql_literal(cursor_key)}, {sql_literal(cursor_value)})
            ON CONFLICT (source_id, dataset, cursor_key) DO UPDATE SET
              cursor_value = CASE
                WHEN meta.ingestion_cursor.dataset = 'ohlcv_daily'
                 AND meta.ingestion_cursor.cursor_key = 'last_successful_trade_date'
                THEN GREATEST(meta.ingestion_cursor.cursor_value::date, EXCLUDED.cursor_value::date)::text
                ELSE EXCLUDED.cursor_value
              END,
              updated_at = now();
            """
        )

    def fetch_ohlcv_rows(self, *, start_date: date, end_date: date, symbols: list[str] | None = None) -> list[dict[str, Any]]:
        symbol_filter = ""
        if symbols:
            symbol_filter = "AND sm.symbol IN (" + ", ".join(sql_literal(symbol) for symbol in symbols) + ")"
        return self.executor.fetch_json(
            f"""
            SELECT sm.symbol, sm.symbol_id, o.trade_date, o.open, o.high, o.low, o.close, o.volume, o.quality_flags
              FROM core.ohlcv_daily o
              JOIN core.symbol_master sm ON sm.symbol_id = o.symbol_id
             WHERE o.trade_date BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
               {symbol_filter}
             ORDER BY sm.symbol, o.trade_date
            """
        )

    def upsert_ta_definitions(self, definitions: list[dict[str, Any]]) -> None:
        if not definitions:
            return
        rows = [
            "("
            f"{sql_literal(item['category'])}, {sql_literal(item['name'])}, "
            f"{jsonb_literal(item.get('parameters', {}))}, {sql_literal(item.get('warmup_days', 0))}, "
            f"{jsonb_literal(item.get('output_schema', {}))}, {sql_literal(item['transform_version'])}"
            ")"
            for item in definitions
        ]
        self.executor.execute_script(
            f"""
            INSERT INTO feature.ta_indicator_definition
              (category, name, parameters_jsonb, warmup_days, output_schema_jsonb, transform_version)
            VALUES {", ".join(rows)}
            ON CONFLICT (category, name, parameters_jsonb) DO UPDATE SET
              warmup_days = EXCLUDED.warmup_days,
              output_schema_jsonb = EXCLUDED.output_schema_jsonb,
              transform_version = EXCLUDED.transform_version;
            """
        )

    def upsert_ta_values(self, *, category: str, rows: list[dict[str, Any]], run_id: UUID) -> None:
        if not rows:
            return
        table = _ta_table_name(category)
        values = [
            "("
            f"{sql_literal(row['symbol_id'])}, {sql_literal(row['trade_date'])}, "
            f"{jsonb_literal(row['values'])}, {sql_literal(run_id)}, {jsonb_literal(row.get('quality_flags', {}))}"
            ")"
            for row in rows
        ]
        self.executor.execute_script(
            f"""
            INSERT INTO {table} (symbol_id, trade_date, values_jsonb, run_id, quality_flags)
            VALUES {", ".join(values)}
            ON CONFLICT (trade_date, symbol_id) DO UPDATE SET
              values_jsonb = EXCLUDED.values_jsonb,
              run_id = EXCLUDED.run_id,
              quality_flags = EXCLUDED.quality_flags;
            """
        )

    def upsert_bok_observations(self, rows: list[dict[str, Any]], run_id: UUID) -> int:
        if not rows:
            return 0
        values = [
            "("
            f"{sql_literal(row['series_id'])}, {sql_literal(row['effective_date'])}, "
            f"{sql_literal(row.get('published_at'))}, {sql_literal(row.get('value'))}, "
            f"{sql_literal(row.get('available_from'))}, {jsonb_literal(row.get('metadata', {}))}, {sql_literal(run_id)}"
            ")"
            for row in rows
        ]
        self.executor.execute_script(
            f"""
            INSERT INTO feature.bok_macro_daily
              (series_id, effective_date, published_at, value, available_from, metadata_jsonb, run_id)
            VALUES {", ".join(values)}
            ON CONFLICT (series_id, effective_date) DO UPDATE SET
              published_at = EXCLUDED.published_at,
              value = EXCLUDED.value,
              available_from = EXCLUDED.available_from,
              metadata_jsonb = EXCLUDED.metadata_jsonb,
              run_id = EXCLUDED.run_id;
            """
        )
        return len(rows)

    def upsert_seibro_reports_and_scores(self, rows: list[dict[str, Any]], run_id: UUID) -> int:
        for row in rows:
            symbol_expr = (
                f"(SELECT symbol_id FROM core.symbol_master WHERE symbol = {sql_literal(row.get('symbol'))})"
                if row.get("symbol")
                else "NULL"
            )
            self.executor.execute_script(
                f"""
                WITH inserted AS (
                  INSERT INTO feature.seibro_report_summary
                    (symbol_id, report_date, company_name, summary, opinion, target_price, close_price,
                     institution, author, source_payload_hash, run_id)
                  VALUES (
                    {symbol_expr}, {sql_literal(row['report_date'])}, {sql_literal(row['company_name'])},
                    {sql_literal(row['summary'])}, {sql_literal(row.get('opinion'))},
                    {sql_literal(row.get('target_price'))}, {sql_literal(row.get('close_price'))},
                    {sql_literal(row.get('institution'))}, {sql_literal(row.get('author'))},
                    {sql_literal(row.get('source_payload_hash'))}, {sql_literal(run_id)}
                  )
                  RETURNING report_id
                )
                INSERT INTO feature.seibro_sentiment
                  (report_id, sentiment_score, model_version, prompt_version, run_id)
                SELECT report_id, {sql_literal(row['sentiment_score'])},
                       {sql_literal(row['model_version'])}, {sql_literal(row['prompt_version'])},
                       {sql_literal(run_id)}
                  FROM inserted
                ON CONFLICT (report_id) DO UPDATE SET
                  sentiment_score = EXCLUDED.sentiment_score,
                  model_version = EXCLUDED.model_version,
                  prompt_version = EXCLUDED.prompt_version,
                  scored_at = now(),
                  run_id = EXCLUDED.run_id;
                """
            )
        return len(rows)

    def upsert_analyst_report_summaries(self, rows: list[AnalystReportSummary], run_id: UUID) -> int:
        if not rows:
            return 0
        deduped = {
            (row.report_date, row.ticker, row.institution, row.author): row
            for row in rows
            if row.ticker and row.summary
        }
        if not deduped:
            return 0
        values = []
        for row in deduped.values():
            values.append(
                "("
                f"{sql_literal(row.report_date)}, {sql_literal(row.ticker)}, {sql_literal(row.company_name)}, "
                f"{sql_literal(row.summary)}, {sql_literal(row.opinion)}, {sql_literal(row.target_price)}, "
                f"{sql_literal(row.close_price)}, {sql_literal(row.institution)}, {sql_literal(row.author)}, "
                f"{sql_literal(row.source_payload_hash)}, {jsonb_literal(row.raw)}, {sql_literal(run_id)}"
                ")"
            )
        self.executor.execute_script(
            f"""
            INSERT INTO raw.analyst_report_summary
              (report_date, ticker, company_name, summary, opinion, target_price, close_price,
               institution, author, source_payload_hash, raw_jsonb, run_id)
            VALUES {", ".join(values)}
            ON CONFLICT (report_date, ticker, institution, author) DO UPDATE SET
              company_name = EXCLUDED.company_name,
              summary = EXCLUDED.summary,
              opinion = EXCLUDED.opinion,
              target_price = EXCLUDED.target_price,
              close_price = EXCLUDED.close_price,
              source_payload_hash = EXCLUDED.source_payload_hash,
              raw_jsonb = EXCLUDED.raw_jsonb,
              run_id = EXCLUDED.run_id,
              updated_at = now();
            """
        )
        return len(deduped)

    def count_analyst_report_summaries(
        self, *, start_date: date, end_date: date, run_id: UUID | None = None
    ) -> int:
        run_filter = f"AND run_id = {sql_literal(run_id)}" if run_id else ""
        rows = self.executor.fetch_json(
            f"""
            SELECT COUNT(*)::int AS row_count
              FROM raw.analyst_report_summary
             WHERE report_date BETWEEN {sql_literal(start_date)} AND {sql_literal(end_date)}
             {run_filter}
            """
        )
        return int(rows[0]["row_count"]) if rows else 0

    def refresh_seibro_universe(self, *, as_of_date: date, min_score: float, min_reports: int, run_id: UUID) -> None:
        self.executor.execute_script(
            f"""
            INSERT INTO feature.seibro_universe_daily
              (as_of_date, symbol_id, avg_sentiment_score, report_count, included, exclusion_reason, run_id)
            SELECT {sql_literal(as_of_date)}::date AS as_of_date,
                   r.symbol_id,
                   AVG(s.sentiment_score)::numeric(6,4) AS avg_sentiment_score,
                   COUNT(*)::int AS report_count,
                   (AVG(s.sentiment_score) >= {sql_literal(min_score)} AND COUNT(*) >= {sql_literal(min_reports)}) AS included,
                   CASE
                     WHEN COUNT(*) < {sql_literal(min_reports)} THEN 'insufficient_reports'
                     WHEN AVG(s.sentiment_score) < {sql_literal(min_score)} THEN 'sentiment_below_threshold'
                     ELSE NULL
                   END AS exclusion_reason,
                   {sql_literal(run_id)}
              FROM feature.seibro_report_summary r
              JOIN feature.seibro_sentiment s ON s.report_id = r.report_id
             WHERE r.symbol_id IS NOT NULL
               AND r.report_date <= {sql_literal(as_of_date)}
             GROUP BY r.symbol_id
            ON CONFLICT (as_of_date, symbol_id) DO UPDATE SET
              avg_sentiment_score = EXCLUDED.avg_sentiment_score,
              report_count = EXCLUDED.report_count,
              included = EXCLUDED.included,
              exclusion_reason = EXCLUDED.exclusion_reason,
              run_id = EXCLUDED.run_id;
            """
        )

    def upsert_dart_corp_map(self, rows: list[dict[str, Any]], run_id: UUID) -> int:
        usable_rows = [row for row in rows if row.get("stock_code")]
        if not usable_rows:
            return 0
        values = [
            "("
            f"{sql_literal(row['corp_code'])}, {sql_literal(row.get('corp_name'))}, "
            f"{sql_literal(row['stock_code'])}, {sql_literal(row.get('modify_date'))}, {sql_literal(run_id)}"
            ")"
            for row in usable_rows
        ]
        self.executor.execute_script(
            f"""
            INSERT INTO feature.dart_corp_symbol_map
              (corp_code, corp_name, symbol, modify_date, run_id)
            VALUES {", ".join(values)}
            ON CONFLICT (corp_code) DO UPDATE SET
              corp_name = EXCLUDED.corp_name,
              symbol = EXCLUDED.symbol,
              modify_date = EXCLUDED.modify_date,
              run_id = EXCLUDED.run_id,
              updated_at = now();
            """
        )
        return len(usable_rows)

    def upsert_kind_symbol_metadata(self, rows: list[dict[str, Any]], run_id: UUID, *, as_of_date: date) -> int:
        usable_rows = [row for row in rows if row.get("symbol") and row.get("company_name")]
        if not usable_rows:
            return 0
        values = [
            "("
            f"{sql_literal(row['symbol'])}, {sql_literal(row.get('company_name'))}, "
            f"{sql_literal(row.get('market_segment'))}, {sql_literal(row.get('listed_at'))}, "
            f"{sql_literal(as_of_date)}, {jsonb_literal(_kind_sector_metadata(row, run_id))}, {sql_literal(run_id)}"
            ")"
            for row in usable_rows
        ]
        self.executor.execute_script(
            f"""
            WITH incoming(symbol, name, market_segment, listed_at, as_of_date, metadata_jsonb, run_id) AS (
                VALUES {", ".join(values)}
            ), resolved AS (
                SELECT sm.symbol_id, i.symbol, i.name, i.market_segment,
                       COALESCE(i.listed_at::date, i.as_of_date::date) AS valid_from,
                       i.metadata_jsonb::jsonb, i.run_id::uuid
                  FROM incoming i
                  JOIN core.symbol_master sm ON sm.symbol = i.symbol
            )
            UPDATE core.symbol_master sm
               SET name = COALESCE(NULLIF(r.name, ''), sm.name),
                   market_segment = COALESCE(NULLIF(r.market_segment, ''), sm.market_segment),
                   listing_status = 'listed',
                   listed_at = COALESCE(LEAST(sm.listed_at, r.valid_from), r.valid_from, sm.listed_at),
                   delisted_at = NULL,
                   metadata_jsonb = sm.metadata_jsonb || r.metadata_jsonb,
                   updated_at = now()
              FROM resolved r
             WHERE sm.symbol_id = r.symbol_id;

            WITH incoming(symbol, name, market_segment, listed_at, as_of_date, metadata_jsonb, run_id) AS (
                VALUES {", ".join(values)}
            ), resolved AS (
                SELECT sm.symbol_id, i.market_segment,
                       COALESCE(i.listed_at::date, i.as_of_date::date) AS valid_from,
                       i.metadata_jsonb::jsonb, i.run_id::uuid
                  FROM incoming i
                  JOIN core.symbol_master sm ON sm.symbol = i.symbol
            )
            INSERT INTO core.symbol_listing_history
              (symbol_id, valid_from, valid_to, market, listing_status, event_type, source_id, run_id, metadata_jsonb)
            SELECT r.symbol_id, r.valid_from, NULL, r.market_segment, 'listed', 'listed', 'KIND', r.run_id, r.metadata_jsonb
              FROM resolved r
            ON CONFLICT (symbol_id, valid_from) DO UPDATE SET
              market = COALESCE(EXCLUDED.market, core.symbol_listing_history.market),
              listing_status = 'listed',
              event_type = 'listed',
              source_id = 'KIND',
              run_id = EXCLUDED.run_id,
              metadata_jsonb = core.symbol_listing_history.metadata_jsonb || EXCLUDED.metadata_jsonb;
            """
        )
        return len(usable_rows)

    def upsert_kind_symbol_sectors(self, rows: list[dict[str, Any]], run_id: UUID) -> int:
        usable_rows = [row for row in rows if row.get("symbol") and row.get("sector")]
        if not usable_rows:
            return 0
        values = [
            "("
            f"{sql_literal(row['symbol'])}, {sql_literal(row.get('sector'))}, "
            f"{sql_literal(row.get('market_segment'))}, {sql_literal(row.get('sector_as_of'))}, "
            f"{jsonb_literal(_kind_sector_metadata(row, run_id))}, {sql_literal(run_id)}"
            ")"
            for row in usable_rows
        ]
        self.executor.execute_script(
            f"""
            WITH incoming(symbol, sector, market_segment, sector_as_of, metadata_jsonb, run_id) AS (
                VALUES {", ".join(values)}
            )
            UPDATE core.symbol_master sm
               SET sector = i.sector,
                   sector_source = 'KIND',
                   sector_as_of = i.sector_as_of::date,
                   sector_run_id = i.run_id::uuid,
                   market_segment = COALESCE(NULLIF(sm.market_segment, ''), NULLIF(i.market_segment, '')),
                   metadata_jsonb = sm.metadata_jsonb || i.metadata_jsonb,
                   updated_at = now()
              FROM incoming i
             WHERE sm.symbol = i.symbol;
            """
        )
        return len(usable_rows)

    def upsert_wics_symbol_sectors(self, rows: list[dict[str, Any]], run_id: UUID) -> int:
        usable_rows = [row for row in rows if row.get("symbol") and row.get("sector")]
        if not usable_rows:
            return 0
        missing_as_of = [row.get("symbol") for row in usable_rows if not row.get("sector_as_of")]
        if missing_as_of:
            raise ValueError(
                "WICS sector rows require an explicit sector_as_of date for PIT history: "
                + ", ".join(str(symbol) for symbol in missing_as_of[:5])
            )
        values = [
            "("
            f"{sql_literal(row['symbol'])}, {sql_literal(row.get('sector_code') or row.get('sector'))}, "
            f"{sql_literal(row.get('sector'))}, {sql_literal(row.get('market_segment'))}, "
            f"{sql_literal(row.get('sector_as_of'))}, "
            f"{jsonb_literal(_wics_sector_metadata(row, run_id))}, {sql_literal(run_id)}"
            ")"
            for row in usable_rows
        ]
        self.executor.execute_script(
            f"""
            WITH incoming(symbol, wics_code, sector, market_segment, valid_from, metadata_jsonb, run_id) AS (
                VALUES {", ".join(values)}
            ), resolved AS (
                SELECT sm.symbol_id, i.wics_code, i.sector, i.market_segment,
                       i.valid_from::date, i.metadata_jsonb::jsonb, i.run_id::uuid
                  FROM incoming i
                  JOIN core.symbol_master sm ON sm.symbol = i.symbol
            )
            INSERT INTO feature.wics_sector_definition
                (wics_code, sector_name, source_id, run_id, metadata_jsonb)
            SELECT DISTINCT r.wics_code, r.sector, 'WICS', r.run_id,
                   r.metadata_jsonb || jsonb_build_object('sector_level', 'sector')
              FROM resolved r
            ON CONFLICT (wics_code) DO UPDATE SET
                sector_name = EXCLUDED.sector_name,
                source_id = EXCLUDED.source_id,
                run_id = EXCLUDED.run_id,
                metadata_jsonb = feature.wics_sector_definition.metadata_jsonb || EXCLUDED.metadata_jsonb,
                updated_at = now();

            WITH incoming(symbol, wics_code, sector, market_segment, valid_from, metadata_jsonb, run_id) AS (
                VALUES {", ".join(values)}
            ), resolved AS (
                SELECT sm.symbol_id, i.wics_code, i.sector, i.market_segment,
                       i.valid_from::date, i.metadata_jsonb::jsonb, i.run_id::uuid
                  FROM incoming i
                  JOIN core.symbol_master sm ON sm.symbol = i.symbol
            )
            DELETE FROM feature.wics_symbol_sector_history h
             USING resolved r
             WHERE h.symbol_id = r.symbol_id
               AND h.valid_from = r.valid_from;

            WITH incoming(symbol, wics_code, sector, market_segment, valid_from, metadata_jsonb, run_id) AS (
                VALUES {", ".join(values)}
            ), resolved AS (
                SELECT sm.symbol_id, i.wics_code, i.sector, i.market_segment,
                       i.valid_from::date, i.metadata_jsonb::jsonb, i.run_id::uuid
                  FROM incoming i
                  JOIN core.symbol_master sm ON sm.symbol = i.symbol
            )
            INSERT INTO feature.wics_symbol_sector_history
                (symbol_id, wics_code, sector_name, market_segment, valid_from, valid_to, source_id, run_id, metadata_jsonb)
            SELECT r.symbol_id, r.wics_code, r.sector, r.market_segment, r.valid_from,
                   NULL, 'WICS', r.run_id, r.metadata_jsonb
              FROM resolved r
             WHERE NOT EXISTS (
                 SELECT 1
                   FROM feature.wics_symbol_sector_history h
                  WHERE h.symbol_id = r.symbol_id
                    AND h.valid_to IS NULL
                    AND h.wics_code = r.wics_code
                    AND h.sector_name = r.sector
             )
            ON CONFLICT (symbol_id, valid_from) DO UPDATE SET
                wics_code = EXCLUDED.wics_code,
                sector_name = EXCLUDED.sector_name,
                market_segment = EXCLUDED.market_segment,
                valid_to = EXCLUDED.valid_to,
                source_id = EXCLUDED.source_id,
                run_id = EXCLUDED.run_id,
                metadata_jsonb = feature.wics_symbol_sector_history.metadata_jsonb || EXCLUDED.metadata_jsonb;

            WITH ordered AS (
                SELECT symbol_id, wics_code, valid_from,
                       LEAD(valid_from) OVER (
                           PARTITION BY symbol_id
                           ORDER BY valid_from
                       ) AS next_valid_from
                  FROM feature.wics_symbol_sector_history
            )
            UPDATE feature.wics_symbol_sector_history h
               SET valid_to = ordered.next_valid_from - 1
              FROM ordered
             WHERE h.symbol_id = ordered.symbol_id
               AND h.wics_code = ordered.wics_code
               AND h.valid_from = ordered.valid_from;

            WITH incoming(symbol, wics_code, sector, market_segment, valid_from, metadata_jsonb, run_id) AS (
                VALUES {", ".join(values)}
            )
            UPDATE core.symbol_master sm
               SET sector = i.sector,
                   sector_source = 'WICS',
                   sector_as_of = i.valid_from::date,
                   sector_run_id = i.run_id::uuid,
                   market_segment = COALESCE(NULLIF(sm.market_segment, ''), NULLIF(i.market_segment, '')),
                   metadata_jsonb = sm.metadata_jsonb || i.metadata_jsonb,
                   updated_at = now()
              FROM incoming i
             WHERE sm.symbol = i.symbol;
            """
        )
        return len(usable_rows)

    def store_wics_raw_payloads(self, rows: list[dict[str, Any]], run_id: UUID) -> int:
        usable_rows = [
            row
            for row in rows
            if row.get("symbol") and row.get("raw_html") and row.get("sector_as_of")
        ]
        if not usable_rows:
            return 0
        values = [
            "("
            f"{sql_literal('WICS')}, {sql_literal(row['symbol'])}, {sql_literal(row['sector_as_of'])}, "
            f"{sql_literal(row.get('source_url'))}, {sql_literal(row['raw_html'])}, "
            f"{sql_literal(_stable_hash(row['raw_html']))}, {sql_literal(run_id)}"
            ")"
            for row in usable_rows
        ]
        self.executor.execute_script(
            f"""
            INSERT INTO raw.wics_company_info_response
              (source_id, ticker, request_date, source_url, payload_html, payload_hash, run_id)
            VALUES {", ".join(values)}
            ON CONFLICT (source_id, ticker, request_date, payload_hash) DO NOTHING;
            """
        )
        return len(usable_rows)

    def upsert_dart_financials(self, rows: list[dict[str, Any]], run_id: UUID) -> int:
        if not rows:
            return 0
        normalized_rows = []
        for row in rows:
            payload_hash = row.get("source_payload_hash") or _stable_hash(row.get("accounts", {}))
            normalized_rows.append({**row, "source_payload_hash": payload_hash})
        values = [
            "("
            "(SELECT symbol_id FROM core.symbol_master WHERE symbol = "
            f"{sql_literal(row['symbol'])}), {sql_literal(row['corp_code'])}, "
            f"{sql_literal(row['period_end'])}, {sql_literal(row.get('available_from'))}, "
            f"{sql_literal(row.get('reported_at'))}, {sql_literal(row['report_code'])}, {sql_literal(row['fs_div'])}, "
            f"{sql_literal(row.get('filing_id') or 'payload:' + row['source_payload_hash'])}, "
            f"{sql_literal(row['source_payload_hash'])}, {sql_literal(row.get('availability_policy') or 'conservative_report_deadline')}, "
            f"{jsonb_literal(row.get('accounts', {}))}, {sql_literal(run_id)}"
            ")"
            for row in normalized_rows
        ]
        self.executor.execute_script(
            f"""
            INSERT INTO feature.dart_financial_quarterly
              (symbol_id, corp_code, period_end, available_from, reported_at, report_code, fs_div,
               filing_id, source_payload_hash, availability_policy, accounts_jsonb, run_id)
            VALUES {", ".join(values)}
            ON CONFLICT (symbol_id, period_end, report_code, fs_div) DO UPDATE SET
              corp_code = EXCLUDED.corp_code,
              available_from = EXCLUDED.available_from,
              reported_at = EXCLUDED.reported_at,
              filing_id = EXCLUDED.filing_id,
              source_payload_hash = EXCLUDED.source_payload_hash,
              availability_policy = EXCLUDED.availability_policy,
              accounts_jsonb = EXCLUDED.accounts_jsonb,
              run_id = EXCLUDED.run_id;

            INSERT INTO feature.dart_financial_filing
              (symbol_id, corp_code, period_end, available_from, reported_at, report_code, fs_div,
               filing_id, source_payload_hash, availability_policy, accounts_jsonb, run_id)
            VALUES {", ".join(values)}
            ON CONFLICT (symbol_id, period_end, report_code, fs_div, source_payload_hash) DO NOTHING;
            """
        )
        account_values = []
        for row in normalized_rows:
            payload_hash = row["source_payload_hash"]
            for account in row.get("account_rows", []):
                account_values.append(
                    "("
                    "(SELECT filing_version_id FROM feature.dart_financial_filing WHERE symbol_id = "
                    f"(SELECT symbol_id FROM core.symbol_master WHERE symbol = {sql_literal(row['symbol'])}) "
                    f"AND period_end = {sql_literal(row['period_end'])} AND report_code = {sql_literal(row['report_code'])} "
                    f"AND fs_div = {sql_literal(row['fs_div'])} AND source_payload_hash = {sql_literal(payload_hash)}), "
                    f"{sql_literal(account['account_id'])}, {sql_literal(account.get('account_name'))}, "
                    f"{sql_literal(account.get('statement_code'))}, {sql_literal(account.get('amount'))}, "
                    f"{sql_literal(account.get('current_cumulative_amount'))}, {sql_literal(account.get('prior_quarter_amount'))}, "
                    f"{sql_literal(account.get('prior_amount'))}, {sql_literal(account.get('prior_year_amount'))}, "
                    f"{sql_literal(account.get('currency'))}, {jsonb_literal(account.get('raw', {}))}"
                    ")"
                )
        if account_values:
            self.executor.execute_script(
                f"""
                INSERT INTO feature.dart_financial_account_value
                  (filing_version_id, account_id, account_name, statement_code, amount,
                   current_cumulative_amount, prior_quarter_amount, prior_amount, prior_year_amount, currency, raw_jsonb)
                VALUES {", ".join(account_values)}
                ON CONFLICT (filing_version_id, account_id) DO UPDATE SET
                    account_name = EXCLUDED.account_name,
                    statement_code = EXCLUDED.statement_code,
                    amount = EXCLUDED.amount,
                    current_cumulative_amount = EXCLUDED.current_cumulative_amount,
                    prior_quarter_amount = EXCLUDED.prior_quarter_amount,
                    prior_amount = EXCLUDED.prior_amount,
                    prior_year_amount = EXCLUDED.prior_year_amount,
                    currency = EXCLUDED.currency,
                    raw_jsonb = EXCLUDED.raw_jsonb;
                """
            )
        return len(normalized_rows)


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _symbol_lifecycle_sql(rows: list[str]) -> str:
    if not rows:
        return ""
    return f"""
        WITH incoming(symbol, valid_from, market, listing_status, event_type, source_id, run_id, metadata_jsonb) AS (
            VALUES {", ".join(rows)}
        ),
        resolved AS (
            SELECT sm.symbol_id,
                   i.valid_from::date AS valid_from,
                   i.market,
                   i.listing_status,
                   i.event_type,
                   i.source_id,
                   i.run_id::uuid AS run_id,
                   i.metadata_jsonb::jsonb AS metadata_jsonb
              FROM incoming i
              JOIN core.symbol_master sm ON sm.symbol = i.symbol
        ),
        closed AS (
            UPDATE core.symbol_listing_history h
               SET valid_to = r.valid_from - 1
              FROM resolved r
             WHERE h.symbol_id = r.symbol_id
               AND h.valid_to IS NULL
               AND (
                    h.market IS DISTINCT FROM r.market
                 OR h.listing_status IS DISTINCT FROM r.listing_status
               )
             RETURNING h.symbol_id
        )
        INSERT INTO core.symbol_listing_history
          (symbol_id, valid_from, valid_to, market, listing_status, event_type, source_id, run_id, metadata_jsonb)
        SELECT r.symbol_id, r.valid_from, NULL, r.market, r.listing_status, r.event_type,
               r.source_id, r.run_id, r.metadata_jsonb
          FROM resolved r
         WHERE NOT EXISTS (
             SELECT 1
               FROM core.symbol_listing_history h
              WHERE h.symbol_id = r.symbol_id
                AND h.valid_to IS NULL
                AND h.market IS NOT DISTINCT FROM r.market
                AND h.listing_status IS NOT DISTINCT FROM r.listing_status
         )
        ON CONFLICT (symbol_id, valid_from) DO UPDATE SET
          market = EXCLUDED.market,
          listing_status = EXCLUDED.listing_status,
          event_type = EXCLUDED.event_type,
          source_id = EXCLUDED.source_id,
          run_id = EXCLUDED.run_id,
          metadata_jsonb = core.symbol_listing_history.metadata_jsonb || EXCLUDED.metadata_jsonb;
        """


def _symbol_security_type_history_sql(rows: list[str]) -> str:
    """Persist every source-backed symbol/date classification as a non-overlapping interval."""

    if not rows:
        return ""
    return f"""
        WITH incoming(symbol, valid_from, security_type, source_id, run_id, source_version, metadata_jsonb) AS (
            VALUES {", ".join(rows)}
        ),
        resolved AS (
            SELECT sm.symbol_id,
                   i.valid_from::date AS valid_from,
                   i.security_type,
                   i.source_id,
                   i.run_id::uuid AS run_id,
                   i.source_version,
                   i.metadata_jsonb::jsonb AS metadata_jsonb
              FROM incoming i
              JOIN core.symbol_master sm ON sm.symbol = i.symbol
        ),
        existing AS (
            SELECT h.symbol_id,
                   h.valid_from,
                   h.security_type,
                   h.source_id,
                   h.run_id,
                   h.source_version,
                   h.metadata_jsonb,
                   0 AS source_priority
              FROM core.symbol_security_type_history h
             WHERE h.symbol_id IN (SELECT DISTINCT symbol_id FROM resolved)
        ),
        timeline AS (
            SELECT symbol_id, valid_from, security_type, source_id, run_id,
                   source_version, metadata_jsonb, 1 AS source_priority
              FROM resolved
            UNION ALL
            SELECT symbol_id, valid_from, security_type, source_id, run_id,
                   source_version, metadata_jsonb, source_priority
              FROM existing
        ),
        deduplicated AS (
            SELECT DISTINCT ON (symbol_id, valid_from)
                   symbol_id, valid_from, security_type, source_id, run_id,
                   source_version, metadata_jsonb
              FROM timeline
             ORDER BY symbol_id, valid_from, source_priority DESC
        ),
        intervals AS (
            SELECT symbol_id,
                   valid_from,
                   LEAD(valid_from) OVER (
                       PARTITION BY symbol_id
                       ORDER BY valid_from
                   ) - 1 AS valid_to,
                   security_type,
                   source_id,
                   run_id,
                   source_version,
                   metadata_jsonb
              FROM deduplicated
        )
        INSERT INTO core.symbol_security_type_history
          (symbol_id, valid_from, valid_to, security_type, source_id, run_id, source_version, metadata_jsonb)
        SELECT symbol_id, valid_from, valid_to, security_type, source_id, run_id,
               source_version, metadata_jsonb
          FROM intervals
        ON CONFLICT (symbol_id, valid_from) DO UPDATE SET
          valid_to = EXCLUDED.valid_to,
          security_type = EXCLUDED.security_type,
          source_id = EXCLUDED.source_id,
          run_id = EXCLUDED.run_id,
          source_version = EXCLUDED.source_version,
          metadata_jsonb = core.symbol_security_type_history.metadata_jsonb || EXCLUDED.metadata_jsonb;
        """


def _symbol_name_history_sql(rows: list[str]) -> str:
    if not rows:
        return ""
    return f"""
        WITH incoming(symbol, valid_from, name, source_id, run_id, metadata_jsonb) AS (
            VALUES {", ".join(rows)}
        ),
        resolved AS (
            SELECT sm.symbol_id,
                   i.valid_from::date AS valid_from,
                   NULLIF(i.name, '') AS name,
                   i.source_id,
                   i.run_id::uuid AS run_id,
                   i.metadata_jsonb::jsonb AS metadata_jsonb
              FROM incoming i
              JOIN core.symbol_master sm ON sm.symbol = i.symbol
             WHERE NULLIF(i.name, '') IS NOT NULL
        ),
        closed AS (
            UPDATE core.symbol_name_history h
               SET valid_to = r.valid_from - 1
              FROM resolved r
             WHERE h.symbol_id = r.symbol_id
               AND h.valid_to IS NULL
               AND h.name IS DISTINCT FROM r.name
             RETURNING h.symbol_id
        )
        INSERT INTO core.symbol_name_history
          (symbol_id, valid_from, valid_to, name, source_id, run_id, metadata_jsonb)
        SELECT r.symbol_id, r.valid_from, NULL, r.name, r.source_id, r.run_id, r.metadata_jsonb
          FROM resolved r
         WHERE NOT EXISTS (
             SELECT 1
               FROM core.symbol_name_history h
              WHERE h.symbol_id = r.symbol_id
                AND h.valid_to IS NULL
                AND h.name = r.name
         )
        ON CONFLICT (symbol_id, valid_from, name) DO UPDATE SET
          source_id = EXCLUDED.source_id,
          run_id = EXCLUDED.run_id,
          metadata_jsonb = core.symbol_name_history.metadata_jsonb || EXCLUDED.metadata_jsonb;
        """


def _api_request_log_row(event: ApiRequestLog, run_id: UUID) -> str:
    request_hash = _stable_hash(event.request)
    response_hash = _stable_hash(event.response) if event.response is not None else None
    return (
        "("
        f"{sql_literal(run_id)}, {sql_literal(event.source_id)}, {sql_literal(event.endpoint_key)}, "
        f"{sql_literal(request_hash)}, {sql_literal(event.success)}, {sql_literal(event.status_code)}, "
        f"{sql_literal(event.elapsed_ms)}, {sql_literal(event.retry_count)}, {sql_literal(response_hash)}, "
        f"{sql_literal(_truncate(event.error_message, 4000))}, {jsonb_literal(event.metadata)}, "
        f"{sql_literal(event.request_started_at.isoformat())}"
        ")"
    )


def _lineage_event_row(event: LineageEvent, run_id: UUID) -> str:
    return (
        "("
        f"{sql_literal(event.target_table)}, {sql_literal(event.target_key)}, "
        f"{sql_literal(event.source_table)}, {sql_literal(event.source_key)}, "
        f"{sql_literal(run_id)}, {sql_literal(event.transform_version)}, {jsonb_literal(event.metadata)}"
        ")"
    )


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value[:limit]


def _kind_sector_metadata(row: dict[str, Any], run_id: UUID) -> dict[str, Any]:
    return {
        "kind_company_name": row.get("company_name"),
        "kind_market_segment_raw": row.get("market_segment_raw"),
        "kind_market_segment": row.get("market_segment"),
        "kind_sector": row.get("sector"),
        "kind_main_products": row.get("main_products"),
        "kind_listed_at": row.get("listed_at"),
        "kind_closing_month": row.get("closing_month"),
        "kind_representative_name": row.get("representative_name"),
        "kind_homepage": row.get("homepage"),
        "kind_region": row.get("region"),
        "kind_sector_source": "KIND",
        "kind_sector_as_of": row.get("sector_as_of"),
        "kind_sector_run_id": str(run_id),
    }


def _wics_sector_metadata(row: dict[str, Any], run_id: UUID) -> dict[str, Any]:
    return {
        "wics_company_name": row.get("company_name"),
        "wics_market_segment_raw": row.get("market_segment_raw"),
        "wics_market_segment": row.get("market_segment"),
        "wics_sector_code": row.get("sector_code"),
        "wics_sector": row.get("sector"),
        "wics_sector_label": row.get("sector_label"),
        "wics_source_url": row.get("source_url"),
        "wics_sector_as_of": row.get("sector_as_of"),
        "wics_sector_run_id": str(run_id),
    }


def _infer_market(raw: dict[str, Any]) -> str | None:
    for key in ("MKT_NM", "mkt_nm", "market"):
        value = raw.get(key)
        if value:
            return str(value)
    return None


def _infer_market_segment(raw: dict[str, Any]) -> str | None:
    raw_market = _infer_market(raw)
    if not raw_market:
        return None
    normalized = str(raw_market).strip().upper().replace(" ", "")
    aliases = {
        "KOSPI": "KOSPI",
        "유가증권": "KOSPI",
        "STK": "KOSPI",
        "KOSDAQ": "KOSDAQ",
        "코스닥": "KOSDAQ",
        "KSQ": "KOSDAQ",
        "KONEX": "KONEX",
        "코넥스": "KONEX",
        "KNX": "KONEX",
    }
    return aliases.get(normalized, str(raw_market).strip())


def _infer_security_type(raw: dict[str, Any]) -> str | None:
    name_value = raw.get("ISU_NM") or raw.get("isu_nm") or raw.get("ISU_ABBRV") or raw.get("isu_abbrv")
    name = str(name_value or "").strip() or None
    return classify_security_type(
        raw,
        name=name,
        market_segment=_infer_market_segment(raw),
    )


def _security_type_history_metadata(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Return explicit source fields that justify a historical classification.

    A name or current market can classify the master record, but cannot prove an
    older security type. Only an observed classification field can open or update a
    point-in-time classification interval.
    """

    evidence_keys = (
        "security_type",
        "SECUGRP_NM",
        "secugrp_nm",
        "SECT_TP_NM",
        "sect_tp_nm",
        "MKT_TP_NM",
        "mkt_tp_nm",
    )
    evidence = {
        key: raw[key]
        for key in evidence_keys
        if raw.get(key) not in (None, "")
    }
    if not evidence:
        return None
    return {"classification_evidence": evidence}


def _symbol_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "MKT_NM",
        "SECT_TP_NM",
        "SECUGRP_NM",
        "MKT_TP_NM",
        "LIST_SHRS",
        "MKTCAP",
        "ISU_ABBRV",
        "ISU_NM",
        "secugrp_nm",
        "sect_tp_nm",
        "mkt_tp_nm",
        "isu_abbrv",
        "isu_nm",
        "market",
        "security_type",
    )
    return {key: raw[key] for key in keys if raw.get(key) not in (None, "")}


def _dq_issue_row(issue: DataQualityIssue, run_id: UUID) -> str:
    return (
        "("
        f"{sql_literal(run_id)}, {sql_literal(issue.dataset)}, {sql_literal(issue.symbol)}, "
        f"{sql_literal(issue.trade_date)}, {sql_literal(issue.severity)}, "
        f"{sql_literal(issue.rule_code)}, {sql_literal(issue.message)}"
        ")"
    )


def _expected_dart_period_values(start_date: date, end_date: date) -> str:
    values = ", ".join(
        f"({sql_literal(report_code)}, {sql_literal(date(year, month, day))}::date)"
        for year in range(start_date.year, end_date.year + 1)
        for report_code, (month, day) in DART_REPORT_CODE_PERIOD_END.items()
        if start_date <= date(year, month, day) <= end_date
    )
    return values or "(NULL::text, NULL::date)"


def _ta_table_name(category: str) -> str:
    allowed = {
        "trend": "feature.ta_trend_daily",
        "momentum": "feature.ta_momentum_daily",
        "volatility": "feature.ta_volatility_daily",
        "volume": "feature.ta_volume_daily",
        "pattern": "feature.ta_pattern_daily",
    }
    key = category.lower()
    if key not in allowed:
        raise ValueError(f"Unsupported TA category: {category}")
    return allowed[key]
