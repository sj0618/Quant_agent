import importlib.util
from datetime import date, timedelta
import os
from pathlib import Path
from unittest.mock import patch
import unittest


class AirflowDagImportTests(unittest.TestCase):
    def test_dag_file_is_import_safe_without_airflow(self):
        module = _load_dag_module()
        self.assertEqual(module.DEFAULT_DAILY_SCHEDULE, "0 20 * * *")
        self.assertEqual(module.DEFAULT_OHLCV_REPAIR_SCHEDULE, "0 7 * * *")

    def test_dag_file_does_not_require_airflow_package(self):
        path = Path("airflow/dags/quant_agent_data_engineering.py")
        spec = importlib.util.spec_from_file_location("quant_agent_data_engineering_dag_no_airflow", path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader

        real_import = __import__

        def import_without_airflow(name, *args, **kwargs):
            if name.startswith("airflow"):
                raise ImportError("airflow intentionally unavailable")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_without_airflow):
            spec.loader.exec_module(module)

        self.assertIsNone(module.dag)
        self.assertIsNone(module.task)
        self.assertEqual(module.DEFAULT_DAILY_SCHEDULE, "0 20 * * *")
        self.assertEqual(module.DEFAULT_OHLCV_REPAIR_SCHEDULE, "0 7 * * *")

    def test_evening_collection_and_morning_repair_are_separated(self):
        source = Path("airflow/dags/quant_agent_data_engineering.py").read_text(encoding="utf-8")

        self.assertIn("dag_id=\"quant_agent_daily_data_engineering\"", source)
        self.assertIn("schedule=DEFAULT_DAILY_SCHEDULE", source)
        self.assertIn("dag_id=\"quant_agent_ohlcv_repair\"", source)
        self.assertIn("schedule=DEFAULT_OHLCV_REPAIR_SCHEDULE", source)
        self.assertIn("include_same_day_trade_date=True", source)
        self.assertIn("include_same_day_trade_date=False", source)

    def test_krx_trade_date_query_respects_same_day_flag(self):
        module = _load_dag_module("quant_agent_data_engineering_dag_trade_date_query")

        inclusive_query = module._krx_trade_date_query(date(2026, 8, 1), include_same_day_trade_date=True)
        exclusive_query = module._krx_trade_date_query(date(2026, 8, 2), include_same_day_trade_date=False)

        self.assertIn("trade_date <= DATE '2026-08-01'", inclusive_query)
        self.assertIn("trade_date < DATE '2026-08-02'", exclusive_query)

    def test_kis_adjusted_ingest_args_use_daily_target_and_symbols(self):
        previous = os.environ.get("OHLCV_SYMBOLS")
        os.environ["OHLCV_SYMBOLS"] = "005930, 000660"
        try:
            module = _load_dag_module("quant_agent_data_engineering_dag_kis_args")
            args = module._kis_adjusted_ingest_args(
                start_date=date(2026, 5, 21),
                end_date=date(2026, 5, 21),
            )
        finally:
            if previous is None:
                os.environ.pop("OHLCV_SYMBOLS", None)
            else:
                os.environ["OHLCV_SYMBOLS"] = previous

        self.assertEqual(
            args,
            [
                "--start-date",
                "2026-05-21",
                "--end-date",
                "2026-05-21",
                "--tickers",
                "005930,000660",
            ],
        )

    def test_ta_args_use_kis_adjusted_source_after_warmup(self):
        module = _load_dag_module("quant_agent_data_engineering_dag_ta_args")

        target_date = date(2026, 5, 21)
        start_date = module._warmup_start_date(target_date)
        args = module._technical_indicator_args(start_date=start_date, end_date=target_date)

        self.assertIn("--input-price-source", args)
        self.assertEqual(args[args.index("--input-price-source") + 1], "kis-adjusted")
        self.assertEqual(args[args.index("--start-date") + 1], start_date.isoformat())
        self.assertEqual(args[args.index("--end-date") + 1], "2026-05-21")

    def test_ta_args_include_configured_worker_cap(self):
        previous = os.environ.get("QUANT_TA_MAX_WORKERS")
        os.environ["QUANT_TA_MAX_WORKERS"] = "2"
        try:
            module = _load_dag_module("quant_agent_data_engineering_dag_ta_worker_cap")
            target_date = date(2026, 5, 21)
            start_date = module._warmup_start_date(target_date)
            args = module._technical_indicator_args(start_date=start_date, end_date=target_date)
        finally:
            if previous is None:
                os.environ.pop("QUANT_TA_MAX_WORKERS", None)
            else:
                os.environ["QUANT_TA_MAX_WORKERS"] = previous

        self.assertIn("--workers", args)
        self.assertEqual(args[args.index("--workers") + 1], "2")

    def test_daily_dag_orders_kis_adjusted_before_ta(self):
        source = Path("airflow/dags/quant_agent_data_engineering.py").read_text(encoding="utf-8")

        self.assertIn("kis_adjusted = ingest_kis_adjusted_ohlcv_daily()", source)
        self.assertIn("kis_adjusted >> computed", source)
        self.assertIn("symbol_metadata = refresh_symbol_metadata_daily()", source)
        self.assertIn("ingested >> [symbol_metadata, kis_adjusted", source)
        self.assertIn("computed >> qa", source)
        self.assertNotIn("ingested >> [computed", source)

    def test_data_quality_args_cover_all_checks(self):
        module = _load_dag_module("quant_agent_data_engineering_dag_qa_args")

        args = module._data_quality_args(start_date=date(2026, 5, 1), end_date=date(2026, 5, 21))

        self.assertEqual(args[args.index("--start-date") + 1], "2026-05-01")
        self.assertEqual(args[args.index("--end-date") + 1], "2026-05-21")
        self.assertEqual(args[args.index("--checks") + 1], "all")

    def test_symbol_metadata_args_use_target_date(self):
        module = _load_dag_module("quant_agent_data_engineering_dag_symbol_metadata_args")

        args = module._symbol_metadata_args(as_of_date=date(2026, 5, 21))

        self.assertEqual(args, ["--as-of-date", "2026-05-21"])

    def test_run_reference_date_is_independent_of_the_ingested_calendar(self):
        module = _load_dag_module("quant_agent_data_engineering_dag_run_reference")

        self.assertEqual(module._run_reference_date("2026-08-26"), date(2026, 8, 26))
        self.assertEqual(module._run_reference_date(None, date(2026, 8, 26)), date(2026, 8, 26))

    def test_daily_ingest_window_ends_at_run_date_even_when_calendar_is_stale(self):
        # The regression guard: the daily OHLCV window must advance to the run date
        # instead of pinning to MAX(core.trading_calendar). A stale calendar (stuck at
        # the last backfilled day) must not cap the ingest end.
        module = _load_dag_module("quant_agent_data_engineering_dag_daily_window")
        run_date = date(2026, 8, 26)

        with patch.object(module, "_latest_ingested_krx_trade_date", return_value=date(2026, 5, 20)):
            start_date, end_date = module._daily_ohlcv_ingest_window(run_date)

        self.assertEqual(end_date, run_date)
        self.assertEqual(start_date, date(2026, 5, 21))

    def test_daily_ingest_window_handles_cold_warehouse_and_never_ingests_the_future(self):
        module = _load_dag_module("quant_agent_data_engineering_dag_daily_window_edges")
        run_date = date(2026, 8, 26)

        with patch.object(module, "_latest_ingested_krx_trade_date", return_value=None):
            self.assertEqual(module._daily_ohlcv_ingest_window(run_date), (run_date, run_date))

        with patch.object(module, "_latest_ingested_krx_trade_date", return_value=run_date):
            self.assertEqual(module._daily_ohlcv_ingest_window(run_date), (run_date, run_date))

    def test_repair_ingest_window_refetches_a_trailing_span_to_run_date(self):
        module = _load_dag_module("quant_agent_data_engineering_dag_repair_window")
        run_date = date(2026, 8, 26)

        start_date, end_date = module._repair_ohlcv_ingest_window(run_date)

        self.assertEqual(end_date, run_date)
        self.assertEqual(start_date, run_date - timedelta(days=module.DEFAULT_OHLCV_REPAIR_LOOKBACK_DAYS))

    def test_ai_prompt_retention_dag_is_independent_and_daily(self):
        module = _load_dag_module("quant_agent_data_engineering_dag_prompt_retention")
        source = Path("airflow/dags/quant_agent_data_engineering.py").read_text(encoding="utf-8")

        self.assertEqual(module.PROMPT_RETENTION_DAG_ID, "quant_agent_ai_prompt_retention")
        self.assertEqual(module.DEFAULT_PROMPT_RETENTION_SCHEDULE, "0 5 * * *")
        self.assertEqual(module.PROMPT_RETENTION_RETRIES, 3)
        self.assertEqual(module.PROMPT_RETENTION_RETRY_DELAY.total_seconds(), 300)
        self.assertEqual(module.PROMPT_RETENTION_SCRIPT.name, "purge_ai_prompt_logs.py")
        self.assertIn("def ai_prompt_retention():", source)
        self.assertIn("catchup=False", source)
        self.assertIn("max_active_runs=1", source)
        self.assertIn("_run_python_script(PROMPT_RETENTION_SCRIPT, [])", source)
        self.assertNotIn("purge_ai_prompt_logs >>", source)


def _load_dag_module(module_name: str = "quant_agent_data_engineering_dag"):
    path = Path("airflow/dags/quant_agent_data_engineering.py")
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
