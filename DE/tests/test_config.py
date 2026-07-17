import ast
from datetime import date
import os
from pathlib import Path
import unittest

from quant_agent.data.config import BokConfig, DartConfig, DatabaseConfig, KisConfig, KrxConfig, PilotConfig, SeibroConfig

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_MODULE = PROJECT_ROOT / "quant_agent" / "data" / "config.py"


class ConfigTests(unittest.TestCase):
    def test_krx_config_does_not_require_dotenv(self):
        with EnvGuard({"KRX_API_KEY": "secret"}):
            config = KrxConfig.from_env()
        self.assertTrue(config.is_configured)
        self.assertEqual(config.api_key, "secret")
        self.assertGreaterEqual(len(config.daily_market_endpoints), 2)

    def test_kis_config_virtual_default(self):
        with EnvGuard({"KIS_APP_KEY": "app", "KIS_APP_SECRET": "secret", "KIS_ACCESS_TOKEN": "token"}):
            config = KisConfig.from_env()
        self.assertTrue(config.is_configured)
        self.assertIn("openapivts", config.base_url)
        self.assertEqual(config.access_token, "token")
        self.assertEqual(config.adjusted_price_flag, "0")
        self.assertEqual(config.original_price_flag, "1")

    def test_pilot_config_dates_from_env(self):
        with EnvGuard(
            {
                "SOURCE_PILOT_SYMBOL": "000660",
                "SOURCE_PILOT_START_DATE": "2026-04-01",
                "SOURCE_PILOT_END_DATE": "2026-05-01",
                "SOURCE_PILOT_KRX_TRADE_DATE": "2026-05-01",
            },
        ):
            config = PilotConfig.from_env()
        self.assertEqual(config.sample_symbol, "000660")
        self.assertEqual(config.start_date, date(2026, 4, 1))
        self.assertEqual(config.end_date, date(2026, 5, 1))
        self.assertEqual(config.krx_trade_date, date(2026, 5, 1))
        self.assertAlmostEqual(config.max_price_issue_ratio, 0.05)

    def test_database_config_does_not_load_dotenv(self):
        with EnvGuard({"QUANT_DB_PASSWORD": "pw", "QUANT_DB_EXECUTION_MODE": "docker"}):
            config = DatabaseConfig.from_env()
        self.assertEqual(config.database, "quant_agent")
        self.assertEqual(config.execution_mode, "docker")
        self.assertEqual(config.password, "pw")

    def test_external_configs_from_env(self):
        with EnvGuard(
            {
                "BOK_API_KEY": "bok",
                "DART_API_KEY": "dart",
                "SEIBRO_COLLECTION_APPROVED": "true",
                "SEIBRO_API_KEY": "seibro",
            }
        ):
            self.assertTrue(BokConfig.from_env().is_configured)
            self.assertTrue(DartConfig.from_env().is_configured)
            self.assertTrue(SeibroConfig.from_env().collection_approved)

    def test_dart_config_accepts_fss_api_key_alias(self):
        with EnvGuard({"FSS_API_KEY": "fss"}):
            config = DartConfig.from_env()
        self.assertTrue(config.is_configured)
        self.assertEqual(config.api_key, "fss")


class ConfigModuleSecurityTests(unittest.TestCase):
    def test_config_module_does_not_load_dotenv(self):
        tree = ast.parse(CONFIG_MODULE.read_text(encoding="utf-8"))
        forbidden_calls = []
        forbidden_imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "dotenv":
                forbidden_imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                forbidden_imports.extend(alias.name for alias in node.names if alias.name == "dotenv")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "load_dotenv":
                forbidden_calls.append(node.func.id)

        self.assertEqual(forbidden_imports, [])
        self.assertEqual(forbidden_calls, [])


class EnvGuard:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.original: dict[str, str | None] = {}

    def __enter__(self) -> None:
        names = set(os.environ) | set(self.values)
        self.original = {name: os.environ.get(name) for name in names}
        os.environ.clear()
        os.environ.update(self.values)

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        os.environ.clear()
        for name, value in self.original.items():
            if value is not None:
                os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
