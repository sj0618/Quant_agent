"""LLM-authored screening: the model writes the SELECT, the system polices it.

Screening used to route a query into one of a handful of hardcoded SQL profiles by
keyword, so the strategies it could express were exactly the ones someone had already
written down. Anything else was silently absorbed into a price-only profile and came
back with unrelated names.

The catalog approach that replaced it had the same defect one level up: it encoded how
each metric is computed, and when that guess was wrong it blocked strategies that were
actually answerable. PER was the concrete case - it was marked impossible for want of a
share count, while DART reports earnings per share directly.

So the schema is handed to the model as it actually is, read from information_schema at
runtime, and the model writes the query. The system does not try to anticipate what can
be asked; it enforces what must be true of any answer: read-only, single statement,
bounded, and returning tickers this warehouse actually knows.
"""

from __future__ import annotations

import logging
import re
from typing import Any

_logger = logging.getLogger(__name__)

# Schemas are discovered rather than listed. A hand-maintained table list is the same
# mistake as hand-maintained metric formulas: whatever the data team adds next is
# invisible until someone remembers to add it here.
SCREENABLE_SCHEMAS: tuple[str, ...] = ("core", "feature", "mart", "raw")
# Raw API payload dumps are enormous and carry nothing a screen can filter on.
EXCLUDED_TABLE_PATTERNS: tuple[str, ...] = ("_response", "_temp_", "_log")

MAX_SCREEN_ROWS = 500

# Hard-won details a reader of the bare schema would get wrong. Each of these produced
# a real, silent failure in this warehouse.
SCHEMA_NOTES = """
Known pitfalls in this warehouse - getting these wrong yields silently wrong results:

1. Ticker keys differ between tables. feature.ta_*_ticker_daily stores tickers as
   '000020#S05' (6-digit code plus a security-type suffix), while
   feature.kis_adjusted_ohlcv_daily, core.symbol_master and mart.dart_financial_asof
   use the bare '000020'. Join with split_part(ticker, '#', 1), and de-duplicate,
   because several security types can collapse onto one 6-digit code.

2. mart.dart_financial_asof must be filtered on available_from (the date the filing
   became public), never on period_end. Selecting by period_end lets a screen read
   figures that had not been disclosed yet.

3. Financial figures live in accounts_jsonb as objects, not scalars. The current value
   is accounts_jsonb->'<account_id>'->>'amount' and it is TEXT that is not always
   numeric - guard every cast, e.g.
     CASE WHEN accounts_jsonb->'ifrs-full_Equity'->>'amount' ~ '^-?[0-9]+$'
          THEN (accounts_jsonb->'ifrs-full_Equity'->>'amount')::numeric END
   The prior period sits at ->'raw'->>'frmtrm_amount' but is populated for only ~4% of
   rows, so year-on-year comparisons should join an earlier filing of the same
   report_code instead.

4. feature.ta_*_ticker_daily keep indicator values in values_jsonb keyed by indicator
   name (RSI_14, MFI_14, STOCHk_14_3_3, CCI_20_0.015, WILLR_14, ROC_10, ...).

5. core.symbol_master.listing_status is broken upstream - every symbol reads as
   delisted. Never filter on it. Join symbol_master for display fields only, and treat
   "has recent rows in feature.kis_adjusted_ohlcv_daily" as the universe.

6. Sector lives on core.symbol_master.sector (WICS snapshot, 26 values such as 반도체,
   화학, 운송, 유틸리티, 은행, 자동차, 건강관리, 소프트웨어). There is no separate
   sector table. mart.common_stock_feature_frame_asof also carries sector.

7. Several tables exist but were never loaded - the row counts in the schema listing
   say which. A condition that depends on an empty table cannot be screened; report it
   under unmet_requirements rather than substituting a different column for it.
"""

REQUIRED_OUTPUT_CONTRACT = f"""
Return one SQL SELECT (a leading WITH is fine) that yields at most {MAX_SCREEN_ROWS}
rows, one per matching stock, with:
  - a column named "ticker" holding the bare 6-digit code
  - one column per metric your conditions used, so the result explains itself
Screen against the most recent trading date present in
feature.kis_adjusted_ohlcv_daily. Do not use INSERT/UPDATE/DELETE/DDL, transactions,
multiple statements, or semicolons.
"""

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|call|do|"
    r"vacuum|analyze|reindex|refresh|comment|lock|set|reset|begin|commit|rollback)\b",
    re.IGNORECASE,
)


class ScreenSQLRejected(RuntimeError):
    """The generated SQL failed a guard and was never executed."""


def build_schema_context(conn: Any) -> str:
    """Describe every screenable table from information_schema, with how full it is.

    Row counts come along because emptiness is the thing a screen most needs to know:
    several tables exist but were never loaded, and a query written against one of them
    returns nothing for reasons that have nothing to do with the strategy.
    """

    # %% because this SQL also carries a psycopg placeholder, which claims a bare %.
    excluded = " AND ".join(
        f"table_name NOT LIKE '%%{pattern}%%'" for pattern in EXCLUDED_TABLE_PATTERNS
    )
    tables = conn.execute(
        f"""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema = ANY(%s) AND {excluded}
        ORDER BY table_schema, table_name
        """,
        [list(SCREENABLE_SCHEMAS)],
    ).fetchall()

    lines: list[str] = []
    for table in tables:
        schema_name = table["table_schema"]
        table_name = table["table_name"]
        columns = conn.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            [schema_name, table_name],
        ).fetchall()
        if not columns:
            continue
        population = _describe_population(conn, schema_name, table_name)
        rendered = ", ".join(f"{col['column_name']} {col['data_type']}" for col in columns)
        lines.append(f"{schema_name}.{table_name} [{population}]\n    ({rendered})")
    return "\n".join(lines)


def _describe_population(conn: Any, schema_name: str, table_name: str) -> str:
    """How full a table is, cheaply.

    The planner's estimate is enough - the prompt only needs to distinguish "loaded"
    from "empty", and count(*) on the seven-million-row indicator tables costs more than
    the whole rest of this function. Empty is confirmed with a bounded existence check,
    because a table that was never analysed also estimates as zero.
    """

    estimate = 0
    # A savepoint keeps one unreadable table from aborting the transaction and taking
    # every later lookup down with it.
    conn.execute("SAVEPOINT table_probe")
    try:
        row = conn.execute(
            """
            SELECT COALESCE(c.reltuples, 0)::bigint AS estimate
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s AND c.relname = %s
            """,
            [schema_name, table_name],
        ).fetchone()
        estimate = int(row["estimate"]) if row else 0
        if estimate <= 0:
            present = conn.execute(
                f"SELECT EXISTS (SELECT 1 FROM {schema_name}.{table_name} LIMIT 1) AS present"
            ).fetchone()
            if present and present["present"]:
                return "loaded (size unknown)"
            conn.execute("RELEASE SAVEPOINT table_probe")
            return "EMPTY - do not use"
        conn.execute("RELEASE SAVEPOINT table_probe")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT table_probe")
        return "unknown"
    return f"~{estimate:,} rows"


def guard_screen_sql(sql: str) -> str:
    """Reject anything that is not a single, read-only SELECT before it reaches the DB.

    This is a guard, not the only defence: the statement is also run inside a read-only
    transaction with a timeout, so a bypass here still cannot write.
    """

    candidate = (sql or "").strip().rstrip(";").strip()
    if not candidate:
        raise ScreenSQLRejected("empty statement")
    if ";" in candidate:
        raise ScreenSQLRejected("multiple statements are not allowed")
    lowered = candidate.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise ScreenSQLRejected("statement must start with SELECT or WITH")
    forbidden = _FORBIDDEN.search(candidate)
    if forbidden:
        raise ScreenSQLRejected(f"forbidden keyword: {forbidden.group(0)}")
    return candidate


def run_screen_sql(conn: Any, sql: str, *, max_rows: int = MAX_SCREEN_ROWS) -> list[dict[str, Any]]:
    """Execute guarded screening SQL read-only and bounded."""

    statement = guard_screen_sql(sql)
    # Read-only for the rest of this transaction: even a guard bypass cannot write.
    conn.execute("SET TRANSACTION READ ONLY")
    rows = conn.execute(
        f"SELECT * FROM ({statement}) AS llm_screen LIMIT {int(max_rows)}"
    ).fetchall()
    return [dict(row) for row in rows]


def validate_screen_rows(
    rows: list[dict[str, Any]], *, known_tickers: set[str]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Post-validate what the query returned; drop rows that cannot be traded.

    Returns the surviving rows and human-readable notes about what was dropped, so a
    partially wrong query degrades visibly instead of silently.
    """

    notes: list[str] = []
    if not rows:
        return [], ["스크리닝 결과가 0건입니다."]
    if "ticker" not in rows[0]:
        raise ScreenSQLRejected("result has no 'ticker' column")

    accepted: list[dict[str, Any]] = []
    seen: set[str] = set()
    malformed = 0
    unknown = 0
    for row in rows:
        ticker = str(row.get("ticker") or "").strip()
        if not ticker.isdigit() or len(ticker) > 6:
            malformed += 1
            continue
        ticker = ticker.zfill(6)
        if known_tickers and ticker not in known_tickers:
            unknown += 1
            continue
        if ticker in seen:
            continue
        seen.add(ticker)
        accepted.append({**row, "ticker": ticker})

    if malformed:
        notes.append(f"티커 형식이 아닌 행 {malformed}건 제외")
    if unknown:
        notes.append(f"현재 유니버스에 없는 티커 {unknown}건 제외")
    return accepted, notes


MAX_SCREEN_ATTEMPTS = 3


def screen_with_llm(conn: Any, query: str) -> dict[str, Any] | None:
    """Research the strategy, write SQL for it, run it, and retry on a bad outcome.

    Returns None when no live provider is available, leaving the caller on its
    deterministic path. Otherwise returns the matched rows plus a trace of what was
    researched, attempted and rejected, so the report can show its work.
    """

    from ai_graph.llm.role_calls import generate_screening_sql, research_screening_terms

    research = research_screening_terms(query=query)
    schema_context = build_schema_context(conn)
    known_tickers = fetch_known_tickers(conn)

    attempts: list[dict[str, Any]] = []
    for attempt_index in range(MAX_SCREEN_ATTEMPTS):
        plan = generate_screening_sql(
            query=query,
            schema_context=schema_context,
            schema_notes=SCHEMA_NOTES,
            output_contract=REQUIRED_OUTPUT_CONTRACT,
            research=research,
            previous_attempts=attempts or None,
        )
        if plan is None:
            return None

        record: dict[str, Any] = {
            "attempt": attempt_index + 1,
            "reasoning": plan.get("reasoning"),
            "sql": plan.get("sql"),
            "unmet_requirements": plan.get("unmet_requirements") or [],
        }
        try:
            rows = run_screen_sql(conn, str(plan.get("sql") or ""))
            accepted, notes = validate_screen_rows(rows, known_tickers=known_tickers)
        except ScreenSQLRejected as exc:
            record["outcome"] = f"rejected: {exc}"
            attempts.append(record)
            continue
        except Exception as exc:
            # Database errors are the most useful feedback of all - the next attempt
            # sees the exact complaint rather than guessing what went wrong.
            record["outcome"] = f"database error: {type(exc).__name__}: {exc}"
            attempts.append(record)
            _rollback_quietly(conn)
            continue

        record["matched"] = len(accepted)
        record["validation_notes"] = notes
        if accepted:
            record["outcome"] = "ok"
            attempts.append(record)
            return {
                "rows": accepted,
                "research": research,
                "attempts": attempts,
                "metrics": plan.get("metrics") or [],
                "unmet_requirements": record["unmet_requirements"],
            }

        record["outcome"] = "matched 0 rows - conditions too strict for this date"
        attempts.append(record)

    return {
        "rows": [],
        "research": research,
        "attempts": attempts,
        "metrics": [],
        "unmet_requirements": attempts[-1].get("unmet_requirements") if attempts else [],
    }


def _rollback_quietly(conn: Any) -> None:
    """A failed statement poisons the transaction; reset so the next attempt can run."""

    try:
        conn.rollback()
    except Exception:
        _logger.debug("could not roll back after failed screening SQL", exc_info=True)


def fetch_known_tickers(conn: Any) -> set[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT ticker
        FROM feature.kis_adjusted_ohlcv_daily
        WHERE time = (SELECT max(time) FROM feature.kis_adjusted_ohlcv_daily)
        """
    ).fetchall()
    return {str(row["ticker"]).zfill(6) for row in rows}
