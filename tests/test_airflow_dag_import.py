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


if __name__ == "__main__":
    unittest.main()
