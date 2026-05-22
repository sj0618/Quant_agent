"""Repository layer for raw/core/feature/mart data engineering writes."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

from quant_agent.data.config import DatabaseConfig
from quant_agent.data.db import SqlExecutor, jsonb_literal, make_executor, sql_literal
from quant_agent.data.models import DataQualityIssue, OhlcvBar, RawSourcePayload
from quant_agent.data.quality import duplicate_keys, is_tradable_ohlcv, ohlcv_quality_flags


DATA_SOURCES = {
    "KRX": ("Korea Exchange", "KRX_DAILY_MARKET_ENDPOINTS", True),
    "KIS": ("Korea Investment Securities", "KIS_BASE_URL", False),
    "SEIBRO": ("KSD SEIBro Open Platform", "SEIBRO_BASE_URL", False),
    "BOK": ("Bank of Korea ECOS", "BOK_BASE_URL", False),
    "DART": ("OpenDART Financial Supervisory Service", "DART_BASE_URL", False),
    "TA": ("TA-Lib technical indicator transform", "TA_TRANSFORM_VERSION", False),
}


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
        calendar_dates: set[date] = set()
        ohlcv_rows = []
        lineage_rows = []
        issue_rows = []

        for bar in symbol_by_code.values():
            symbol_rows.append(
                "("
                f"{sql_literal(bar.symbol)}, {sql_literal(bar.name or bar.symbol)}, "
                f"{sql_literal(_infer_market(bar.raw))}, {sql_literal(_infer_security_type(bar.raw))}"
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

        calendar_rows = [
            "("
            f"{sql_literal('KRX')}, {sql_literal(trade_date)}, TRUE, "
            f"{sql_literal(source_id)}, {sql_literal(run_id)}"
            ")"
            for trade_date in sorted(calendar_dates)
        ]

        duplicate_issue_rows = [_dq_issue_row(issue, run_id) for issue in issues if issue.rule_code == "DUPLICATE_SYMBOL_DATE"]
        all_issue_rows = issue_rows + duplicate_issue_rows

        script_parts = [
            "BEGIN;",
            f"""
            INSERT INTO core.symbol_master (symbol, name, market, security_type)
            VALUES {", ".join(symbol_rows)}
            ON CONFLICT (symbol) DO UPDATE SET
              name = COALESCE(NULLIF(EXCLUDED.name, ''), core.symbol_master.name),
              market = COALESCE(EXCLUDED.market, core.symbol_master.market),
              security_type = COALESCE(EXCLUDED.security_type, core.symbol_master.security_type),
              updated_at = now();
            """,
            f"""
            INSERT INTO core.trading_calendar (market, trade_date, is_open, source_id, run_id)
            VALUES {", ".join(calendar_rows)}
            ON CONFLICT (market, trade_date) DO UPDATE SET
              is_open = EXCLUDED.is_open,
              source_id = EXCLUDED.source_id,
              run_id = EXCLUDED.run_id;
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
            f"{jsonb_literal(row.get('metadata', {}))}, {sql_literal(run_id)}"
            ")"
            for row in rows
        ]
        self.executor.execute_script(
            f"""
            INSERT INTO feature.bok_macro_daily
              (series_id, effective_date, published_at, value, metadata_jsonb, run_id)
            VALUES {", ".join(values)}
            ON CONFLICT (series_id, effective_date) DO UPDATE SET
              published_at = EXCLUDED.published_at,
              value = EXCLUDED.value,
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

    def upsert_dart_financials(self, rows: list[dict[str, Any]], run_id: UUID) -> int:
        if not rows:
            return 0
        values = [
            "("
            "(SELECT symbol_id FROM core.symbol_master WHERE symbol = "
            f"{sql_literal(row['symbol'])}), {sql_literal(row['corp_code'])}, "
            f"{sql_literal(row['period_end'])}, {sql_literal(row.get('reported_at'))}, "
            f"{sql_literal(row['report_code'])}, {sql_literal(row['fs_div'])}, "
            f"{jsonb_literal(row.get('accounts', {}))}, {sql_literal(run_id)}"
            ")"
            for row in rows
        ]
        self.executor.execute_script(
            f"""
            INSERT INTO feature.dart_financial_quarterly
              (symbol_id, corp_code, period_end, reported_at, report_code, fs_div, accounts_jsonb, run_id)
            VALUES {", ".join(values)}
            ON CONFLICT (symbol_id, period_end, report_code, fs_div) DO UPDATE SET
              corp_code = EXCLUDED.corp_code,
              reported_at = EXCLUDED.reported_at,
              accounts_jsonb = EXCLUDED.accounts_jsonb,
              run_id = EXCLUDED.run_id;
            """
        )
        return len(rows)


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _infer_market(raw: dict[str, Any]) -> str | None:
    for key in ("MKT_NM", "mkt_nm", "market"):
        value = raw.get(key)
        if value:
            return str(value)
    return None


def _infer_security_type(raw: dict[str, Any]) -> str | None:
    for key in ("SECUGRP_NM", "isu_abbrv", "security_type"):
        value = raw.get(key)
        if value:
            return str(value)
    return None


def _dq_issue_row(issue: DataQualityIssue, run_id: UUID) -> str:
    return (
        "("
        f"{sql_literal(run_id)}, {sql_literal(issue.dataset)}, {sql_literal(issue.symbol)}, "
        f"{sql_literal(issue.trade_date)}, {sql_literal(issue.severity)}, "
        f"{sql_literal(issue.rule_code)}, {sql_literal(issue.message)}"
        ")"
    )


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
