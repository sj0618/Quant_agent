from __future__ import annotations

from datetime import date, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


pytestmark = pytest.mark.integration


def test_optional_kis_ta_qa_docker_smoke(tmp_path: Path):
    if os.getenv("RUN_KIS_INTEGRATION_TESTS", "").lower() != "true":
        pytest.skip("Set RUN_KIS_INTEGRATION_TESTS=true to run the real Docker DB + KIS smoke test.")
    if not os.getenv("KIS_APP_KEY") or not os.getenv("KIS_APP_SECRET"):
        pytest.skip("KIS_APP_KEY/KIS_APP_SECRET are required for the real KIS integration test.")

    ticker = os.getenv("KIS_INTEGRATION_TICKER", "005930")
    target_date = _target_date()
    warmup_start = (date.fromisoformat(target_date) - timedelta(days=365)).isoformat()
    kis_output = tmp_path / "kis.json"
    ta_output = tmp_path / "ta.json"
    qa_output = tmp_path / "qa.json"

    _run(
        [
            sys.executable,
            "scripts/ingest_kis_adjusted_ohlcv.py",
            "--start-date",
            target_date,
            "--end-date",
            target_date,
            "--tickers",
            ticker,
            "--request-window-days",
            "1",
            "--workers",
            "1",
            "--request-sleep-seconds",
            "0",
            "--db-mode",
            "docker",
            "--output",
            str(kis_output),
        ]
    )
    _run(
        [
            sys.executable,
            "scripts/compute_technical_indicators_pipeline.py",
            "--db-mode",
            "docker",
            "--start-date",
            warmup_start,
            "--end-date",
            target_date,
            "--input-price-source",
            "kis-adjusted",
            "--tickers",
            ticker,
            "--workers",
            "1",
            "--ticker-batch-size",
            "1",
            "--flush-rows",
            "1000",
            "--output",
            str(ta_output),
        ]
    )
    _run(
        [
            sys.executable,
            "scripts/run_data_quality_checks.py",
            "--db-mode",
            "docker",
            "--start-date",
            target_date,
            "--end-date",
            target_date,
            "--checks",
            "all",
            "--output",
            str(qa_output),
        ]
    )

    kis_summary = json.loads(kis_output.read_text(encoding="utf-8"))
    ta_summary = json.loads(ta_output.read_text(encoding="utf-8"))
    qa_summary = json.loads(qa_output.read_text(encoding="utf-8"))
    assert not kis_summary["failed_windows"]
    assert ta_summary["failed_tickers"] == []
    assert qa_summary["status"] == "success"
    assert _query_scalar(
        f"SELECT count(*) FROM meta.api_request_log WHERE run_id='{kis_summary['run_id']}'"
    ) >= 1
    assert _query_scalar(
        f"SELECT count(*) FROM mart.symbol_feature_frame_asof WHERE base_ticker='{ticker}' AND as_of_date='{target_date}'"
    ) >= 1


def _target_date() -> str:
    configured = os.getenv("KIS_INTEGRATION_TARGET_DATE")
    if configured:
        return configured
    return _query_text("SELECT max(trade_date)::text FROM core.ohlcv_daily")


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], text=True, check=False)
    assert completed.returncode == 0


def _query_scalar(sql: str) -> int:
    return int(_query_text(sql))


def _query_text(sql: str) -> str:
    completed = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            os.getenv("QUANT_DB_CONTAINER", "quant-agent-db"),
            "psql",
            "-U",
            os.getenv("QUANT_DB_USER", "quant_agent"),
            "-d",
            os.getenv("QUANT_DB_NAME", "quant_agent"),
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            sql,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return completed.stdout.strip()
