import importlib.util
from datetime import date
import os
from pathlib import Path
from unittest.mock import patch
import unittest


class AirflowDagImportTests(unittest.TestCase):
    def test_dag_file_is_import_safe_without_airflow(self):
        module = _load_dag_module()
        self.assertTrue(module.DEFAULT_DAILY_SCHEDULE)

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
        self.assertTrue(module.DEFAULT_DAILY_SCHEDULE)

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
