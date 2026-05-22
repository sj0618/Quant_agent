import importlib.util
from pathlib import Path
import unittest


class AirflowDagImportTests(unittest.TestCase):
    def test_dag_file_is_import_safe_without_airflow(self):
        path = Path("airflow/dags/quant_agent_data_engineering.py")
        spec = importlib.util.spec_from_file_location("quant_agent_data_engineering_dag", path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        self.assertTrue(module.DEFAULT_DAILY_SCHEDULE)


if __name__ == "__main__":
    unittest.main()
