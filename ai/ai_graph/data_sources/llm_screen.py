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

from .identity import canonical_ticker, display_name

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

8. EVERY read of a *_daily table must carry a bounded date filter. They are partitioned
   by date - 531 partitions each - and the server allows only 64 locks per transaction,
   so an unbounded scan dies with "out of shared memory / max_locks_per_transaction"
   before returning a single row. This bites hardest where it looks innocent:
     BAD   (SELECT max(time) FROM feature.kis_adjusted_ohlcv_daily)
     GOOD  (SELECT max(time) FROM feature.kis_adjusted_ohlcv_daily
            WHERE time >= CURRENT_DATE - INTERVAL '90 days')
   Anchor to the latest trading date that way, then window every other daily table off
   it - 420 days is enough for a year of indicators, 90 for short lookbacks. Multi-year
   history is only affordable for one ticker at a time, never across the universe.
"""

REQUIRED_OUTPUT_CONTRACT = f"""
Return one SQL SELECT (a leading WITH is fine) only when every material strategy
condition is expressible. It must yield at most {MAX_SCREEN_ROWS} rows, one per matching
stock, with:
  - a column named "ticker" holding the bare 6-digit code
  - one column per metric your conditions used, so the result explains itself
Screen against the most recent trading date present in
feature.kis_adjusted_ohlcv_daily. Do not use INSERT/UPDATE/DELETE/DDL, transactions,
multiple statements, or semicolons.
If any material condition cannot be expressed, return an empty sql string and empty
metrics/condition lists, and name every missing input in unmet_requirements. Do not
execute or propose a partial-rule substitute.
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

    Two set-based queries, no per-table probing. The earlier version looped over ~35
    tables issuing a column query and a row-count probe for each; one failure inside
    that loop aborted the transaction and every later statement failed with it, so a
    single unreadable table took out the whole schema listing.

    How full a table is comes from the planner's own statistics rather than count(*) -
    the prompt only needs to tell "loaded" from "never loaded", and counting rows on the
    seven-million-row indicator tables costs more than everything else here combined.
    """

    # %% because this SQL also carries a psycopg placeholder, which claims a bare %.
    excluded = " AND ".join(
        f"c.table_name NOT LIKE '%%{pattern}%%'" for pattern in EXCLUDED_TABLE_PATTERNS
    )
    columns = conn.execute(
        f"""
        SELECT c.table_schema, c.table_name, c.column_name, c.data_type
        FROM information_schema.columns c
        WHERE c.table_schema = ANY(%s) AND {excluded}
        ORDER BY c.table_schema, c.table_name, c.ordinal_position
        """,
        [list(SCREENABLE_SCHEMAS)],
    ).fetchall()

    # Partitioned parents hold no rows of their own, so their own statistics read as
    # empty however full the table is. Roll the partitions up into the parent, or every
    # daily table - the ones that matter most - is advertised as unusable.
    stats = conn.execute(
        """
        SELECT n.nspname AS table_schema,
               c.relname AS table_name,
               c.relkind,
               (c.reltuples + COALESCE(parts.child_tuples, 0))::bigint AS estimate,
               (c.relpages + COALESCE(parts.child_pages, 0))::bigint AS pages
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN LATERAL (
            SELECT sum(child.reltuples) AS child_tuples,
                   sum(child.relpages) AS child_pages
            FROM pg_inherits i
            JOIN pg_class child ON child.oid = i.inhrelid
            WHERE i.inhparent = c.oid
        ) parts ON TRUE
        WHERE n.nspname = ANY(%s)
        """,
        [list(SCREENABLE_SCHEMAS)],
    ).fetchall()
    population_by_table = {
        (row["table_schema"], row["table_name"]): _population_label(
            int(row["estimate"] or 0), int(row["pages"] or 0), str(row["relkind"])
        )
        for row in stats
    }

    grouped: dict[tuple[str, str], list[str]] = {}
    for column in columns:
        key = (column["table_schema"], column["table_name"])
        grouped.setdefault(key, []).append(
            f"{column['column_name']} {column['data_type']}"
        )

    lines: list[str] = []
    for (schema_name, table_name), rendered in grouped.items():
        population = population_by_table.get((schema_name, table_name), "unknown")
        joined = ", ".join(rendered)
        lines.append(f"{schema_name}.{table_name} [{population}]\n    ({joined})")
    return "\n".join(lines)


def _population_label(estimate: int, pages: int, relkind: str) -> str:
    """Turn planner statistics into the one distinction the prompt needs.

    A table with no rows and no pages was never written to. A zero estimate with pages
    on disk only means it was never analysed, which is not the same thing - saying so
    keeps the model from writing off data that is actually there.
    """

    if estimate > 0:
        return f"~{estimate:,} rows"
    if relkind == "v":
        # Views carry no statistics of their own, and the whole mart layer is views over
        # populated tables - reading that zero as empty writes off usable data.
        return "view (size unknown - reflects its source tables)"
    if pages == 0:
        return "EMPTY - do not use"
    return "loaded, size unknown (never analysed)"


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
    from ai_graph.progress import report_activity

    # This stage runs for minutes behind a single "전략 해석 중" label, and its provider
    # calls carry no debate role, so nothing reached the live view without these.
    report_activity("step", label="전략 용어 리서치", detail="지표 정의와 계산식을 웹에서 확인 중")
    research = research_screening_terms(query=query)
    if research:
        metric_names = [
            str(metric.get("name")) for metric in research.get("metrics") or [] if metric
        ]
        report_activity(
            "step",
            label="용어 해석 완료",
            detail=(", ".join(metric_names[:5]) or research.get("strategy_reading", ""))[:160],
        )

    report_activity("step", label="스키마 확인", detail="적재된 테이블과 컬럼을 읽는 중")
    schema_context = build_schema_context(conn)
    known_tickers = fetch_known_tickers(conn)

    attempts: list[dict[str, Any]] = []
    for attempt_index in range(MAX_SCREEN_ATTEMPTS):
        report_activity(
            "step",
            label=f"스크리닝 질의 작성 {attempt_index + 1}차",
            detail="스키마에 맞춰 조건을 SQL로 옮기는 중"
            if attempt_index == 0
            else "직전 시도 결과를 반영해 다시 작성 중",
        )
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

        unmet_requirements = list(plan.get("unmet_requirements") or [])
        record: dict[str, Any] = {
            "attempt": attempt_index + 1,
            "reasoning": plan.get("reasoning"),
            "sql": plan.get("sql"),
            "unmet_requirements": unmet_requirements,
        }
        if unmet_requirements:
            # A partial SQL result would be indistinguishable from a validation of the
            # user's rule. Preserve the exact rule and hand the missing inputs to the
            # data-availability layer instead of executing a weakened substitute.
            record["outcome"] = "blocked: required data unavailable for exact rule"
            attempts.append(record)
            report_activity(
                "step",
                label="원래 규칙 보류",
                detail=(", ".join(str(item) for item in unmet_requirements))[:160],
            )
            return {
                "rows": [],
                "research": research,
                "attempts": attempts,
                "metrics": [],
                "unmet_requirements": unmet_requirements,
                "entry_conditions": [],
                "exit_conditions": [],
                "exact_rule_blocked": True,
            }
        try:
            rows = run_screen_sql(conn, str(plan.get("sql") or ""))
            accepted, notes = validate_screen_rows(rows, known_tickers=known_tickers)
        except ScreenSQLRejected as exc:
            record["outcome"] = f"rejected: {exc}"
            report_activity("step", label=f"질의 거부 {attempt_index + 1}차", detail=str(exc))
            attempts.append(record)
            continue
        except Exception as exc:
            # Database errors are the most useful feedback of all - the next attempt
            # sees the exact complaint rather than guessing what went wrong.
            record["outcome"] = f"database error: {type(exc).__name__}: {exc}"
            hint = _repair_hint(exc)
            if hint:
                # The raw Postgres text names a symptom, not the cause. Saying which
                # part of the query to change turns a wasted retry into a fix.
                record["how_to_fix"] = hint
            report_activity(
                "step",
                label=f"질의 오류 {attempt_index + 1}차",
                detail=f"{type(exc).__name__}: {exc}"[:160],
            )
            attempts.append(record)
            _rollback_quietly(conn)
            continue

        record["matched"] = len(accepted)
        record["validation_notes"] = notes
        if accepted:
            accepted = enrich_with_symbol_master(conn, accepted)
            record["outcome"] = "ok"
            report_activity(
                "step",
                label=f"스크리닝 완료 · {len(accepted)}종목",
                detail=" · ".join(notes) if notes else ", ".join(plan.get("metrics") or [])[:160],
            )
            attempts.append(record)
            return {
                "rows": accepted,
                "research": research,
                "attempts": attempts,
                "metrics": plan.get("metrics") or [],
                "unmet_requirements": record["unmet_requirements"],
                # The structured form of the rule the SQL just ran, so the backtest can
                # compile the same conditions instead of the LLM re-deriving them.
                "entry_conditions": plan.get("entry_conditions") or [],
                "exit_conditions": plan.get("exit_conditions") or [],
            }

        record["outcome"] = "matched 0 rows - conditions too strict for this date"
        report_activity(
            "step",
            label=f"매칭 0건 {attempt_index + 1}차",
            detail="조건이 이 날짜에는 너무 좁습니다. 완화해 재작성합니다.",
        )
        attempts.append(record)

    return {
        "rows": [],
        "research": research,
        "attempts": attempts,
        "metrics": [],
        "unmet_requirements": attempts[-1].get("unmet_requirements") if attempts else [],
    }


def _repair_hint(exc: Exception) -> str | None:
    """Translate a database complaint into the edit that fixes it."""

    message = str(exc).lower()
    if "shared memory" in message or "max_locks_per_transaction" in message:
        return (
            "A daily table was read without a bounded date filter, so all 531 date "
            "partitions were locked. Add a date window to every *_daily table read - "
            "including the max(time) subquery used to find the latest trading date."
        )
    if "statement timeout" in message or "canceling statement" in message:
        return (
            "The query was too slow. Narrow the date window, screen on the latest date "
            "only, and avoid joining several multi-million-row daily tables at once."
        )
    if "does not exist" in message:
        return "A referenced table or column is not in the schema listing; use only what is listed."
    return None


def _rollback_quietly(conn: Any) -> None:
    """A failed statement poisons the transaction; reset so the next attempt can run."""

    try:
        conn.rollback()
    except Exception:
        _logger.debug("could not roll back after failed screening SQL", exc_info=True)


def enrich_with_symbol_master(conn: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill in name, market and sector for the matched tickers.

    The screen is asked for tickers and the metrics behind its conditions - identity
    fields are the warehouse's job, not something to make the query carry. Downstream
    ScreeningMatch requires a non-empty name, so leaving this to the generated SQL meant
    a query that simply did not select `name` failed the whole analysis.
    """

    if not rows:
        return rows
    tickers = sorted({canonical_ticker(row.get("ticker")) for row in rows if row.get("ticker")})
    if not tickers:
        return rows
    found = conn.execute(
        """
        SELECT symbol, name, market, market_segment, sector
        FROM core.symbol_master
        WHERE symbol = ANY(%s)
        """,
        [tickers],
    ).fetchall()
    by_ticker: dict[str, dict[str, Any]] = {}
    for master in found:
        ticker = canonical_ticker(master.get("symbol"))
        if not ticker:
            continue
        previous = by_ticker.get(ticker)
        if previous is None or (
            not display_name(previous.get("name")) and display_name(master.get("name"))
        ):
            by_ticker[ticker] = master
    enriched: list[dict[str, Any]] = []
    for row in rows:
        ticker = canonical_ticker(row.get("ticker"))
        master = by_ticker.get(ticker) or {}
        master_name = display_name(master.get("name"))
        enriched.append(
            {
                **row,
                # A ticker with no master row still trades; showing its code is better
                # than dropping it.
                "ticker": ticker,
                "name": master_name or display_name(row.get("name")) or ticker,
                "market": row.get("market")
                or master.get("market_segment")
                or master.get("market")
                or "KRX",
                "sector": row.get("sector") or master.get("sector"),
            }
        )
    return enriched


def fetch_known_tickers(conn: Any) -> set[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT ticker
        FROM feature.kis_adjusted_ohlcv_daily
        WHERE time = (SELECT max(time) FROM feature.kis_adjusted_ohlcv_daily)
        """
    ).fetchall()
    return {str(row["ticker"]).zfill(6) for row in rows}
