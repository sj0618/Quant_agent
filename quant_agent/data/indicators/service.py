"""Technical indicator storage service."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from quant_agent.data.config import TaConfig
from quant_agent.data.indicators.catalog import INDICATOR_CATALOG, validate_catalog_counts
from quant_agent.data.indicators.compute import compute_symbol_indicator_rows
from quant_agent.data.repository import DataRepository


class TechnicalIndicatorService:
    def __init__(self, repository: DataRepository | None = None, config: TaConfig | None = None) -> None:
        self.repository = repository or DataRepository()
        self.config = config or TaConfig.from_env()

    def register_catalog(self) -> None:
        validate_catalog_counts()
        definitions = [
            {
                **definition.to_repository_dict(),
                "transform_version": self.config.transform_version,
            }
            for definition in INDICATOR_CATALOG
        ]
        self.repository.upsert_ta_definitions(definitions)

    def compute_and_store(self, *, start_date: date, end_date: date, symbols: list[str] | None = None) -> dict[str, int]:
        self.register_catalog()
        run_id = self.repository.start_ingestion_run(
            dag_id="manual_ta_indicator_compute",
            task_id="compute_ta_indicators",
            source_id="TA",
            params={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "symbols": symbols or [],
                "transform_version": self.config.transform_version,
            },
        )
        counts: dict[str, int] = defaultdict(int)
        try:
            rows = self.repository.fetch_ohlcv_rows(start_date=start_date, end_date=end_date, symbols=symbols)
            by_symbol: dict[str, list[dict]] = defaultdict(list)
            for row in rows:
                by_symbol[str(row["symbol"])].append(row)

            for symbol_rows in by_symbol.values():
                computed_by_category = compute_symbol_indicator_rows(symbol_rows)
                for category, category_rows in computed_by_category.items():
                    self.repository.upsert_ta_values(category=category, rows=category_rows, run_id=run_id)
                    counts[category] += len(category_rows)

            self.repository.finish_ingestion_run(run_id, status="success")
        except Exception as exc:
            self.repository.finish_ingestion_run(run_id, status="failed", error_message=str(exc))
            raise
        return dict(counts)
