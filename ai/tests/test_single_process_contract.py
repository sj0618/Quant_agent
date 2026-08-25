"""Running a second worker has to fail loudly, not leak events and rate limits."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ai_graph.api import create_app
from ai_graph.jobs import InMemoryAnalysisJobStore
from ai_graph.single_process import (
    WEB_CONCURRENCY_ENV,
    MultiProcessStartupError,
    enforce_single_process,
)


@pytest.mark.parametrize(
    ("argv", "environ"),
    (
        (["uvicorn", "combined_main:app", "--workers", "4"], {}),
        (["uvicorn", "combined_main:app", "--workers=3"], {}),
        (["uvicorn", "combined_main:app", "-w", "2"], {}),
        (["gunicorn", "combined_main:app", "--workers", "2"], {}),
        (["uvicorn", "combined_main:app"], {WEB_CONCURRENCY_ENV: "8"}),
    ),
)
def test_more_than_one_worker_is_refused(argv: list[str], environ: dict[str, str]) -> None:
    with pytest.raises(MultiProcessStartupError):
        enforce_single_process(argv=argv, environ=environ)


@pytest.mark.parametrize(
    ("argv", "environ"),
    (
        (["uvicorn", "combined_main:app", "--workers", "1"], {}),
        (["uvicorn", "combined_main:app"], {}),
        (["uvicorn", "combined_main:app"], {WEB_CONCURRENCY_ENV: "1"}),
        # An unparseable setting changes no behaviour; taking the service down over a
        # typo would be worse than ignoring it.
        (["uvicorn", "combined_main:app", "--workers", "많이"], {}),
        (["uvicorn", "combined_main:app"], {WEB_CONCURRENCY_ENV: "  "}),
        # A worker flag belonging to some other tool is not a deployment topology.
        (["pytest", "-w", "4"], {}),
    ),
)
def test_a_single_worker_or_no_request_starts(argv: list[str], environ: dict[str, str]) -> None:
    enforce_single_process(argv=argv, environ=environ)


def test_the_message_names_the_setting_and_the_way_out() -> None:
    with pytest.raises(MultiProcessStartupError) as caught:
        enforce_single_process(argv=["uvicorn", "app", "--workers", "4"], environ={})

    message = str(caught.value)
    assert "--workers 4" in message
    assert "1" in message


def test_the_app_refuses_to_start_under_multiple_workers(monkeypatch) -> None:
    """The contract is enforced where it matters: startup, before anything is served."""

    monkeypatch.setattr("sys.argv", ["uvicorn", "combined_main:app", "--workers", "4"])

    with pytest.raises(MultiProcessStartupError):
        with TestClient(create_app(InMemoryAnalysisJobStore())):
            pass


def test_the_app_starts_normally_under_one_worker(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["uvicorn", "combined_main:app", "--workers", "1"])

    with TestClient(create_app(InMemoryAnalysisJobStore())) as client:
        assert client.get("/health").status_code == 200
