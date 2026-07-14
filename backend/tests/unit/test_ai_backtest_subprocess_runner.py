from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.schemas.ai_backtest import AICodeBacktestFlowRequest, CodeExecutionResult
from app.services import ai_backtest_subprocess_runner as runner


def _release_fd(payload: bytes) -> int:
    read_fd, write_fd = os.pipe()
    if payload:
        os.write(write_fd, payload)
    os.close(write_fd)
    return read_fd
@pytest.mark.parametrize(
    "payload",
    [b"", b"\x00", runner._RELEASE_BYTE + b"\x00"],
    ids=["eof", "invalid-byte", "extra-byte"],
)

def test_runner_rejects_unreleased_child_without_reading_input(monkeypatch, tmp_path, payload):
    read_paths: list[Path] = []

    def unexpected_read(path: Path, *, encoding: str) -> str:
        read_paths.append(path)
        raise AssertionError("release rejection must precede all file reads")

    monkeypatch.setattr(Path, "read_text", unexpected_read)
    exit_code = runner.main(
        [
            str(tmp_path / "request.json"),
            str(tmp_path / "generated.py"),
            str(tmp_path / "result.json"),
            str(uuid4()),
            str(_release_fd(payload)),
        ]
    )

    assert exit_code == runner._RELEASE_FAILURE_EXIT_CODE
    assert read_paths == []
    assert not (tmp_path / "result.json").exists()


def test_runner_reads_and_executes_only_after_valid_release(monkeypatch, tmp_path):
    request = AICodeBacktestFlowRequest(
        natural_language_prompt="release barrier test",
        target_runtime="python-sandbox",
        code_purpose="backtest",
    )
    request_path = tmp_path / "request.json"
    code_path = tmp_path / "generated.py"
    result_path = tmp_path / "result.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    code_path.write_text("def build_signals(prices):\n    return []\n", encoding="utf-8")
    executed: list[tuple[AICodeBacktestFlowRequest, str]] = []

    def execute(captured_request, generated, *, trace_id):
        executed.append((captured_request, generated.generated_code))
        now = datetime.now(UTC)
        return CodeExecutionResult(
            runtime_env=generated.target_runtime,
            status="succeeded",
            timeout_seconds=captured_request.timeout_seconds,
            memory_limit_mb=captured_request.memory_limit_mb,
            started_at=now,
            ended_at=now,
        )

    monkeypatch.setattr(runner, "_execute_generated_backtest", execute)
    exit_code = runner.main(
        [str(request_path), str(code_path), str(result_path), str(uuid4()), str(_release_fd(runner._RELEASE_BYTE))]
    )

    assert exit_code == 0
    assert executed == [(request, "def build_signals(prices):\n    return []\n")]
    assert CodeExecutionResult.model_validate_json(result_path.read_text(encoding="utf-8")).status == "succeeded"
