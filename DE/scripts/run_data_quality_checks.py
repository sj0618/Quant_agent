"""Run Quant-Agent data quality checks as a first-class pipeline stage.

The script records its own ``meta.ingestion_run`` and writes findings to
``meta.data_quality_issue``. It does not load ``.env`` files; database settings
must be present in the process environment.
"""

from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant_agent.data.config import (  # noqa: E402
    DEFAULT_BOK_STALENESS_DAYS,
    DEFAULT_MIN_SYMBOL_COVERAGE,
    DatabaseConfig,
)
from quant_agent.data.quality import OhlcvQualityConfig  # noqa: E402
from quant_agent.data.repository import DataRepository  # noqa: E402


QA_SOURCE_ID = "QA"
QA_RULE_VERSION = "quality-framework-v1"


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    if end_date < start_date:
        raise ValueError("--end-date must be greater than or equal to --start-date.")

    db_config = DatabaseConfig.from_env()
    if args.db_mode:
        db_config = DatabaseConfig(**{**db_config.__dict__, "execution_mode": args.db_mode})
    repository = DataRepository(db_config=db_config)
    quality_config = OhlcvQualityConfig(
        stale_price_days=args.stale_price_days,
        volume_anomaly_multiplier=Decimal(str(args.volume_anomaly_multiplier)),
        min_volume_sample_count=args.min_volume_sample_count,
        price_mismatch_tolerance_ratio=Decimal(str(args.price_mismatch_tolerance_ratio)),
    )

    checks = tuple(args.checks)
    run_id = repository.start_ingestion_run(
        dag_id=args.dag_id,
        task_id=args.task_id,
        source_id=QA_SOURCE_ID,
        params={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "source_id": args.source_id,
            "checks": checks,
            "rule_version": QA_RULE_VERSION,
            "stale_price_days": quality_config.stale_price_days,
            "volume_anomaly_multiplier": str(quality_config.volume_anomaly_multiplier),
            "min_volume_sample_count": quality_config.min_volume_sample_count,
            "price_mismatch_tolerance_ratio": str(quality_config.price_mismatch_tolerance_ratio),
            "bok_staleness_days": args.bok_staleness_days,
        },
    )

    try:
        if "ohlcv" in checks or "all" in checks:
            repository.run_ohlcv_quality_framework(
                run_id=run_id,
                source_id=args.source_id,
                start_date=start_date,
                end_date=end_date,
                min_coverage=args.min_symbol_coverage,
                config=quality_config,
            )
        if "kis-krx" in checks or "all" in checks:
            repository.run_kis_krx_consistency_checks(
                run_id=run_id,
                start_date=start_date,
                end_date=end_date,
                config=quality_config,
            )
        if "backtest-readiness" in checks or "all" in checks:
            repository.run_backtest_readiness_checks(
                run_id=run_id,
                start_date=start_date,
                end_date=end_date,
                bok_staleness_days=args.bok_staleness_days,
            )
        error_count = repository.count_data_quality_errors(run_id=run_id)
        if error_count:
            raise RuntimeError(f"Data quality gate found {error_count} error-level issue(s).")
        repository.finish_ingestion_run(run_id, status="success")
    except Exception as exc:
        repository.finish_ingestion_run(run_id, status="failed", error_message=str(exc))
        raise

    summary = {
        "run_id": str(run_id),
        "status": "success",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "checks": checks,
        "error_count": 0,
        "rule_version": QA_RULE_VERSION,
    }
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Quant-Agent OHLCV data quality checks.")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--source-id", default="KRX", help="core.ohlcv_daily source_id for OHLCV checks.")
    parser.add_argument(
        "--checks",
        nargs="+",
        choices=["all", "ohlcv", "kis-krx", "backtest-readiness"],
        default=["all"],
        help="Quality check groups to execute.",
    )
    parser.add_argument("--min-symbol-coverage", type=float, default=DEFAULT_MIN_SYMBOL_COVERAGE)
    parser.add_argument("--stale-price-days", type=int, default=OhlcvQualityConfig().stale_price_days)
    parser.add_argument(
        "--volume-anomaly-multiplier",
        type=float,
        default=float(OhlcvQualityConfig().volume_anomaly_multiplier),
    )
    parser.add_argument("--min-volume-sample-count", type=int, default=OhlcvQualityConfig().min_volume_sample_count)
    parser.add_argument(
        "--price-mismatch-tolerance-ratio",
        type=float,
        default=float(OhlcvQualityConfig().price_mismatch_tolerance_ratio),
    )
    parser.add_argument("--bok-staleness-days", type=int, default=DEFAULT_BOK_STALENESS_DAYS)
    parser.add_argument("--db-mode", choices=["docker", "psycopg"], default=None)
    parser.add_argument("--dag-id", default="manual_data_quality_checks")
    parser.add_argument("--task-id", default="run_data_quality_checks")
    parser.add_argument("--output", default=None)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
